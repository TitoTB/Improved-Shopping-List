"""Explicit, bounded retrieval of one linked official product page."""
from asyncio import Lock, sleep
from copy import deepcopy
from html.parser import HTMLParser
import json
import time
from urllib.parse import urljoin, urlsplit

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .price_sources import PriceError, PriceSources, amount
from .product_references import brand_name, content, gtin, inferred_content
from .store_links import HOSTS, normalize_link
from .store_location import reference_location
from .receipt_quantities import measure_price


class ProductScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.current = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            try:
                self.scripts.append(json.loads("".join(self.current)))
            except (ValueError, RecursionError):
                pass
            self.current = None


def text(value, limit=500):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def metadata(product):
    """Only explicit commercial fields; never derive a brand from a generic name."""
    brand = product.get("brand", product.get("brands", product.get("item_brand", "")))
    if isinstance(brand, dict):
        brand = brand.get("name", "")
    result = {"brand": brand_name(text(brand, 160))}
    name = text(product.get("name") or product.get("display_name") or product.get("item_name") or product.get("store_name"))
    if name:
        result["name"] = name
    quantity, unit = inferred_content({"description": text(product.get("size") or product.get("quantity")) or name})
    weight = product.get("weight")
    if isinstance(weight, dict):
        units = {"GRM":"g", "KGM":"kg", "MLT":"ml", "LTR":"l", "C62":"uds"}
        try:
            quantity, unit = content(float(weight.get("value")), units.get(weight.get("unitCode"), weight.get("unitText", "")))
        except (ValueError, TypeError):
            pass
    try:
        result["content_quantity"], result["content_unit"] = content(quantity, unit)
    except ValueError:
        pass
    image = product.get("image", product.get("thumbnail", ""))
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    if isinstance(image, str) and len(image) <= 2048:
        parsed = urlsplit(image)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            result["image_url"] = image
    grade = text(product.get("nutriscore_grade") or product.get("nutriScore") or "", 20).lower()
    properties = product.get("additionalProperty", [])
    if isinstance(properties, dict):
        properties = [properties]
    for prop in properties if isinstance(properties, list) else []:
        if isinstance(prop, dict) and text(prop.get("name")).lower().replace("-", "").replace(" ", "") == "nutriscore":
            grade = text(prop.get("value"), 20).lower()
    if grade in "abcde" and len(grade) == 1:
        result["nutriscore"] = {"grade": grade, "checked_at": int(time.time())}
    return result


