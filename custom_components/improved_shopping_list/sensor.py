"""Counts, saved-price estimates and receipt history exposed as native sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass

from .const import DOMAIN
from .entity import ShoppingEntity
from .store_links import STORES

SENSORS = (
    SensorEntityDescription(key="shopping_list_products", icon="mdi:cart", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="next_purchase_amount", icon="mdi:cash", device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR", suggested_display_precision=2),
    SensorEntityDescription(key="catalog_products", icon="mdi:view-grid", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="catalog_categories", icon="mdi:label", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="low_stock_products", icon="mdi:package-variant", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="last_purchase_date", icon="mdi:calendar-clock", device_class=SensorDeviceClass.TIMESTAMP),
    SensorEntityDescription(key="last_purchase_amount", icon="mdi:receipt-text", device_class=SensorDeviceClass.MONETARY, suggested_display_precision=2),
    SensorEntityDescription(key="last_purchase_store", icon="mdi:store"),
    SensorEntityDescription(key="active_readers", icon="mdi:barcode-scan", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="default_store", icon="mdi:heart"),
    SensorEntityDescription(key="active_stores", icon="mdi:store-check", state_class=SensorStateClass.MEASUREMENT),
)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN]["entity_data"]
    async_add_entities(ShoppingSensor(entry, data, description) for description in SENSORS)


class ShoppingSensor(ShoppingEntity, SensorEntity):
    def __init__(self, entry, data, description):
        super().__init__(entry, data, description.key)
        self.entity_description = description

    @property
    def available(self):
        if self.entity_description.key == "shopping_list_products":
            return super().available and self.data.pending is not None
        if self.entity_description.key == "next_purchase_amount":
            return super().available and self.data.estimate is not None
        return super().available

    @property
    def native_value(self):
        data, key = self.data, self.entity_description.key
        purchase = data.last_purchase
        match key:
            case "shopping_list_products": return len(data.pending) if data.pending is not None else None
            case "next_purchase_amount": return data.estimate["cents"] / 100 if data.estimate else None
            case "catalog_products": return len(data.managers["catalog"].products)
            case "catalog_categories": return len(data.managers["catalog"].snapshot["categories"])
            case "low_stock_products": return len(data.low_stock)
            case "last_purchase_date": return purchase["date"] if purchase else None
            case "last_purchase_amount": return purchase["total"] if purchase else None
            case "last_purchase_store": return purchase.get("store_name") or STORES.get(purchase["store"], purchase["store"]) if purchase else None
            case "active_readers": return sum(bool(reader.get("enabled")) for reader in data.managers["readers"].snapshot["readers"])
            case "default_store": return STORES.get(data.settings["favorite_store"])
            case "active_stores": return sum(bool(config.get("enabled")) for config in data.settings["stores"].values())
        return None

    @property
    def native_unit_of_measurement(self):
        if self.entity_description.key == "last_purchase_amount":
            return self.data.last_purchase.get("currency", "EUR") if self.data.last_purchase else "EUR"
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self):
        key = self.entity_description.key
        if key == "shopping_list_products":
            return {"list_entity": self.data.settings["primary_entity"]}
        if key == "next_purchase_amount":
            return {key: value for key, value in (self.data.estimate or {}).items() if key != "cents"}
        if key == "low_stock_products":
            return {"products": [item["name"] for item in self.data.low_stock]}
        if key.startswith("last_purchase_"):
            return {"receipt_id": self.data.last_purchase["id"]} if self.data.last_purchase else {}
        if key == "default_store":
            return {"store": self.data.settings["favorite_store"] or None}
        if key == "active_stores":
            return {"stores": [store for store, config in self.data.settings["stores"].items() if config.get("enabled")],
                "store_names": sorted(STORES[store] for store, config in self.data.settings["stores"].items() if config.get("enabled") and store in STORES)}
        return None
