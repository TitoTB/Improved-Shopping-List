"""Anonymous, bounded requests to explicitly linked official product endpoints."""

from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import urlencode

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .store_links import normalize_link
from .regional_stores import POSTAL_PATTERN, valid_area
from .eroski import EroskiClient, EroskiError
from .dia import DiaClient, DiaError


class PriceError(ValueError):
    def __init__(self, message, **diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def amount(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or not 0 <= value <= 1000000:
            raise InvalidOperation
        return format(value.quantize(Decimal("0.01")), ".2f")
    except (InvalidOperation, ValueError, TypeError):
        raise PriceError("La tienda no ha devuelto un precio válido.", response_class="invalid_price") from None


def carrefour_offer(data, link):
    """Validate the public product analytics response against the selected reference."""
    if not isinstance(data, dict) or not isinstance(data.get("impressions"), list):
        raise PriceError("Carrefour ha devuelto una respuesta no válida.", response_class="invalid_response")
    if not data["impressions"]:
        return None
    reference = link["id"].removeprefix("R-")
    # Legacy prod references and their numeric analytics IDs are different IDs.
    # Only numeric references carry a numeric suffix that can be cross-checked.
    suffix = reference.rsplit("-", 1)[-1]
    numeric_id = suffix if re.fullmatch(r"[0-9]+", suffix) else None
    matches = [item for item in data["impressions"] if isinstance(item, dict)
        and (str(item.get("item_internal_id", "")) == reference
             and (numeric_id is None or str(item.get("item_id", "")) in ("", numeric_id))
             or numeric_id is not None and not item.get("item_internal_id")
             and str(item.get("item_id", "")) == numeric_id)]
    if len(matches) != 1:
        raise PriceError("Carrefour no permite confirmar una única referencia coincidente.", response_class="invalid_product",
            match_count=len(matches), impression_count=len(data["impressions"]),
            returned_references=[{"internal_id":str(item.get("item_internal_id", ""))[:80],
                "item_id":str(item.get("item_id", ""))[:80]}
                for item in data["impressions"][:5] if isinstance(item, dict)])
    product = matches[0]
    if product.get("currency") != "EUR":
        raise PriceError("Carrefour no ha devuelto un precio en EUR.", response_class="invalid_price")
    codes = product.get("item_ean", [])
    if isinstance(codes, str):
        codes = [codes]
    ean = next((code for code in codes if isinstance(code, str) and re.fullmatch(r"[0-9]{8,14}", code)), "") if isinstance(codes, list) else ""
    return {"store_name":str(product.get("item_name", "")).replace("-", " ")[:300],
        "price":amount(product.get("price")), "currency":"EUR", "ean":ean, "available":None}


def consum_offer(data, link):
    if not isinstance(data, dict) or str(data.get("code", "")) != link["id"]:
        raise PriceError("Consum no ha confirmado la referencia solicitada.", response_class="invalid_product")
    product, prices = data.get("productData"), data.get("priceData")
    if not isinstance(product, dict) or not isinstance(prices, dict) or not isinstance(prices.get("prices"), list):
        raise PriceError("Consum no ha devuelto un precio válido.", response_class="invalid_response")
    candidates = [p.get("value") for p in prices["prices"] if isinstance(p, dict) and p.get("id") == "PRICE"]
    if len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise PriceError("Consum no ha devuelto un único precio de venta.", response_class="invalid_price")
    value = candidates[0]
    # The merchant calls these centAmount, but its API returns decimal euros.
    price = amount(value.get("centAmount"))
    if Decimal(price) <= 0 or product.get("temporaryOutOfStock") is True:
        return None
    return {"store_name":str(product.get("description") or product.get("name") or "")[:300],
        "price":price, "currency":"EUR", "ean":str(data.get("ean") or "")[:14], "available":True,
        "reference_price":amount(value["centUnitAmount"]) if value.get("centUnitAmount") is not None else None,
        "reference_unit":str(prices.get("unitPriceUnitType") or "")[:40]}


def sirena_product(data, link):
    if not isinstance(data, list):
        raise PriceError("La Sirena ha devuelto una respuesta no válida.", response_class="invalid_response")
    if not data:
        return None
    matches = [p for p in data if isinstance(p, dict) and str(p.get("productId", "")) == link["id"]]
    if len(matches) != 1 or not isinstance(matches[0].get("items"), list) or len(matches[0]["items"]) != 1:
        raise PriceError("La Sirena no permite confirmar una única variante del producto.", response_class="invalid_product")
    product, sku = matches[0], matches[0]["items"][0]
    if not isinstance(sku, dict) or not re.fullmatch(r"[0-9]{1,12}", str(sku.get("itemId", ""))):
        raise PriceError("La Sirena no ha confirmado una referencia válida.", response_class="invalid_product")
    return product, sku


def sirena_offer(data, product, sku, configuration):
    if (not isinstance(data, dict) or data.get("postalCode") != configuration["postal_code"]
        or data.get("country") != "ESP" or not isinstance(data.get("items"), list)):
        raise PriceError("La Sirena no ha confirmado el código postal de la consulta.", response_class="invalid_response")
    items = [i for i in data["items"] if isinstance(i, dict) and str(i.get("id", "")) == str(sku["itemId"])
        and i.get("seller") == configuration["area_id"] and i.get("quantity") == 1]
    if len(items) != 1:
        raise PriceError("La Sirena no ha confirmado el producto y centro seleccionados.", response_class="invalid_product")
    item = items[0]
    if item.get("availability") != "available":
        return None
    cents = item.get("sellingPrice")
    if type(cents) is not int or cents <= 0:
        raise PriceError("La Sirena no ha devuelto un precio válido.", response_class="invalid_price")
    # Checkout simulation returns integer cents, unlike the catalog endpoint.
    return {"store_name":str(product.get("productName") or "")[:300], "price":amount(Decimal(cents)/100),
        "currency":"EUR", "ean":str(sku.get("ean") or "")[:14], "available":True}


class PriceSources:
    def __init__(self, hass):
        self.hass = hass
        self.eroski = EroskiClient(hass)
        self.dia = DiaClient(hass)

    def close(self):
        self.eroski.close()
        self.dia.close()

    def expected_requests(self, store, configuration):
        if store == "dia":
            return 1 if self.dia.opener is not None and self.dia.postal == configuration.get("postal_code") else 2
        if store == "eroski":
            key = (configuration.get("postal_code"), configuration.get("area_id"), configuration.get("zone"))
            return 1 if self.eroski.context == key else 4
        return 2 if store == "lasirena" else 1

    async def fetch(self, store, link, configuration, before_request):
        if configuration.get("location_error"):
            raise PriceError(configuration["location_error"], **{"response_class":"location_unavailable",**configuration.get("location_diagnostics",{})})
        link = normalize_link(store, link)
        if store == "dia":
            try:
                return await self.dia.fetch(link,configuration,before_request)
            except DiaError as err:
                raise PriceError(str(err), **err.diagnostics) from err
        if store == "eroski":
            if (not re.fullmatch(POSTAL_PATTERN, configuration.get("postal_code", ""))
                or not valid_area(store, configuration.get("area_id"))
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", configuration.get("zone", ""))):
                raise PriceError("Configura el código postal y centro de Eroski.", response_class="missing_region")
            try:
                return await self.eroski.fetch(link,configuration,before_request)
            except EroskiError as err:
                raise PriceError(str(err), **err.diagnostics) from err
        if store in ("consum", "lasirena"):
            return await self._fetch_regional(store, link, configuration, before_request)
        if store == "mercadona":
            warehouse = configuration.get("warehouse", "")
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", warehouse):
                raise PriceError("Configura el código postal de Mercadona.", response_class="missing_region")
            url = f"https://tienda.mercadona.es/api/products/{link['id']}/?" + urlencode({"lang":"es", "wh":warehouse})
        elif store == "alcampo":
            parameters = {"retailerProductId":link["id"]}
            if configuration.get("region_id"):
                parameters["regionId"] = configuration["region_id"]
            url = "https://www.compraonline.alcampo.es/api/webproductpagews/v5/products/bop?" + urlencode(parameters)
        elif store == "carrefour":
            sale_point = configuration.get("sale_point", "005290")
            if not re.fullmatch(r"[0-9]{6}", sale_point):
                raise PriceError("Configura un centro de Carrefour de seis dígitos.", response_class="missing_region")
            url = "https://www.carrefour.es/cloud-api/pdp-food-analytics/v1/impressions?" + urlencode({"product_id":link["id"]})
        else:
            raise PriceError("Tienda no compatible.", response_class="unsupported_store")
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            await before_request()
            async with session.get(url, headers={"Accept":"application/json",
                # Alcampo rejects the bare application name, even for its public API.
                "User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)" if store == "alcampo" else "Improved-Shopping-List",
                "Referer":link["url"],
                **({"ecom-request-source":"web"} if store == "alcampo" else {}),
                **({"sale_point":sale_point} if store == "carrefour" else {})},
                timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
                status = response.status
                if status == 404:
                    return None
                if status != 200:
                    wait = response.headers.get("Retry-After", "")
                    raise PriceError(f"{store.capitalize()}: consulta rechazada (HTTP {status}). Se conserva el último precio.",
                        http_status=status, response_class="access_denied" if status == 403 else "rate_limited" if status == 429 else "http_error",
                        retry_seconds=min(86400, int(wait)) if wait.isdigit() else 0,
                        server=str(response.headers.get("Server", ""))[:80], reference_id=link["id"],
                        **({"endpoint":"/cloud-api/pdp-food-analytics/v1/impressions", "sale_point":sale_point} if store == "carrefour" else {}),
                        **({"endpoint":"/api/webproductpagews/v5/products/bop", "region_id":configuration.get("region_id", "")} if store == "alcampo" else {}))
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > 4*1024*1024:
                        raise PriceError("La respuesta de la tienda es demasiado grande.", response_class="response_too_large")
            if store == "carrefour":
                result = carrefour_offer(json.loads(raw), link)
                if result is None:
                    return None
                result["sale_point"] = sale_point
            else:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise PriceError("La respuesta de la tienda no es válida.", response_class="invalid_response")
                product = data.get("product") if store == "alcampo" else data
                field = "retailerProductId" if store == "alcampo" else "id"
                if not isinstance(product, dict) or str(product.get(field, "")) != link["id"]:
                    raise PriceError("La respuesta no corresponde a la referencia solicitada.", response_class="invalid_product")
                if store == "mercadona":
                    prices = product.get("price_instructions")
                    if not isinstance(prices, dict):
                        raise PriceError("Mercadona no ha devuelto un precio válido.", response_class="invalid_price")
                    reference = prices.get("reference_price", prices.get("bulk_price"))
                    result = {"store_name":str(product.get("display_name", ""))[:300],
                        "price":amount(prices.get("unit_price")), "currency":"EUR", "ean":str(product.get("ean") or ""),
                        "reference_price":amount(reference) if reference is not None else None,
                        "reference_unit":str(prices.get("reference_format", ""))[:40],
                        "available":product.get("published") if type(product.get("published")) is bool else None,
                        "approximate":prices.get("approx_size") is True}
                else:
                    price = product.get("price", {})
                    if not isinstance(price, dict) or price.get("currency") != "EUR":
                        raise PriceError("Alcampo no ha devuelto un precio en EUR.", response_class="invalid_price")
                    unit = product.get("unitPrice") or {}
                    if not isinstance(unit, dict):
                        unit = {}
                    result = {"store_name":str(product.get("name", ""))[:300], "price":amount(price.get("amount")),
                        "currency":"EUR", "available":product.get("available") if type(product.get("available")) is bool else None,
                        "reference_price":amount(unit["price"]["amount"]) if isinstance(unit.get("price"), dict) and unit["price"].get("amount") is not None else None,
                        "reference_unit":str(unit.get("unitName", ""))[:40], "ean":""}
                    # This is metadata, not executable HTML and not a scanner reassignment.
                    details = data.get("bopData") or {}
                    for field in details.get("fields", []) if isinstance(details, dict) and isinstance(details.get("fields", []), list) else []:
                        if isinstance(field, dict) and field.get("title") == "features":
                            match = re.search(r"<td>\s*EAN\s*</td>\s*<td>\s*([0-9]{8,14})\s*</td>", str(field.get("content", "")), re.I)
                            if match:
                                result["ean"] = match[1]
            return {**result, "store":store, "reference_id":link["id"], "url":link["url"]}
        finally:
            session.detach()

    async def _fetch_regional(self, store, link, configuration, before_request):
        postal, area = configuration.get("postal_code", ""), configuration.get("area_id", "")
        if not re.fullmatch(POSTAL_PATTERN, postal) or not valid_area(store, area):
            raise PriceError("Configura el código postal y centro de la tienda.", response_class="missing_region")
        if store == "consum" and configuration.get("zone") != area[:-1]:
            raise PriceError("La zona de Consum no es válida.", response_class="missing_region")
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            if store == "consum":
                data = await self._regional_json(session, store,
                    f"https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{link['id']}?showRecommendations=false",
                    link, before_request, {"x-tol-app":"shop-front", "x-tol-channel":"1", "x-tol-locale":"es",
                        "x-tol-currency":"EUR", "x-tol-zone":configuration["zone"], "x-tol-shipping-zone":area})
                result = consum_offer(data, link) if data is not None else None
                public_url = data.get("productData", {}).get("url") if result else None
            else:
                data = await self._regional_json(session, store,
                    "https://www.lasirena.es/api/catalog_system/pub/products/search?" + urlencode({"fq":f"productId:{link['id']}"}),
                    link, before_request)
                selected = sirena_product(data, link) if data is not None else None
                if selected is None:
                    return None
                product, sku = selected
                public_url = f"https://www.lasirena.es/es/{product['linkText']}/p" if product.get("linkText") else None
                data = await self._regional_json(session, store,
                    f"https://www.lasirena.es/_v/public/middleware/client/vtex/simulationCart/{sku['itemId']}/{area}/{postal}",
                    link, before_request)
                result = sirena_offer(data, product, sku, configuration) if data is not None else None
            canonical = link["url"]
            if result and public_url:
                try:
                    candidate = normalize_link(store, public_url)
                    if candidate["id"] == link["id"]:
                        canonical = candidate["url"]
                except ValueError:
                    pass
            return {**result, "store":store, "reference_id":link["id"], "url":canonical} if result else None
        finally:
            session.detach()

    async def _regional_json(self, session, store, url, link, before_request, headers=None):
        # Every request, including La Sirena's SKU lookup, uses the durable 5-minute gate.
        await before_request()
        async with session.get(url, headers={"Accept":"application/json", "User-Agent":"Improved-Shopping-List", **(headers or {})},
            timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                wait = response.headers.get("Retry-After", "")
                raise PriceError(f"{'La Sirena' if store == 'lasirena' else 'Consum'}: consulta rechazada (HTTP {response.status}). Se conserva el último precio.",
                    http_status=response.status, response_class="access_denied" if response.status == 403 else "rate_limited" if response.status == 429 else "http_error",
                    retry_seconds=min(86400, int(wait)) if wait.isdigit() else 0,
                    server=str(response.headers.get("Server", ""))[:80], reference_id=link["id"])
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > 4*1024*1024:
                    raise PriceError("La respuesta de la tienda es demasiado grande.", response_class="response_too_large")
        try:
            return json.loads(raw)
        except ValueError:
            raise PriceError("La tienda no ha devuelto JSON válido.", response_class="invalid_response") from None
