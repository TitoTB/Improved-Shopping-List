"""Mercadona catalog: verified dictionary links and anonymous product API only."""
from decimal import Decimal, InvalidOperation
import json
import time

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .catalog_sources import CatalogSources
from .price_sources import PriceError, amount
from .product_references import brand_name, content, gtin
from .receipt_quantities import measure_price
from .store_links import normalize_link
from .store_location import reference_location

STORE = "mercadona"


def positive(value):
    if isinstance(value,bool):return None
    try:
        number=Decimal(str(value))
        return float(number) if number.is_finite() and 0<number<=1000000 else None
    except (ValueError,InvalidOperation,TypeError):return None


def product_data(data,link,expected_ean=""):
    if not isinstance(data,dict) or str(data.get("id",""))!=link["id"]:
        raise PriceError("La ficha de Mercadona no corresponde al producto.",response_class="invalid_product")
    code=data.get("ean")
    if not gtin(code) or expected_ean and gtin(code)!=gtin(expected_ean):
        raise PriceError("El EAN de Mercadona no coincide con el producto.",response_class="ean_mismatch")
    prices=data.get("price_instructions")
    if not isinstance(prices,dict):
        raise PriceError("Mercadona no ha devuelto los datos del envase.",response_class="invalid_response")
    details=data.get("details") if isinstance(data.get("details"),dict) else {}
    result={"store":STORE,"reference_id":link["id"],"url":link["url"],"ean":code,
        "name":str(data.get("display_name") or "")[:500],
        "brand":brand_name(data.get("brand") or details.get("brand") or ""),"checked_at":int(time.time())}
    # unit_size is the size of the sellable package; pack_size describes its presentation.
    # Variable-weight and approximate packages do not declare a fixed package content.
    if not data.get("is_variable_weight") and not prices.get("approx_size") and not data.get("is_bulk"):
        unit=str(prices.get("size_format") or "").lower().strip()
        unit={"ud":"uds","unidad":"uds","unidades":"uds"}.get(unit,unit)
        quantity=positive(prices.get("unit_size"))
        try:
            quantity,unit=content(quantity,unit)
            if quantity is not None:result.update(content_quantity=quantity,content_unit=unit)
        except ValueError:pass
    if prices.get("unit_price") is not None:
        result.update(price=float(amount(prices["unit_price"])),currency="EUR")
    rate=positive(prices.get("reference_price") or prices.get("bulk_price"))
    basis=str(prices.get("reference_format") or "").lower().strip()
    basis={"ud":"uds","unidad":"uds","unidades":"uds"}.get(basis,basis)
    if rate and basis in ("kg","l","uds"):
        result["measure_price"]=measure_price({"price":rate,"quantity":1,"unit":basis,"currency":"EUR","source":"web","checked_at":result["checked_at"]})
    return result


async def retrieve(hass,url,before_request,expected_ean=""):
    link=normalize_link(STORE,url)
    warehouse=reference_location(STORE)["warehouse"]
    endpoint=f"https://tienda.mercadona.es/api/products/{link['id']}/?lang=es&wh={warehouse}"
    session=async_create_clientsession(hass,auto_cleanup=False,cookie_jar=aiohttp.DummyCookieJar())
    try:
        await before_request()
        async with session.get(endpoint,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=25),headers={"Accept":"application/json"}) as response:
            diagnostics={"endpoint":endpoint.split("?",1)[0],"stage":"product_api","http_status":response.status,"warehouse":warehouse}
            if response.status!=200:
                retry=response.headers.get("Retry-After","")
                raise PriceError(f"Mercadona ha rechazado la consulta (HTTP {response.status}).",**diagnostics,
                    response_class="access_denied" if response.status==403 else "http_error",
                    retry_seconds=min(86400,max(900,int(retry) if retry.isdigit() else 900)) if response.status in (403,429,503) else 0)
            raw=bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>2*1024*1024:
                    raise PriceError("La ficha de Mercadona supera el tamaño permitido.",**diagnostics,response_class="response_too_large")
            try:payload=json.loads(raw)
            except (ValueError,UnicodeError) as err:
                raise PriceError("Mercadona no ha devuelto una ficha reconocida.",**diagnostics,response_class="invalid_response") from err
            return product_data(payload,link,expected_ean)
    except (aiohttp.ClientError,TimeoutError) as err:
        raise PriceError("No se ha podido conectar con Mercadona.",endpoint=endpoint.split("?",1)[0],
            stage="product_api",response_class="connection_error",error_type=type(err).__name__) from err
    finally:
        session.detach()


class MercadonaCatalog(CatalogSources):
    source_store=STORE
    source_name="Mercadona"
