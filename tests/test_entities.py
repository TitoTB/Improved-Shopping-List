"""Native HA entities, push updates, shared configuration and reload lifecycle."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITIES, CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.stock import DEFAULT_CONFIG
from custom_components.improved_shopping_list.store_links import normalize_link


class Todo:
    def __init__(self):
        self.todo_items, self.listeners = [], []

    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def publish(self, *names):
        self.todo_items = [TodoItem(uid=str(index), summary=name, status=TodoItemStatus.NEEDS_ACTION)
            for index, name in enumerate(names)]
        for listener in tuple(self.listeners):
            listener(self.todo_items)


@pytest.fixture
async def env(hass, monkeypatch):
    for entity in ("todo.main", "todo.other"):
        hass.states.async_set(entity, "0", {"supported_features": 7})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"},
        options={CONF_TODO_ENTITIES: ["todo.main", "todo.other"], "price_update_time": "03:15"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    managers = hass.data[DOMAIN]
    monkeypatch.setattr(managers["price_manager"], "_queue", Mock())
    fetch = AsyncMock(side_effect=AssertionError("Sensors must not request prices"))
    monkeypatch.setattr(managers["price_manager"].sources, "fetch", fetch)
    todos = {entity: Todo() for entity in ("todo.main", "todo.other")}
    component = hass.data[DATA_COMPONENT]
    monkeypatch.setattr(component, "get_entity", todos.get)
    managers["settings"].notify()
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def state(key, domain="sensor"):
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id is not None
        return hass.states.get(entity_id)

    yield SimpleNamespace(entry=entry, managers=managers, todos=todos, state=state, fetch=fetch)
    if hass.data[DOMAIN]["active"]:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_fifteen_entities_share_one_device_and_update_without_http(env, hass):
    entries = er.async_entries_for_config_entry(er.async_get(hass), env.entry.entry_id)
    assert len(entries) == 15
    assert len({entry.device_id for entry in entries}) == 1
    device = dr.async_get(hass).async_get(entries[0].device_id)
    assert device.name == "Improved Shopping List" and device.manufacturer == "Aguacatec"
    assert env.state("catalog_products").state == "0"
    assert env.state("catalog_categories").state == "0"
    assert env.state("shopping_list_products").state == "0"
    assert env.state("active_stores").state == "0"
    assert env.state("last_purchase_date").state == "unknown"
    assert env.state("last_purchase_amount").state == "unknown"
    catalog = env.managers["catalog"]
    await catalog.async_save_product({"name": "Café"})
    await catalog.async_save_category({"name": "Desayunos", "icon": "mdi:coffee", "color": "#123456"})
    assert env.state("catalog_products").state == "1"
    assert env.state("catalog_categories").state == "1"
    env.todos["todo.main"].publish("CAFÉ", "Pan")
    assert env.state("shopping_list_products").state == "2"
    env.todos["todo.main"].todo_items[0].status = TodoItemStatus.COMPLETED
    for listener in tuple(env.todos["todo.main"].listeners): listener(env.todos["todo.main"].todo_items)
    assert env.state("shopping_list_products").state == "1"
    env.fetch.assert_not_called()


async def test_estimate_uses_most_covered_active_store_then_cheapest(env):
    managers = env.managers
    catalog, settings, prices = (managers[key] for key in ("catalog", "settings", "price_manager"))
    products = []
    for name, identifier in (("Café", "1234"), ("Arroz", "5678")):
        products.append(await catalog.async_save_product({"name": name, "store_links": {
            "carrefour": normalize_link("carrefour", "R-prod"+identifier),
            "alcampo": normalize_link("alcampo", identifier)}}))
    for store in ("alcampo", "carrefour"):
        await settings.async_toggle_located_store(store, True)
    for product in products:
        link = product["store_links"]["carrefour"]
        prices._data["offers"][prices.key("carrefour", link, prices.scope("carrefour"))] = {
            "store": "carrefour", "price": "1.15", "currency": "EUR", "checked_at": 9999999999}
    product = products[0]; link = product["store_links"]["alcampo"]
    prices._data["offers"][prices.key("alcampo", link, prices.scope("alcampo"))] = {
        "store": "alcampo", "price": "0.20", "currency": "EUR", "checked_at": 9999999999}
    env.todos["todo.main"].publish("cafe", "Arroz", "Sin precio")
    estimate = env.state("next_purchase_amount")
    assert float(estimate.state) == 2.30 and estimate.attributes["store"] == "carrefour"
    assert estimate.attributes["priced_products"] == 2 and estimate.attributes["unpriced_products"] == 1
    # More coverage takes precedence over the favorite and a cheaper partial basket.
    await settings.async_favorite_store("alcampo")
    assert env.state("default_store").state == "Alcampo"
    assert env.state("next_purchase_amount").attributes["store"] == "carrefour"
    product = products[1]; link = product["store_links"]["alcampo"]
    prices._data["offers"][prices.key("alcampo", link, prices.scope("alcampo"))] = {
        "store": "alcampo", "price": "0.30", "currency": "EUR", "checked_at": 9999999999}
    prices._notify()
    assert float(env.state("next_purchase_amount").state) == 0.5
    assert env.state("next_purchase_amount").attributes["store"] == "alcampo"
    managers["quantities"]._entries = {"todo.main": {"0": {"quantity": 2, "unit": "uds", "step": 1}}}
    managers["quantities"]._notify()
    assert float(env.state("next_purchase_amount").state) == .7
    assert env.state("active_stores").state == "2"
    assert env.state("active_stores").attributes["store_names"] == ["Alcampo", "Carrefour"]
    await settings.async_toggle_located_store("alcampo", False)
    assert env.state("next_purchase_amount").attributes["store"] == "carrefour"
    env.fetch.assert_not_called()


async def test_primary_selection_availability_and_price_switch(env, hass):
    settings = env.managers["settings"]
    env.todos["todo.main"].publish("Pan", "Arroz")
    env.todos["todo.other"].publish("Leche")
    assert env.state("shopping_list_products").state == "2"
    settings.update("primary", "todo.other")
    assert env.state("shopping_list_products").state == "1"
    assert env.state("shopping_list_products").attributes["list_entity"] == "todo.other"
    env.todos["todo.main"].publish("Anterior")
    assert env.state("shopping_list_products").state == "1"
    hass.states.async_set("todo.other", "unavailable")
    await hass.async_block_till_done()
    assert env.state("shopping_list_products").state == "unavailable"
    assert env.state("next_purchase_amount").state == "unavailable"
    assert env.state("catalog_products").state == "0"
    hass.states.async_set("todo.other", "1", {"supported_features": 7})
    await hass.async_block_till_done()
    assert env.state("shopping_list_products").state == "1"
    await hass.services.async_call("switch", "turn_off", {"entity_id": env.state("price_updates", "switch").entity_id}, blocking=True)
    assert not settings.snapshot["price_updates_enabled"]
    assert env.state("next_purchase_amount").state == "unavailable"
    await hass.services.async_call("switch", "turn_on", {"entity_id": env.state("price_updates", "switch").entity_id}, blocking=True)
    assert settings.snapshot["price_updates_enabled"]
    assert env.state("next_purchase_amount").state == "0.0"


async def test_controls_persist_and_panel_changes_are_reflected(env, hass):
    number = env.state("price_update_days", "number").entity_id
    time = env.state("price_update_time", "time").entity_id
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 3}, blocking=True)
    await hass.services.async_call("time", "set_value", {"entity_id": time, "time": "04:27:00"}, blocking=True)
    assert env.entry.options["price_update_days"] == 3 and env.entry.options["price_update_time"] == "04:27"
    for value in (0, 1.5, 3651):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call("number", "set_value", {"entity_id": number, "value": value}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("time", "set_value", {"entity_id": time, "time": "04:27:12"}, blocking=True)
    env.managers["settings"].update_price_schedule("07:10", False, 5)
    assert float(env.state("price_update_days", "number").state) == 5
    assert env.state("price_update_time", "time").state == "07:10:00"
    assert env.state("price_updates", "switch").state == "off"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(env.entry.entry_id)
    assert not env.managers["entity_data"]._listeners
    assert await hass.config_entries.async_setup(env.entry.entry_id)
    await hass.async_block_till_done()
    assert env.state("price_update_days", "number").entity_id == number
    assert env.state("price_update_time", "time").entity_id == time
    assert float(env.state("price_update_days", "number").state) == 5
    assert env.state("price_update_time", "time").state == "07:10:00"
    assert len(er.async_entries_for_config_entry(er.async_get(hass), env.entry.entry_id)) == 15
    assert len(env.managers["entity_data"]._listeners) == 15


async def test_receipt_history_low_stock_reader_and_community_states(env, hass):
    managers = env.managers
    stock = managers["stock"]
    stock._items = {key: {**DEFAULT_CONFIG, **changes, "id": key, "name": key, "revision": 1,
        "catalog_product_id": "", "configured": True} for key, changes in {
            "low": {"quantity": 1, "reorder_enabled": True, "reorder_at": 2},
            "enough": {"quantity": 5, "reorder_enabled": True, "reorder_at": 2},
            "percent": {"mode": "perishable", "quantity": 20, "refill_quantity": 250,
                "reorder_enabled": True, "reorder_percent": 10},
            "no-alert": {"quantity": 0, "reorder_enabled": False}}.items()}
    stock._notify()
    assert env.state("low_stock_products").state == "2"
    assert set(env.state("low_stock_products").attributes["products"]) == {"low", "percent"}
    first = {"id": "old", "purchased_at": "2026-04-01T10:16:00", "total": 30.5,
        "store": "carrefour", "store_name": "Carrefour", "currency": "EUR", "lines": []}
    latest = {**first, "id": "latest", "purchased_at": "2026-04-03T18:30:00", "total": 42.75}
    stock.receipts["history"] = {receipt["id"]: receipt for receipt in (latest, first)}
    stock._notify()
    assert env.state("last_purchase_amount").state == "42.75"
    assert env.state("last_purchase_store").state == "Carrefour"
    assert env.state("last_purchase_date").attributes["receipt_id"] == "latest"
    expected = dt_util.as_utc(dt_util.parse_datetime(latest["purchased_at"]).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))
    assert dt_util.parse_datetime(env.state("last_purchase_date").state) == expected
    hass.states.async_set("sensor.scanner", "")
    hass.states.async_set("sensor.scanner_other", "")
    await managers["readers"].async_save_reader({"name": "Cocina", "entity_id": "sensor.scanner", "enabled": True})
    await managers["readers"].async_save_reader({"name": "Despensa", "entity_id": "sensor.scanner_other", "enabled": False})
    assert env.state("active_readers").state == "1"
    community = managers["community_sync"]
    community._data["sharing"] = True
    community._notify()
    assert env.state("community_sharing", "binary_sensor").state == "on"
    assert env.state("community_sharing", "binary_sensor").attributes["authorized"] is False
    assert "credentials" not in env.state("community_sharing", "binary_sensor").attributes
    community._data["sharing"] = False; community._notify()
    assert env.state("community_sharing", "binary_sensor").state == "off"
