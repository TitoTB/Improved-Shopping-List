"""Shared list and display settings stored in config-entry options."""

import asyncio
from copy import deepcopy
import re
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_TODO_ENTITY, CONF_TODO_ENTITIES
from .const import DOMAIN
from .stores import StoreError, async_resolve_mercadona

DEFAULT_APPEARANCE = {
    "gradient_start": "#ee524f", "gradient_end": "#b52a27",
    "completed_gradient_start": "#4faba2", "completed_gradient_end": "#26857c",
    "columns": 3, "mobile_columns": 1,
}
DEFAULT_STORES = {"mercadona": {"enabled": False, "postal_code": "", "warehouse": "", "checked_at": None}, "carrefour": {"enabled": False, "sale_point":"005290"}, "alcampo":{"enabled":False,"region_id":""}}


def normalize_appearance(data: dict, *, defaults: dict | None = None) -> dict:
    required = {"gradient_start", "gradient_end", "columns", "mobile_columns"}
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - set(DEFAULT_APPEARANCE):
        raise ListSettingsError("La personalización contiene campos no válidos.")
    data = {**(defaults or DEFAULT_APPEARANCE), **data}
    result = {}
    for key in ("gradient_start", "gradient_end", "completed_gradient_start", "completed_gradient_end"):
        if not isinstance(data[key], str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", data[key]):
            raise ListSettingsError("Selecciona un color hexadecimal válido, como #ee524f.")
        result[key] = data[key].lower()
    for key, limit in (("columns", 6), ("mobile_columns", 4)):
        if type(data[key]) is not int or not 1 <= data[key] <= limit:
            raise ListSettingsError(f"El número de productos por fila debe estar entre 1 y {limit}.")
        result[key] = data[key]
    return result


class ListSettingsError(ValueError):
    """An invalid list-settings operation."""


def list_options(entry: ConfigEntry) -> dict:
    """Read older entries without losing their configured default."""
    primary = entry.options.get(CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY])
    entities = list(entry.options.get(CONF_TODO_ENTITIES, [primary] if primary else []))
    return {"entities": entities, "primary_entity": primary if primary in entities else next(iter(entities), ""),
            "appearance": {**DEFAULT_APPEARANCE, **entry.options.get("appearance", {})},
            "stores": {key:{**deepcopy(defaults), **deepcopy(entry.options.get("stores", {}).get(key, {}))} for key,defaults in DEFAULT_STORES.items()},
            "favorite_store": entry.options.get("favorite_store", ""), "price_update_time":entry.options.get("price_update_time", "01:00")}


