"""Threshold notifications from native todo pushes and local pantry state."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import logging
import re

from homeassistant.components.todo import DATA_COMPONENT, serialize_todo_item
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .stock import stock_needs_reorder
from .notification_settings import RESERVED_SERVICES

_LOGGER = logging.getLogger(__name__)


def signature(rule):
    return json.dumps([rule["enabled"], rule["threshold"], sorted(rule["targets"])], ensure_ascii=True)


def render_message(text, values):
    # Plain placeholders deliberately avoid evaluating user-provided templates/code.
    return re.sub(r"\{(lista|cantidad|limite|productos)\}", lambda match: str(values[match[1]]), text)[:4000]


class NotificationManager:
    def __init__(self, hass, settings, stock, activity):
        self.hass, self.settings, self.stock, self.activity = hass, settings, stock, activity
        self._store = Store(hass, 1, f"{DOMAIN}.notifications")
        self._above, self._lists, self._items, self._stops = {}, {}, {}, []
        self._active, self._dirty, self._task = False, False, None

    async def async_load(self):
        saved = await self._store.async_load()
        if saved is not None:
            above = saved.get("above") if isinstance(saved, dict) else None
            if not isinstance(above, dict) or any(not isinstance(key, str) or not isinstance(value, dict)
                or type(value.get("above")) is not bool or not isinstance(value.get("signature"), str) for key, value in above.items()):
                raise ValueError("No se ha podido leer el estado de las notificaciones.")
            self._above = above

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.settings.subscribe(self._changed), self.stock.subscribe(self._queue),
                       self.hass.bus.async_listen("state_changed", self._state_changed),
                       async_track_time_interval(self.hass, self._queue, timedelta(minutes=1))]
        self._changed()

    @callback
    def _state_changed(self, event):
        if event.data.get("entity_id") in self.settings.snapshot["entities"]:
            self._changed()

    @callback
    def _changed(self, *_args):
        if not self._active:
            return
        config = self.settings.snapshot
        component = self.hass.data.get(DATA_COMPONENT)
        wanted = set(config["entities"]) if config["notifications"]["shopping_list"]["enabled"] else set()
        for entity_id in tuple(self._lists):
            entity = component.get_entity(entity_id) if component else None
            if entity_id not in wanted or entity is not self._lists[entity_id][0]:
                self._lists.pop(entity_id)[1]()
                self._items.pop(entity_id, None)
        if component:
            for entity_id in wanted - self._lists.keys():
                if (entity := component.get_entity(entity_id)) is not None:
                    self._items[entity_id] = [serialize_todo_item(item) for item in entity.todo_items] if entity.todo_items is not None else None
                    stop = entity.async_subscribe_updates(lambda items, key=entity_id: self._items_changed(key, items))
                    self._lists[entity_id] = (entity, stop)
        self._queue()

    @callback
    def _items_changed(self, entity_id, items):
        if self._active:
            self._items[entity_id] = [serialize_todo_item(item) for item in items] if items is not None else None
            self._queue()

    @callback
    def _queue(self, *_args):
        if not self._active:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_background_task(self._run(), "Shopping list notifications")

    def _observations(self, settings):
        result = []
        for entity_id in settings["entities"]:
            state, items = self.hass.states.get(entity_id), self._items.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable") or items is None:
                result.append(("shopping_list:"+entity_id, "shopping_list", entity_id, None))
            else:
                result.append(("shopping_list:"+entity_id, "shopping_list", entity_id,
                               [item.get("summary", "") for item in items if item.get("status") == "needs_action"]))
        result.append(("low_stock", "low_stock", "", [item["name"] for item in self.stock.snapshot["items"] if stock_needs_reorder(item)]))
        return result

    def _eligible(self, event):
        if not self._active:
            return False
        settings = self.settings.snapshot
        rule = settings["notifications"][event["kind"]]
        if signature(rule) != event["signature"]:
            return False
        observation = next((row for row in self._observations(settings) if row[0] == event["key"]), None)
        return observation is not None and observation[3] is not None and len(observation[3]) > rule["threshold"]

    async def _run(self):
        try:
            while self._active and self._dirty:
                self._dirty = False
                settings = self.settings.snapshot
                updated, events = {}, []
                for key, kind, entity_id, products in self._observations(settings):
                    rule = settings["notifications"][kind]
                    if not rule["enabled"] or not rule["targets"]:
                        continue
                    stamp = signature(rule)
                    previous = self._above.get(key, {})
                    if products is None:
                        if previous.get("signature") == stamp:
                            updated[key] = previous
                        continue  # Unavailability must not rearm a previously sent alert.
                    above = len(products) > rule["threshold"]
                    updated[key] = {"above": above, "signature": stamp}
                    if above and (previous.get("signature") != stamp or not previous.get("above")):
                        state = self.hass.states.get(entity_id) if entity_id else None
                        values = {"lista":state.attributes.get("friendly_name",entity_id) if state else "Stock",
                                  "cantidad":len(products), "limite":rule["threshold"], "productos":", ".join(products)[:3000]}
                        events.append({"key":key,"kind":kind,"signature":stamp,"entity_id":entity_id,
                                       "rule":deepcopy(rule),"values":values})
                if updated != self._above:
                    await self._store.async_save({"above": updated})
                    self._above = updated
                for event in events:
                    if self._eligible(event):
                        await self._send(event)
        except (OSError, HomeAssistantError) as err:
            self.activity.record("notification.error", "No se han podido guardar los avisos. No se enviaron las notificaciones pendientes.",
                                 source="automatic", diagnostics={"error":str(err)})
            _LOGGER.warning("Could not persist shopping list notification state: %s", err)
        finally:
            self._task = None
            if self._active and self._dirty:
                self._queue()

    async def _send(self, event):
        sent, failed = [], []
        rule = event["rule"]
        for target in rule["targets"]:
            if not self._eligible(event):
                break
            data = {"message":render_message(rule["message"], event["values"])}
            if rule["title"]:
                data["title"] = render_message(rule["title"], event["values"])[:160]
            try:
                kind, identifier = target.split(":", 1)
                if kind == "entity":
                    state = self.hass.states.get(identifier)
                    if state is None or state.state == "unavailable":
                        raise HomeAssistantError("El destino no está disponible.")
                    await self.hass.services.async_call("notify", "send_message", {**data, "entity_id":identifier}, blocking=True)
                else:
                    service = identifier.split(".", 1)[1]
                    if service in RESERVED_SERVICES:
                        raise HomeAssistantError("El destino no identifica un dispositivo concreto.")
                    await self.hass.services.async_call("notify", service, data, blocking=True)
                sent.append(target)
            except (HomeAssistantError, OSError, TimeoutError) as err:
                failed.append({"target":target,"error":str(err)})
        if sent or failed:
            self.activity.record("notification.error" if failed else "notification.sent",
                ("Aviso de stock bajo" if event["kind"] == "low_stock" else "Aviso de lista: "+event["values"]["lista"]) + (" · con incidencias" if failed else " · enviado"),
                source="automatic", list_entity=event["entity_id"],
                diagnostics={"count":event["values"]["cantidad"],"threshold":rule["threshold"],"sent":sent,"failed":failed})

    async def async_stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        for _, stop in self._lists.values():
            stop()
        self._lists, self._items = {}, {}
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