def page_product(html, store, link):
    parser = ProductScripts()
    parser.feed(html)
    products = []

    def collect(value, depth=0):
        if depth > 20:
            return
        if isinstance(value, list):
            for item in value:
                collect(item, depth+1)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if "Product" in ([types] if isinstance(types, str) else types if isinstance(types, list) else []):
                products.append(value)
            collect(value.get("@graph", []), depth+1)

    for script in parser.scripts:
        collect(script)
    matches = []
    for product in products:
        url = product.get("url") or product.get("@id")
        if isinstance(url, str):
            try:
                if normalize_link(store, urljoin(link["url"], url))["id"] == link["id"]:
                    matches.append(product)
            except ValueError:
                pass
        elif str(product.get("sku", "")) in (link["id"], link["id"].removeprefix("R-")) or len(products) == 1:
            matches.append(product)
    if len(matches) != 1:
        return None
    product = matches[0]
    result = metadata(product)
    result["ean"] = next((str(product[key]) for key in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin") if gtin(str(product.get(key, "")))), "")
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else None
    if isinstance(offers, dict) and offers.get("priceCurrency") == "EUR" and offers.get("price") is not None:
        try:
            result.update(price=float(amount(offers["price"])), currency="EUR")
        except PriceError:
            pass
    specs=offers.get("priceSpecification",[]) if isinstance(offers,dict) else []
    if isinstance(specs,dict):
        specs=[specs]
    rates=[]
    for spec in specs if isinstance(specs,list) else []:
        if not isinstance(spec,dict) or spec.get("@type")!="UnitPriceSpecification":
            continue
        base=spec.get("referenceQuantity",{})
        if not isinstance(base,dict):
            continue
        unit={"KGM":"kg","GRM":"g","LTR":"l","MLT":"ml","C62":"uds"}.get(base.get("unitCode"),base.get("unitText",""))
        try:
            rates.append(measure_price({"price":float(spec.get("price")),"quantity":float(base.get("value",1)),"unit":unit,
                "currency":spec.get("priceCurrency",offers.get("priceCurrency")),"checked_at":int(time.time()),"source":"web"}))
        except (ValueError,TypeError):
            continue
    if len(rates)==1:
        result["measure_price"]=rates[0]
    return result


def web_measure_price(result):
    if result.get("measure_price"):
        return measure_price(result["measure_price"])
    raw={"price":result.get("reference_price"),"quantity":1,"unit":result.get("reference_unit"),"currency":"EUR","checked_at":int(time.time()),"source":"web"}
    if raw["price"] is None:
        raw.update(price=result.get("price"),quantity=result.get("content_quantity"),unit=result.get("content_unit"))
    try:
        raw["price"]=float(raw["price"])
        return measure_price(raw)
    except (ValueError,TypeError):
        return None


class OptionLookup:
    def __init__(self, hass):
        self.hass = hass
        self.sources = PriceSources(hass)
        self._lock, self._next, self._cache = Lock(), 0, {}
        self._blocked_until = {}

    def close(self):
        self.sources.close()

    async def _before_request(self):
        delay = self._next - time.monotonic()
        if delay > 0:
            await sleep(delay)
        self._next = time.monotonic() + 5

    async def _page(self, store, link, before_request=None):
        if store == "lasirena":
            from .lasirena_product import retrieve
            return await retrieve(self.hass, link["url"], before_request or self._before_request)
        if store in ("masymas","bm","consum"):
            from .public_catalogs import retrieve
            return await retrieve(self.hass,store,link["url"],before_request or self._before_request)
        if store == "mercadona":
            from .mercadona_catalog import retrieve
            return await retrieve(self.hass,link["url"],before_request or self._before_request)
        if store == "elcorteingles":
            from .eci_catalog import ECIClient
            client=ECIClient(self.hass)
            try:
                return await client.retrieve(link["url"],before_request or self._before_request)
            finally:
                await client.async_close()
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            current = link["url"]
            for _ in range(3):
                await (before_request or self._before_request)()
                async with session.get(current, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20),
                    headers={"Accept":"text/html", "User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)"}) as response:
                    if response.status in (301,302,303,307,308):
                        destination = normalize_link(store, urljoin(current, response.headers.get("Location", "")))
                        if destination["id"] != link["id"]:
                            raise PriceError("La web redirige a otro producto.", response_class="invalid_product")
                        current = destination["url"]
                        continue
                    if response.status != 200:
                        if response.status in (429,503):
                            retry=response.headers.get("Retry-After", "")
                            self._blocked_until[store]=time.monotonic()+min(86400,max(900,int(retry) if retry.isdigit() else 900))
                        raise PriceError(f"La web ha rechazado la consulta (HTTP {response.status}).", http_status=response.status,
                            response_class="access_denied" if response.status == 403 else "rate_limited" if response.status in (429,503) else "http_error",
                            endpoint=urlsplit(current).path, content_type=response.headers.get("Content-Type", "")[:120],
                            server=response.headers.get("Server", "")[:80])
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body) > 2*1024*1024:
                            raise PriceError("La ficha supera el tamaño máximo permitido.")
                    result = page_product(body.decode("utf-8", errors="replace"), store, link)
                    if result is None:
                        raise PriceError("La página no contiene un único producto estructurado coincidente.",
                            http_status=response.status, response_class="structured_product_missing", endpoint=urlsplit(current).path,
                            content_type=response.headers.get("Content-Type", "")[:120], response_bytes=len(body),
                            server=response.headers.get("Server", "")[:80])
                    return result
            raise PriceError("La ficha redirige demasiadas veces.")
        finally:
            session.detach()

    async def retrieve(self, value, store="", expected_ean="", *, measure=False, before_request=None, force=False):
        # A full official URL is authoritative, even if the option was filed
        # under another store. normalize_link still validates the complete path.
        if "://" in value or not store:
            host = urlsplit(value).hostname
            store = next((key for key, hosts in HOSTS.items() if host in hosts), "")
        link = normalize_link(store, value)
        if store == "elcorteingles":
            raise PriceError("La consulta de El Corte Inglés está retirada temporalmente. Puedes editar los datos manualmente.",response_class="source_unavailable")
        if not link["url"]:
            raise PriceError("Indica el enlace completo de la ficha del producto.")
        async with self._lock:
            cached = self._cache.get((store, link["id"]))
            if not force and cached and cached[0] > time.monotonic():
                result = deepcopy(cached[1])
            else:
                if self._blocked_until.get(store,0)>time.monotonic():
                    raise PriceError("La tienda está en pausa de reintento. Puedes indicar la cantidad manualmente.",response_class="rate_limited")
                warnings, attempts, result = [], [], {}
                statuses=[]
                try:
                    result = await (self._page(store, link, before_request) if before_request else self._page(store, link)) or {}
                except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                    warnings.append(str(err))
                    statuses.append(getattr(err,"diagnostics",{}).get("http_status"))
                    attempts.append({"stage":"product_page", "error_type":type(err).__name__,
                                     **getattr(err,"diagnostics",{})})
                    if self._blocked_until.get(store,0)>time.monotonic():
                        raise PriceError("La tienda ha solicitado una pausa. Puedes indicar la cantidad manualmente.",
                            response_class="rate_limited", attempts=attempts, errors=warnings,
                            retry_seconds=max(0,int(self._blocked_until[store]-time.monotonic()))) from err
                if store not in ("lasirena","lidl","elcorteingles","mercadona","masymas","bm","consum") and (not result.get("name") or result.get("price") is None or not result.get("brand") or result.get("content_quantity") is None):
                    try:
                        offer = await self.sources.fetch(store, link, reference_location(store), before_request or self._before_request)
                        if offer:
                            safe = {**metadata(offer), **{key:offer[key] for key in ("price", "currency", "ean", "reference_price", "reference_unit") if key in offer}}
                            for key, val in safe.items():
                                if val not in (None, "") and result.get(key) in (None, ""):
                                    result[key] = val
                        else:
                            attempts.append({"stage":"product_api", "response_class":"no_offer"})
                    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                        warnings.append(str(err))
                        statuses.append(getattr(err,"diagnostics",{}).get("http_status"))
                        attempts.append({"stage":"product_api", "error_type":type(err).__name__,
                                         **getattr(err,"diagnostics",{})})
                if any(status in (403,429,503) for status in statuses) and result.get("price") is None:
                    retry=max([900,*[item["retry_seconds"] for item in attempts
                        if type(item.get("retry_seconds")) in (int,float) and 0<=item["retry_seconds"]<=86400]])
                    self._blocked_until[store]=time.monotonic()+retry
                if not any(result.get(key) for key in ("name", "brand", "ean", "content_quantity", "image_url", "nutriscore")) and result.get("price") is None:
                    blocked=max(0,int(self._blocked_until.get(store,0)-time.monotonic()))
                    status=next((status for status in statuses if status in (403,429,503)),None)
                    message=f"La tienda ha rechazado la consulta (HTTP {status}). Se conservan los datos anteriores." if status else "No se han podido recuperar datos de esta ficha. Puedes conservar la URL y completar la opción manualmente."
                    raise PriceError(message, errors=warnings, attempts=attempts, reference_id=link["id"],
                        response_class="access_denied" if status == 403 else "rate_limited" if status else "product_data_missing",
                        **({"http_status":status} if status else {}), retry_seconds=blocked)
                result.update(store=store, reference_id=link["id"], url=link["url"], checked_at=int(time.time()))
                if result.get("price") is None and attempts:
                    result["retrieval_diagnostics"] = {"attempts":attempts,"errors":warnings}
                if result.get("price") is not None:
                    result["price"] = float(amount(result["price"]))
                if not gtin(result.get("ean", "")):
                    result.pop("ean", None)
                if rate:=web_measure_price(result):
                    result["measure_price"]=rate
                self._cache[(store, link["id"])] = (time.monotonic()+60, deepcopy(result))
                self._cache = dict(list(self._cache.items())[-100:])
            if expected_ean and result.get("ean") and gtin(expected_ean) != gtin(result["ean"]):
                raise PriceError("El EAN de la web no coincide con esta opción. Revisa el enlace antes de vincularlo.", response_class="ean_mismatch")
            return result
