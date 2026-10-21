"""Anonymous, bounded requests to explicitly linked official product endpoints."""

from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import urlencode

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .store_links import normalize_link


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
    numeric_id = reference.rsplit("-", 1)[-1]
    matches = [item for item in data["impressions"] if isinstance(item, dict)
        and (str(item.get("item_internal_id", "")) == reference and str(item.get("item_id", "")) in ("", numeric_id)
             or not item.get("item_internal_id") and str(item.get("item_id", "")) == numeric_id)]
    if len(matches) != 1:
        raise PriceError("Carrefour no permite confirmar una única referencia coincidente.", response_class="invalid_product")
    product = matches[0]
    if product.get("currency") != "EUR":
        raise PriceError("Carrefour no ha devuelto un precio en EUR.", response_class="invalid_price")
    codes = product.get("item_ean", [])
    if isinstance(codes, str):
        codes = [codes]
    ean = next((code for code in codes if isinstance(code, str) and re.fullmatch(r"[0-9]{8,14}", code)), "") if isinstance(codes, list) else ""
    return {"store_name":str(product.get("item_name", "")).replace("-", " ")[:300],
        "price":amount(product.get("price")), "currency":"EUR", "ean":ean, "available":None}


class PriceSources:
    def __init__(self, hass):
        self.hass = hass

    async def fetch(self, store, link, configuration, before_request):
        link = normalize_link(store, link)
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
                "User-Agent":"Improved-Shopping-List", "Referer":link["url"],
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
                        **({"endpoint":"/cloud-api/pdp-food-analytics/v1/impressions", "sale_point":sale_point} if store == "carrefour" else {}))
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
