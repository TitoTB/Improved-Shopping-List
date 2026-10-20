"""Warehouse-scoped Mercadona offers, matched only by exact GTIN."""

import asyncio
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import time

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .product_lookup import is_product_barcode
from .stores import StoreError

SEARCH_URL = "https://tornillos.mercadona.es/search"
TTL = 6 * 3600


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

    async def async_load(self):
        data = await self._store.async_load()
        self._cache = data.get("offers", {}) if isinstance(data, dict) else {}

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
                "enabled": store.get("enabled", False), "warehouse": warehouse, "error": "", "remaining": 0}

    async def async_refresh(self, force=False):
        async with self._lock:
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
            if pending and now < self._retry_after:
                result["error"] = "Mercadona no está disponible. Espera un minuto antes de volver a intentarlo."
                return result
            for key, product in pending[:20]:
                if time.time() - now >= 35:
                    break
                try:
                    offer = await self._fetch(product["code"], warehouse, product["name"])
                except StoreError as err:
                    error = str(err)
                    self._retry_after = time.time() + 60
                    break
                current = self.settings.snapshot["stores"]["mercadona"]
                if (not self.hass.data.get(DOMAIN, {}).get("active") or self.settings.entry is not entry
                    or self.settings._generation != generation or not current.get("enabled")
                    or current.get("warehouse") != warehouse):
                    raise StoreError("La configuración de la tienda ha cambiado. Vuelve a abrir el popup.")
                self._cache[f"{warehouse}:{key}"] = {"offer": offer, "checked_at": int(time.time())}
                changed = True
                processed += 1
                if processed < min(len(pending), 20):
                    await asyncio.sleep(.3)
            if changed:
                self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1].get("checked_at", 0), reverse=True)[:2000])
                await self._store.async_save({"offers": self._cache})
            result = self.snapshot()
            result.update(error=error, remaining=len(pending) - processed)
            return result

    async def _fetch(self, code, warehouse, name):
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            # Search by code first, then by catalog name; both require an exact EAN in the result.
            for query in dict.fromkeys((code, name)):
                async with session.post(SEARCH_URL, json={"query": query, "wh": warehouse, "lang": "es"},
                    headers={"Accept": "application/json", "Origin": "https://tienda.mercadona.es", "Referer": "https://tienda.mercadona.es/"},
                    timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False) as response:
                    if response.status != 200:
                        raise StoreError(f"Mercadona ha rechazado la consulta de productos (HTTP {response.status}). Se conservan los precios anteriores.")
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            raise StoreError("La respuesta de productos de Mercadona es demasiado grande.")
                    data = json.loads(body)
                    offer = exact_offer(data.get("hits") if isinstance(data, dict) else None, code)
                    if offer is not None:
                        return offer
            return None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            if isinstance(err, StoreError):
                raise
            raise StoreError("No se han podido consultar los precios de Mercadona. Se conservan los anteriores.") from err
        finally:
            session.detach()
