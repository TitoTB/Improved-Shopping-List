"""Shared list and display settings stored in config-entry options."""

import asyncio
from copy import deepcopy
import re
from secrets import randbelow

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_TODO_ENTITY, CONF_TODO_ENTITIES
from .const import DOMAIN
from .stores import StoreError
from .notification_settings import notification_options, normalize_notifications
from .regional_stores import REGIONAL_STORES
from .store_location import REFERENCE_LOCATIONS, reference_location
from . import store_availability

DEFAULT_APPEARANCE = {
    "gradient_start": "#ee524f", "gradient_end": "#b52a27",
    "completed_gradient_start": "#4faba2", "completed_gradient_end": "#26857c",
    "columns": 3, "mobile_columns": 1,
    "quantity_color": "#267052",
    "recipe_gradient_start": "#66bb6a", "recipe_gradient_end": "#2e7d32",
    "stock_gradient_start": "#f59a23", "stock_gradient_end": "#c65b0c",
}
DEFAULT_PURCHASE_DETECTION = {"enabled":False,"threshold":5,"zone_assignment":False,"persons":[],"store_zones":{}}
DEFAULT_STORES = {store: {"enabled": False, **reference_location(store)} for store in REFERENCE_LOCATIONS}


def normalize_appearance(data: dict, *, defaults: dict | None = None) -> dict:
    required = {"gradient_start", "gradient_end", "columns", "mobile_columns"}
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - set(DEFAULT_APPEARANCE):
        raise ListSettingsError("La personalización contiene campos no válidos.")
    data = {**(defaults or DEFAULT_APPEARANCE), **data}
    result = {}
    for key in ("gradient_start", "gradient_end", "completed_gradient_start", "completed_gradient_end", "quantity_color", "recipe_gradient_start", "recipe_gradient_end", "stock_gradient_start", "stock_gradient_end"):
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
            "purchase_detection": {**DEFAULT_PURCHASE_DETECTION, **entry.options.get("purchase_detection", {})},
            "gateway_lists": deepcopy(entry.options.get("gateway_lists", [])),
            "notifications": notification_options(entry.options.get("notifications")),
            "appearance": {**DEFAULT_APPEARANCE, **entry.options.get("appearance", {})},
            "stores": {key: {**deepcopy(defaults), "enabled": bool(entry.options.get("stores", {}).get(key, {}).get("enabled", False))} for key, defaults in DEFAULT_STORES.items()},
            "favorite_store": entry.options.get("favorite_store", ""), "price_update_time":entry.options.get("price_update_time", "01:00"),
            "price_updates_enabled":entry.options.get("price_updates_enabled",True), "price_update_days":entry.options.get("price_update_days",1)}


