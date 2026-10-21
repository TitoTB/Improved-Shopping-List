"""Persist readers and process physical scans without an open frontend."""

from asyncio import Lock, gather
from copy import deepcopy
from datetime import UTC, datetime
import logging
import time
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .catalog import READER_ACTIONS, CatalogError, code_key, normalized_name
from .const import DOMAIN
from .product_lookup import ProductLookup, is_product_barcode

_LOGGER = logging.getLogger(__name__)
INVALID_STATES = {"", "unknown", "unavailable", "none"}


def normalize_reader(data: dict, hass: HomeAssistant, settings) -> dict:
    fields = {"id", "revision", "name", "kind", "source", "entity_id", "attribute", "device_id", "list_entity", "cooldown", "enabled", "default_action"}
    if not isinstance(data, dict) or set(data) - fields:
        raise CatalogError("El lector contiene campos no admitidos.")
    result = {}
    for field, limit in (("name", 100), ("entity_id", 255), ("attribute", 100), ("device_id", 100), ("list_entity", 255)):
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise CatalogError("Los campos del lector no son válidos.")
        result[field] = value.strip()
    if not result["name"]:
        raise CatalogError("El nombre del lector es obligatorio.")
    result["kind"] = data.get("kind", "barcode")
    result["source"] = data.get("source", "entity")
    if result["kind"] not in ("barcode", "nfc") or result["source"] not in ("entity", "tag"):
        raise CatalogError("Selecciona un tipo y una fuente de lectura válidos.")
    if result["source"] == "entity":
        if hass.states.get(result["entity_id"]) is None:
            raise CatalogError("Selecciona una entidad existente en Home Assistant.")
        result["device_id"] = ""
    else:
        if result["kind"] != "nfc" or not result["device_id"]:
            raise CatalogError("Los eventos NFC necesitan el device_id del lector para distinguirlo de otros dispositivos.")
        result["entity_id"] = result["attribute"] = ""
    if result["list_entity"] and result["list_entity"] not in settings.snapshot["entities"]:
        raise CatalogError("Añade la lista de destino en Ajustes o utiliza la principal.")
    result["cooldown"] = data.get("cooldown", 60)
    result["enabled"] = data.get("enabled", True)
    result["default_action"] = data.get("default_action", "none")
    if not isinstance(result["default_action"], str) or result["default_action"] not in READER_ACTIONS:
        raise CatalogError("Selecciona una acción por defecto válida para el lector.")
    if type(result["cooldown"]) is not int or not 1 <= result["cooldown"] <= 3600 or not isinstance(result["enabled"], bool):
        raise CatalogError("La protección antirrepetición debe estar entre 1 y 3600 segundos.")
    return result


