"""Threshold notifications: multiple lists, multiple targets, restart latches and failures."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, CONF_TODO_ENTITIES, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.notification_settings import DEFAULT_NOTIFICATIONS, normalize_notifications
from custom_components.improved_shopping_list.notifications import NotificationManager


class Todo:
    def __init__(self):
        self.todo_items, self.listeners = [], []
    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)
    def emit(self, count, completed=0):
        self.todo_items = [TodoItem(uid=str(index), summary=f"Producto {index}", status=TodoItemStatus.NEEDS_ACTION if index < count else TodoItemStatus.COMPLETED)
                           for index in range(count + completed)]
        for listener in tuple(self.listeners):
            listener(self.todo_items)


class Stock:
    def __init__(self):
        self.snapshot, self.listeners = {"items": []}, []
    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)
    def emit(self, count):
        self.snapshot = {"items": [{"name": f"Despensa {index}", "configured": True, "mode": "manual", "quantity": 0,
                                    "reorder_at": 1, "reorder_enabled": True} for index in range(count)]}
        for listener in tuple(self.listeners):
            listener()


class SnapshotSource:
    def __init__(self, snapshot):
        self.snapshot, self.listeners = snapshot, []
    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)
    def emit(self, snapshot):
        self.snapshot = snapshot
        for listener in tuple(self.listeners):
            listener()


async def settled(manager):
    for _ in range(10):
        task = manager._task
        if task is None:
            return
        await task


@pytest.fixture
async def env(hass):
    todos = {key: Todo() for key in ("todo.main", "todo.other")}
    for key, name in (("todo.main", "Compra principal"), ("todo.other", "Otra compra")):
        hass.states.async_set(key, "0", {"friendly_name": name, "supported_features": 7})
    hass.data[DATA_COMPONENT] = SimpleNamespace(get_entity=todos.get)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"}, options={CONF_TODO_ENTITIES: list(todos)})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    stock, activity, sent = Stock(), SimpleNamespace(record=Mock()), []
    async def notify(call):
        sent.append((call.service, dict(call.data)))
    for service in ("mobile_app_one", "mobile_app_two", "send_message"):
        hass.services.async_register("notify", service, notify)
    catalog = SnapshotSource({"products": [], "dismissed_suggestions": []})
    readers = SnapshotSource({"pending": []})
    manager = NotificationManager(hass, settings, stock, activity, catalog, readers)
    await manager.async_load()
    manager.start()
    await settled(manager)
    yield SimpleNamespace(manager=manager, settings=settings, stock=stock, todos=todos, sent=sent, activity=activity, catalog=catalog, readers=readers)
    await manager.async_stop()
    settings.detach()


def configure(env, kind="shopping_list", threshold=2, targets=None):
    config = deepcopy(DEFAULT_NOTIFICATIONS)
    config[kind].update(enabled=True, threshold=threshold, targets=targets or ["service:notify.mobile_app_one", "service:notify.mobile_app_two"])
    env.settings.update_notifications(config)


async def test_notifications_watch_each_list_once_and_ignore_completed_quantities(hass, env):
    configure(env)
    await settled(env.manager)
    env.todos["todo.main"].emit(2, completed=5)
    await settled(env.manager)
    assert env.sent == []
    env.todos["todo.main"].emit(3)
    env.todos["todo.other"].emit(3)
    await settled(env.manager)
    assert len(env.sent) == 4
    assert {data["message"] for _, data in env.sent} == {"Compra principal tiene 3 productos pendientes.", "Otra compra tiene 3 productos pendientes."}
    env.todos["todo.main"].emit(8)
    await settled(env.manager)
    assert len(env.sent) == 4
    env.todos["todo.other"].emit(2)
    await settled(env.manager)
    env.todos["todo.other"].emit(3)
    await settled(env.manager)
    assert len(env.sent) == 6
    await env.manager.async_stop()
    assert not any(todo.listeners for todo in env.todos.values())
    assert env.stock.listeners == []


async def test_low_stock_threshold_custom_message_and_notify_entities(hass, env):
    hass.states.async_set("notify.phone", "unknown", {"friendly_name": "Teléfono"})
    config = deepcopy(DEFAULT_NOTIFICATIONS)
    config["low_stock"].update(enabled=True, threshold=1, targets=["entity:notify.phone"], title="Stock: {cantidad}", message="Mínimo {limite}: {productos}")
    env.settings.update_notifications(config)
    await settled(env.manager)
    env.stock.emit(1)
    await settled(env.manager)
    assert env.sent == []
    env.stock.emit(2)
    await settled(env.manager)
    assert env.sent == [("send_message", {"entity_id": "notify.phone", "title": "Stock: 2", "message": "Mínimo 1: Despensa 0, Despensa 1"})]
    env.stock.emit(3)
    await settled(env.manager)
    assert len(env.sent) == 1
    env.stock.emit(1)
    await settled(env.manager)
    env.stock.emit(2)
    await settled(env.manager)
    assert len(env.sent) == 2


async def test_notification_latches_survive_restart_and_unavailable_lists(hass, env):
    configure(env)
    await settled(env.manager)
    env.todos["todo.main"].emit(3)
    await settled(env.manager)
    assert len(env.sent) == 2
    await env.manager.async_stop()
    restored = NotificationManager(hass, env.settings, env.stock, env.activity)
    await restored.async_load()
    restored.start()
    try:
        await settled(restored)
        assert len(env.sent) == 2
        hass.states.async_set("todo.main", "unavailable")
        await hass.async_block_till_done()
        await settled(restored)
        hass.states.async_set("todo.main", "3", {"friendly_name": "Compra principal"})
        await hass.async_block_till_done()
        await settled(restored)
        assert len(env.sent) == 2
        env.todos["todo.main"].emit(1)
        await settled(restored)
        env.todos["todo.main"].emit(3)
        await settled(restored)
        assert len(env.sent) == 4
    finally:
        await restored.async_stop()


async def test_notification_failure_is_logged_and_other_destinations_still_receive(hass, env):
    async def fail(call):
        raise HomeAssistantError("Teléfono desconectado")
    hass.services.async_register("notify", "mobile_app_one", fail)
    configure(env)
    await settled(env.manager)
    env.todos["todo.main"].emit(3)
    await settled(env.manager)
    assert len(env.sent) == 1 and env.sent[0][0] == "mobile_app_two"
    event = env.activity.record.call_args
    assert event.args[0] == "notification.error"
    assert event.kwargs["diagnostics"]["failed"][0]["target"] == "service:notify.mobile_app_one"
    env.todos["todo.main"].emit(4)
    await settled(env.manager)
    assert len(env.sent) == 1


async def test_notification_state_write_failure_prevents_delivery(hass, env, monkeypatch):
    configure(env)
    await settled(env.manager)
    old = deepcopy(env.manager._above)
    monkeypatch.setattr(env.manager._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    env.todos["todo.main"].emit(3)
    await settled(env.manager)
    assert env.sent == [] and env.manager._above == old


async def test_notifications_are_opt_in_and_rules_can_rearm_on_changed_threshold(hass, env):
    env.todos["todo.main"].emit(5)
    env.stock.emit(5)
    await settled(env.manager)
    assert env.sent == []
    configure(env)
    await settled(env.manager)
    assert len(env.sent) == 2
    configure(env, threshold=3)
    await settled(env.manager)
    assert len(env.sent) == 4
    env.settings.update_notifications(deepcopy(DEFAULT_NOTIFICATIONS))
    await settled(env.manager)
    env.todos["todo.main"].emit(10)
    await settled(env.manager)
    assert len(env.sent) == 4


@pytest.mark.parametrize("changes", [
    {"threshold": True}, {"threshold": -1}, {"threshold": 1.5}, {"threshold": 100001},
    {"targets": ["service:light.turn_on"]}, {"targets": ["service:notify.notify"]}, {"targets": "phone"},
    {"enabled": True, "targets": []}, {"enabled": True, "targets": ["service:notify.mobile_app_one"], "message": " "},
    {"title": "x" * 161}, {"message": "x" * 2001}, {"unexpected": True},
])
def test_notification_rule_validation(changes):
    data = deepcopy(DEFAULT_NOTIFICATIONS)
    data["shopping_list"].update(changes)
    with pytest.raises(ValueError):
        normalize_notifications(data)


async def test_notification_config_websocket_is_admin_only_and_durable(hass, hass_ws_client, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    config = deepcopy(DEFAULT_NOTIFICATIONS)
    config["shopping_list"].update(enabled=True, targets=["service:notify.mobile_app_one"])
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/notifications", "notifications": config})
    assert (await client.receive_json())["result"]["notifications"] == config
    assert entry.options["notifications"] == config
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    readonly = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    await readonly.send_json({"id": 1, "type": f"{DOMAIN}/settings/notifications", "notifications": config})
    assert (await readonly.receive_json())["error"]["code"] == "unauthorized"


async def test_new_catalog_products_include_scans_and_unique_names_and_exclude_known_and_dismissed(hass, env):
    env.catalog.emit({"products": [{"name": "Seitán", "barcode": "known", "nfc_tags": ["AA:BB"]}], "dismissed_suggestions": ["AGUACATE"]})
    for key, names in (("todo.main", [" SEITAN ", "Arroz", "arroz", "aguacate"]), ("todo.other", ["ARROZ", "Leche"])):
        todo = env.todos[key]
        todo.todo_items = [TodoItem(uid=str(index), summary=name, status=TodoItemStatus.COMPLETED if name == "Leche" else TodoItemStatus.NEEDS_ACTION) for index, name in enumerate(names)]
    env.readers.emit({"pending": [{"kind": "barcode", "code": "known"}, {"kind": "nfc", "code": "aa-bb"},
                                  {"kind": "barcode", "code": "new", "identification": {"name": "Cacao"}},
                                  {"kind": "barcode", "code": "new"}]})
    config = deepcopy(DEFAULT_NOTIFICATIONS)
    config["catalog_new"].update(enabled=True, threshold=2, targets=["service:notify.mobile_app_one"], message="{lista}: {cantidad} · {productos}")
    env.settings.update_notifications(config)
    await settled(env.manager)
    assert env.sent == [("mobile_app_one", {"title": "Productos nuevos", "message": "Catálogo: 3 · Arroz, Leche, Cacao"})]
    assert not config["shopping_list"]["enabled"] and all(todo.listeners for todo in env.todos.values())
    env.readers.emit({"pending": [{"kind": "barcode", "code": "new"}, {"kind": "nfc", "code": "other"}]})
    await settled(env.manager)
    assert len(env.sent) == 1
    env.readers.emit({"pending": []})
    await settled(env.manager)
    assert env.manager._above["catalog_new"]["above"] is False
    env.readers.emit({"pending": [{"kind": "nfc", "code": "other"}]})
    await settled(env.manager)
    assert len(env.sent) == 2
    assert env.activity.record.call_args.args[1] == "Aviso de productos nuevos · enviado"
    await env.manager.async_stop()
    assert env.catalog.listeners == [] and env.readers.listeners == []


async def test_catalog_changes_rearm_new_products_and_restart_does_not_repeat(hass, env):
    env.todos["todo.main"].emit(1)
    configure(env, kind="catalog_new", threshold=0, targets=["service:notify.mobile_app_one"])
    await settled(env.manager)
    assert len(env.sent) == 1
    await env.manager.async_stop()
    restored = NotificationManager(hass, env.settings, env.stock, env.activity, env.catalog, env.readers)
    await restored.async_load()
    restored.start()
    try:
        await settled(restored)
        assert len(env.sent) == 1
        hass.states.async_set("todo.other", "unavailable")
        await hass.async_block_till_done()
        await settled(restored)
        hass.states.async_set("todo.other", "0")
        await hass.async_block_till_done()
        await settled(restored)
        assert len(env.sent) == 1
        env.catalog.emit({"products": [{"name": "Producto 0"}], "dismissed_suggestions": []})
        await settled(restored)
        env.catalog.emit({"products": [], "dismissed_suggestions": ["Producto 0"]})
        await settled(restored)
        assert len(env.sent) == 1
        env.catalog.emit({"products": [], "dismissed_suggestions": []})
        await settled(restored)
        assert len(env.sent) == 2
    finally:
        await restored.async_stop()


def test_legacy_notification_panels_keep_new_rule_settings():
    config = deepcopy(DEFAULT_NOTIFICATIONS)
    config["catalog_new"].update(enabled=True, targets=["service:notify.mobile_app_one"])
    legacy = {key: value for key, value in config.items() if key != "catalog_new"}
    assert normalize_notifications(legacy)["catalog_new"] == DEFAULT_NOTIFICATIONS["catalog_new"]
    assert normalize_notifications(legacy, config) == config
