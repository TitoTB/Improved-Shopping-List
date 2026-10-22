"""Native time-of-day control for the persisted price schedule."""

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import ShoppingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PriceUpdateTime(entry, hass.data[DOMAIN]["entity_data"], "price_update_time")])


class PriceUpdateTime(ShoppingEntity, TimeEntity):
    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self):
        return time.fromisoformat(self.data.settings["price_update_time"])

    async def async_set_value(self, value):
        if value.second or value.microsecond or value.tzinfo is not None:
            raise ServiceValidationError("Indica la hora y los minutos, sin segundos ni zona horaria.")
        self.save_price_schedule(time=value.strftime("%H:%M"))