class ReaderManager:
    def __init__(self, hass, catalog, settings):
        self.hass, self.catalog, self.settings = hass, catalog, settings
        self._store = Store(hass, 1, f"{DOMAIN}.readers")
        self._data = {"readers": {}, "pending": {}, "dismissed": [], "cooldowns": {}}
        self._lock = Lock()
        self._operation_lock = Lock()
        self._listeners = set()
        self._last = {}
        self._tasks = set()
        self._unsubscribers = []
        self._active = False
        self.lookup = ProductLookup(hass)
        self._lookup_pending = set()
        self.activity = None

    async def async_load(self):
        await self.lookup.async_load()
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or any(not isinstance(data.get(key), dict) for key in ("readers", "pending", "cooldowns")) or not isinstance(data.get("dismissed"), list):
                raise CatalogError("No se han podido leer los lectores guardados.", "storage_error")
            self._data = data
            for reader in self._data["readers"].values():
                reader.setdefault("default_action", "none")

    @property
    def snapshot(self):
        return {
            "readers": [{**deepcopy(reader), "last": deepcopy(self._last.get(reader["id"]))} for reader in sorted(self._data["readers"].values(), key=lambda item: item["name"].casefold())],
            "pending": [{**deepcopy(item), "identification": self._identification(item)} for item in self._data["pending"].values() if self.catalog.find_by_code(item["kind"], item["code"]) is None],
        }

    def _identification(self, item):
        if item["kind"] != "barcode" or not is_product_barcode(item["code"]):
            return {"status": "unsupported"}
        return self.lookup.cached(item["code"]) or {"status": "pending"}

    @callback
    def _schedule_lookup(self, item):
        if item["id"] in self._lookup_pending or item["kind"] != "barcode" or not is_product_barcode(item["code"]) or self.lookup.is_fresh(item["code"]):
            return
        self._lookup_pending.add(item["id"])
        if self._spawn(self._identify(item), background=True) is None:
            self._lookup_pending.discard(item["id"])

    async def _identify(self, item):
        try:
            if item["id"] in self._data["pending"] and self.catalog.find_by_code(item["kind"], item["code"]) is None:
                await self.lookup.async_lookup(item["code"])
                if self._active:
                    self._notify()
        except Exception:
            _LOGGER.exception("Could not identify a pending product")
        finally:
            self._lookup_pending.discard(item["id"])

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    async def _persist(self, data):
        await self._store.async_save(data)
        self._data = data

    @callback
    def _status(self, reader_id, code, message, product=None):
        self._last[reader_id] = {"code": code, "message": message, "product": product, "time": datetime.now(UTC).isoformat()}
        if self.activity:
            reader = self._data["readers"].get(reader_id, {})
            self.activity.record("reader.scan", message, source="reader", reader=reader.get("name", reader_id),
                                 product=product or "", code=code, list_entity=reader.get("list_entity") or self.settings.snapshot["primary_entity"])
        self._notify()

    async def async_save_reader(self, data):
        reader = normalize_reader(data, self.hass, self.settings)
        async with self._lock:
            reader_id = data.get("id")
            if reader_id is not None and not isinstance(reader_id, str):
                raise CatalogError("Identificador de lector no válido.")
            current = self._data["readers"].get(reader_id)
            if reader_id and current is None:
                raise CatalogError("El lector ya no existe.", "not_found")
            if current and data.get("revision") != current["revision"]:
                raise CatalogError("Otra sesión ha cambiado el lector. Vuelve a abrirlo.", "conflict")
            if current and "default_action" not in data:
                reader["default_action"] = current.get("default_action", "none")
            for other in self._data["readers"].values():
                if other["id"] == reader_id:
                    continue
                if reader["source"] == other["source"] and (reader["entity_id"] if reader["source"] == "entity" else reader["device_id"]) == (other["entity_id"] if other["source"] == "entity" else other["device_id"]):
                    raise CatalogError("Ya hay un lector configurado con esa fuente.")
            reader.update({"id": reader_id or str(uuid4()), "revision": current["revision"] + 1 if current else 1})
            updated = deepcopy(self._data)
            updated["readers"][reader["id"]] = reader
            await self._persist(updated)
        self._listen_sources()

        self._notify()
        return deepcopy(reader)

    async def async_delete_reader(self, reader_id, revision):
        async with self._lock:
            current = self._data["readers"].get(reader_id)
            if not current or current["revision"] != revision:
                raise CatalogError("El lector ha cambiado o ya no existe. Actualiza la vista.", "conflict")
            updated = deepcopy(self._data)
            del updated["readers"][reader_id]
            await self._persist(updated)
        self._last.pop(reader_id, None)
        self._listen_sources()
        self._notify()

    async def async_dismiss(self, pending_id):
        async with self._lock:
            item = self._data["pending"].get(pending_id)
            if item is None:
                return
            updated = deepcopy(self._data)
            key = f'{item["kind"]}:{code_key(item["kind"], item["code"])}'
            if key not in updated["dismissed"]:
                updated["dismissed"].append(key)
            del updated["pending"][pending_id]
            await self._persist(updated)
        self._notify()

    @callback
    def start(self):
        self._active = True
        self._catalog_unsubscribe = self.catalog.subscribe(self._catalog_changed)
        self._listen_sources()
        for item in self._data["pending"].values():
            if self.catalog.find_by_code(item["kind"], item["code"]) is None:
                self._schedule_lookup(item)

    async def async_stop(self):
        self._active = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if getattr(self, "_catalog_unsubscribe", None):
            self._catalog_unsubscribe()
            self._catalog_unsubscribe = None
        for task in tuple(self._tasks):
            task.cancel()
        await gather(*self._tasks, return_exceptions=True)
        self._lookup_pending.clear()

    @callback
    def _spawn(self, coroutine, *, background=False):
        if not self._active or len(self._tasks) >= 100:
            coroutine.close()
            return
        task = (self.hass.async_create_background_task(coroutine, "Improved Shopping List product lookup")
                if background else self.hass.async_create_task(coroutine))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @callback
    def _catalog_changed(self):
        self._notify()
        self._spawn(self._prune_pending())

    async def _prune_pending(self):
        try:
            async with self._lock:
                keep = {key: item for key, item in self._data["pending"].items() if self.catalog.find_by_code(item["kind"], item["code"]) is None}
                if len(keep) != len(self._data["pending"]):
                    updated = deepcopy(self._data)
                    updated["pending"] = keep
                    await self._persist(updated)
        except OSError:
            _LOGGER.exception("Could not remove resolved scan suggestions")

    @callback
    def _listen_sources(self):
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if not self._active:
            return
        entities = [reader["entity_id"] for reader in self._data["readers"].values() if reader["enabled"] and reader["source"] == "entity"]
        if entities:
            self._unsubscribers.append(async_track_state_change_event(self.hass, entities, self._entity_event))
        if any(reader["enabled"] and reader["source"] == "tag" for reader in self._data["readers"].values()):
            self._unsubscribers.append(self.hass.bus.async_listen("tag_scanned", self._tag_event))

    @callback
    def _entity_event(self, event):
        old, state = event.data.get("old_state"), event.data.get("new_state")
        # Never execute a stale value restored when an entity first appears.
        if old is None or state is None or state.state in ("unknown", "unavailable") or state.attributes.get("restored"):
            return
        for reader in self._data["readers"].values():
            if reader["source"] != "entity" or not reader["enabled"] or reader["entity_id"] != state.entity_id:
                continue
            attribute = reader["attribute"]
            code = state.attributes.get(attribute) if attribute else state.state
            previous = old.attributes.get(attribute) if attribute else old.state
            # Attribute-only updates are not new scans; event entities change their timestamp.
            if code == previous and state.state == old.state and state.attributes != old.attributes:
                continue
            self._spawn(self.async_process(reader["id"], code))

    @callback
    def _tag_event(self, event):
        for reader in self._data["readers"].values():
            if reader["enabled"] and reader["source"] == "tag" and reader["device_id"] == event.data.get("device_id"):
                self._spawn(self.async_process(reader["id"], event.data.get("tag_id")))

    async def async_process(self, reader_id, code):
        if not isinstance(code, str) or not code.strip() or len(code) > 1024 or any(ord(char) < 32 and char not in "\r\n\t" for char in code):
            return
        code = code.strip()
        pending_id = None
        if any(ord(char) < 32 for char in code):
            return
        if code.casefold() in INVALID_STATES:
            return
        try:
            async with self._lock:
                reader = deepcopy(self._data["readers"].get(reader_id))
                if not self._active or not reader or not reader["enabled"]:
                    return
                product = self.catalog.find_by_code(reader["kind"], code)
                now = time.time()
                code_id = f'{reader["kind"]}:{code_key(reader["kind"], code)}'
                keys = [f"{reader_id}:code:{code_id}"]
                if product:
                    keys.append(f'{reader_id}:product:{product["id"]}')
                if any(now - self._data["cooldowns"].get(key, 0) < reader["cooldown"] for key in keys):
                    self._status(reader_id, code, "Lectura repetida ignorada", product["name"] if product else None)
                    return
                updated = deepcopy(self._data)
                updated["cooldowns"] = {key: timestamp for key, timestamp in updated["cooldowns"].items() if now - timestamp < 3600}
                updated["cooldowns"].update({key: now for key in keys})
                if not product and code_id not in updated["dismissed"]:
                    existing = next((item for item in updated["pending"].values() if item["kind"] == reader["kind"] and code_key(item["kind"], item["code"]) == code_key(reader["kind"], code)), None)
                    pending_id = existing["id"] if existing else str(uuid4())
                    updated["pending"][pending_id] = {"id": pending_id, "kind": reader["kind"], "code": code, "reader_id": reader_id, "reader_name": reader["name"], "time": datetime.now(UTC).isoformat()}
                await self._persist(updated)  # Persist the guard before any provider mutation.
            if product is None:
                self._status(reader_id, code, "Código desconocido en Sugerencias" if code_id not in self._data["dismissed"] else "Código desconocido descartado")
                if pending_id and (pending := self._data["pending"].get(pending_id)):
                    self._schedule_lookup(pending)
                return
            action = product.get("reader_actions", {}).get(reader_id, reader.get("default_action", "none"))
            if action == "none":
                self._status(reader_id, code, "Sin acción configurada para este producto y lector", product["name"])
            elif action in ("stock_remove", "stock_add"):
                self._status(reader_id, code, "Acción de stock guardada; inventario pendiente de implementar", product["name"])
            elif action == "add_list":
                async with self._operation_lock:
                    await self._add_to_list(reader, product, code)
        except Exception:  # Provider and storage failures must never become unhandled tasks.
            _LOGGER.exception("Could not process reader %s", reader_id)
            self._status(reader_id, code, "No se pudo completar la lectura. Comprueba el lector, la lista o el registro.")

    def _still_current(self, reader, product, code, target):
        current = self._data["readers"].get(reader["id"])
        matched = self.catalog.find_by_code(reader["kind"], code)
        if not self._active or current != reader or not matched or matched["revision"] != product["revision"]:
            raise CatalogError("La configuración cambió durante la lectura.")
        if target not in self.settings.snapshot["entities"]:
            raise CatalogError("La lista ya no está añadida a la integración.")

    async def _add_to_list(self, reader, product, code):
        target = reader["list_entity"] or self.settings.snapshot["primary_entity"]
        self._still_current(reader, product, code, target)
        state = self.hass.states.get(target)
        if state is None or state.state in ("unknown", "unavailable"):
            raise CatalogError("La lista de destino no está disponible.")
        result = await self.hass.services.async_call("todo", "get_items", {"entity_id": target}, blocking=True, return_response=True)
        items = result.get(target, {}).get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise CatalogError("No se ha podido comprobar el contenido de la lista.")
        matches = [item for item in items if normalized_name(item.get("summary", "")) == normalized_name(product["name"])]
        if any(item.get("status") != "completed" for item in matches):
            self._status(reader["id"], code, "El producto ya estaba pendiente en la lista", product["name"])
            return
        self._still_current(reader, product, code, target)
        state = self.hass.states.get(target)
        if state is None or state.state in ("unknown", "unavailable"):
            raise CatalogError("La lista de destino no está disponible.")
        features = int(state.attributes.get("supported_features", 0))
        completed = next((item for item in matches if item.get("uid") and item.get("status") == "completed"), None)
        context = self.activity.reader_context(reader["name"]) if self.activity else None
        if completed and features & 4:
            await self.hass.services.async_call("todo", "update_item", {"entity_id": target, "item": completed["uid"], "status": "needs_action"}, blocking=True, context=context)
        elif features & 1:
            await self.hass.services.async_call("todo", "add_item", {"entity_id": target, "item": product["name"]}, blocking=True, context=context)
        else:
            raise CatalogError("La lista de destino no permite añadir o recuperar el producto.")
        self._status(reader["id"], code, f"Añadido a {state.attributes.get('friendly_name', target)}", product["name"])