class ListSettings:
    """Apply individual operations atomically on HA's event loop."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.entry: ConfigEntry | None = None
        self._listeners: set = set()
        self._stores_lock = asyncio.Lock()
        self._generation = 0

    @callback
    def attach(self, entry: ConfigEntry) -> None:
        self._generation += 1
        self.entry = entry
        if "lidl" in entry.options.get("stores", {}) or entry.options.get("favorite_store") == "lidl":
            stores = self.snapshot["stores"]
            favorite = entry.options.get("favorite_store", "")
            if favorite == "lidl":
                favorite = next((key for key,value in stores.items() if value.get("enabled")), "")
            self.hass.config_entries.async_update_entry(entry, options={
                **entry.options, "stores":stores, "favorite_store":favorite,
            })
        if CONF_TODO_ENTITIES not in entry.options:
            # Keep the lists exposed by previous installations, including a
            # configured entity that has not finished starting yet.
            primary = entry.options.get(CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY])
            entities = list(dict.fromkeys([primary, *self.hass.states.async_entity_ids("todo")]))
            entities = [entity for entity in entities if entity]
            self.hass.config_entries.async_update_entry(entry, options={
                **entry.options, CONF_TODO_ENTITIES: entities, CONF_TODO_ENTITY: primary,
            })

    @callback
    def detach(self) -> None:
        self._generation += 1
        self.entry = None

    @property
    def snapshot(self) -> dict:
        return list_options(self.entry) if self.entry else {"entities": [], "primary_entity": "", "appearance": dict(DEFAULT_APPEARANCE), "stores": deepcopy(DEFAULT_STORES), "favorite_store": "", "price_update_time":"01:00"}

    async def async_update_store(self, enabled: bool, postal_code: str, verify: bool = False) -> dict:
        """Verify before saving, serialize writes and preserve unrelated options."""
        generation = self._generation
        async with self._stores_lock:
            entry = self.entry
            if generation != self._generation or not entry or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise StoreError("La integración no está activa.")
            current = self.snapshot["stores"]["mercadona"]
            if enabled or verify:
                warehouse = await async_resolve_mercadona(self.hass, postal_code)
                store = {"enabled": enabled, "postal_code": postal_code, "warehouse": warehouse, "checked_at": int(time.time())}
            else:
                store = {**current, "enabled": False}
            if generation != self._generation or self.entry is not entry or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise StoreError("La integración se ha detenido. Vuelve a abrirla para guardar los ajustes.")
            self.hass.config_entries.async_update_entry(entry, options={
                **entry.options, "stores": {**self.snapshot["stores"], "mercadona": store},
                "favorite_store": self._favorite({**self.snapshot["stores"], "mercadona": store}),
            })
            self.notify()
            return self.snapshot

    def _favorite(self, stores):
        active = [key for key, value in stores.items() if value.get("enabled")]
        current = self.snapshot["favorite_store"]
        return current if current in active else next(iter(active), "")

    async def async_update_carrefour(self, enabled, sale_point=None):
        if sale_point is not None and not re.fullmatch(r"[0-9]{6}", sale_point):
            raise StoreError("El centro de Carrefour debe contener seis dígitos, conservando los ceros iniciales.")
        generation = self._generation
        async with self._stores_lock:
            if generation != self._generation or not self.entry or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise StoreError("La integración no está activa.")
            current = self.snapshot["stores"]["carrefour"]
            stores = {**self.snapshot["stores"], "carrefour": {**current,"enabled": enabled,"sale_point":sale_point if sale_point is not None else current["sale_point"]}}
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options,
                "stores": stores, "favorite_store": self._favorite(stores)})
            self.notify()
            return self.snapshot

    async def async_favorite_store(self, store):
        generation = self._generation
        async with self._stores_lock:
            if generation != self._generation or not self.entry or not self.hass.data.get(DOMAIN, {}).get("active") or not self.snapshot["stores"].get(store, {}).get("enabled"):
                raise StoreError("Selecciona una tienda habilitada.")
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "favorite_store": store})
            self.notify()
            return self.snapshot

    async def async_update_alcampo(self, enabled, region_id):
        if region_id and not re.fullmatch(r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}", region_id):
            raise StoreError("La región de Alcampo debe ser un identificador UUID válido.")
        generation = self._generation
        async with self._stores_lock:
            if generation != self._generation or not self.entry or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise StoreError("La integración no está activa.")
            stores = {**self.snapshot["stores"], "alcampo":{"enabled":enabled,"region_id":region_id.lower()}}
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options,
                "stores":stores,"favorite_store":self._favorite(stores)})
            self.notify()
            return self.snapshot

    def update_price_schedule(self, value):
        if not self.entry or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
            raise StoreError("Selecciona una hora válida para la revisión diaria.")
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options,"price_update_time":value})
        self.notify()
        return self.snapshot

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def update(self, action: str, entity_id: str) -> dict:
        if not self.entry:
            raise ListSettingsError("La integración no está activa.")
        current = self.snapshot
        entities = current["entities"]
        primary = current["primary_entity"]
        if action == "add":
            if not entity_id.startswith("todo.") or self.hass.states.get(entity_id) is None:
                raise ListSettingsError("Selecciona una entidad todo existente en Home Assistant.")
            if entity_id not in entities:
                entities.append(entity_id)
            if not primary:
                primary = entity_id
        elif action == "remove":
            entities = [entity for entity in entities if entity != entity_id]
            if primary == entity_id:
                primary = next(iter(entities), "")
        elif action == "primary":
            if entity_id not in entities:
                raise ListSettingsError("Añade primero esta lista a la integración.")
            primary = entity_id
        else:
            raise ListSettingsError("Acción de listas no válida.")
        self.hass.config_entries.async_update_entry(self.entry, options={
            **self.entry.options, CONF_TODO_ENTITIES: entities, CONF_TODO_ENTITY: primary,
        })
        self.notify()
        return self.snapshot

    @callback
    def update_appearance(self, data: dict) -> dict:
        if not self.entry:
            raise ListSettingsError("La integración no está activa.")
        appearance = normalize_appearance(data, defaults=self.snapshot["appearance"])
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "appearance": appearance})
        self.notify()
        return self.snapshot
