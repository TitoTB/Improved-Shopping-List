"""Bounded, durable activity history based on actual changes, not attempted writes."""

from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
import logging
from time import monotonic
from uuid import uuid4

from homeassistant.components.todo import DATA_COMPONENT, serialize_todo_item
from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .catalog import normalized_name
from .const import DOMAIN

MAX_ENTRIES = 1000
_LOGGER = logging.getLogger(__name__)


class ActivityLog:
    """Observe configured lists using the same item subscriptions as HA's todo UI."""

    def __init__(self, hass, catalog, settings, readers):
        self.hass, self.catalog, self.settings, self.readers = hass, catalog, settings, readers
        self._store = Store(hass, 1, f"{DOMAIN}.activity")
        self._entries = deque(maxlen=MAX_ENTRIES)
        self._listeners = set()
        self._unsubscribers = []
        self._lists = {}
        self._snapshots = {}
        self._intents = deque(maxlen=200)
        self._contexts = {}
        self._active = False

    async def async_load(self):
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
                raise ValueError("No se ha podido leer el historial de actividad.")
            self._entries.extend(data["entries"][-MAX_ENTRIES:])

    @property
    def snapshot(self):
        return {"entries": deepcopy(list(reversed(self._entries))), "limit": MAX_ENTRIES}

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def record(self, kind, message, *, source="integration", **fields):
        if not self._active:
            return
        self._entries.append({"id": str(uuid4()), "time": datetime.now(UTC).isoformat(),
                              "kind": kind, "source": source, "message": message, **fields})
        self._store.async_delay_save(lambda: {"entries": list(self._entries)}, 1)
        for listener in tuple(self._listeners):
            listener()

    @callback
    def reader_context(self, name):
        context = Context()
        self._contexts[context.id] = (monotonic(), name)
        return context

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._catalog_state = deepcopy(self.catalog.snapshot)
        self._settings_state = deepcopy(self.settings.snapshot)
        self._reader_state = self._reader_config()
        self._unsubscribers = [
            self.catalog.subscribe(self._catalog_changed),
            self.settings.subscribe(self._settings_changed),
            self.readers.subscribe(self._readers_changed),
            self.hass.bus.async_listen("call_service", self._service_called),
            self.hass.bus.async_listen("state_changed", self._state_changed),
        ]
        self._sync_lists()

    async def async_stop(self):
        self._active = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        for _, unsubscribe in self._lists.values():
            unsubscribe()
        self._lists.clear()
        self._snapshots.clear()
        self._contexts.clear()
        self._intents.clear()
        try:
            await self._store.async_save({"entries": list(self._entries)})
        except (OSError, HomeAssistantError):
            _LOGGER.exception("Could not save activity history")

    @callback
    def _state_changed(self, event):
        entity_id = event.data.get("entity_id", "")
        if entity_id.startswith("todo.") and entity_id in self.settings.snapshot["entities"]:
            self._sync_lists()

    @callback
    def _sync_lists(self):
        if not self._active:
            return
        component = self.hass.data.get(DATA_COMPONENT)
        wanted = set(self.settings.snapshot["entities"])
        for entity_id in tuple(self._lists):
            entity = component.get_entity(entity_id) if component else None
            if entity_id not in wanted or entity is not self._lists[entity_id][0]:
                self._lists.pop(entity_id)[1]()
                self._snapshots.pop(entity_id, None)
        if component is None:
            return
        for entity_id in wanted - self._lists.keys():
            entity = component.get_entity(entity_id)
            if entity is None:
                continue
            self._list_changed(entity_id, entity.todo_items)
            self._lists[entity_id] = (entity, entity.async_subscribe_updates(
                lambda items, entity_id=entity_id: self._list_changed(entity_id, items)))

    @callback
    def _service_called(self, event):
        if event.data.get("domain") != "todo":
            return
        service = event.data.get("service")
        if service not in ("add_item", "update_item", "remove_item", "remove_completed_items"):
            return
        data = event.data.get("service_data", {})
        targets = data.get("entity_id", [])
        targets = [targets] if isinstance(targets, str) else targets
        now = monotonic()
        self._contexts = {key: value for key, value in self._contexts.items() if now - value[0] < 120}
        reader = self._contexts.get(event.context.id)
        source = "reader" if reader else "automatic" if event.context.parent_id else "manual" if event.context.user_id else "home_assistant"
        for target in targets or []:
            if target in self.settings.snapshot["entities"]:
                self._intents.append({"time": now, "entity_id": target, "service": service,
                                      "data": dict(data), "source": source, "reader": reader[1] if reader else ""})

    def _origin(self, entity_id, kind, before, after):
        for intent in reversed(self._intents):
            if monotonic() - intent["time"] > 120 or intent["entity_id"] != entity_id:
                continue
            service, data = intent["service"], intent["data"]
            item = after or before
            if item.get("uid") in intent.get("used", set()) or intent["service"] == "add_item" and intent.get("used"):
                continue
            requested = data.get("item", [])
            requested = [requested] if isinstance(requested, str) else requested
            identified = any(value == item.get("uid") or normalized_name(str(value)) == normalized_name((before or item).get("summary") or "") for value in requested or [])
            matches = (
                kind == "list.added" and service == "add_item" and normalized_name(str(data.get("item", ""))) == normalized_name(item.get("summary") or "")
                or kind == "list.removed" and (service == "remove_item" and identified or service == "remove_completed_items" and before.get("status") == "completed")
                or kind in ("list.completed", "list.restored", "list.updated") and service == "update_item" and identified
                and ("status" not in data or data["status"] == after.get("status"))
                and ("rename" not in data or data["rename"] == after.get("summary"))
            )
            if matches:
                intent.setdefault("used", set()).add(item.get("uid"))
                return {"source": intent["source"], "reader": intent["reader"]}
        return {"source": "external"}

    @callback
    def _list_changed(self, entity_id, items):
        # None means the provider is loading; a reconnect must not fabricate removals.
        if items is None:
            return
        current = {str(item.uid): serialize_todo_item(item) for item in items if item.uid}
        previous = self._snapshots.get(entity_id)
        self._snapshots[entity_id] = current
        if previous is None:
            return  # Initial contents are a baseline, not new purchases.
        state = self.hass.states.get(entity_id)
        list_name = state.attributes.get("friendly_name", entity_id) if state else entity_id
        for uid in dict.fromkeys([*previous, *current]):
            old, new = previous.get(uid), current.get(uid)
            if old == new:
                continue
            product = (new or old).get("summary") or "Producto sin nombre"
            if old is None:
                kind, text = "list.added", "Añadido a la lista"
            elif new is None:
                kind, text = "list.removed", "Eliminado de la lista"
            elif old.get("status") != new.get("status"):
                kind, text = ("list.completed", "Marcado como comprado") if new.get("status") == "completed" else ("list.restored", "Recuperado como pendiente")
            else:
                kind, text = "list.updated", "Producto modificado en la lista"
            details = {}
            if old and new and old.get("summary") != new.get("summary"):
                details["previous_name"] = old.get("summary")
            self.record(kind, f"{text}: {product}", product=product, list_entity=entity_id,
                        list_name=list_name, **details, **self._origin(entity_id, kind, old, new))

    @callback
    def _catalog_changed(self):
        current = self.catalog.snapshot
        for field, label in (("products", "Producto"), ("categories", "Categoría")):
            old = {item["id"]: item for item in self._catalog_state[field]}
            new = {item["id"]: item for item in current[field]}
            for uid in dict.fromkeys([*old, *new]):
                before, after = old.get(uid), new.get(uid)
                ignored = {"id", "revision", "updated_at", "created_at", "product_count", "name_en", "price_updated_at"}
                changed = [key for key in set(before or {}) | set(after or {}) if key not in ignored and (before or {}).get(key) != (after or {}).get(key)]
                if before and after and not changed:
                    continue
                action, verb = ("created", "añadido" if field == "products" else "añadida") if before is None else ("deleted", "eliminado" if field == "products" else "eliminada") if after is None else ("updated", "modificado" if field == "products" else "modificada")
                item = after or before
                self.record(f"catalog.{field}.{action}", f"{label} {verb}: {item['name']}",
                            product=item["name"] if field == "products" else "", category=item.get("category", "") if field == "products" else item["name"],
                            changed_fields=sorted(changed), previous_name=before.get("name") if before and after and before["name"] != after["name"] else "")
        self._catalog_state = deepcopy(current)

    def _reader_config(self):
        return {item["id"]: {key: value for key, value in item.items() if key != "last"} for item in self.readers.snapshot["readers"]}

    @callback
    def _readers_changed(self):
        current = self._reader_config()
        for uid in dict.fromkeys([*self._reader_state, *current]):
            before, after = self._reader_state.get(uid), current.get(uid)
            if before == after:
                continue
            verb = "añadido" if before is None else "eliminado" if after is None else "modificado"
            self.record("reader.config", f"Lector {verb}: {(after or before)['name']}", reader=(after or before)["name"])
        self._reader_state = deepcopy(current)

    @callback
    def _settings_changed(self):
        current = self.settings.snapshot
        if current != self._settings_state:
            self.record("settings.updated", "Ajustes de listas o personalización modificados")
            self._settings_state = deepcopy(current)
        self._sync_lists()
