"""Anonymous, bounded requests to explicitly linked official product pages."""

from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlencode, urljoin

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


class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.documents, self._script, self._parts = [], False, []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._script, self._parts = True, []

    def handle_data(self, data):
        if self._script:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self._script = False
            try:
                self.documents.append(json.loads("".join(self._parts)))
            except (ValueError, RecursionError):
                pass


def structured_offer(body, link):
    parser = ProductHTML()
    parser.feed(body)
    found = []
    def visit(value, depth=0):
        if depth > 15:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth+1)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if types == "Product" or isinstance(types, list) and "Product" in types:
                found.append(value)
            for key in ("@graph", "mainEntity", "itemListElement", "item"):
                visit(value.get(key), depth+1)
    for document in parser.documents:
        visit(document)
    identifiers = {link["id"], link["id"].removeprefix("R-"), link["id"].rsplit("-", 1)[-1]}
    matches = [item for item in found if str(item.get("sku", "")) in identifiers
               or str(item.get("productID", "")) in identifiers
               or str(item.get("url", "")).split("?", 1)[0].rstrip("/") == link["url"].rstrip("/")]
    if not matches and len(found) == 1:
        item = found[0]
        # A contradictory identifier must not be accepted as the selected item.
        if not item.get("sku") and not item.get("productID") and not item.get("url"):
            matches = found
    if len(matches) != 1:
        raise PriceError("La ficha no permite confirmar un único producto y precio.", response_class="unconfirmed_product")
    product = matches[0]
    offers = product.get("offers")
    if isinstance(offers, list) and len(offers) == 1:
        offers = offers[0]
    if not isinstance(offers, dict) or offers.get("priceCurrency") != "EUR" or "price" not in offers:
        raise PriceError("No hay un precio de venta inequívoco en la ficha.", response_class="unsupported_price")
    return {"store_name": str(product.get("name", ""))[:300], "price": amount(offers["price"]),
        "currency": "EUR", "ean": str(product.get("gtin13") or product.get("gtin14") or ""),
        "available": None if not offers.get("availability") else str(offers["availability"]).endswith("/InStock")}


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
        else:
            url = link["url"]
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            # Redirects are followed only after validating the same store and reference.
            for _ in range(4):
                await before_request()
                async with session.get(url, headers={"Accept":"application/json" if store != "carrefour" else "text/html",
                    "User-Agent":"Improved-Shopping-List", "Referer":link["url"]},
                    timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
                    status = response.status
                    if status in (301, 302, 303, 307, 308) and store == "carrefour":
                        redirect = normalize_link(store, urljoin(url, response.headers.get("Location", "")))
                        if redirect["id"] != link["id"]:
                            raise PriceError("La redirección apunta a otro producto.", response_class="invalid_redirect")
                        url, link = redirect["url"], redirect
                        continue
                    if status == 404:
                        return None
                    if status != 200:
                        wait = response.headers.get("Retry-After", "")
                        raise PriceError(f"{store.capitalize()}: consulta rechazada (HTTP {status}). Se conserva el último precio.",
                            http_status=status, response_class="access_denied" if status == 403 else "rate_limited" if status == 429 else "http_error",
                            retry_seconds=min(86400, int(wait)) if wait.isdigit() else 0,
                            server=str(response.headers.get("Server", ""))[:80], reference_id=link["id"])
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw) > 4*1024*1024:
                            raise PriceError("La respuesta de la tienda es demasiado grande.", response_class="response_too_large")
                if store == "carrefour":
                    result = structured_offer(raw.decode("utf-8", errors="replace"), link)
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
            raise PriceError("Demasiadas redirecciones de la tienda.", response_class="invalid_redirect")
        finally:
            session.detach()