class ListSettings:
    """Apply individual operations atomically on HA's event loop."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.entry: ConfigEntry | None = None
        self._listeners: set = set()
        self._stores_lock = asyncio.Lock()
        self._generation = 0
        minute=randbelow(1440)
        self._default_price_time=f"{minute//60:02d}:{minute%60:02d}"

    @callback
    def attach(self, entry: ConfigEntry) -> None:
        self._generation += 1
        self.entry = entry
        # Drop all historical user locations and coverage errors atomically.
        # Keep store activation, lists, favorite and unrelated preferences.
        stores = list_options(entry)["stores"]
        favorite = entry.options.get("favorite_store", "")
        if favorite not in stores or not stores[favorite].get("enabled"):
            favorite = next((key for key, value in stores.items() if value.get("enabled")), "")
        options = {key: value for key, value in entry.options.items() if key != "store_postal_code"}
        options.update(stores=stores, favorite_store=favorite,
            price_update_time=entry.options.get("price_update_time",self._default_price_time),
            price_updates_enabled=entry.options.get("price_updates_enabled",True),price_update_days=entry.options.get("price_update_days",1))
        if options != dict(entry.options):
            self.hass.config_entries.async_update_entry(entry, options=options)
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
        snapshot = list_options(self.entry) if self.entry else {"entities": [], "primary_entity": "", "gateway_lists": [], "purchase_detection":dict(DEFAULT_PURCHASE_DETECTION), "notifications": notification_options(), "appearance": dict(DEFAULT_APPEARANCE), "stores": deepcopy(DEFAULT_STORES), "favorite_store": "", "price_update_time":self._default_price_time,"price_updates_enabled":True,"price_update_days":1}
        return store_availability.apply_availability(snapshot)

    async def async_toggle_located_store(self, store, enabled):
        """Enable a fixed reference without postal discovery or HTTP requests."""
        if store not in DEFAULT_STORES:
            raise StoreError("Tienda no compatible.")
        if enabled and store not in store_availability.AVAILABLE_STORES:
            raise StoreError("Esta tienda está archivada y no se puede activar.")
        generation = self._generation
        async with self._stores_lock:
            entry = self.entry
            if not entry or generation != self._generation or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise StoreError("La integración no está activa.")
            stores = {**list_options(entry)["stores"], store: {"enabled": enabled, **reference_location(store)}}
            self.hass.config_entries.async_update_entry(entry, options={**entry.options,
                "stores": stores, "favorite_store": self._favorite(stores)})
            self.notify()
            return self.snapshot

    async def async_ensure_store_location(self, store):
        """Return the canonical reference; obsolete saved locations cannot leak in."""
        if not self.entry or not self.hass.data.get(DOMAIN, {}).get("active"):
            raise StoreError("La integración no está activa.")
        current = self.snapshot["stores"].get(store, {})
        if not current.get("enabled"):
            raise StoreError("Habilita la tienda antes de actualizar sus precios.")
        return current

    async def async_update_store(self, enabled: bool, postal_code: str = "", verify: bool = False) -> dict:
        """Compatibility for older clients: location parameters no longer apply."""
        return await self.async_toggle_located_store("mercadona", enabled)

    def _favorite(self, stores):
        active = [key for key, value in stores.items() if value.get("enabled") and key in store_availability.AVAILABLE_STORES]
        current = self.snapshot["favorite_store"]
        return current if current in active else next(iter(active), "")

    async def async_update_carrefour(self, enabled, sale_point=None):
        return await self.async_toggle_located_store("carrefour", enabled)

    async def async_favorite_store(self, store):
        generation = self._generation
        async with self._stores_lock:
            if generation != self._generation or not self.entry or not self.hass.data.get(DOMAIN, {}).get("active") or not self.snapshot["stores"].get(store, {}).get("enabled"):
                raise StoreError("Selecciona una tienda habilitada.")
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "favorite_store": store})
            self.notify()
            return self.snapshot

    async def async_update_alcampo(self, enabled, region_id=""):
        return await self.async_toggle_located_store("alcampo", enabled)

    async def async_update_regional(self, store, enabled, postal_code="", area_id="", verify=False):
        if store not in REGIONAL_STORES:
            raise StoreError("Tienda no compatible.")
        return await self.async_toggle_located_store(store, enabled)

    def update_price_schedule(self, value, enabled=None, days=None):
        if not self.entry or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
            raise StoreError("Selecciona una hora válida para la actualización.")
        enabled=self.snapshot["price_updates_enabled"] if enabled is None else enabled
        days=self.snapshot["price_update_days"] if days is None else days
        if type(enabled) is not bool or type(days) is not int or not 1 <= days <= 3650:
            raise StoreError("Indica una frecuencia de entre 1 y 3650 días.")
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options,"price_update_time":value,
            "price_updates_enabled":enabled,"price_update_days":days})
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
            if any(item["entity_id"] == entity_id for item in current["gateway_lists"]):
                raise ListSettingsError("Esta entidad ya se utiliza como lista pasarela.")
            if not entity_id.startswith("todo.") or self.hass.states.get(entity_id) is None:
                raise ListSettingsError("Selecciona una entidad todo existente en Home Assistant.")
            if entity_id not in entities:
                entities.append(entity_id)
            if not primary:
                primary = entity_id
        elif action == "remove":
            if any(item["target_entity"] == entity_id for item in current["gateway_lists"]):
                raise ListSettingsError("Cambia primero el destino de las pasarelas vinculadas a esta lista.")
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
    def update_purchase_detection(self, data):
        if (not self.entry or not isinstance(data,dict) or set(data)-set(DEFAULT_PURCHASE_DETECTION) or not {"enabled","threshold"}.issubset(data) or
                type(data["enabled"]) is not bool or type(data["threshold"]) is not int or not 1 <= data["threshold"] <= 1000):
            raise ListSettingsError("Indica un umbral entre 1 y 1000 productos.")
        config = {**deepcopy(DEFAULT_PURCHASE_DETECTION), **self.snapshot["purchase_detection"], **deepcopy(data)}
        persons, zones = config["persons"], config["store_zones"]
        if (type(config["zone_assignment"]) is not bool or not isinstance(persons,list) or len(persons)>50 or
                any(not isinstance(entity,str) or not re.fullmatch(r"person\.[a-z0-9_]+",entity) for entity in persons) or
                not isinstance(zones,dict) or set(zones)-set(DEFAULT_STORES) or
                any(not isinstance(values,list) or len(values)>50 or
                    any(not isinstance(entity,str) or not re.fullmatch(r"zone\.[a-z0-9_]+",entity) for entity in values)
                    for values in zones.values())):
            raise ListSettingsError("Selecciona personas y zonas válidas de Home Assistant.")
        config["persons"] = list(dict.fromkeys(persons))
        config["store_zones"] = {store:list(dict.fromkeys(values)) for store,values in zones.items()}
        if config["zone_assignment"] and not config["persons"]:
            raise ListSettingsError("Selecciona al menos una persona para la asignación por zona.")
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options,"purchase_detection":config})
        self.notify()
        return self.snapshot

    @callback
    def update_notifications(self, data: dict) -> dict:
        if self.entry is None:
            raise ListSettingsError("La integración no está activa.")
        try:
            notifications = normalize_notifications(data, self.snapshot["notifications"])
        except ValueError as err:
            raise ListSettingsError(str(err)) from err
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "notifications": notifications})
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
