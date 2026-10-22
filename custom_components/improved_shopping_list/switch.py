"""Native price-update enable/disable control, shared with panel settings."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .entity import ShoppingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PriceUpdatesSwitch(entry, hass.data[DOMAIN]["entity_data"], "price_updates")])


class PriceUpdatesSwitch(ShoppingEntity, SwitchEntity):
    _attr_icon = "mdi:cash-sync"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return self.data.settings["price_updates_enabled"]

    async def async_turn_on(self, **kwargs):
        self.save_price_schedule(enabled=True)

    async def async_turn_off(self, **kwargs):
        self.save_price_schedule(enabled=False)
