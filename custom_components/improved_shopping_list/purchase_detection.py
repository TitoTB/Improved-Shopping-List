"""Daily purchase detection from newly completed native to-do entries."""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import logging

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .catalog import normalized_name
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PurchaseDetection:
    def __init__(self, hass, settings, receipts, activity, carrefour):
        self.hass, self.settings, self.receipts = hass, settings, receipts
        self.activity, self.carrefour = activity, carrefour
        self._store = Store(hass, 1, f"{DOMAIN}.purchase_detection", private=True)
        self._days, self._events, self._stops = {}, deque(), []
        self._active, self._dirty, self._task = False, False, None
        self._lock = asyncio.Lock()

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
            async_track_time_interval(self.hass,self._queue,timedelta(minutes=1))]
        self._queue()

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
                return
            days = deepcopy(self._days)
            events = list(self._events)
            for day, when, key, product in events:
                record = days.setdefault(day, {"entries":{},"first_at":when,"created":False,
                    "receipt_id":"detected:"+day})
                if len(record["entries"]) < 2500:
                    record["entries"].setdefault(key,product)
            cutoff = (dt_util.now().date()-timedelta(days=7)).isoformat()
            days = {day:value for day,value in days.items() if day >= cutoff}
            if days != self._days:
                await self._store.async_save({"days":days})
                self._days = days
            for _ in events:
                self._events.popleft()
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
                    await self.receipts.async_save_detected_purchase(record["receipt_id"],record["first_at"],products)
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
