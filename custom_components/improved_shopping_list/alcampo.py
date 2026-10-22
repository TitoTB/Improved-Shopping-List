"""Opt-in Alcampo discovery and spread refreshes; one public request per five minutes."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import re
import time
from urllib.parse import urlencode, unquote, urlsplit

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .catalog import CatalogError, normalized_name, product_codes
from .const import DOMAIN
from .price_sources import PriceError, PriceSources
from .store_links import normalize_link
from .store_location import reference_location

DAY = 86400
REQUEST_INTERVAL = 300
MAX_BYTES = 4 * 1024 * 1024


def valid_ean(code):
    if not isinstance(code, str) or len(code) not in (8, 12, 13, 14) or not code.isascii() or not code.isdigit():
        return False
    digits = [int(value) for value in reversed(code[:-1])]
    return (10 - sum(value * (3 if index % 2 == 0 else 1) for index, value in enumerate(digits)) % 10) % 10 == int(code[-1])


def search_terms(names, generic):
    originals = []
    for name in names:
        name = " ".join(name.split())[:50] if isinstance(name, str) else ""
        if name and normalized_name(name) != normalized_name(generic) and name.casefold() not in [item.casefold() for item in originals]:
            originals.append(name)
    if len(originals) >= 2:
        return originals[:2]
    if originals:
        simplified = " ".join(re.sub(r"[^\w\s]", " ", originals[0], flags=re.UNICODE).split())
        if simplified and simplified.casefold() != originals[0].casefold():
            originals.append(simplified)
    return originals[:2]


def linked_commercial_names(product):
    names = []
    for store, link in product.get("store_links", {}).items():
        if store == "alcampo":
            continue
        try:
            verified = normalize_link(store, link)
            parts = [unquote(part) for part in urlsplit(verified["url"]).path.split("/") if part]
            slug = ""
            if store == "carrefour" and len(parts) == 4:
                slug = parts[1]
            elif store == "mercadona" and len(parts) == 3:
                slug = parts[2]
            elif store == "consum" and len(parts) >= 3:
                slug = parts[-2]
            elif store == "lasirena":
                slug = parts[-2].removesuffix("-"+verified["id"])
            elif store == "eroski":
                slug = parts[-1].removeprefix(verified["id"]+"-")
            elif store == "dia" and len(parts) >= 3:
                slug = parts[-3]
            if slug and slug not in ("producto", "es", "supermercado") and not slug.isdigit():
                names.append(slug.replace("-", " "))
        except (ValueError, IndexError):
            continue
    return names


def search_candidates(html):
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*([\s\S]*?)</script>", html)
    if not match:
        raise PriceError("Alcampo no ha devuelto resultados de búsqueda legibles.", response_class="invalid_response")
    try:
        state = json.loads(match[1].strip().removesuffix(";"))
        search = state["data"]["search"]["catalogue"]
        if search.get("fetchError") or search.get("error"):
            raise ValueError
        groups = search["data"]["productGroups"]
        entities = state["data"]["products"]["productEntities"]
        # Only catalogue results, never unrelated page recommendations.
        identifiers = []
        for group in groups:
            for product in group.get("products", []):
                item = entities.get(product) if isinstance(product, str) else product
                if isinstance(item, dict):
                    identifier = str(item.get("retailerProductId", ""))
                    if re.fullmatch(r"[0-9]{1,12}", identifier) and identifier not in identifiers:
                        identifiers.append(identifier)
        return identifiers[:3]
    except (KeyError, ValueError, TypeError, AttributeError) as err:
        raise PriceError("La búsqueda de Alcampo tiene un formato no compatible.", response_class="invalid_response") from err


class AlcampoManager:
    def __init__(self, hass, catalog, settings, prices, receipts, activity):
        self.hass, self.catalog, self.settings = hass, catalog, settings
        self.prices, self.receipts, self.activity = prices, receipts, activity
        self._store = Store(hass, 1, f"{DOMAIN}.alcampo")
        self._data = {"search_enabled":False, "refresh_enabled":False, "days":30,
            "attempts":{}, "offers":{}, "due":{}, "next_request":0, "retry_at":0, "failures":0, "error":""}
        self._active, self._task, self._timer = False, None, None
        self._lock = asyncio.Lock()
        self.sources = PriceSources(hass)
        self._saved = None
        self._prefer_search = False

    async def async_load(self):
        saved = await self._store.async_load()
        if isinstance(saved, dict):
            self._data.update({key:value for key,value in saved.items() if key in self._data})
        self._saved = deepcopy(self._data)

    def start(self):
        if self._active:
            return
        self._active = True
        self._timer = async_track_time_interval(self.hass, self._wake, timedelta(minutes=1))
        self._wake()

    def _wake(self, *_args):
        if self._active and (self._task is None or self._task.done()):
            self._task = self.hass.async_create_task(self.async_tick())

    async def async_stop(self):
        self._active = False
        if self._timer:
            self._timer(); self._timer = None
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.sources.close()

    async def _save(self):
        if self._data != self._saved:
            await self._store.async_save(deepcopy(self._data))
            self._saved = deepcopy(self._data)
            self.prices._notify()

    @property
    def snapshot(self):
        return {key:deepcopy(self._data[key]) for key in ("search_enabled", "refresh_enabled", "days", "next_request", "retry_at", "error")}

    async def async_options(self, options):
        if (not isinstance(options, dict) or set(options) != {"search_enabled", "refresh_enabled", "days"}
                or type(options["search_enabled"]) is not bool or type(options["refresh_enabled"]) is not bool
                or type(options["days"]) is not int or not 1 <= options["days"] <= 3650):
            raise CatalogError("Indica un periodo de Alcampo entre 1 y 3650 días.")
        async with self._lock:
            if options["days"] != self._data["days"] or options["refresh_enabled"] and not self._data["refresh_enabled"]:
                self._data["due"] = {}
            self._data.update(options)
            await self._save()
        self._wake()
        return self.snapshot

    def _enabled(self):
        return (self._active and self.settings.snapshot.get("price_updates_enabled", True)
            and self.settings.snapshot.get("stores", {}).get("alcampo", {}).get("enabled", False))

    def _names(self, product):
        found = []
        for receipt in sorted(self.receipts.stock.receipts["history"].values(), key=lambda item:item["purchased_at"], reverse=True):
            if receipt.get("store") == "alcampo" or receipt.get("summary_only"):
                continue
            for line in receipt.get("lines", []):
                if line.get("product_id") == product["id"] and line.get("description"):
                    found.append(line["description"])
        return search_terms(found + linked_commercial_names(product), product["name"])

    def offer_for(self, product):
        link = product.get("store_links", {}).get("alcampo")
        offer = self._data["offers"].get(link["id"]) if link else None
        return deepcopy(offer) if offer else None

    async def _before_request(self):
        if not self._enabled():
            raise asyncio.CancelledError
        # Persist the reservation before HTTP so reloads cannot reset the rate limit.
        self._data["next_request"] = time.time() + REQUEST_INTERVAL
        await self._save()

    async def _search(self, term):
        await self._before_request()
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            async with session.get("https://www.compraonline.alcampo.es/search?" + urlencode({"q":term}),
                    headers={"User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)", "Accept":"text/html"},
                    timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
                if response.status != 200:
                    retry = response.headers.get("Retry-After", "")
                    raise PriceError(f"Alcampo: búsqueda rechazada (HTTP {response.status}).",
                        http_status=response.status, retry_seconds=int(retry) if retry.isdigit() else 0)
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise PriceError("La búsqueda de Alcampo es demasiado grande.", response_class="response_too_large")
            return search_candidates(raw.decode("utf-8"))
        finally:
            session.detach()

    async def _fetch(self, identifier):
        return await self.sources.fetch("alcampo", normalize_link("alcampo", identifier),
            reference_location("alcampo"), self._before_request)

    async def _remember(self, offer):
        if offer:
            self._data["offers"][offer["reference_id"]] = {**offer, "checked_at":time.time(), "source":"web"}

    async def async_tick(self):
        if not self._enabled() or self._lock.locked():
            return
        async with self._lock:
            now = time.time()
            if now < max(self._data["next_request"], self._data["retry_at"]):
                return
            try:
                # Refreshes and discovery share one queue and one rate limit.
                if self._prefer_search and self._data["search_enabled"] and await self._discover_one():
                    self._prefer_search = False
                elif self._data["refresh_enabled"] and await self._refresh_one(now):
                    self._prefer_search = True
                elif self._data["search_enabled"]:
                    await self._discover_one()
                    self._prefer_search = False
                else:
                    return
                self._data.update(failures=0, retry_at=0, error="")
            except asyncio.CancelledError:
                raise
            except (PriceError, aiohttp.ClientError, asyncio.TimeoutError, UnicodeError, json.JSONDecodeError) as err:
                self._data["failures"] += 1
                diagnostics = getattr(err, "diagnostics", {})
                delay = min(DAY, 3600 * 2 ** min(self._data["failures"] - 1, 5))
                delay = max(delay, min(DAY, diagnostics.get("retry_seconds", 0)))
                self._data.update(retry_at=time.time()+delay, error=str(err) or "Alcampo no está disponible.")
                self.activity.record("stores.error", self._data["error"], source="integration",
                    diagnostics={**diagnostics, "retry_seconds":delay, "provider":"alcampo"})
            except CatalogError as err:
                self.activity.record("stores.error", str(err), source="integration", diagnostics={"provider":"alcampo"})
            await self._save()

    async def _refresh_one(self, now):
        products = [p for p in self.catalog.products if p.get("store_links", {}).get("alcampo")]
        if not products:
            return False
        period = self._data["days"] * DAY
        gap = max(REQUEST_INTERVAL, period / len(products))
        keys = {p["id"]+":"+p["store_links"]["alcampo"]["id"] for p in products}
        self._data["due"] = {key:due for key,due in self._data["due"].items() if key in keys}
        new = [p for p in sorted(products, key=lambda p:p["id"]) if p["id"]+":"+p["store_links"]["alcampo"]["id"] not in self._data["due"]]
        for index, product in enumerate(new):
            key = product["id"]+":"+product["store_links"]["alcampo"]["id"]
            self._data["due"][key] = now + index * gap
        due = sorted((self._data["due"][p["id"]+":"+p["store_links"]["alcampo"]["id"]], p["id"], p) for p in products)
        if due[0][0] > now:
            return False
        _, _, product = due[0]
        link = product["store_links"]["alcampo"]
        offer = await self._fetch(link["id"])
        if not self._enabled() or not self._data["refresh_enabled"]:
            return True
        await self._remember(offer)
        self._data["due"][product["id"]+":"+link["id"]] = time.time()+period
        return True

    async def _discover_one(self):
        for product in self.catalog.products:
            if product.get("store_links", {}).get("alcampo"):
                continue
            for ean in dict.fromkeys(product_codes(product, "barcode")):
                if not valid_ean(ean):
                    continue
                job = self._data["attempts"].get(ean)
                if job and job.get("done"):
                    continue
                if not job:
                    terms = self._names(product)
                    if not terms:
                        continue
                    job = {"terms":terms, "searches":0, "candidates":[], "visited":[], "done":False}
                    self._data["attempts"][ean] = job
                if job["candidates"]:
                    identifier = job["candidates"][0]
                    offer = await self._fetch(identifier)
                    job["candidates"].pop(0)
                    job["visited"].append(identifier)
                    if not self._enabled() or not self._data["search_enabled"]:
                        return
                    if offer and offer.get("ean") == ean:
                        if await self.catalog.async_bind_alcampo(product["id"], ean, normalize_link("alcampo", identifier)):
                            await self._remember(offer)
                            self.activity.record("stores.matched", "Alcampo: producto vinculado por EAN exacto",
                                source="integration", product=product["name"], code=ean,
                                diagnostics={"reference_id":identifier})
                        job["done"] = True
                    return True
                if job["searches"] < min(2, len(job["terms"])):
                    term = job["terms"][job["searches"]]
                    job["searches"] += 1
                    # Save the search budget before HTTP, including failed attempts.
                    await self._save()
                    candidates = await self._search(term)
                    job["candidates"] = [identifier for identifier in candidates[:3] if identifier not in job["visited"]]
                    return True
                job["done"] = True
