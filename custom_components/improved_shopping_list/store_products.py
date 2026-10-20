"""Warehouse-scoped Mercadona offers, matched only by exact GTIN."""

import asyncio
from asyncio import sleep
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import json
import logging
import re
import time
from uuid import uuid4
from urllib.parse import quote

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .product_lookup import is_product_barcode
from .stores import StoreError

LEGACY_SEARCH_URL = "https://tornillos.mercadona.es/search"
# Public search-only configuration used by Mercadona's own anonymous web client.
# Verified in https://tienda.mercadona.es/v9969/index-DIFZJQot.js (its Algolia fallback).
ALGOLIA_APP = "7UZJKL1DJ0"
ALGOLIA_SEARCH_KEY = "9d8f2e39e90df472b4f2e559a116fe17"
SEARCH_URL = "https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_{warehouse}_es/query"
PRODUCT_URL = "https://tienda.mercadona.es/api/products/{identifier}/?lang=es&wh={warehouse}"
PROVIDER = "algolia-product-api-v1"
TTL = 6 * 3600
# Match the five-second Delay in the original Mercadona n8n workflow.
REQUEST_INTERVAL = 5.0
_LOGGER = logging.getLogger(__name__)


class LookupPending(Exception):
    """A successful but incomplete candidate scan; never a network error or miss."""


class StoreConfigurationChanged(StoreError):
    """Stop in-flight candidate scans when their entry or warehouse changes."""


def search_url(warehouse):
    return SEARCH_URL.format(warehouse=quote(warehouse, safe=""))


class StoreRequestError(StoreError):
    """Safe technical diagnostics, never raw headers, bodies or credentials."""

    def __init__(self, message, diagnostics, retry_seconds=0):
        super().__init__(message)
        self.diagnostics = diagnostics
        self.retry_seconds = retry_seconds


def retry_seconds(value):
    """Respect Retry-After seconds or HTTP dates, bounded to one day."""
    try:
        seconds = int(value) if str(value).isdigit() else parsedate_to_datetime(value).timestamp() - time.time()
        return max(0, min(86400, int(seconds)))
    except (TypeError, ValueError, OverflowError):
        return 0


def exact_offer(hits, code):
    """Never infer an association from a similar product name."""
    if not isinstance(hits, list):
        raise StoreError("La respuesta de productos de Mercadona no es válida.")
    matches = [hit for hit in hits if isinstance(hit, dict) and str(hit.get("ean", "")).zfill(14) == code.zfill(14)]
    if not matches:
        return None
    if len({str(hit.get("id")) for hit in matches}) != 1:
        raise StoreError("Mercadona devuelve varias referencias para el mismo EAN.")
    hit = matches[0]
    identifier = str(hit.get("id", ""))
    if not identifier.isascii() or not identifier.isdigit() or len(identifier) > 12:
        raise StoreError("La referencia de Mercadona no es válida.")
    prices = hit.get("price_instructions")
    if not isinstance(prices, dict):
        return None
    try:
        price = Decimal(str(prices.get("unit_price")))
        if not price.is_finite() or not 0 <= price <= 1000000:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return None
    reference = None
    try:
        number = Decimal(str(prices.get("reference_price", prices.get("bulk_price"))))
        if number.is_finite() and 0 <= number <= 1000000:
            reference = float(number)
    except (InvalidOperation, ValueError):
        pass
    return {"ean": code, "store_product_id": identifier, "store_name": str(hit.get("display_name", ""))[:200],
            "price": float(price), "currency": "EUR", "reference_price": reference,
            "reference_unit": str(prices.get("reference_format", ""))[:20],
            "approximate": prices.get("approx_size") is True,
            "available": hit.get("published") is not False,
            "url": f"https://tienda.mercadona.es/product/{identifier}"}


