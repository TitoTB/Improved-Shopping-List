"""Native price-update frequency configuration."""

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import ShoppingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PriceUpdateDays(entry, hass.data[DOMAIN]["entity_data"], "price_update_days")])


class PriceUpdateDays(ShoppingEntity, NumberEntity):
    _attr_icon = "mdi:calendar-sync"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 3650
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self.data.settings["price_update_days"]

    async def async_set_native_value(self, value):
        if not math.isfinite(value) or value != int(value) or not 1 <= value <= 3650:
            raise ServiceValidationError("Indica un número entero de entre 1 y 3650 días.")
        self.save_price_schedule(days=int(value))
