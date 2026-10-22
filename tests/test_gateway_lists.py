"""Gateway baselines, forwarding, durable retries and configuration safeguards."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus, serialize_todo_item
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.gateway_lists import GatewayLists
from custom_components.improved_shopping_list.list_settings import ListSettings, ListSettingsError


class Todo:
    def __init__(self):
        self.todo_items, self.listeners = [], []

    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def publish(self):
        for listener in tuple(self.listeners):
            listener(self.todo_items)

    def add(self, uid, name, status=TodoItemStatus.NEEDS_ACTION):
        self.todo_items.append(TodoItem(uid=uid, summary=name, status=status))
        self.publish()


@pytest.fixture
async def env(hass, monkeypatch):
    todos = {key: Todo() for key in ("todo.main", "todo.voice", "todo.other")}
    for key in todos:
        hass.states.async_set(key, "0", {"supported_features": 7})
    hass.data[DATA_COMPONENT] = SimpleNamespace(get_entity=todos.get)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass); settings.attach(entry)
    activity = SimpleNamespace(record=Mock())
    manager = GatewayLists(hass, settings, activity, asyncio.Lock())
    await manager.async_load()
    # Drive flush/retry explicitly, while keeping real item subscriptions.
    monkeypatch.setattr(manager, "_queue", Mock())
    calls, fail = [], {"add": False, "remove": False}

    async def get_items(call):
        key = call.data["entity_id"]
        return {key: {"items": [serialize_todo_item(item) for item in todos[key].todo_items]}}

    async def add_item(call):
        if fail["add"]:
            raise HomeAssistantError("Provider unavailable")
        calls.append(("add", dict(call.data)))
        todos[call.data["entity_id"]].add(f"new-{len(calls)}", call.data["item"])

    async def update_item(call):
        calls.append(("update", dict(call.data)))
        todo = todos[call.data["entity_id"]]
        next(item for item in todo.todo_items if item.uid == call.data["item"]).status = TodoItemStatus(call.data["status"])
        todo.publish()

    async def remove_item(call):
        if fail["remove"]:
            raise HomeAssistantError("Cannot delete yet")
        calls.append(("remove", dict(call.data)))
        todo = todos[call.data["entity_id"]]
        todo.todo_items = [item for item in todo.todo_items if item.uid != call.data["item"]]
        todo.publish()

    hass.services.async_register("todo", "get_items", get_items, supports_response=SupportsResponse.ONLY)
    hass.services.async_register("todo", "add_item", add_item)
    hass.services.async_register("todo", "update_item", update_item)
    hass.services.async_register("todo", "remove_item", remove_item)
    manager.start()
    yield SimpleNamespace(manager=manager, todos=todos, settings=settings, activity=activity, calls=calls, fail=fail)
    await manager.async_stop()


async def test_only_new_items_forward_and_names_deduplicate(env):
    voice, main = env.todos["todo.voice"], env.todos["todo.main"]
    voice.add("old", "Ya estaba")
    await env.manager.async_configure("todo.voice", "todo.main", False)
    await env.manager.async_check()
    assert env.calls == []
    assert "todo.voice" not in env.settings.snapshot["entities"]
    voice.add("a", "  Seitán  ")
    voice.add("b", "SEITAN")
    voice.add("c", "Completado", TodoItemStatus.COMPLETED)
    await env.manager.async_check()
    assert len(main.todo_items) == 1 and main.todo_items[0].summary == "  Seitán  "
    assert len(voice.todo_items) == 4 and len(env.calls) == 1
    voice.publish(); await env.manager.async_check()
    assert len(env.calls) == 1


async def test_remove_after_pending_duplicate_or_restore_completed(env):
    voice, main = env.todos["todo.voice"], env.todos["todo.main"]
    await env.manager.async_configure("todo.voice", "todo.main", True)
    main.add("existing", "Café")
    main.add("completed", "Arroz", TodoItemStatus.COMPLETED)
    voice.add("a", "cafe"); voice.add("b", "arroz")
    await env.manager.async_check()
    assert not voice.todo_items
    assert len(main.todo_items) == 2
    assert all(item.status == TodoItemStatus.NEEDS_ACTION for item in main.todo_items)
    assert [kind for kind, _ in env.calls] == ["remove", "update", "remove"]
    assert env.activity.record.call_args.args[0] == "gateway.transferred"


async def test_failed_destination_keeps_source_and_retries(env):
    await env.manager.async_configure("todo.voice", "todo.main", True)
    env.fail["add"] = True
    env.todos["todo.voice"].add("a", "Cacao")
    await env.manager.async_check()
    assert not env.calls and len(env.todos["todo.voice"].todo_items) == 1
    assert env.activity.record.call_args.args[0] == "gateway.error"
    env.fail["add"] = False
    env.manager._retry_at.clear()
    await env.manager.async_check()
    assert [kind for kind, _ in env.calls] == ["add", "remove"]


async def test_failed_cleanup_survives_restart_without_redelivery(env, hass, monkeypatch):
    await env.manager.async_configure("todo.voice", "todo.main", True)
    env.fail["remove"] = True
    env.todos["todo.voice"].add("a", "Cacao")
    await env.manager.async_check()
    assert [kind for kind, _ in env.calls] == ["add"]
    # Even if the user buys it while cleanup fails, retry only the source deletion.
    env.todos["todo.main"].todo_items[0].status = TodoItemStatus.COMPLETED
    await env.manager.async_stop()
    restored = GatewayLists(hass, env.settings, env.activity, asyncio.Lock())
    await restored.async_load()
    monkeypatch.setattr(restored, "_queue", Mock())
    restored.start()
    env.fail["remove"] = False
    await restored.async_check()
    assert [kind for kind, _ in env.calls] == ["add", "remove"]
    assert env.todos["todo.main"].todo_items[0].status == TodoItemStatus.COMPLETED
    await restored.async_stop()


async def test_new_items_while_offline_and_existing_baseline_persist(env, hass, monkeypatch):
    voice = env.todos["todo.voice"]
    voice.add("old", "Anterior")
    await env.manager.async_configure("todo.voice", "todo.main", False)
    await env.manager.async_stop()
    voice.add("offline", "Leche")
    restored = GatewayLists(hass, env.settings, env.activity, asyncio.Lock())
    await restored.async_load(); monkeypatch.setattr(restored, "_queue", Mock()); restored.start()
    await restored.async_check()
    assert [item.summary for item in env.todos["todo.main"].todo_items] == ["Leche"]
    await restored.async_stop()


async def test_two_gateways_share_deduplication_and_no_chains(env):
    await env.manager.async_configure("todo.voice", "todo.main", False)
    await env.manager.async_configure("todo.other", "todo.main", False)
    env.todos["todo.voice"].add("a", "Café")
    env.todos["todo.other"].add("b", "CAFE")
    await env.manager.async_check()
    assert len(env.todos["todo.main"].todo_items) == 1
    for source, target in [("todo.main", "todo.main"), ("todo.voice", "todo.voice"), ("todo.other", "todo.voice")]:
        with pytest.raises(ListSettingsError):
            await env.manager.async_configure(source, target, False)
    with pytest.raises(ListSettingsError): env.settings.update("remove", "todo.main")
    with pytest.raises(ListSettingsError): env.settings.update("add", "todo.voice")
    await env.manager.async_remove("todo.voice")
    env.todos["todo.voice"].add("new", "Pan")
    await env.manager.async_check()
    assert len(env.calls) == 1
    env.settings.update("add", "todo.voice")


async def test_reconfiguration_and_deleted_pending_do_not_import_old_items(env):
    voice = env.todos["todo.voice"]
    voice.add("old", "Anterior")
    await env.manager.async_configure("todo.voice", "todo.main", False)
    await env.manager.async_configure("todo.voice", "todo.other", True)
    voice.add("new", "Pan")
    voice.add("removed", "Cancelado")
    voice.todo_items = [item for item in voice.todo_items if item.uid != "removed"]
    voice.publish()
    await env.manager.async_check()
    assert [item.summary for item in env.todos["todo.other"].todo_items] == ["Pan"]
    assert [item.summary for item in voice.todo_items] == ["Anterior"]


async def test_live_subscription_runs_without_frontend(env, monkeypatch):
    monkeypatch.setattr(env.manager, "_queue", GatewayLists._queue.__get__(env.manager))
    await env.manager.async_configure("todo.voice", "todo.main", False)
    await env.manager._task
    env.todos["todo.voice"].add("a", "Cacao")
    await env.manager._task
    assert [item.summary for item in env.todos["todo.main"].todo_items] == ["Cacao"]


async def test_unavailable_destination_retries_and_capabilities_are_checked(env, hass):
    await env.manager.async_configure("todo.voice", "todo.main", True)
    hass.states.async_set("todo.main", "unavailable", {"supported_features": 7})
    env.todos["todo.voice"].add("a", "Pan")
    await env.manager.async_check()
    assert not env.calls and len(env.todos["todo.voice"].todo_items) == 1
    hass.states.async_set("todo.main", "0", {"supported_features": 7})
    env.manager._retry_at.clear(); await env.manager.async_check()
    assert len(env.todos["todo.main"].todo_items) == 1
    hass.states.async_set("todo.other", "0", {"supported_features": 1})
    with pytest.raises(ListSettingsError):
        await env.manager.async_configure("todo.other", "todo.main", True)


async def test_gateway_api_is_admin_only(hass, hass_ws_client, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    for index, fields in enumerate(({"type": f"{DOMAIN}/settings/gateway_save", "entity_id": "todo.voice",
        "target_entity": "todo.main", "remove_after_transfer": False},
        {"type": f"{DOMAIN}/settings/gateway_remove", "entity_id": "todo.voice"}), 1):
        await client.send_json({"id": index, **fields})
        assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert hass.data[DOMAIN]["settings"].snapshot["gateway_lists"] == []
    assert await hass.config_entries.async_unload(entry.entry_id)
