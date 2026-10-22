"""Common device, subscriptions and configuration validation for local entities."""

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME, VERSION
from .stores import StoreError


class ShoppingEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, data, key):
        self.data = data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=NAME,
            manufacturer="Aguacatec", model=NAME, sw_version=VERSION, entry_type=DeviceEntryType.SERVICE)

    @property
    def available(self):
        return self.data.active

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.data.subscribe(self.async_write_ha_state))

    def save_price_schedule(self, **changes):
        current = self.data.settings
        try:
            self.data.managers["settings"].update_price_schedule(changes.get("time", current["price_update_time"]),
                changes.get("enabled", current["price_updates_enabled"]), changes.get("days", current["price_update_days"]))
        except StoreError as err:
            raise ServiceValidationError(str(err)) from err
