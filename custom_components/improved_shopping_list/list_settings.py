"""Shared list selection stored in the integration's config-entry options."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_TODO_ENTITY, CONF_TODO_ENTITIES


class ListSettingsError(ValueError):
    """An invalid list-settings operation."""


def list_options(entry: ConfigEntry) -> dict:
    """Read older entries without losing their configured default."""
    primary = entry.options.get(CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY])
    entities = list(entry.options.get(CONF_TODO_ENTITIES, [primary] if primary else []))
    return {"entities": entities, "primary_entity": primary if primary in entities else next(iter(entities), "")}


class ListSettings:
    """Apply individual operations atomically on HA's event loop."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.entry: ConfigEntry | None = None
        self._listeners: set = set()

    @callback
    def attach(self, entry: ConfigEntry) -> None:
        self.entry = entry
        if CONF_TODO_ENTITIES not in entry.options:
            # Keep the lists exposed by previous installations, including a
            # configured entity that has not finished starting yet.
            primary = entry.options.get(CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY])
            entities = list(dict.fromkeys([primary, *self.hass.states.async_entity_ids("todo")]))
            entities = [entity for entity in entities if entity]
            self.hass.config_entries.async_update_entry(entry, options={
                **entry.options, CONF_TODO_ENTITIES: entities, CONF_TODO_ENTITY: primary,
            })

    @property
    def snapshot(self) -> dict:
        return list_options(self.entry) if self.entry else {"entities": [], "primary_entity": ""}

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
