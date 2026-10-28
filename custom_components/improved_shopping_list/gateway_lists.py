"""Forward newly pending to-do items, with durable baselines and safe retries."""

import asyncio
from copy import deepcopy
from datetime import timedelta
import logging
from time import monotonic

from homeassistant.components.todo import DATA_COMPONENT, serialize_todo_item
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .catalog import normalized_name
from .const import CONF_TODO_ENTITIES, DOMAIN
from .list_settings import ListSettingsError
from .todo_names import named_item

_LOGGER = logging.getLogger(__name__)


class GatewayLists:
    """Observe provider item updates even while the frontend is closed."""

    def __init__(self, hass, settings, activity, operation_lock):
        self.hass, self.settings, self.activity = hass, settings, activity
        self._operation_lock = operation_lock
        self._store = Store(hass, 1, f"{DOMAIN}.gateway_lists")
        self._state = {}
        self._lists, self._retry_at = {}, {}
        self._stops = []
        self._active = False
        self._task = None
        self._dirty = False

    async def async_load(self):
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("lists"), dict):
                raise ValueError("No se ha podido leer el estado de las listas pasarela.")
            self._state = data["lists"]

    async def _save(self):
        await self._store.async_save({"lists": deepcopy(self._state)})

    @property
    def configs(self):
        return {item["entity_id"]: item for item in self.settings.snapshot.get("gateway_lists", [])}

    def _validate(self, source, target, remove):
        if not self._active or not self.settings.entry:
            raise ListSettingsError("La integración no está activa.")
        snapshot = self.settings.snapshot
        configs = self.configs
        if source == target or target not in snapshot["entities"] or target in configs:
            raise ListSettingsError("Selecciona una lista de la compra de destino; no puede ser otra pasarela.")
        if source == snapshot["primary_entity"] or any(item["target_entity"] == source for item in configs.values()):
            raise ListSettingsError("Esta lista es principal o destino de otra pasarela. Elige otra entidad de origen.")
        for entity_id in (source, target):
            state = self.hass.states.get(entity_id)
            if not entity_id.startswith("todo.") or state is None:
                raise ListSettingsError("Selecciona entidades todo existentes.")
        features = int(self.hass.states.get(source).attributes.get("supported_features", 0))
        if remove and not features & 2:
            raise ListSettingsError("La lista pasarela no permite eliminar productos. Selecciona conservarlos.")
        if not int(self.hass.states.get(target).attributes.get("supported_features", 0)) & 1:
            raise ListSettingsError("La lista de destino no permite añadir productos.")

    async def async_configure(self, source, target, remove):
        async with self._operation_lock:
            self._validate(source, target, remove)
            if source not in self.configs:
                # Capture existing items BEFORE enabling forwarding. Never import the backlog.
                items = await self._items(source)
                self._validate(source, target, remove)
                self._state[source] = {"seen": self._snapshot(items), "pending": {}}
                await self._save()
                self._validate(source, target, remove)
            entry = self.settings.entry
            configs = self.configs
            configs[source] = {"entity_id": source, "target_entity": target, "remove_after_transfer": remove}
            self.hass.config_entries.async_update_entry(entry, options={**entry.options,
                CONF_TODO_ENTITIES: [entity for entity in self.settings.snapshot["entities"] if entity != source],
                "gateway_lists": list(configs.values())})
            self.settings.notify()
            return self.settings.snapshot

    async def async_remove(self, source):
        async with self._operation_lock:
            if not self._active or not self.settings.entry:
                raise ListSettingsError("La integración no está activa.")
            entry = self.settings.entry
            self.hass.config_entries.async_update_entry(entry, options={**entry.options,
                "gateway_lists": [item for item in self.configs.values() if item["entity_id"] != source]})
            self.settings.notify()
            self._state.pop(source, None)
            await self._save()
            return self.settings.snapshot

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.settings.subscribe(self._changed),
            self.hass.bus.async_listen("state_changed", self._state_changed),
            async_track_time_interval(self.hass, self._changed, timedelta(minutes=1))]
        self._changed()

    @callback
    def _state_changed(self, event):
        if event.data.get("entity_id", "").startswith("todo."):
            self._changed()

    @callback
    def _changed(self, *_args):
        if not self._active:
            return
        component = self.hass.data.get(DATA_COMPONENT)
        configs = self.configs
        for source in tuple(self._lists):
            entity = component.get_entity(source) if component else None
            if source not in configs or entity is not self._lists[source][0]:
                self._lists.pop(source)[1]()
        if component:
            for source in configs.keys() - self._lists.keys():
                entity = component.get_entity(source)
                if entity is not None:
                    self._receive(source, entity.todo_items)
                    self._lists[source] = (entity, entity.async_subscribe_updates(
                        lambda items, key=source: self._receive(key, items)))
        self._queue()

    @staticmethod
    def _snapshot(items):
        return {str(item["uid"]): {"summary": item.get("summary") or "", "status": item.get("status")}
            for item in items if item.get("uid")}

    @callback
    def _receive(self, source, items):
        if not self._active or items is None or source not in self.configs:
            return
        current = self._snapshot([named_item(self.settings, source, serialize_todo_item(item)) for item in items])
        state = self._state.get(source)
        if state is None:
            self._state[source] = {"seen": current, "pending": {}}
        else:
            for uid, item in current.items():
                old = state["seen"].get(uid)
                if item["status"] == "needs_action" and (old is None or old["status"] == "completed"):
                    if normalized_name(item["summary"]):
                        state["pending"][uid] = {"name": item["summary"], "delivered": False}
                pending = state["pending"].get(uid)
                if pending and pending["name"] != item["summary"]:
                    # A correction before delivery follows the new name. Once delivered,
                    # never delete a source entry the user has repurposed meanwhile.
                    state["pending"].pop(uid)
                    if not pending["delivered"] and normalized_name(item["summary"]):
                        state["pending"][uid] = {"name": item["summary"], "delivered": False}
            state["seen"] = current
            # Removed/completed entries are no longer requests to forward.
            state["pending"] = {uid: pending for uid, pending in state["pending"].items()
                if uid in current and current[uid]["status"] == "needs_action"}
        self._queue()

    @callback
    def _queue(self):
        if not self._active:
            return
        self._dirty = True
        if not self._task or self._task.done():
            self._task = self.hass.async_create_background_task(self._drain(), "Shopping gateway lists")

    async def _drain(self):
        try:
            while self._active and self._dirty:
                self._dirty = False
                await self.async_check()
        except Exception:
            _LOGGER.exception("Could not process shopping gateway lists")

    async def _items(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            raise ListSettingsError(f"La lista {entity_id} no está disponible.")
        result = await self.hass.services.async_call("todo", "get_items", {"entity_id": entity_id},
            blocking=True, return_response=True)
        items = result.get(entity_id, {}).get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise ListSettingsError(f"No se pudo comprobar el contenido de {entity_id}.")
        return [named_item(self.settings, entity_id, item) for item in items]

    def _current(self, source, config, uid, pending):
        return (self._active and self.configs.get(source) == config
            and self._state.get(source, {}).get("pending", {}).get(uid) is pending)

    async def async_check(self):
        async with self._operation_lock:
            if not self._active:
                return
            # Persist observations before making any provider changes.
            await self._save()
            for source, config in self.configs.items():
                if self._retry_at.get(source, 0) > monotonic():
                    continue
                for uid, pending in list(self._state.get(source, {}).get("pending", {}).items()):
                    if not self._current(source, config, uid, pending):
                        continue
                    try:
                        await self._transfer(source, config, uid, pending)
                    except Exception as err:
                        self._retry_at[source] = monotonic() + 60
                        self.activity.record("gateway.error", f"No se pudo transferir {pending['name']} desde la lista pasarela",
                            source="automatic", product=pending["name"], list_entity=source,
                            diagnostics={"target_entity": config["target_entity"], "error": str(err)})
                        break

    async def _transfer(self, source, config, uid, pending):
        name, target = pending["name"], config["target_entity"]
        source_items = await self._items(source)
        item = next((item for item in source_items if str(item.get("uid")) == uid), None)
        if not self._current(source, config, uid, pending):
            return
        if not item or item.get("status") != "needs_action" or item.get("summary") != name:
            self._state[source]["pending"].pop(uid, None)
            await self._save()
            return
        if not pending["delivered"]:
            items = await self._items(target)
            if not self._current(source, config, uid, pending):
                return
            matches = [item for item in items if normalized_name(item.get("summary") or "") == normalized_name(name)]
            if not any(item.get("status") == "needs_action" for item in matches):
                state = self.hass.states.get(target)
                features = int(state.attributes.get("supported_features", 0)) if state else 0
                completed = next((item for item in matches if item.get("status") == "completed" and item.get("uid")), None)
                if completed and features & 4:
                    await self.hass.services.async_call("todo", "update_item", {"entity_id": target,
                        "item": completed["uid"], "status": "needs_action"}, blocking=True)
                elif features & 1:
                    await self.hass.services.async_call("todo", "add_item", {"entity_id": target, "item": name}, blocking=True)
                else:
                    raise ListSettingsError("La lista de destino no permite añadir este producto.")
            pending["delivered"] = True
            await self._save()
        if not self._current(source, config, uid, pending):
            return
        if config["remove_after_transfer"]:
            await self.hass.services.async_call("todo", "remove_item", {"entity_id": source, "item": uid}, blocking=True)
        self._state[source]["pending"].pop(uid, None)
        await self._save()
        self.activity.record("gateway.transferred", f"Lista pasarela: {name} transferido a la lista de la compra",
            source="automatic", product=name, list_entity=target,
            diagnostics={"gateway_entity": source, "removed_from_gateway": config["remove_after_transfer"]})

    async def async_stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        for _, stop in self._lists.values():
            stop()
        self._lists.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        await self._save()
        self._retry_at.clear()
