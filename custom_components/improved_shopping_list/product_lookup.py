"""Optional product hints from Open Food Facts; never associate a scan automatically."""

from asyncio import Lock, sleep
from copy import deepcopy
import json
import logging
import time

from aiohttp import ClientError, ClientTimeout
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://world.openfoodfacts.org"
FIELDS = "code,generic_name_es,generic_name,product_name_es,product_name,brands,quantity"
TTLS = {"found": 30 * 86400, "not_found": 86400, "error": 300}


def is_product_barcode(code):
    """Only send GTIN-shaped identifiers with a valid check digit, never QR/NFC data."""
    if not isinstance(code, str) or len(code) not in (8, 12, 13, 14) or not code.isascii() or not code.isdigit():
        return False
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(code[:-1])))
    return (10 - total % 10) % 10 == int(code[-1])


def product_hint(data, code):
    if not isinstance(data, dict) or not isinstance(data.get("product"), dict):
        raise ValueError("Invalid product response")
    product = data["product"]
    if str(product.get("code", "")).zfill(14) != code.zfill(14):
        raise ValueError("Product barcode mismatch")

    def field(key, limit):
        value = product.get(key)
        return " ".join(value.split())[:limit] if isinstance(value, str) else ""

    name = next((value for key in ("generic_name_es", "generic_name", "product_name_es", "product_name") if (value := field(key, 160))), "")
    if not name:
        return {"status": "not_found"}
    return {"status": "found", "name": name, "product_name": field("product_name_es", 160) or field("product_name", 160),
            "brand": field("brands", 100), "quantity": field("quantity", 100), "source": "Open Food Facts",
            "url": f"{BASE_URL}/product/{code}", "license": "ODbL"}


class ProductLookup:
    def __init__(self, hass):
        self.hass = hass
        self._store = Store(hass, 1, f"{DOMAIN}.product_lookup")
        self._cache = {}
        self._lock = Lock()
        self._next_request = 0.0

    async def async_load(self):
        try:
            data = await self._store.async_load()
            if isinstance(data, dict):
                self._cache = {key: item for key, item in data.items() if isinstance(item, dict)
                               and isinstance(item.get("expires"), (int, float)) and isinstance(item.get("result"), dict)
                               and item["result"].get("status") in TTLS}
        except (OSError, ValueError, HomeAssistantError):
            _LOGGER.warning("Could not load the optional product lookup cache")

    def cached(self, code):
        entry = self._cache.get(code.zfill(14))
        return deepcopy(entry["result"]) if entry else None

    def is_fresh(self, code):
        entry = self._cache.get(code.zfill(14))
        return bool(entry and entry["expires"] > time.time())

    async def async_lookup(self, code):
        if not is_product_barcode(code):
            return {"status": "unsupported"}
        # Serialise requests, deduplicate UPC/EAN aliases and stay below 15 reads/minute.
        async with self._lock:
            if self.is_fresh(code):
                return self.cached(code)
            delay = self._next_request - time.monotonic()
            if delay > 0:
                await sleep(delay)
            self._next_request = time.monotonic() + 4.1
            try:
                result = await self._fetch(code)
            except (ClientError, TimeoutError, ValueError, TypeError):
                result = {"status": "error"}
            self._cache[code.zfill(14)] = {"expires": time.time() + TTLS[result["status"]], "result": result}
            self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1]["expires"])[-500:])
            try:
                await self._store.async_save(self._cache)
            except (OSError, HomeAssistantError):
                _LOGGER.warning("Could not persist the optional product lookup cache")
            return deepcopy(result)

    async def _fetch(self, code):
        session = async_get_clientsession(self.hass)
        async with session.get(f"{BASE_URL}/api/v3/product/{code}", params={"fields": FIELDS, "lc": "es"},
                               headers={"User-Agent": f"ImprovedShoppingList/{VERSION} (https://github.com/TitoTB/Improved-Shopping-List)"},
                               timeout=ClientTimeout(total=10), allow_redirects=False) as response:
            if response.status == 404:
                return {"status": "not_found"}
            if response.status == 429:
                self._next_request = time.monotonic() + 60
            response.raise_for_status()
            if response.status != 200:
                raise ValueError("Unexpected response")
            body = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                body.extend(chunk)
                if len(body) > 65536:
                    raise ValueError("Product response too large")
            return product_hint(json.loads(body), code)
