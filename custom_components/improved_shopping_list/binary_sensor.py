"""Community consent status; GitHub authorization stays in the integration UI."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import ShoppingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CommunitySharingSensor(entry, hass.data[DOMAIN]["entity_data"], "community_sharing")])


class CommunitySharingSensor(ShoppingEntity, BinarySensorEntity):
    _attr_icon = "mdi:account-group"

    @property
    def is_on(self):
        return bool(self.data.managers["community_sync"].snapshot["sharing"])

    @property
    def extra_state_attributes(self):
        return {"authorized": bool(self.data.managers["community_sync"].snapshot["connected"])}
