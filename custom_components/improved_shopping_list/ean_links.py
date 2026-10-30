"""Read-only EAN-to-shop links, independent of community icons and prices."""
import asyncio
import csv
from datetime import timedelta
import io
import math
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .product_references import gtin, normalized_references, reference_from_line
from .store_links import normalize_link

URL = "https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/main/data/ean-links-v4.csv"
DAY = 86400
MAX_BYTES = 8 * 1024 * 1024


def dictionary_url(value, store="carrefour"):
    """Accept official product pages or this feed's narrowly scoped Awin links."""
    try:
        return normalize_link(store, value)["url"]
    except ValueError:
        if store != "carrefour":
            raise
        parsed = urlsplit(value)
        query = parse_qs(parsed.query, strict_parsing=True)
        if (parsed.scheme != "https" or parsed.netloc != "www.awin1.com" or parsed.path != "/pclick.php"
                or parsed.fragment or set(query) != {"p", "a", "m"} or query["m"] != ["25399"]
                or query["a"] != ["1535625"] or len(query["p"]) != 1 or not re.fullmatch(r"[0-9]{1,20}", query["p"][0])):
            raise ValueError("Unsupported dictionary URL")
        return value


def key_store(key):
    """Keep historical Carrefour cache keys; namespace the additional shop."""
    store, code = tuple(key.split(":",1)) if key.startswith(("alcampo:","lidl:","mercadona:")) else ("carrefour", key)
    if not code or gtin(code) != code:
        raise ValueError("Invalid EAN cache key")
    return store


