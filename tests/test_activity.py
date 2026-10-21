"""Observe actual item changes, keep bounded history and stop cleanly."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem
from homeassistant.core import Context
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.activity import ActivityLog, MAX_ENTRIES
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN


class Source:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.listeners = []

    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def notify(self):
        for listener in tuple(self.listeners):
            listener()


class Entity:
    def __init__(self):
        self.todo_items = [TodoItem(uid="initial", summary="Existente", status="needs_action")]
        self.listeners = []

    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def emit(self, items):
        self.todo_items = items
        for listener in tuple(self.listeners):
            listener(items)


@pytest.fixture
async def activity_env(hass):
    catalog = Source({"products": [], "categories": []})
    settings = Source({"entities": ["todo.test"], "primary_entity": "todo.test"})
    readers = Source({"readers": []})
    entity = Entity()
    hass.states.async_set("todo.test", "1", {"friendly_name": "La compra"})
    await hass.async_block_till_done()
    hass.data[DATA_COMPONENT] = SimpleNamespace(get_entity=lambda entity_id: entity if entity_id == "todo.test" else None)
    activity = ActivityLog(hass, catalog, settings, readers)
    await activity.async_load()
    activity.start()
    yield SimpleNamespace(activity=activity, entity=entity, catalog=catalog, settings=settings, readers=readers)
    await activity.async_stop()


async def test_actual_changes_include_same_count_updates_and_skip_initial_or_loading(activity_env):
    env = activity_env
    assert env.activity.snapshot["entries"] == []
    env.entity.emit(None)
    env.entity.emit([TodoItem(uid="initial", summary="Corregido", status="completed")])
    event = env.activity.snapshot["entries"][0]
    assert event["kind"] == "list.completed" and event["previous_name"] == "Existente"
    assert event["source"] == "external" and event["list_name"] == "La compra"
    env.entity.emit([TodoItem(uid="second", summary="Leche", status="needs_action")])
    assert {event["kind"] for event in env.activity.snapshot["entries"][:2]} == {"list.added", "list.removed"}
    count = len(env.activity.snapshot["entries"])
    env.entity.emit(deepcopy(env.entity.todo_items))
    assert len(env.activity.snapshot["entries"]) == count


async def test_real_service_context_identifies_automatic_reader_and_manual_changes(hass, activity_env):
    env = activity_env
    for source, context, name in (
        ("automatic", Context(parent_id="automation-parent"), "Arroz"),
        ("reader", env.activity.reader_context("Cocina"), "Cacao"),
        ("manual", Context(user_id="manual-user"), "Pan"),
    ):
        hass.bus.async_fire("call_service", {"domain": "todo", "service": "add_item", "service_data": {"entity_id": "todo.test", "item": name}}, context=context)
        await hass.async_block_till_done()
        # A request by itself is not a successful mutation.
        before = len(env.activity.snapshot["entries"])
        env.entity.emit([*(env.entity.todo_items or []), TodoItem(uid=name, summary=name, status="needs_action")])
        event = env.activity.snapshot["entries"][0]
        assert len(env.activity.snapshot["entries"]) == before + 1
        assert event["source"] == source
        if source == "reader":
            assert event["reader"] == "Cocina"


async def test_used_service_context_does_not_claim_later_external_changes(hass, activity_env):
    env = activity_env
    hass.bus.async_fire("call_service", {"domain": "todo", "service": "add_item", "service_data": {"entity_id": "todo.test", "item": "Pan"}}, context=Context(user_id="user"))
    await hass.async_block_till_done()
    env.entity.emit([TodoItem(uid="pan", summary="Pan", status="needs_action")])
    env.entity.emit([])
    env.entity.emit([TodoItem(uid="pan", summary="Pan", status="needs_action")])
    assert env.activity.snapshot["entries"][0]["source"] == "external"


async def test_catalog_categories_and_reader_configuration_logged_after_notifications(activity_env):
    env = activity_env
    category = {"id": "category", "name": "Despensa", "icon": "mdi:food", "color": "#267052", "revision": 1}
    env.catalog.snapshot["categories"].append(category)
    env.catalog.notify()
    category["name"] = "Comida"
    category["color"] = "#000000"
    env.catalog.notify()
    event = env.activity.snapshot["entries"][0]
    assert event["kind"] == "catalog.categories.updated"
    assert event["previous_name"] == "Despensa" and event["changed_fields"] == ["color", "name"]
    category["product_count"] = 2
    env.catalog.notify()
    assert env.activity.snapshot["entries"][0] == event
    env.readers.snapshot["readers"].append({"id": "reader", "name": "Cocina", "last": None})
    env.readers.notify()
    assert env.activity.snapshot["entries"][0]["kind"] == "reader.config"
    count = len(env.activity.snapshot["entries"])
    env.readers.snapshot["readers"][0]["last"] = {"message": "Lectura"}
    env.readers.notify()
    assert len(env.activity.snapshot["entries"]) == count


async def test_retention_persistence_snapshot_isolation_and_unsubscribe(hass, activity_env):
    env = activity_env
    for index in range(MAX_ENTRIES + 3):
        env.activity.record("reader.scan", str(index), source="reader")
    snapshot = env.activity.snapshot
    assert len(snapshot["entries"]) == MAX_ENTRIES and snapshot["entries"][0]["message"] == str(MAX_ENTRIES + 2)
    snapshot["entries"][0]["message"] = "Not stored"
    await env.activity.async_stop()
    assert env.entity.listeners == [] and env.catalog.listeners == []
    restored = ActivityLog(hass, env.catalog, env.settings, env.readers)
    await restored.async_load()
    assert restored.snapshot == env.activity.snapshot
    env.activity.record("reader.scan", "Stopped")
    assert env.activity.snapshot == restored.snapshot


async def test_removing_list_stops_observing_it(activity_env):
    env = activity_env
    env.settings.snapshot["entities"] = []
    env.settings.notify()
    assert env.entity.listeners == []
    count = len(env.activity.snapshot["entries"])
    env.entity.emit([])
    assert len(env.activity.snapshot["entries"]) == count


async def test_logs_websocket_initial_live_updates_and_unloaded_guard(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.test"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/logs/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"]["entries"] == []
    await hass.data[DOMAIN]["catalog"].async_save_category({"name": "Despensa"})
    event = (await client.receive_json())["event"]["entries"][0]
    assert event["kind"] == "catalog.categories.created" and event["category"] == "Despensa"
    await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 2, "type": f"{DOMAIN}/logs/get"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"


async def test_derived_store_location_updates_do_not_create_extra_activity_entries(activity_env):
    env=activity_env
    env.settings.snapshot["stores"]={"eroski":{"enabled":True,"postal_code":"28024","checked_at":1}}
    env.settings.notify()
    count=len(env.activity.snapshot["entries"])
    env.settings.snapshot["stores"]["eroski"].update(checked_at=2,location_error="HTTP 403",location_diagnostics={"endpoint":"/es/"})
    env.settings.notify()
    assert len(env.activity.snapshot["entries"])==count
    env.settings.snapshot["stores"]["eroski"]["enabled"]=False;env.settings.notify()
    assert len(env.activity.snapshot["entries"])==count+1


async def test_durable_summary_is_idempotent_after_failed_save_and_restart(activity_env,hass,monkeypatch):
    activity=activity_env.activity
    persist=activity._store.async_save
    monkeypatch.setattr(activity._store,"async_save",AsyncMock(side_effect=OSError("disk")))
    fields={"entry_id":"price-batch:test", "source":"manual", "diagnostics":{"batch_id":"test"}}
    with pytest.raises(OSError):await activity.async_record_durable("stores.summary","Resumen",**fields)
    assert len(activity.snapshot["entries"])==1
    monkeypatch.setattr(activity._store,"async_save",persist)
    assert await activity.async_record_durable("stores.summary","Resumen",**fields)
    restored=ActivityLog(hass,activity_env.catalog,activity_env.settings,activity_env.readers)
    await restored.async_load();restored._active=True
    assert await restored.async_record_durable("stores.summary","Resumen",**fields)
    assert len(restored.snapshot["entries"])==1
    # Older versions used a random event ID. Batch identity also prevents duplication.
    restored._entries[0]["id"]="old-random-id"
    assert await restored.async_record_durable("stores.summary","Resumen",**fields)
    assert len(restored.snapshot["entries"])==1
    await restored.async_stop()