class StoreProducts:
    """Bounded, cached lookups; network failures retain previously known prices."""

    def __init__(self, hass, catalog, settings):
        self.hass, self.catalog, self.settings = hass, catalog, settings
        self._store = Store(hass, 1, f"{DOMAIN}.store_products")
        self._cache = {}
        self._lookups = {}
        self._details = {}
        self._cycle = {}
        self._deadline = None
        self._context = None
        self._run_processed = 0
        self._run_total = None
        self._run_started = None
        self._run_candidates = 0
        self._run_pending = None
        self._lock = asyncio.Lock()
        self._retry_after = 0
        self._last_error = ""
        self._failures = 0
        self._last_diagnostics = {}
        self._request_lock = asyncio.Lock()
        self._next_request = 0
        self._request_count = 0
        self._batch_id = ""
        self._listeners = set()
        self.progress = {"running": False}
        self.activity = None

    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _update_progress(self, **changes):
        self.progress = {**self.progress, **changes}
        if self.progress.get("running"):
            elapsed = max(0, time.time() - self.progress["started_at"])
            remaining = self.progress["total"] - self.progress["processed"]
            processed = self.progress["processed"]
            self.progress["estimated_seconds"] = round(remaining * max(REQUEST_INTERVAL, elapsed / processed)) if processed else None
        for listener in tuple(self._listeners):
            listener()

    async def async_load(self):
        data = await self._store.async_load()
        self._cache = data.get("offers", {}) if isinstance(data, dict) else {}
        if isinstance(data, dict):
            self._retry_after = data.get("retry_after", 0)
            self._last_error = data.get("last_error", "")
            self._last_diagnostics = data.get("last_diagnostics", {})
            self._failures = data.get("failures", 0)
            self._lookups = data.get("lookups", {})
            self._details = data.get("details", {})
            self._cycle = data.get("cycle", {})
            if data.get("provider") != PROVIDER:
                # Old search misses are not proof that the new candidate lookup has run.
                self._cache = {key: value for key, value in self._cache.items() if value.get("offer")}
                self._lookups, self._details, self._cycle = {}, {}, {}
            if self._last_diagnostics.get("endpoint") == LEGACY_SEARCH_URL:
                # That provider will never be called again; don't carry its cooldown to another service.
                self._retry_after, self._failures = 0, 0
                self._last_error, self._last_diagnostics = "", {}

    async def _persist(self):
        await self._store.async_save({"offers": self._cache, "retry_after": self._retry_after,
            "last_error": self._last_error, "last_diagnostics": self._last_diagnostics, "failures": self._failures,
            "provider": PROVIDER, "lookups": self._lookups, "details": self._details, "cycle": self._cycle})

    def _record(self, kind, message, diagnostics, **fields):
        if self.activity:
            self.activity.record(f"stores.{kind}", message, store="Mercadona", diagnostics=deepcopy(diagnostics), **fields)

    def _codes(self):
        codes = {}
        for product in self.catalog.products:
            for code in [product.get("barcode", ""), *product.get("barcodes", [])]:
                if is_product_barcode(code):
                    codes.setdefault(code.zfill(14), {"code": code, "name": product["name"]})
        return codes

    def _check_context(self):
        if self._context is None:
            return
        entry, generation, warehouse = self._context
        current = self.settings.snapshot["stores"]["mercadona"]
        if (not self.hass.data.get(DOMAIN, {}).get("active") or self.settings.entry is not entry
            or self.settings._generation != generation or not current.get("enabled") or current.get("warehouse") != warehouse):
            raise StoreConfigurationChanged("La configuración de la tienda ha cambiado. Vuelve a abrir el popup.")

    def snapshot(self):
        store = self.settings.snapshot["stores"]["mercadona"]
        warehouse = store.get("warehouse", "")
        products = []
        if store.get("enabled"):
            for key, product in self._codes().items():
                cached = self._cache.get(f"{warehouse}:{key}", {})
                if offer := cached.get("offer"):
                    products.append({**deepcopy(offer), "name": product["name"], "checked_at": cached["checked_at"]})
        return {"products": sorted(products, key=lambda product: product["name"].casefold()),
                "enabled": store.get("enabled", False), "warehouse": warehouse,
                "error": self._last_error if store.get("enabled") else "", "remaining": 0,
                "automatic_refresh_blocked": store.get("enabled", False) and self._last_diagnostics.get("http_status") == 403,
                "not_found": sum(1 for key in self._codes() if store.get("enabled")
                    and (cached := self._cache.get(f"{warehouse}:{key}")) and not cached.get("offer")
                    and time.time() - cached.get("checked_at", 0) < TTL),
                "retry_at": self._retry_after if store.get("enabled") else 0, "processed": 0, "total": len(self._codes())}

    async def async_refresh(self, force=False):
        async with self._lock:
            self._run_processed, self._run_total = 0, None
            self._run_started, self._run_candidates = time.time(), 0
            self._run_pending = None
            try:
                while True:
                    self._check_context()
                    result = await self._async_refresh(force)
                    self._run_processed += result["processed"]
                    result.update(processed=self._run_processed, total=self._run_total if self._run_total is not None else result["total"])
                    if (not result["remaining"] or result.get("error") or result.get("automatic_refresh_blocked")
                        or not result.get("enabled")):
                        return result
                    # The checkpoint has been saved. Continue while retaining the same
                    # lock, progress totals and request pacing, with no extra user action.
            finally:
                if self.progress.get("running"):
                    self._update_progress(running=False, estimated_seconds=0)
                self._deadline = None
                self._context = None
                self._run_pending = None

    async def _async_refresh(self, force=False):
        result = self.snapshot()
        warehouse = result["warehouse"]
        entry = self.settings.entry
        generation = self.settings._generation
        if not result["enabled"] or not warehouse:
            return result
        self._context = (entry, generation, warehouse)
        now = time.time()
        codes = self._codes()
        pending = [(key, product) for key, product in codes.items()
                   if force or now - self._cache.get(f"{warehouse}:{key}", {}).get("checked_at", 0) >= TTL]
        if force:
            queries = {key: product["name"] for key, product in codes.items()}
            if self._cycle.get("warehouse") != warehouse or self._cycle.get("queries") != queries or not self._cycle.get("pending"):
                self._cycle = {"warehouse": warehouse, "queries": queries, "pending": list(codes)}
            pending = [(key, product) for key, product in pending if key in self._cycle["pending"]]
        if self._run_pending is None:
            self._run_pending = {key for key, product in pending}
        else:
            pending = [(key, product) for key, product in pending if key in self._run_pending]
        pending.sort(key=lambda item: self._cache.get(f"{warehouse}:{item[0]}", {}).get("checked_at", 0))
        error, changed, processed = "", False, 0
        if not force and result["automatic_refresh_blocked"]:
            # Opening the view is a read after an access rejection, even after cooldown expires.
            result["remaining"] = len(pending)
            return result
        if pending and now < self._retry_after:
            result["error"] = self._last_error or "Las consultas de Mercadona están temporalmente pausadas."
            self._record("cooldown", "Mercadona: consulta omitida durante la pausa de reintento", {
                "warehouse": warehouse, "retry_at": self._retry_after, "wait_seconds": int(self._retry_after - now),
                "http_requests": 0, "last_http_status": self._last_diagnostics.get("http_status")})
            return result
        self._batch_id = uuid4().hex
        self._request_count = 0
        self._deadline = time.monotonic() + 35
        self._run_total = max(self._run_total or 0, self._run_processed + len(pending))
        self._update_progress(running=True, batch_id=self._batch_id, warehouse=warehouse,
                              started_at=self._run_started if self._run_started is not None else now,
                              total=self._run_total, processed=self._run_processed, candidates=self._run_candidates, phase="starting")
        self._record("refresh", "Mercadona: inicio de actualización de precios", {
            "batch_id": self._batch_id, "warehouse": warehouse, "force": force,
            "valid_codes": len(codes), "pending_codes": len(pending), "request_interval_seconds": REQUEST_INTERVAL,
            "provider": PROVIDER})
        for key, product in pending[:20]:
            if time.time() - now >= 35:
                break
            try:
                offer = await self._fetch(product["code"], warehouse, product["name"])
            except LookupPending:
                changed = True
                self._update_progress(phase="continuation")
                break
            except StoreConfigurationChanged:
                raise
            except StoreError as err:
                error = str(err)
                self._failures += 1
                diagnostics = {"endpoint": search_url(warehouse), "method": "POST", "warehouse": warehouse,
                    "ean": product["code"], "batch_id": self._batch_id,
                    **getattr(err, "diagnostics", {"response_class": "invalid_response"})}
                status = diagnostics.get("http_status")
                base = 900 if status == 403 else 300 if status == 429 else 60
                wait = max(min(base * 2 ** min(self._failures - 1, 5), 3600), getattr(err, "retry_seconds", 0))
                self._retry_after = time.time() + wait
                diagnostics.update(retry_seconds=wait, retry_at=self._retry_after, consecutive_failures=self._failures)
                self._last_error, self._last_diagnostics = error, diagnostics
                self._record("error", f"Mercadona: error al consultar precios. {error}", diagnostics,
                             product=product["name"], code=product["code"])
                _LOGGER.warning("Mercadona price lookup failed: %s", json.dumps(diagnostics, ensure_ascii=False))
                changed = True
                break
            current = self.settings.snapshot["stores"]["mercadona"]
            if (not self.hass.data.get(DOMAIN, {}).get("active") or self.settings.entry is not entry
                or self.settings._generation != generation or not current.get("enabled")
                or current.get("warehouse") != warehouse):
                raise StoreError("La configuración de la tienda ha cambiado. Vuelve a abrir el popup.")
            self._cache[f"{warehouse}:{key}"] = {"offer": offer, "checked_at": int(time.time())}
            changed = True
            processed += 1
            self._run_pending.discard(key)
            if self._cycle.get("warehouse") == warehouse and key in self._cycle.get("pending", []):
                self._cycle["pending"].remove(key)
            self._update_progress(processed=self._run_processed + processed, phase="processed")
            self._last_error, self._last_diagnostics = "", {}
            self._retry_after, self._failures = 0, 0
        if changed:
            self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1].get("checked_at", 0), reverse=True)[:2000])
            self._lookups = dict(sorted(self._lookups.items(), key=lambda item: item[1].get("expires", 0), reverse=True)[:2000])
            self._details = dict(sorted(self._details.items(), key=lambda item: item[1].get("checked_at", 0), reverse=True)[:5000])
            await self._persist()
        result = self.snapshot()
        result.update(error=error or self._last_error, remaining=len(pending) - processed,
                      processed=processed, total=len(pending))
        self._record("summary", "Mercadona: actualización detenida por un error" if error else
            "Mercadona: avance guardado; la actualización continúa" if len(pending) > processed else "Mercadona: actualización finalizada", {
            "batch_id": self._batch_id, "warehouse": warehouse, "processed_codes": processed,
            "pending_codes": len(pending) - processed, "http_requests": self._request_count,
            "elapsed_ms": round((time.time() - now) * 1000), "failed": bool(error),
            "retry_at": self._retry_after, "matched_products": len(result["products"])})
        return result

    async def _fetch(self, code, warehouse, name):
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            key = f"{warehouse}:{code.zfill(14)}"
            previous = self._cache.get(key, {}).get("offer")
            if previous and re.fullmatch(r"[0-9]{1,12}", str(previous.get("store_product_id", ""))):
                detail = await self._product(session, previous["store_product_id"], code, warehouse, refresh=True)
                if detail and (offer := exact_offer([detail], code)):
                    self._lookups.pop(key, None)
                    return offer

            # Algolia's public index has names and references but no EAN. Never use its
            # price until the direct product API has confirmed the exact barcode.
            queries = [name]
            readers = self.hass.data.get(DOMAIN, {}).get("readers")
            hint = readers.lookup.cached(code) if readers else None
            if hint and hint.get("product_name"):
                queries.append(hint["product_name"])
            queries = list(dict.fromkeys(queries))
            state = self._lookups.get(key)
            if not state or state.get("queries") != queries or state.get("expires", 0) <= time.time():
                state = {"queries": queries, "query_index": 0, "page": 0, "ids": None, "cursor": 0, "matches": [],
                         "expires": time.time() + TTL}
                self._lookups[key] = state
            while state["query_index"] < len(queries):
                if state["ids"] is None:
                    data, diagnostics = await self._search(session, queries[state["query_index"]], code, warehouse, state["page"])
                    hits = data.get("hits") if isinstance(data, dict) else None
                    pages = data.get("nbPages", 1) if isinstance(data, dict) else None
                    if (not isinstance(hits, list) or len(hits) > 100 or type(pages) is not int
                        or not 0 <= pages <= 1000 or data.get("page", state["page"]) != state["page"]):
                        raise StoreRequestError("La respuesta de búsqueda de Mercadona no es válida.",
                            {**diagnostics, "response_class": "invalid_response"})
                    identifiers = []
                    for hit in hits:
                        identifier = str(hit.get("id", "")) if isinstance(hit, dict) else ""
                        if not re.fullmatch(r"[0-9]{1,12}", identifier):
                            raise StoreRequestError("La referencia de búsqueda de Mercadona no es válida.",
                                {**diagnostics, "response_class": "invalid_reference"})
                        if identifier not in identifiers:
                            identifiers.append(identifier)
                    state.update(ids=identifiers, cursor=0, pages=pages)
                while state["cursor"] < len(state["ids"]):
                    identifier = state["ids"][state["cursor"]]
                    detail = await self._product(session, identifier, code, warehouse)
                    state["cursor"] += 1
                    self._run_candidates += 1
                    self._update_progress(candidates=self._run_candidates)
                    if detail and (offer := exact_offer([detail], code)):
                        state["matches"].append(detail)
                if state["page"] + 1 < state["pages"]:
                    state.update(page=state["page"] + 1, ids=None, cursor=0)
                else:
                    state.update(query_index=state["query_index"] + 1, page=0, ids=None, cursor=0)
            self._lookups.pop(key, None)
            return exact_offer(state["matches"], code)
        finally:
            session.detach()

    async def _product(self, session, identifier, code, warehouse, refresh=False):
        key = f"{warehouse}:{identifier}"
        cached = self._details.get(key)
        if not refresh and cached and time.time() - cached["checked_at"] < TTL:
            return cached["product"]
        url = PRODUCT_URL.format(identifier=quote(identifier, safe=""), warehouse=quote(warehouse, safe=""))
        data, diagnostics = await self._request(session, "GET", url, code, warehouse, "details")
        if data is not None and (not isinstance(data, dict) or str(data.get("id", "")) != identifier):
            raise StoreRequestError("La ficha devuelta por Mercadona no corresponde a la referencia consultada.",
                {**diagnostics, "response_class": "invalid_product"})
        product = {key: data.get(key) for key in ("id", "ean", "display_name", "price_instructions", "published")} if data else None
        self._details[key] = {"product": product, "checked_at": int(time.time())}
        return product

    async def _search(self, session, query, code, warehouse, page=0):
        return await self._request(session, "POST", search_url(warehouse), code, warehouse, "name",
            payload={"query": query, "page": page, "hitsPerPage": 20, "analytics": False, "clickAnalytics": False},
            headers={"X-Algolia-Application-Id": ALGOLIA_APP, "X-Algolia-API-Key": ALGOLIA_SEARCH_KEY})

    async def _request(self, session, method, url, code, warehouse, query_type, payload=None, headers=None):
        diagnostics = {"endpoint": url, "method": method, "warehouse": warehouse,
                       "ean": code, "query_type": query_type, "batch_id": self._batch_id}
        async with self._request_lock:
            delay = max(0, self._next_request - time.monotonic())
            if self._deadline is not None and time.monotonic() + delay >= self._deadline:
                raise LookupPending
            if delay:
                self._update_progress(phase="waiting")
                await sleep(delay)
            self._check_context()
            self._update_progress(phase=query_type)
            started = time.monotonic()
            self._request_count += 1
            diagnostics["request_number"] = self._request_count
            try:
                async with session.request(method, url, json=payload,
                    headers={"Accept": "application/json", **(headers or {})},
                    timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False) as response:
                    diagnostics["http_status"] = response.status
                    for header, key in (("Content-Type", "content_type"), ("Server", "server")):
                        value = response.headers.get(header, "")
                        if value:
                            diagnostics[key] = re.sub(r"[^a-zA-Z0-9_./:+;= -]", "", value)[:100]
                    for header in ("x-request-id", "x-correlation-id", "cf-ray"):
                        value = response.headers.get(header, "")
                        if re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", value):
                            diagnostics[header] = value
                    body = bytearray()
                    limit = 16384 if response.status != 200 else 2 * 1024 * 1024
                    async for chunk in response.content.iter_chunked(8192):
                        body.extend(chunk)
                        if len(body) > limit:
                            if response.status != 200:
                                break
                            raise StoreRequestError("La respuesta de productos de Mercadona es demasiado grande.",
                                {**diagnostics, "response_class": "response_too_large"})
                    diagnostics["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                    self._check_context()
                    if method == "GET" and response.status == 404:
                        return None, diagnostics
                    if response.status != 200:
                        # Classify known block pages without retaining their HTML, IP or other personal data.
                        blocked = b"uso indebido" in body.lower() or b"service is being misused" in body.lower()
                        reference = re.search(rb"\b(?:0|18)\.[a-fA-F0-9]{6,16}\.[0-9]{8,12}\.[a-fA-F0-9]{6,32}\b", body)
                        if reference:
                            diagnostics["block_reference"] = reference.group().decode("ascii")
                        diagnostics["response_class"] = "service_misuse" if blocked else "access_denied" if response.status == 403 else "rate_limited" if response.status == 429 else "server_error" if response.status >= 500 else "unexpected_status"
                        server_wait = retry_seconds(response.headers.get("Retry-After"))
                        if server_wait:
                            diagnostics["server_retry_seconds"] = server_wait
                        raise StoreRequestError(f"Mercadona ha rechazado la consulta de productos (HTTP {response.status}). Se conservan los precios anteriores.", diagnostics, server_wait)
                    try:
                        return json.loads(body), diagnostics
                    except (ValueError, UnicodeError) as err:
                        raise StoreRequestError("La respuesta de Mercadona no contiene datos JSON válidos.",
                            {**diagnostics, "response_class": "invalid_json"}) from err
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                diagnostics.update(response_class="timeout" if isinstance(err, asyncio.TimeoutError) else "network_error",
                                   exception_type=type(err).__name__, elapsed_ms=round((time.monotonic() - started) * 1000))
                raise StoreRequestError("No se han podido consultar los precios de Mercadona. Se conservan los anteriores.", diagnostics) from err
            finally:
                self._next_request = time.monotonic() + REQUEST_INTERVAL