def parse_dictionary(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("EAN dictionary too large")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or "EAN" not in reader.fieldnames or "Carrefour" not in reader.fieldnames:
        raise ValueError("Invalid EAN dictionary columns")
    result = {}
    for number, row in enumerate(reader):
        if number >= 100000:
            raise ValueError("Too many EAN entries")
        code = gtin(row.get("EAN", ""))
        if not code or not any(row.get(column) for column in ("Carrefour", "Alcampo", "Lidl", "Mercadona")):
            raise ValueError("Invalid EAN entry")
        for store, column in (("carrefour", "Carrefour"), ("alcampo", "Alcampo"), ("lidl", "Lidl"), ("mercadona", "Mercadona")):
            if not row.get(column):
                continue
            key = code if store == "carrefour" else store+":"+code
            value = dictionary_url(row[column], store)
            if key in result and result[key] != value:
                raise ValueError("Conflicting EAN entry")
            result[key] = value
    if not result:
        raise ValueError("Empty EAN dictionary")
    return result


def product_eans(product):
    codes = [product.get("barcode", ""), *product.get("barcodes", [])]
    codes += [ref.get("ean", "") for ref in product.get("commercial_references", []) if ref.get("active", True)]
    return {key: code for code in codes if (key := gtin(code))}


def enrich_product(product, resolved):
    """Fill exact EAN matches; preserve user URLs, exclusions, formats and prices."""
    changed = False
    for store in ("carrefour", "alcampo", "lidl", "mercadona"):
        changed = _enrich_store(product, resolved, store) or changed
    return changed


def _enrich_store(product, resolved, store):
    refs = product.setdefault("commercial_references", [])
    changed = False
    for key, code in product_eans(product).items():
        link = resolved.get(key if store == "carrefour" else store+":"+key)
        if not link:
            continue
        matches = [ref for ref in refs if ref["store"] == store and gtin(ref.get("ean")) == key]
        if any(not ref.get("active", True) or ref.get("url") for ref in matches):
            continue
        ref = next(iter(matches), None)
        if ref and ref.get("reference_id") and ref["reference_id"] != link["id"]:
            continue
        duplicate = next((other for other in refs if other.get("store") == store and other.get("reference_id") == link["id"] and other is not ref),None)
        if duplicate:
            if ref is None and duplicate.get("active",True) and not duplicate.get("ean") and duplicate.get("url") == link["url"]:
                duplicate["ean"] = code
                changed = True
            continue
        if ref is None:
            ref = next((row for row in refs if not row["store"] and gtin(row.get("ean")) == key and row.get("active", True)), None)
        if ref is None:
            if len(refs) >= 200:
                continue
            ref = reference_from_line(store, {"ean":code, "name":product["name"]})
            refs.append(ref)
            if store in ("alcampo","mercadona"):ref["catalog_source"]=True
        elif not ref.get("store") and store in ("alcampo","mercadona"):
            ref["catalog_source"]=True
        ref.update(store=store, url=link["url"], reference_id=link["id"])
        changed = True
    if changed:
        product["commercial_references"] = normalized_references(refs)
    return changed


def redirect_product(location):
    """Extract the official destination without following advertising redirects."""
    if not isinstance(location, str) or len(location) > 8192:
        raise ValueError("Invalid redirect")
    candidates = re.findall(r'https://(?:www\.)?carrefour\.es/supermercado/[^\s<>"?&#]+', unquote(location))
    links = {normalize_link("carrefour", candidate)["url"] for candidate in candidates}
    if len(links) != 1:
        raise ValueError("Ambiguous Carrefour destination")
    return normalize_link("carrefour", links.pop())


class EANLinks:
    def __init__(self, hass, catalog):
        self.hass, self.catalog = hass, catalog
        self._store = Store(hass, 1, f"{DOMAIN}.ean_links")
        self._data = {"links":{}, "resolved":{}, "failed":{}, "etag":"", "checked_at":0}
        self._active = False
        self._task = self._timer = self._stop = self._unsubscribe = None
        self._next_download = self._next_request = 0
        self.error = ""
        self.enabled_stores = {"carrefour"}
        self.catalog_stores = set()

    async def async_load(self):
        data = await self._store.async_load()
        if isinstance(data, dict):
            try:
                links = {key:dictionary_url(value, key_store(key)) for key,value in data.get("links", {}).items()}
                resolved = {key:normalize_link(key_store(key), value) for key,value in data.get("resolved", {}).items()}
                failed = {key:at for key,at in data.get("failed", {}).items() if key_store(key)
                          and type(at) in (int,float) and math.isfinite(at) and time.time() < at <= time.time()+DAY}
                checked = float(data.get("checked_at", 0))
                if not math.isfinite(checked) or checked > time.time():
                    checked = 0
                etag = str(data.get("etag", ""))[:256]
                if any(ord(char)<32 for char in etag):
                    etag = ""
                self._data.update(links=links, resolved=resolved, failed=failed, etag=etag, checked_at=checked)
                if data.get("index_version") != 4:
                    self._data.update(etag="", checked_at=0)
            except (ValueError, TypeError, AttributeError):
                pass  # A damaged optional cache must not prevent Home Assistant startup.

    @property
    def resolved(self):
        return {key:value for key,value in self._data["resolved"].items() if key_store(key) in self.enabled_stores}

    async def async_store_links(self, store):
        """Read exact official links for an explicitly enabled catalog source."""
        if store not in self.enabled_stores | self.catalog_stores:
            return {}
        try:
            await self._download()
        except (ClientError, TimeoutError, OSError, ValueError) as err:
            self.error = str(err)
        codes = {key for product in self.catalog.products for key in product_eans(product)}
        return {key:normalize_link(store,value) for key,value in self._data["links"].items()
                if key_store(key) == store and key.rsplit(":",1)[-1] in codes}

    async def async_find_link(self, store, code):
        """Exact URL lookup for a user-initiated receipt review, keeping offline data."""
        key=gtin(code)
        if not key or store not in ("carrefour","alcampo","lidl","mercadona"):
            return None
        try:
            await self._download()
        except (ClientError,TimeoutError,OSError,ValueError) as err:
            self.error=str(err)
        value=self._data["links"].get(key if store=="carrefour" else store+":"+key)
        return normalize_link(store,value) if value and urlsplit(value).hostname!="www.awin1.com" else None

    def start(self):
        if self._active:
            return
        self._active = True
        self._unsubscribe = self.catalog.subscribe(self._queue)
        self._stop = async_track_time_interval(self.hass, self._queue, timedelta(hours=1))
        self._queue()

    @callback
    def _queue(self, *_args):
        if self._active and self._timer is None:
            self._timer = async_call_later(self.hass, max(1, self._next_request-time.time()), self._launch)

    @callback
    def _launch(self, *_args):
        self._timer = None
        if self._active and (self._task is None or self._task.done()):
            self._task = self.hass.async_create_background_task(self.async_sync(), "Shopping EAN link dictionary")

    async def async_stop(self):
        self._active = False
        for stop in (self._timer, self._stop, self._unsubscribe):
            if stop:
                stop()
        self._timer = self._stop = self._unsubscribe = None
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _download(self):
        now = time.time()
        if now < max(self._data["checked_at"]+DAY, self._next_download):
            return
        self._next_download = now+DAY
        session = async_get_clientsession(self.hass)
        headers = {"If-None-Match":self._data["etag"]} if self._data["etag"] else {}
        async with session.get(URL, headers=headers, timeout=ClientTimeout(total=25), allow_redirects=False) as response:
            if response.status == 304:
                self._data["checked_at"] = now
            elif response.status == 200:
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("EAN dictionary too large")
                links = await self.hass.async_add_executor_job(parse_dictionary, bytes(raw))
                if links != self._data["links"]:
                    self._data["resolved"] = {key:value for key,value in self.resolved.items() if links.get(key) == self._data["links"].get(key)}
                    self._data["failed"] = {}
                self._data.update(links=links, etag=response.headers.get("ETag", "")[:256], checked_at=now, index_version=4)
            else:
                raise ValueError(f"GitHub HTTP {response.status}")
        await self._store.async_save(self._data)

    def _pending(self):
        codes = {key for product in self.catalog.products for key in product_eans(product)}
        keys = codes | {store+":"+code for store in self.enabled_stores if store != "carrefour" for code in codes}
        return sorted(key for key in keys if key_store(key) in self.enabled_stores and key in self._data["links"] and key not in self.resolved
                      and time.time() >= self._data["failed"].get(key, 0))

    async def async_sync(self):
        if not self._active or not any(product_eans(product) for product in self.catalog.products):
            return
        try:
            try:
                await self._download()
            except (ClientError, TimeoutError, OSError, ValueError) as err:
                self.error = str(err)  # Continue using the previous local dictionary offline.
            await self.catalog.async_apply_ean_links(self.resolved)
            pending = self._pending()
            if pending and time.time() >= self._next_request:
                key = pending[0]
                self._next_request = time.time()+5
                try:
                    value = self._data["links"][key]
                    if urlsplit(value).hostname == "www.awin1.com":
                        async with async_get_clientsession(self.hass).head(value, allow_redirects=False, timeout=ClientTimeout(total=15)) as response:
                            if response.status not in (301,302,303,307,308):
                                raise ValueError(f"Awin HTTP {response.status}")
                            link = redirect_product(response.headers.get("Location"))
                    else:
                        link = normalize_link(key_store(key), value)
                    self._data["resolved"][key] = link
                    self.error = ""
                except (ClientError, TimeoutError, OSError, ValueError) as err:
                    self.error = str(err)
                    self._data["failed"][key] = time.time()+DAY
                await self._store.async_save(self._data)
                await self.catalog.async_apply_ean_links(self.resolved)
        finally:
            if self._pending():
                self._queue()
