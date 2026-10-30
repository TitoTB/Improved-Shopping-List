"""Read one La Sirena product from its public catalog, never its HTML GTIN."""
import json
import re

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .price_sources import PriceError, amount, sirena_product
from .product_references import gtin
from .store_links import normalize_link


def product_data(data, link):
    from .option_lookup import metadata

    selected = sirena_product(data, link)
    if selected is None:
        raise PriceError("La Sirena no ha encontrado esta referencia.", response_class="invalid_product")
    product, sku = selected
    if not gtin(sku.get("ean")):
        raise PriceError("La Sirena no ha confirmado un EAN válido.", response_class="invalid_product")
    package = product.get("Envase", [])
    package = package[0] if isinstance(package, list) and len(package) == 1 else package if isinstance(package, str) else ""
    result = metadata({"name": product.get("productName"), "brand": product.get("brand"), "size": package})
    result["ean"] = sku["ean"]
    pack = re.search(r"\b(\d+)\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|g|ml|cl|l)\b", package, re.I)
    if pack and 1 <= int(pack[1]) <= 1000000:
        result["pack_count"] = int(pack[1])
    # Use only the single default seller; never pick the cheapest of ambiguous offers.
    sellers = [s for s in sku.get("sellers", []) if isinstance(s, dict) and s.get("sellerDefault") is True]
    if len(sellers) == 1:
        offer = sellers[0].get("commertialOffer", {})
        if isinstance(offer, dict) and offer.get("IsAvailable") is True and offer.get("Price") is not None:
            result.update(price=float(amount(offer["Price"])), currency="EUR")
    return result


async def request(hass, query, before_request):
    endpoint = "https://www.lasirena.es/api/catalog_system/pub/products/search"
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
    try:
        await before_request()
        async with session.get(endpoint, params={"fq": query}, allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=25), headers={"Accept": "application/json"}) as response:
            diagnostics = {"endpoint": endpoint, "stage": "product_api", "http_status": response.status}
            if response.status != 200:
                retry = response.headers.get("Retry-After", "")
                raise PriceError(f"La Sirena ha rechazado la consulta (HTTP {response.status}).", **diagnostics,
                    response_class="access_denied" if response.status == 403 else "http_error",
                    retry_seconds=min(86400, max(900, int(retry) if retry.isdigit() else 900)) if response.status in (403, 429, 503) else 0)
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > 2 * 1024 * 1024:
                    raise PriceError("La ficha de La Sirena supera el tamaño permitido.", **diagnostics, response_class="response_too_large")
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError) as err:
                raise PriceError("La Sirena no ha devuelto una ficha reconocida.", **diagnostics, response_class="invalid_response") from err
            if not isinstance(payload, list):
                raise PriceError("La Sirena no ha devuelto un catálogo reconocido.", **diagnostics, response_class="invalid_response")
            return payload
    except (aiohttp.ClientError, TimeoutError) as err:
        raise PriceError("No se ha podido conectar con La Sirena.", endpoint=endpoint,
            stage="product_api", response_class="connection_error", error_type=type(err).__name__) from err
    finally:
        session.detach()


async def retrieve(hass, url, before_request):
    link = normalize_link("lasirena", url)
    return product_data(await request(hass, f"productId:{link['id']}", before_request), link)


async def search(hass, code, before_request):
    """Confirm the returned SKU's GTIN, never a similarity in the product name."""
    code = gtin(code)
    if not code:
        raise PriceError("Indica un EAN válido.", response_class="invalid_product")
    native = code[1:] if code.startswith("0") else code
    payload = await request(hass, f"alternateIds_Ean:{native}", before_request)
    matches = [p for p in payload if isinstance(p, dict) and isinstance(p.get("items"), list)
               and any(isinstance(s, dict) and gtin(s.get("ean")) == code for s in p["items"])]
    if not matches:
        return None
    if len(matches) != 1:
        raise PriceError("La Sirena devuelve varias referencias para este EAN.", response_class="ambiguous_product")
    product = matches[0]
    link = normalize_link("lasirena", product.get("link", ""))
    result = product_data(matches, link)
    result.update(store="lasirena", reference_id=link["id"], url=link["url"])
    return result
