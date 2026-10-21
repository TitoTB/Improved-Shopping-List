"""Durable recurring purchases, independent of open frontend sessions."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import logging
import time

from homeassistant.core import Context, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .catalog import normalized_name
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
DAY = 86400


class RecurrenceManager:
    def __init__(self, hass, catalog, settings, activity, operation_lock, stock=None):
        self.hass, self.catalog, self.settings, self.activity = hass, catalog, settings, activity
        self._operation_lock = operation_lock
        self._store = Store(hass, 1, f"{DOMAIN}.recurrence")
        self._schedules = {}
        self._retry_after = {}
        self._active = False
        self._unsubscribers = []
        self._task = None
        self._lock = asyncio.Lock()
        self._needs_save = False
        self.stock = stock
        if stock is not None:
            stock.recurrence_coordinated = True

    async def async_load(self):
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("schedules"), dict):
                raise ValueError("No se ha podido leer la programación de recurrencias.")
            self._schedules = data["schedules"]

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._unsubscribers = [self.catalog.subscribe(self._queue), self.settings.subscribe(self._queue),
                               async_track_time_interval(self.hass, self._queue, timedelta(minutes=1))]
        if self.stock is not None:
            self._unsubscribers.append(self.stock.subscribe(self._queue))
        self._queue()

    @callback
    def _queue(self, *_args):
        if not self._active:
            return
        self._dirty = True
        if not self._task or self._task.done():
            self._task = self.hass.async_create_task(self._drain())

    async def _drain(self):
        try:
            while self._active and self._dirty:
                self._dirty = False
                await self.async_check()
        except Exception:
            _LOGGER.exception("Could not check recurring shopping products")

    async def async_stop(self):
        self._active = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        if self._needs_save:
            await self._checkpoint()

    async def _checkpoint(self):
        try:
            await self._store.async_save({"schedules": deepcopy(self._schedules)})
        except OSError:
            self._needs_save = True
            _LOGGER.exception("Could not persist recurring purchases")
            return False
        self._needs_save = False
        return True

    async def async_check(self):
        async with self._lock:
            if not self._active:
                return
            if self.stock is not None:
                await self._sync_stock()
                return  # Pantry expiration is the single scheduler for linked recurrence.
            products = {product["id"]: product for product in self.catalog.products
                        if product.get("recurrence", {}).get("enabled")}
            self._retry_after = {key: value for key, value in self._retry_after.items() if key in products}
            updated = {key: value for key, value in self._schedules.items() if key in products}
            for key, product in products.items():
                config = product["recurrence"]
                anchor = product.get("recurrence_started_at") or product.get("updated_at")
                current = updated.get(key, {})
                if current.get("anchor") != anchor or current.get("days") != config["days"]:
                    updated[key] = {"anchor": anchor, "days": config["days"],
                                    "next_due": datetime.fromisoformat(anchor).timestamp() + config["days"] * DAY}
                    self._retry_after.pop(key, None)
            if updated != self._schedules:
                self._schedules = updated
                self._needs_save = True
            if self._needs_save and not await self._checkpoint():
                return
            for key, schedule in list(self._schedules.items()):
                if not self._active:
                    return
                if time.time() < max(schedule["next_due"], self._retry_after.get(key, 0)):
                    continue
                product = products[key]
                try:
                    async with self._operation_lock:
                        async with asyncio.timeout(30):
                            result, target = await self._add_or_restore(product)
                except Exception as err:
                    self._retry_after[key] = time.time() + 300
                    _LOGGER.warning("Could not apply recurrence for %s: %s", product["name"], err)
                    self.activity.record("recurrence.error", f"No se pudo aplicar la recurrencia: {product['name']}",
                                         source="automatic", product=product["name"], error=str(err))
                    continue
                # Reset from completion, including when the product was already pending.
                schedule["next_due"] = time.time() + schedule["days"] * DAY
                self._needs_save = True
                self._retry_after.pop(key, None)
                await self._checkpoint()
                message = "Periodo reiniciado; ya estaba en la lista" if result == "pending" else "Recuperado por recurrencia" if result == "restored" else "Añadido por recurrencia"
                self.activity.record(f"recurrence.{result}", f"{message}: {product['name']}", source="automatic",
                                     product=product["name"], list_entity=target)

    async def async_sync_stock(self):
        """Reconcile durable user edits before returning an editor's new revision."""
        if self.stock is not None:
            async with self._lock:
                await self._sync_stock()

    async def _sync_stock(self):
        for product in self.catalog.products:
            item = self.stock.item_for(product)
            recurrence = product.get("recurrence", {"enabled":False,"days":7})
            anchor = product.get("recurrence_started_at")
            started = datetime.fromisoformat(anchor).timestamp() if anchor else 0
            product_stamp = product.get("recurrence_updated_at") or started
            stock_stamp = self.stock.recurrence_stamp(item)
            if stock_stamp > product_stamp:
                recurrence = {"enabled":item["mode"] == "perishable", "days":item["days"]}
                started = (item.get("expires_at",0)-item["days"]*DAY) if item.get("expires_at") else time.time()
                product = await self.catalog.async_sync_recurrence(product["id"],product["revision"],recurrence,stock_stamp,started)
                product_stamp = stock_stamp
                due = item.get("expires_at",0)
            else:
                if product_stamp and product.get("recurrence_updated_at") != product_stamp:
                    product = await self.catalog.async_sync_recurrence(product["id"],product["revision"],recurrence,product_stamp,started)
                due = started+recurrence["days"]*DAY if recurrence["enabled"] else 0
                previous = self._schedules.get(product["id"],{})
                if ((not item or item.get("mode") != "perishable") and previous.get("anchor") == anchor and previous.get("days") == recurrence["days"]
                    and isinstance(previous.get("next_due"),(int,float))):
                    due = previous["next_due"]
            await self.stock.async_sync_recurrence(product,product_stamp,due)

    def _validate(self, product, target):
        current = next((item for item in self.catalog.products if item["id"] == product["id"]), None)
        settings = self.settings.snapshot
        if (not self._active or not current or current["name"] != product["name"]
            or current.get("recurrence") != product.get("recurrence")
            or current.get("recurrence_started_at") != product.get("recurrence_started_at")
            or settings["primary_entity"] != target or target not in settings["entities"]):
            raise ValueError("El producto, su recurrencia o la lista principal han cambiado.")
        state = self.hass.states.get(target)
        if state is None or state.state in ("unknown", "unavailable"):
            raise ValueError("La lista principal no está disponible.")
        return state

    async def _add_or_restore(self, product):
        target = self.settings.snapshot["primary_entity"]
        self._validate(product, target)
        response = await self.hass.services.async_call("todo", "get_items", {"entity_id": target}, blocking=True, return_response=True)
        state = self._validate(product, target)
        items = response.get(target, {}).get("items") if isinstance(response, dict) else None
        if not isinstance(items, list):
            raise ValueError("No se ha podido comprobar el contenido de la lista principal.")
        matches = [item for item in items if normalized_name(item.get("summary", "")) == normalized_name(product["name"])]
        if any(item.get("status") != "completed" for item in matches):
            return "pending", target
        completed = next((item for item in matches if item.get("uid") and item.get("status") == "completed"), None)
        if matches and not completed:
            raise ValueError("La lista no devuelve un identificador para recuperar el producto comprado.")
        features = int(state.attributes.get("supported_features", 0))
        context = Context(parent_id=Context().id)
        if completed:
            if not features & 4:
                raise ValueError("La lista no permite recuperar el producto comprado sin duplicarlo.")
            await self.hass.services.async_call("todo", "update_item", {"entity_id": target, "item": completed["uid"], "status": "needs_action"}, blocking=True, context=context)
            return "restored", target
        if not features & 1:
            raise ValueError("La lista principal no permite añadir productos.")
        await self.hass.services.async_call("todo", "add_item", {"entity_id": target, "item": product["name"]}, blocking=True, context=context)
        return "added", target
