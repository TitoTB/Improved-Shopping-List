"""Private, bounded web-price observations and comparison data from reviewed receipts."""
from asyncio import Lock
from copy import deepcopy
import math
import time

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .store_links import STORES
from .product_references import format_observation

MAX_OBSERVATIONS = 12000
RETENTION = 730 * 86400


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 1000000 else None
    except (ValueError, TypeError):
        return None


def stamp(value):
    if not isinstance(value, str):
        return None
    date = dt_util.parse_datetime(value)
    return dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE) if date and date.tzinfo is None else date).timestamp() if date else None


class PriceHistory:
    def __init__(self, hass):
        self._store = Store(hass, 1, f"{DOMAIN}.price_history")
        self._entries = []
        self._lock = Lock()

    async def async_load(self):
        data = await self._store.async_load()
        data = data if isinstance(data, dict) else {}
        self._entries = [entry for entry in data.get("entries", []) if isinstance(entry, dict) and finite(entry.get("price")) is not None and isinstance(entry.get("at"), (int, float)) and math.isfinite(entry["at"]) and entry["at"] > 0][-MAX_OBSERVATIONS:]

    async def async_record(self, offer):
        """Record actual observation times; never fabricate earlier price dates."""
        if offer.get("store") not in STORES or not isinstance(offer.get("currency"), str) or len(offer["currency"]) != 3:
            return
        at = offer.get("checked_at")
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at) or at <= 0 or finite(offer.get("price")) is None:
            return
        entry = {key:deepcopy(offer.get(key)) for key in ("store", "reference_id", "ean", "price", "currency", "reference_price", "reference_unit", "store_name", "name")}
        entry["at"] = at
        async with self._lock:
            if any(existing == entry for existing in self._entries):
                return
            entries = sorted([existing for existing in self._entries if existing.get("at", 0) >= time.time()-RETENTION] + [entry], key=lambda item:item["at"])[-MAX_OBSERVATIONS:]
            await self._store.async_save({"entries":entries})
            self._entries = entries

    def comparison_data(self, catalog, settings, receipts, current_offers):
        products = catalog.products
        product_ids = {product["id"] for product in products}
        product_map = {product["id"]:product for product in products}
        enabled = [store for store in STORES if settings.snapshot.get("stores", {}).get(store, {}).get("enabled")]
        observations, purchases = [], []
        for receipt in receipts.stock.receipts["history"].values():
            if receipt.get("summary_only") or receipt.get("pending_review"):
                continue
            at = stamp(receipt.get("purchased_at"))
            if not at:
                continue
            lines = []
            for line in receipt.get("lines", []):
                product_id = line.get("product_id", "")
                safe = {key:deepcopy(line.get(key)) for key in ("id", "description", "count", "amount", "unit_price", "ean", "pack_quantity", "pack_unit")}
                safe["product_id"] = product_id if product_id in product_ids else ""
                if safe["product_id"]:
                    safe=format_observation(product_map[product_id],receipt.get("store",""),{**safe,"reference_id":line.get("reference_id","")})
                    if safe.get("reference_excluded"):
                        safe["product_id"]=""
                lines.append(safe)
                if line.get("price_saved") and safe["product_id"] and receipt.get("store") in enabled:
                    observations.append({**safe, "store":receipt["store"], "price":line.get("unit_price"), "currency":receipt.get("currency", "EUR"), "at":at, "source":"receipt"})
            purchases.append({"id":receipt["id"], "store":receipt.get("store", ""), "store_name":receipt.get("store_name", ""), "purchased_at":receipt["purchased_at"], "at":at,
                "total":receipt.get("total"), "shipping":receipt.get("shipping", 0), "discount":receipt.get("discount", 0), "currency":receipt.get("currency", "EUR"), "lines":lines})
        by_reference = {(store, link.get("id")):product["id"] for product in products for store, link in product.get("store_links", {}).items() if isinstance(link, dict) and link.get("id")}
        by_reference.update({(ref["store"],ref["reference_id"]):product["id"] for product in products for ref in product.get("commercial_references",[]) if ref.get("store") and ref.get("reference_id")})
        for entry in self._entries:
            product_id = by_reference.get((entry.get("store"), entry.get("reference_id")))
            if product_id and entry.get("store") in enabled:
                observations.append({**format_observation(product_map[product_id],entry.get("store",""),entry), "product_id":product_id, "source":"web"})
        for offer in current_offers:
            product_id = offer.get("catalog_product_id")
            at = offer.get("checked_at")
            if product_id in product_ids and offer.get("store") in enabled and offer.get("source") != "receipt" and isinstance(at, (int, float)):
                observations.append({**format_observation(product_map[product_id],offer["store"],{key:deepcopy(offer.get(key)) for key in ("store", "price", "currency", "reference_price", "reference_unit", "ean", "name", "reference_id")}), "product_id":product_id, "at":at, "source":"web"})
        observations = [entry for entry in observations if finite(entry.get("price")) is not None and isinstance(entry.get("at"), (int, float)) and math.isfinite(entry["at"]) and entry["at"] > 0]
        return {"observations":sorted(observations, key=lambda item:item["at"], reverse=True)[:20000], "observations_truncated":len(observations)>20000, "purchases":sorted(purchases, key=lambda item:item["at"], reverse=True), "stores":enabled, "generated_at":time.time(), "historical_window_days":30}
