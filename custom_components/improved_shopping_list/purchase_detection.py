"""Daily purchase detection from newly completed native to-do entries."""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import logging
import math

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .catalog import normalized_name
from .catalog import CatalogError
from .const import DOMAIN
from .store_links import STORES

_LOGGER = logging.getLogger(__name__)


class PurchaseDetection:
    def __init__(self, hass, settings, receipts, activity, carrefour):
        self.hass, self.settings, self.receipts = hass, settings, receipts
        self.activity, self.carrefour = activity, carrefour
        self._store = Store(hass, 1, f"{DOMAIN}.purchase_detection", private=True)
        self._days, self._events, self._stops = {}, deque(), []
        self._visits = deque()
        self._active, self._dirty, self._task = False, False, None
        self._lock = asyncio.Lock()
        self._ticket_lock = asyncio.Lock()

    async def async_load(self):
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            self._days = {day:value for day,value in data["days"].items()
                if isinstance(day,str) and isinstance(value,dict) and isinstance(value.get("entries"),dict)}

    @property
    def enabled(self):
        return self.settings.snapshot.get("purchase_detection", {}).get("enabled", False)

    @property
    def pending_for_today(self):
        if not self._active or not self.enabled:
            return False
        record = self._days.get(dt_util.now().date().isoformat(), {})
        receipt = self.receipts.stock.receipts["history"].get(record.get("receipt_id"))
        return bool(receipt and receipt.get("detected_purchase") and receipt.get("needs_details"))

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.settings.subscribe(self._queue), self.receipts.stock.subscribe(self._queue),
            async_track_time_interval(self.hass,self._queue,timedelta(minutes=1)),
            self.hass.bus.async_listen("state_changed", self._presence_changed)]
        self._queue()

    @property
    def zone_config(self):
        return self.settings.snapshot.get("purchase_detection", {})

    @callback
    def _presence_changed(self, event):
        config = self.zone_config
        entity = event.data.get("entity_id", "")
        if entity in config.get("persons", []):
            self._observe_presence(entity, event.data.get("new_state"))
            self._queue()
        elif entity in {zone for zones in config.get("store_zones", {}).values() for zone in zones}:
            self._queue()

    def _observe_presence(self, entity, state):
        config = self.zone_config
        if not self.enabled or not config.get("zone_assignment") or not state or state.state in ("unknown","unavailable"):
            return
        day = dt_util.now().date().isoformat()
        for store, zones in config.get("store_zones", {}).items():
            if not self.settings.snapshot.get("stores", {}).get(store, {}).get("enabled"):
                continue
            for zone_id in zones:
                zone = self.hass.states.get(zone_id)
                if zone and self._inside_zone(state, zone):
                    self._visits.append((day, entity, zone_id))

    @staticmethod
    def _inside_zone(person, zone):
        """Prefer coordinates; zone names also support trackers without GPS attributes."""
        values = (person.attributes.get("latitude"), person.attributes.get("longitude"),
                  zone.attributes.get("latitude"), zone.attributes.get("longitude"), zone.attributes.get("radius"))
        if any(type(value) in (int,float) and not math.isfinite(value) for value in values):
            return False
        if all(type(value) in (int,float) and math.isfinite(value) for value in values):
            lat, lon, target_lat, target_lon, radius = values
            if not (-90 <= lat <= 90 and -90 <= target_lat <= 90 and -180 <= lon <= 180 and -180 <= target_lon <= 180 and radius >= 0):
                return False
            delta_lat, delta_lon = math.radians(target_lat-lat), math.radians(target_lon-lon)
            a = math.sin(delta_lat/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(target_lat))*math.sin(delta_lon/2)**2
            return 6371000 * 2 * math.asin(min(1, math.sqrt(max(0,a)))) <= radius
        expected = "home" if zone.entity_id == "zone.home" else zone.attributes.get("friendly_name", zone.entity_id.split(".",1)[-1])
        return person.state.casefold() == str(expected).casefold()

    def zone_stores(self, day=None):
        if not self.enabled or not self.zone_config.get("zone_assignment"):
            return []
        day = day or dt_util.now().date().isoformat()
        visits = self._days.get(day, {}).get("visits", {})
        persons = set(self.zone_config.get("persons", []))
        return sorted(store for store,zones in self.zone_config.get("store_zones", {}).items()
            if store in STORES and self.settings.snapshot.get("stores",{}).get(store,{}).get("enabled") and
            any(persons.intersection(visits.get(zone,[])) for zone in zones))

    def ticket_search_order(self, stores):
        visited = self.zone_stores()
        favorite = self.settings.snapshot.get("favorite_store", "")
        return sorted(stores, key=lambda store:(store not in visited, store != favorite, store))

    def _today_identified(self):
        identifier = self._days.get(dt_util.now().date().isoformat(), {}).get("receipt_id")
        if not identifier:
            return False
        history = self.receipts.stock.receipts["history"]
        return any(receipt.get("detection_id") == identifier for receipt in history.values()) or bool(
            history.get(identifier) and not history[identifier].get("needs_details", True))

    async def async_search_ticket_sources(self, sources):
        """Order available account connectors and stop after a confirmed purchase match."""
        async with self._ticket_lock:
            for store in self.ticket_search_order(sources):
                await self.receipts.async_reconcile_detected_purchases()
                if self._today_identified():
                    break
                try:
                    await sources[store]()
                except (CatalogError, OSError, TimeoutError) as err:
                    self.activity.record("stores.account", STORES.get(store,store)+": no se pudo recuperar el ticket automáticamente",
                        source="automatic", diagnostics={"store":store, **getattr(err,"diagnostics",{})})
                    continue
                await self.receipts.async_reconcile_detected_purchases()
                if self._today_identified():
                    break

    @callback
    def note_completion(self, entity_id, item, quantity=None):
        if not self._active or not self.enabled or entity_id not in self.settings.snapshot["entities"] or not item.get("uid"):
            return
        when = dt_util.now()
        product = next((p for p in self.receipts.stock.catalog.products if normalized_name(p["name"]) == normalized_name(item.get("summary", ""))), None)
        self._events.append((when.date().isoformat(), when.isoformat(),
            sha256((entity_id+":"+str(item["uid"])).encode()).hexdigest(),
            {"name":item.get("summary", "")[:255], "product_id":product["id"] if product else "",
             "list_entity":entity_id, "quantity":quantity.get("quantity",1) if quantity else 1,
             "unit":quantity.get("unit","uds") if quantity else "uds"}))
        self._queue()

    @callback
    def _queue(self, *_args):
        if not self._active:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_background_task(self._drain(), "Shopping purchase detection")

    async def _drain(self):
        try:
            while self._active and self._dirty:
                self._dirty = False
                await self.async_check()
        except Exception:
            _LOGGER.exception("Could not save automatic purchase detection")
            self.activity.record("purchase.detection.error", "No se pudo guardar la compra detectada; se reintentará", source="automatic")

    async def async_check(self):
        async with self._lock:
            if not self._active:
                return
            if not self.enabled:
                self._events.clear()
                self._visits.clear()
                return
            for entity in self.zone_config.get("persons", []):
                self._observe_presence(entity, self.hass.states.get(entity))
            days = deepcopy(self._days)
            visits = list(self._visits)
            for day, entity, zone in visits:
                record = days.setdefault(day, {"entries":{},"first_at":dt_util.now().isoformat(),
                    "created":False,"receipt_id":"detected:"+day})
                observed = record.setdefault("visits", {}).setdefault(zone, [])
                if entity not in observed:
                    observed.append(entity)
            events = list(self._events)
            for day, when, key, product in events:
                record = days.setdefault(day, {"entries":{},"first_at":when,"created":False,
                    "receipt_id":"detected:"+day})
                if len(record["entries"]) < 2500:
                    if not record["entries"]:
                        record["first_at"] = when
                    record["entries"].setdefault(key,product)
            cutoff = (dt_util.now().date()-timedelta(days=6)).isoformat()
            days = {day:value for day,value in days.items() if day >= cutoff}
            if days != self._days:
                await self._store.async_save({"days":days})
                self._days = days
            for _ in events:
                self._events.popleft()
            for _ in visits:
                self._visits.popleft()
            today = dt_util.now().date().isoformat()
            request_ticket = False
            event_days = {event[0] for event in events}
            for day, record in self._days.items():
                if day != today and day not in event_days and not record.get("created"):
                    continue
                products = list(record["entries"].values())
                if len(products) <= self.settings.snapshot.get("purchase_detection",{}).get("threshold",5):
                    continue
                existing = self.receipts.stock.receipts["history"].get(record["receipt_id"])
                if not record.get("created") or existing and existing.get("detected_purchase"):
                    await self.receipts.async_save_detected_purchase(record["receipt_id"],record["first_at"],products,
                        zone_stores=self.zone_stores(day))
                if not record.get("created"):
                    saved = deepcopy(self._days)
                    saved[day]["created"] = True
                    await self._store.async_save({"days":saved})
                    self._days = saved
                    self.activity.record("purchase.detected", "Compra detectada automáticamente: "+str(len(products))+" productos completados", source="automatic")
                    request_ticket = request_ticket or day == today
            await self.receipts.async_reconcile_detected_purchases()
            if request_ticket and self.pending_for_today:
                # Respect Carrefour's explicit automatic-ticket opt-in and daily limit.
                self.carrefour.note_completion()

    async def async_stop(self):
        # Flush already observed completions before removing subscriptions.
        if self._active:
            try:
                await self.async_check()
            except OSError:
                _LOGGER.exception("Could not flush purchase detection before stopping")
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
