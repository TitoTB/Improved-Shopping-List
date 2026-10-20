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

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .product_lookup import is_product_barcode
from .stores import StoreError

SEARCH_URL = "https://tornillos.mercadona.es/search"
TTL = 6 * 3600
# Match the five-second Delay in the original Mercadona n8n workflow.
REQUEST_INTERVAL = 5.0
_LOGGER = logging.getLogger(__name__)


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
            self.progress["estimated_seconds"] = round(max(0, min(35 - elapsed, remaining * (2 * REQUEST_INTERVAL + 1))))
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

    async def _persist(self):
        await self._store.async_save({"offers": self._cache, "retry_after": self._retry_after,
            "last_error": self._last_error, "last_diagnostics": self._last_diagnostics, "failures": self._failures})

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
                "retry_at": self._retry_after if store.get("enabled") else 0, "processed": 0, "total": len(self._codes())}

    async def async_refresh(self, force=False):
        async with self._lock:
            try:
                return await self._async_refresh(force)
            finally:
                if self.progress.get("running"):
                    self._update_progress(running=False, estimated_seconds=0)

    async def _async_refresh(self, force=False):
        result = self.snapshot()
        warehouse = result["warehouse"]
        entry = self.settings.entry
        generation = self.settings._generation
        if not result["enabled"] or not warehouse:
            return result
        now = time.time()
        codes = self._codes()
        pending = [(key, product) for key, product in codes.items()
                   if force or now - self._cache.get(f"{warehouse}:{key}", {}).get("checked_at", 0) >= TTL]
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
        self._update_progress(running=True, batch_id=self._batch_id, warehouse=warehouse,
                              started_at=now, total=len(pending), processed=0, phase="starting")
        self._record("refresh", "Mercadona: inicio de actualización de precios", {
            "batch_id": self._batch_id, "warehouse": warehouse, "force": force,
            "valid_codes": len(codes), "pending_codes": len(pending), "request_interval_seconds": REQUEST_INTERVAL})
        for key, product in pending[:20]:
            if time.time() - now >= 35:
                break
            try:
                offer = await self._fetch(product["code"], warehouse, product["name"])
            except StoreError as err:
                error = str(err)
                self._failures += 1
                diagnostics = {"endpoint": SEARCH_URL, "method": "POST", "warehouse": warehouse,
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
            self._update_progress(processed=processed, phase="processed")
            self._last_error, self._last_diagnostics = "", {}
            self._retry_after, self._failures = 0, 0
        if changed:
            self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1].get("checked_at", 0), reverse=True)[:2000])
            await self._persist()
        result = self.snapshot()
        result.update(error=error or self._last_error, remaining=len(pending) - processed,
                      processed=processed, total=len(pending))
        self._record("summary", "Mercadona: actualización detenida por un error" if error else "Mercadona: actualización finalizada", {
            "batch_id": self._batch_id, "warehouse": warehouse, "processed_codes": processed,
            "pending_codes": len(pending) - processed, "http_requests": self._request_count,
            "elapsed_ms": round((time.time() - now) * 1000), "failed": bool(error),
            "retry_at": self._retry_after, "matched_products": len(result["products"])})
        return result

    async def _fetch(self, code, warehouse, name):
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            for query in dict.fromkeys((code, name)):
                data, diagnostics = await self._search(session, query, code, warehouse, "ean" if query == code else "name")
                try:
                    offer = exact_offer(data.get("hits") if isinstance(data, dict) else None, code)
                except StoreError as err:
                    raise StoreRequestError(str(err), {**diagnostics, "response_class": "invalid_response"}) from err
                if offer is not None:
                    return offer
            return None
        finally:
            session.detach()

    async def _search(self, session, query, code, warehouse, query_type):
        diagnostics = {"endpoint": SEARCH_URL, "method": "POST", "warehouse": warehouse,
                       "ean": code, "query_type": query_type, "batch_id": self._batch_id}
        async with self._request_lock:
            delay = max(0, self._next_request - time.monotonic())
            if delay:
                self._update_progress(phase="waiting")
                await sleep(delay)
            self._update_progress(phase=query_type)
            started = time.monotonic()
            self._request_count += 1
            diagnostics["request_number"] = self._request_count
            try:
                async with session.post(SEARCH_URL, json={"query": query, "wh": warehouse, "lang": "es"},
                    headers={"Accept": "application/json", "Origin": "https://tienda.mercadona.es", "Referer": "https://tienda.mercadona.es/"},
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
