"""Physical purchase quantities, durable UID overrides, bounds and isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus, serialize_todo_item
from homeassistant.core import SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, FIELDS, normalize_product
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.quantities import ListQuantities


class Todo:
    def __init__(self):
        self.todo_items, self.listeners = [], []

    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def publish(self):
        for listener in tuple(self.listeners): listener(self.todo_items)


@pytest.fixture
async def env(hass):
    todos = {key: Todo() for key in ("todo.main", "todo.other")}
    for key, todo in todos.items():
        hass.states.async_set(key, "1", {"supported_features": 7})
        todo.todo_items = [TodoItem(uid="same-uid", summary="Pavo", status=TodoItemStatus.NEEDS_ACTION)]
    hass.data[DATA_COMPONENT] = SimpleNamespace(get_entity=todos.get)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"}); entry.add_to_hass(hass)
    settings = ListSettings(hass); settings.attach(entry)
    catalog = Catalog(hass); await catalog.async_load()
    product = await catalog.async_save_product({"name": "Pavo", "purchase_unit": "g", "unit_quantity": 250, "quantity_step": 50})
    async def get_items(call):
        key = call.data["entity_id"]
        return {key: {"items": [serialize_todo_item(item) for item in todos[key].todo_items]}}
    hass.services.async_register("todo", "get_items", get_items, supports_response=SupportsResponse.ONLY)
    activity = SimpleNamespace(record=Mock())
    manager = ListQuantities(hass, catalog, settings, activity); await manager.async_load(); manager.start()
    await manager._task
    yield SimpleNamespace(manager=manager, catalog=catalog, product=product, settings=settings, todos=todos, activity=activity)
    await manager.async_stop()


def item(): return {"uid": "same-uid", "summary": "Pavo"}


async def test_catalog_purchase_fields_defaults_validation_and_old_clients(hass):
    assert normalize_product({"name": "Pan"})["unit_quantity"] == 1
    for fields in ({"unit_quantity": 0}, {"unit_quantity": True}, {"quantity_step": -1},
        {"quantity_step": .0001}, {"purchase_unit": ""}, {"unit_quantity": float("inf")}):
        with pytest.raises(CatalogError): normalize_product({"name": "Pan", **fields})
    catalog = Catalog(hass); await catalog.async_load()
    product = await catalog.async_save_product({"name": "Pavo", "unit_quantity": 250, "purchase_unit": "g", "quantity_step": 50})
    legacy = {key: value for key, value in product.items() if key in FIELDS - {"unit_quantity", "purchase_unit", "quantity_step"}}
    saved = await catalog.async_save_product(legacy)
    assert saved["unit_quantity"] == 250 and saved["quantity_step"] == 50 and saved["purchase_unit"] == "g"
    restored = Catalog(hass); await restored.async_load()
    assert restored.products[0]["unit_quantity"] == 250


async def test_defaults_and_adjustments_do_not_modify_native_names_or_other_lists(env, hass):
    original = [serialize_todo_item(value) for value in env.todos["todo.main"].todo_items]
    assert env.manager.value("todo.main", item())["quantity"] == 250
    await asyncio.gather(env.manager.async_adjust("todo.main", "same-uid", 1), env.manager.async_adjust("todo.main", "same-uid", 1))
    assert env.manager.value("todo.main", item())["quantity"] == 350
    assert env.manager.value("todo.other", item())["quantity"] == 250
    assert [serialize_todo_item(value) for value in env.todos["todo.main"].todo_items] == original
    restored = ListQuantities(hass, env.catalog, env.settings, env.activity); await restored.async_load()
    assert restored.value("todo.main", item())["quantity"] == 350
    assert env.activity.record.call_args.args[0] == "list.quantity"


async def test_quantity_minimum_and_removed_uid_cleanup(env):
    for _ in range(4): await env.manager.async_adjust("todo.main", "same-uid", -1)
    assert env.manager.value("todo.main", item())["quantity"] == 50
    with pytest.raises(CatalogError): await env.manager.async_adjust("todo.main", "same-uid", -1)
    with pytest.raises(CatalogError): await env.manager.async_adjust("todo.main", "missing", 1)
    env.todos["todo.main"].todo_items = []; env.todos["todo.main"].publish()
    await env.manager._task
    assert env.manager.snapshot["entries"] == {}


async def test_unit_changes_cannot_reinterpret_old_overrides_and_missing_catalog_keeps_units(env):
    await env.manager.async_adjust("todo.main", "same-uid", 1)
    editable = {key: value for key, value in env.product.items() if key in FIELDS}
    updated = await env.catalog.async_save_product({**editable, "purchase_unit": "kg", "unit_quantity": .25, "quantity_step": .05})
    value = env.manager.value("todo.main", item())
    assert value["quantity"] == .25 and value["unit"] == "kg"
    await env.manager.async_adjust("todo.main", "same-uid", 1)
    await env.catalog.async_delete_product(updated["id"], updated["revision"])
    value = env.manager.value("todo.main", item())
    assert value["quantity"] == .3 and value["unit"] == "kg"


async def test_quantity_api_permissions_and_unload(hass, hass_ws_client, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"}); entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    await client.send_json({"id": 1, "type": f"{DOMAIN}/quantities/adjust", "entity_id": "todo.main", "uid": "a", "direction": 1})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/quantities/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"] == {"entries": {}}
    await client.close(); await hass.async_block_till_done()
    # Only the native estimated-price sensor remains subscribed.
    assert len(hass.data[DOMAIN]["quantities"]._listeners) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.data[DOMAIN]["quantities"]._listeners


async def test_recipe_adds_exact_physical_quantities_and_sums_pending_without_duplicates(hass, env):
    salt = await env.catalog.async_save_product({"name": "Sal", "purchase_unit": "g", "unit_quantity": 100, "quantity_step": 5})
    recipe = await env.catalog.async_save_recipe({"name": "Pavo con sal", "ingredients": [
        {"product_id": env.product["id"], "quantity": 50}, {"product_id": salt["id"], "quantity": 5}]})
    async def add_item(call):
        todo = env.todos[call.data["entity_id"]]
        todo.todo_items.append(TodoItem(uid="salt-uid", summary=call.data["item"], status=TodoItemStatus.NEEDS_ACTION))
        todo.publish()
    hass.services.async_register("todo", "add_item", add_item)
    lock = asyncio.Lock()
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", lock)
    assert result["error"] == "" and len(result["applied"]) == 2
    assert len(env.todos["todo.main"].todo_items) == 2
    assert env.manager.value("todo.main", item())["quantity"] == 300
    assert env.manager.value("todo.main", {"uid": "salt-uid", "summary": "Sal"})["quantity"] == 5
    assert env.manager.value("todo.other", item())["quantity"] == 250
    await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", lock)
    assert len(env.todos["todo.main"].todo_items) == 2
    assert env.manager.value("todo.main", item())["quantity"] == 350
    assert env.manager.value("todo.main", {"uid": "salt-uid", "summary": "Sal"})["quantity"] == 10


async def test_recipe_restores_completed_with_recipe_quantity_and_rejects_changed_units(hass, env):
    env.todos["todo.main"].todo_items[0].status = TodoItemStatus.COMPLETED
    recipe = await env.catalog.async_save_recipe({"name": "Pavo", "ingredients": [{"product_id": env.product["id"], "quantity": 70}]})
    async def update_item(call):
        env.todos["todo.main"].todo_items[0].status = TodoItemStatus.NEEDS_ACTION
        env.todos["todo.main"].publish()
    hass.services.async_register("todo", "update_item", update_item)
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert result["error"] == ""
    assert env.manager.value("todo.main", item())["quantity"] == 70
    assert len(env.todos["todo.main"].todo_items) == 1
    changed = await env.catalog.async_save_product({"id": env.product["id"], "revision": env.product["revision"], "name": "Pavo", "purchase_unit": "kg"})
    with pytest.raises(CatalogError, match="unidades distintas"):
        await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert changed["purchase_unit"] == "kg"


async def test_recipe_partial_provider_failure_reports_exact_applied_ingredients(hass, env):
    missing = await env.catalog.async_save_product({"name": "Pan"})
    recipe = await env.catalog.async_save_recipe({"name": "Bocadillo", "ingredients": [
        {"product_id": env.product["id"], "quantity": 10}, {"product_id": missing["id"], "quantity": 1}]})
    from homeassistant.exceptions import HomeAssistantError
    async def fail(call):
        raise HomeAssistantError("Proveedor sin conexión")
    hass.services.async_register("todo", "add_item", fail)
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert result["error"] == "Proveedor sin conexión"
    assert [item["name"] for item in result["applied"]] == ["Pavo"]
    assert env.manager.value("todo.main", item())["quantity"] == 260


async def test_simultaneous_recipe_additions_do_not_lose_quantities(hass, env):
    recipe = await env.catalog.async_save_recipe({"name": "Pavo", "ingredients": [{"product_id": env.product["id"], "quantity": 25}]})
    lock = asyncio.Lock()
    results = await asyncio.gather(*(env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", lock) for _ in range(2)))
    assert all(not result["error"] for result in results)
    assert env.manager.value("todo.main", item())["quantity"] == 300
    assert len(env.todos["todo.main"].todo_items) == 1


@pytest.mark.parametrize("mode", ["create", "restore", "pending_without_uid"])
async def test_recipe_waits_for_provider_confirmation_without_repeating_writes(hass, env, monkeypatch, mode):
    monkeypatch.setattr("custom_components.improved_shopping_list.quantities.RECIPE_CONFIRM_DELAYS", (.001, .001))
    todo = env.todos["todo.main"]
    initial = todo.todo_items[0]
    if mode == "create":
        todo.todo_items = []
    elif mode == "restore":
        initial.status = TodoItemStatus.COMPLETED
    else:
        initial.uid = None
    salt = await env.catalog.async_save_product({"name": "Sal"})
    recipe = await env.catalog.async_save_recipe({"name": "Pavo y sal", "ingredients": [
        {"product_id": env.product["id"], "quantity": 70}, {"product_id": salt["id"], "quantity": 2}]})
    writes, refreshes = [], []

    async def write(call):
        writes.append((call.service, call.data["item"]))
        if call.data["item"] == "Sal":
            todo.todo_items.append(TodoItem(uid="salt", summary="Sal", status=TodoItemStatus.NEEDS_ACTION))
            todo.publish()
        # The first write succeeds remotely, but its result is not yet visible.

    async def refresh(*, force_refresh):
        assert force_refresh
        refreshes.append(True)
        if len(refreshes) == 2:
            todo.todo_items = [TodoItem(uid="confirmed", summary="Pavo", status=TodoItemStatus.NEEDS_ACTION)]
            todo.publish()

    todo.async_update_ha_state = AsyncMock(side_effect=refresh)
    hass.services.async_register("todo", "add_item", write)
    hass.services.async_register("todo", "update_item", write)
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert result["error"] == ""
    assert [value["name"] for value in result["applied"]] == ["Pavo", "Sal"]
    assert len(refreshes) == 2
    assert len(writes) == (1 if mode == "pending_without_uid" else 2)
    expected = 320 if mode == "pending_without_uid" else 70
    assert env.manager.value("todo.main", {"uid": "confirmed", "summary": "Pavo"})["quantity"] == expected
    assert env.manager.value("todo.main", {"uid": "salt", "summary": "Sal"})["quantity"] == 2
    assert env.activity.record.call_args.kwargs["diagnostics"]["confirmations"][0]["confirmed"]


async def test_recipe_confirmation_failure_is_bounded_and_identifies_missing_product(hass, env, monkeypatch):
    monkeypatch.setattr("custom_components.improved_shopping_list.quantities.RECIPE_CONFIRM_DELAYS", (.001, .001))
    salt = await env.catalog.async_save_product({"name": "Sal"})
    recipe = await env.catalog.async_save_recipe({"name": "Pavo y sal", "ingredients": [
        {"product_id": env.product["id"], "quantity": 10}, {"product_id": salt["id"], "quantity": 2}]})
    add = AsyncMock()
    env.todos["todo.main"].async_update_ha_state = AsyncMock()
    hass.services.async_register("todo", "add_item", add)
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert "«Sal»" in result["error"]
    assert [value["name"] for value in result["applied"]] == ["Pavo"]
    assert add.await_count == 1
    assert env.manager.value("todo.main", item())["quantity"] == 260
    diagnostics = env.activity.record.call_args.kwargs["diagnostics"]
    assert diagnostics["failed_product"] == "Sal" and diagnostics["stage"] == "confirm"
    assert diagnostics["confirmations"][0]["reads"] == 3
    assert not diagnostics["confirmations"][0]["confirmed"]


async def test_recipe_stops_confirmation_when_list_is_removed(hass, env, monkeypatch):
    monkeypatch.setattr("custom_components.improved_shopping_list.quantities.RECIPE_CONFIRM_DELAYS", (.001,))
    env.todos["todo.main"].todo_items = []
    recipe = await env.catalog.async_save_recipe({"name": "Pavo", "ingredients": [
        {"product_id": env.product["id"], "quantity": 10}]})
    async def add(call):
        env.manager._active = False
    refresh = AsyncMock()
    env.todos["todo.main"].async_update_ha_state = refresh
    hass.services.async_register("todo", "add_item", add)
    result = await env.manager.async_add_recipe(recipe["id"], recipe["revision"], "todo.main", asyncio.Lock())
    assert "no está disponible" in result["error"]
    assert not result["applied"]
    refresh.assert_not_awaited()
