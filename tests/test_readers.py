"""Real HA events, durable scan protection, mappings and native todo actions."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, normalize_product
from custom_components.improved_shopping_list.activity import ActivityLog
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.readers import ReaderManager
from custom_components.improved_shopping_list import readers as readers_module


@pytest.fixture
async def reader_env(hass, monkeypatch):
    clock = [1800000000.0]
    monkeypatch.setattr(readers_module, "time", SimpleNamespace(time=lambda: clock[0]))
    for entity in ("todo.bring", "todo.local"):
        hass.states.async_set(entity, "0", {"supported_features": 5, "friendly_name": entity})
    hass.states.async_set("sensor.scanner", "")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    catalog = Catalog(hass)
    await catalog.async_load()
    manager = ReaderManager(hass, catalog, settings)
    monkeypatch.setattr(manager.lookup, "_fetch", AsyncMock(return_value={"status":"not_found"}))
    await manager.async_load()
    manager.start()
    calls = []
    items = {"todo.bring": [], "todo.local": []}

    async def get_items(call):
        return {call.data["entity_id"]:{"items":deepcopy(items[call.data["entity_id"]])}}

    async def add_item(call):
        calls.append(("add",dict(call.data)))
        items[call.data["entity_id"]].append({"uid":f"item-{len(calls)}","summary":call.data["item"],"status":"needs_action"})

    async def update_item(call):
        calls.append(("update",dict(call.data)))
        next(item for item in items[call.data["entity_id"]] if item["uid"]==call.data["item"])["status"]=call.data["status"]

    hass.services.async_register("todo","get_items",get_items,supports_response=SupportsResponse.ONLY)
    hass.services.async_register("todo","add_item",add_item)
    hass.services.async_register("todo","update_item",update_item)
    env = SimpleNamespace(manager=manager,catalog=catalog,settings=settings,clock=clock,calls=calls,items=items)
    yield env
    await manager.async_stop()


async def add_reader(env, **changes):
    return await env.manager.async_save_reader({"name":"Cocina","entity_id":"sensor.scanner",**changes})


async def test_reader_history_runs_without_open_panel(hass, reader_env):
    env = reader_env
    activity = ActivityLog(hass, env.catalog, env.settings, env.manager)
    await activity.async_load()
    env.manager.activity = activity
    activity.start()
    reader = await add_reader(env)
    await add_product(env, reader)
    await env.manager.async_process(reader["id"], "0012345")
    event = activity.snapshot["entries"][0]
    assert event["kind"] == "reader.scan" and event["source"] == "reader"
    assert event["reader"] == "Cocina" and event["product"] == "Cacao"
    assert "Añadido" in event["message"]
    await activity.async_stop()
    env.manager.activity = None


async def add_product(env, reader, **changes):
    return await env.catalog.async_save_product({"name":"Cacao","barcode":"0012345","barcodes":["0012346"],"nfc_tags":["AA:BB:CC:DD"],"reader_actions":{reader["id"]:"add_list"},**changes})


async def test_product_capture_suppresses_actions_and_suggestions_until_released(reader_env):
    env = reader_env
    reader = await add_reader(env, default_action="add_list")
    await add_product(env, reader)
    events = []
    stop = env.manager.capture(reader["id"], events.append)
    with pytest.raises(CatalogError, match="otra ficha"):
        env.manager.capture(reader["id"], lambda reading: None)
    await env.manager.async_process(reader["id"], "0012345")
    await env.manager.async_process(reader["id"], "unknown-new-code")
    await env.manager.async_process(reader["id"], "0012345")
    assert [event["code"] for event in events] == ["0012345", "unknown-new-code", "0012345"]
    assert all(event["kind"] == "barcode" and event["status"] == "scanned" for event in events)
    assert env.calls == [] and env.manager.snapshot["pending"] == []
    assert env.manager._data["cooldowns"] == {}
    stop(); stop()
    await env.manager.async_process(reader["id"], "0012345")
    assert len(env.calls) == 1


async def test_capture_receives_fresh_nfc_events_and_cancel_on_reader_change(hass, reader_env):
    env = reader_env
    reader = await add_reader(env, kind="nfc", source="tag", entity_id="", device_id="nfc-device")
    events = []
    env.manager.capture(reader["id"], events.append)
    hass.bus.async_fire("tag_scanned", {"device_id":"another-device", "tag_id":"ignored"})
    hass.bus.async_fire("tag_scanned", {"device_id":"nfc-device", "tag_id":"AA:BB:CC:DD"})
    await hass.async_block_till_done()
    assert len(events) == 1 and events[0]["kind"] == "nfc" and events[0]["code"] == "AA:BB:CC:DD"
    await env.manager.async_save_reader({**reader,"enabled":False})
    assert events[-1] == {"status":"cancelled"}
    with pytest.raises(CatalogError): env.manager.capture(reader["id"], events.append)


async def test_capture_expires_and_integration_stop_releases_reader(reader_env):
    env = reader_env
    reader = await add_reader(env)
    events = []
    env.manager.capture(reader["id"], events.append)
    # Fire the scheduled lease callback without waiting a real minute.
    env.manager._captures[reader["id"]]["timer"]._callback()
    assert events == [{"status":"expired"}] and not env.manager._captures
    env.manager.capture(reader["id"], events.append)
    await env.manager.async_stop()
    assert events[-1] == {"status":"cancelled"} and not env.manager._captures


async def test_default_action_adds_known_product_and_keeps_existing_guards(hass, reader_env):
    env = reader_env
    reader = await add_reader(env, default_action="add_list", list_entity="todo.local")
    await add_product(env, reader, reader_actions={})
    await env.manager.async_process(reader["id"], "0012345")
    assert env.calls == [("add", {"entity_id":"todo.local", "item":"Cacao"})]
    await env.manager.async_process(reader["id"], "0012346")
    assert len(env.calls) == 1
    assert "repetida" in env.manager.snapshot["readers"][0]["last"]["message"]
    env.clock[0] += 61
    await env.manager.async_process(reader["id"], "0012346")
    assert len(env.calls) == 1  # No duplicate pending list entry after the cooldown.
    assert env.catalog.products[0]["reader_actions"] == {}  # Inheritance stays dynamic.
    restored = ReaderManager(hass, env.catalog, env.settings)
    await restored.async_load()
    assert restored.snapshot["readers"][0]["default_action"] == "add_list"
    await env.manager.async_save_reader({**reader,"default_action":"stock_remove"})
    env.clock[0] += 61
    await env.manager.async_process(reader["id"], "0012345")
    assert "inventario pendiente" in env.manager.snapshot["readers"][0]["last"]["message"]
    assert len(env.calls) == 1


@pytest.mark.parametrize("override", ["none", "stock_remove", "stock_add"])
async def test_explicit_product_action_overrides_reader_default(reader_env, override):
    env = reader_env
    reader = await add_reader(env, default_action="add_list")
    await add_product(env, reader, reader_actions={reader["id"]:override})
    await env.manager.async_process(reader["id"], "0012345")
    assert env.calls == []
    message = env.manager.snapshot["readers"][0]["last"]["message"]
    assert ("Sin acción" if override == "none" else "inventario pendiente") in message


@pytest.mark.parametrize("default_action", ["stock_remove", "stock_add"])
async def test_default_stock_action_is_reserved_without_touching_lists(reader_env, default_action):
    env = reader_env
    reader = await add_reader(env, default_action=default_action)
    await add_product(env, reader, reader_actions={})
    await env.manager.async_process(reader["id"], "0012345")
    assert env.calls == []
    assert "inventario pendiente" in env.manager.snapshot["readers"][0]["last"]["message"]


async def test_default_action_does_not_associate_unknown_codes(reader_env):
    env = reader_env
    reader = await add_reader(env, default_action="add_list")
    await env.manager.async_process(reader["id"], "unknown-product-code")
    assert env.calls == [] and env.catalog.products == []
    assert env.manager.snapshot["pending"][0]["code"] == "unknown-product-code"


async def test_old_reader_migration_and_old_client_toggle_preserve_default(hass, reader_env):
    env = reader_env
    reader = await add_reader(env)
    del env.manager._data["readers"][reader["id"]]["default_action"]
    await env.manager._store.async_save(env.manager._data)
    restored = ReaderManager(hass, env.catalog, env.settings)
    await restored.async_load()
    legacy = restored.snapshot["readers"][0]
    assert legacy["default_action"] == "none"
    saved = await env.manager.async_save_reader({**reader, "default_action":"add_list"})
    old_payload = {key:value for key,value in saved.items() if key != "default_action"}
    saved = await env.manager.async_save_reader({**old_payload,"enabled":False})
    assert saved["default_action"] == "add_list" and saved["enabled"] is False
    await add_product(env, saved, reader_actions={})
    await env.manager.async_process(saved["id"], "0012345")
    assert env.calls == []


@pytest.mark.parametrize("invalid", ["default", "delete", "", None, {}, []])
async def test_invalid_default_action_is_rejected_without_saving(reader_env, invalid):
    with pytest.raises(CatalogError, match="acción por defecto"):
        await add_reader(reader_env, default_action=invalid)
    assert reader_env.manager.snapshot["readers"] == []


async def test_lookup_enriches_unknown_scan_without_associating_or_adding(hass, reader_env, monkeypatch):
    env=reader_env
    reader=await add_reader(env)
    fetch=AsyncMock(return_value={"status":"found","name":"Cacao soluble"})
    monkeypatch.setattr(env.manager.lookup,"_fetch",fetch)
    await env.manager.async_process(reader["id"],"3017620422003")
    await asyncio.gather(*tuple(env.manager._tasks))
    pending=env.manager.snapshot["pending"][0]
    assert pending["identification"]["name"] == "Cacao soluble"
    assert env.catalog.products == [] and env.calls == []
    env.clock[0]+=61
    await env.manager.async_process(reader["id"],"3017620422003")
    assert fetch.await_count == 1 and len(env.manager.snapshot["pending"]) == 1
    restored=ReaderManager(hass,env.catalog,env.settings)
    await restored.async_load()
    assert restored.snapshot["pending"][0]["identification"]["name"] == "Cacao soluble"


async def test_pending_lookup_does_not_block_known_scans_or_restore_dismissed_items(hass, reader_env, monkeypatch):
    env=reader_env
    reader=await add_reader(env)
    await add_product(env,reader)
    started,release=asyncio.Event(),asyncio.Event()
    async def slow_fetch(code):
        started.set()
        await release.wait()
        return {"status":"not_found"}
    monkeypatch.setattr(env.manager.lookup,"_fetch",slow_fetch)
    await env.manager.async_process(reader["id"],"3017620422003")
    await asyncio.wait_for(started.wait(),2)
    pending=env.manager.snapshot["pending"][0]
    assert pending["identification"]["status"] == "pending"
    await env.manager.async_process(reader["id"],"0012345")
    assert len(env.calls) == 1
    await env.manager.async_dismiss(pending["id"])
    release.set()
    await asyncio.gather(*tuple(env.manager._tasks))
    assert env.manager.snapshot["pending"] == []


async def test_reader_entity_events_add_once_and_restore_completed(hass, reader_env):
    env=reader_env
    reader=await add_reader(env)
    await add_product(env,reader)
    hass.states.async_set("sensor.scanner","0012345")
    await hass.async_block_till_done()
    assert len(env.calls)==1 and env.calls[0][1]["entity_id"]=="todo.bring"
    assert env.items["todo.bring"][0]["summary"]=="Cacao"
    # A second code for the same product is guarded by reader/product, not just raw code.
    hass.states.async_set("sensor.scanner","0012346")
    await hass.async_block_till_done()
    assert len(env.calls)==1
    assert "repetida" in env.manager.snapshot["readers"][0]["last"]["message"]
    env.clock[0]+=61
    hass.states.async_set("sensor.scanner","0012345")
    await hass.async_block_till_done()
    assert len(env.calls)==1  # Already pending: never insert a second entry.
    env.items["todo.bring"][0]["status"]="completed"
    env.clock[0]+=61
    hass.states.async_set("sensor.scanner","0012345",force_update=True)
    await hass.async_block_till_done()
    assert env.calls[-1][0]=="update"
    assert env.calls[-1][1]["item"]==env.items["todo.bring"][0]["uid"]
    assert env.items["todo.bring"][0]["status"]=="needs_action"
    assert len(env.items["todo.bring"])==1


async def test_reader_per_reader_targets_and_cross_reader_no_duplicates(hass, reader_env):
    env=reader_env
    first=await add_reader(env,list_entity="todo.local")
    hass.states.async_set("sensor.second", "")
    second=await add_reader(env,name="Despensa",entity_id="sensor.second",list_entity="todo.local")
    await add_product(env,first,reader_actions={first["id"]:"add_list",second["id"]:"add_list"})
    await asyncio.gather(env.manager.async_process(first["id"],"0012345"),env.manager.async_process(second["id"],"0012345"))
    assert len(env.calls)==1 and env.calls[0][1]["entity_id"]=="todo.local"
    assert len(env.items["todo.local"])==1 and env.items["todo.bring"]==[]


async def test_reader_rejects_duplicate_sources_and_invalid_config(reader_env):
    env=reader_env
    await add_reader(env)
    with pytest.raises(CatalogError,match="Ya hay"):
        await add_reader(env,name="Duplicado")
    for changes in ({"cooldown":0},{"cooldown":True},{"entity_id":"sensor.missing"},{"kind":"other"},{"list_entity":"todo.missing"},{"source":"tag","kind":"nfc","device_id":""}):
        with pytest.raises(CatalogError):
            await add_reader(env,**changes)


async def test_unknown_codes_suggestions_association_and_dismissal(hass, reader_env):
    env=reader_env
    reader=await add_reader(env)
    await env.manager.async_process(reader["id"],"00009999")
    pending=env.manager.snapshot["pending"]
    assert len(pending)==1 and pending[0]["code"]=="00009999"
    assert env.calls==[]
    env.clock[0]+=61
    await env.manager.async_process(reader["id"],"00009999")
    assert len(env.manager.snapshot["pending"])==1
    await add_product(env,reader,barcode="00009999")
    await hass.async_block_till_done()
    assert env.manager.snapshot["pending"]==[]
    assert env.calls==[]  # Associating a past scan never replays an action.
    env.clock[0]+=61
    await env.manager.async_process(reader["id"],"new-unknown")
    pending=env.manager.snapshot["pending"][0]
    await env.manager.async_dismiss(pending["id"])
    env.clock[0]+=61
    await env.manager.async_process(reader["id"],"new-unknown")
    assert env.manager.snapshot["pending"]==[]


async def test_nfc_events_and_attribute_entities(hass, reader_env):
    env=reader_env
    nfc=await add_reader(env,name="NFC",kind="nfc",source="tag",device_id="device-1")
    await add_product(env,nfc)
    hass.bus.async_fire("tag_scanned",{"device_id":"other-device","tag_id":"aa-bb-cc-dd"})
    await hass.async_block_till_done()
    assert env.calls==[]
    hass.bus.async_fire("tag_scanned",{"device_id":"device-1","tag_id":"aa-bb-cc-dd"})
    await hass.async_block_till_done()
    assert len(env.calls)==1
    hass.states.async_set("event.scanner","first",{"code":""})
    attribute=await add_reader(env,name="Atributo",entity_id="event.scanner",attribute="code")
    hass.states.async_set("event.scanner","second",{"code":"https://example.test/qr/001"})
    await hass.async_block_till_done()
    assert env.manager.snapshot["pending"][0]["code"]=="https://example.test/qr/001"
    assert env.manager.snapshot["pending"][0]["reader_id"]==attribute["id"]


async def test_stock_disabled_and_durable_cooldown(hass, reader_env):
    env=reader_env
    reader=await add_reader(env)
    await add_product(env,reader,reader_actions={reader["id"]:"stock_remove"})
    await env.manager.async_process(reader["id"],"0012345")
    assert env.calls==[]
    assert "inventario pendiente" in env.manager.snapshot["readers"][0]["last"]["message"]
    await env.manager.async_stop()
    restored=ReaderManager(hass,env.catalog,env.settings)
    await restored.async_load()
    restored.start()
    try:
        await restored.async_process(reader["id"],"0012346")
        assert "repetida" in restored.snapshot["readers"][0]["last"]["message"]
        saved=await restored.async_save_reader({**reader,"enabled":False})
        env.clock[0]+=61
        await restored.async_process(reader["id"],"new")
        assert restored.snapshot["pending"]==[]
        with pytest.raises(CatalogError,match="cambiado"):
            await restored.async_delete_reader(reader["id"],reader["revision"])
        await restored.async_delete_reader(saved["id"],saved["revision"])
        assert restored.snapshot["readers"]==[]
    finally:
        await restored.async_stop()


async def test_reader_disk_failure_and_unavailable_target_are_not_silent(hass, reader_env, monkeypatch):
    env=reader_env
    reader=await add_reader(env)
    await add_product(env,reader)
    save=env.manager._store.async_save
    monkeypatch.setattr(env.manager._store,"async_save",AsyncMock(side_effect=OSError("Disk full")))
    await env.manager.async_process(reader["id"],"0012345")
    assert env.calls==[]
    assert "No se pudo" in env.manager.snapshot["readers"][0]["last"]["message"]
    monkeypatch.setattr(env.manager._store,"async_save",save)
    hass.states.async_set("todo.bring","unavailable",{"supported_features":5})
    await env.manager.async_process(reader["id"],"0012345")
    assert env.calls==[]
    assert "No se pudo" in env.manager.snapshot["readers"][0]["last"]["message"]


async def test_multiple_codes_uniqueness_and_legacy_edits(hass):
    catalog=Catalog(hass)
    await catalog.async_load()
    product=await catalog.async_save_product({"name":"Cacao","barcode":"001","barcodes":["002","002"],"nfc_tags":["AA:BB:CC:DD"],"reader_actions":{"reader-1":"stock_add"}})
    assert product["barcodes"]==["002"]
    assert catalog.find_by_code("nfc","aa-bb-cc-dd")["id"]==product["id"]
    with pytest.raises(CatalogError,match="Ya existe"):
        await catalog.async_save_product({"name":"Otro","barcode":"002"})
    with pytest.raises(CatalogError,match="Ya existe"):
        await catalog.async_save_product({"name":"Otro","nfc_tags":["aabbccdd"]})
    legacy={key:value for key,value in product.items() if key in {"id","revision","name","category","tags","brand","barcode","format","price","currency","image_url","icon","notes"}}
    updated=await catalog.async_save_product({**legacy,"name":"Cacao puro"})
    assert updated["barcodes"]==["002"] and updated["nfc_tags"]==["AA:BB:CC:DD"]
    assert updated["reader_actions"]=={"reader-1":"stock_add"}


@pytest.mark.parametrize("changes",[{"barcodes":"123"},{"nfc_tags":["x\ny"]},{"reader_actions":{"r":{}}},{"reader_actions":{"r":"execute_shell"}}])
def test_code_fields_validation(changes):
    with pytest.raises(CatalogError):
        normalize_product({"name":"Cacao",**changes})


async def test_reader_websocket_admin_and_reload(hass,hass_ws_client,hass_read_only_user):
    hass.states.async_set("sensor.scanner","")
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/readers/save","reader":{"name":"Cocina","entity_id":"sensor.scanner","default_action":"add_list"}})
    saved=(await client.receive_json())["result"]
    assert saved["cooldown"]==60
    assert saved["default_action"]=="add_list"
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    readonly=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await readonly.send_json({"id":1,"type":f"{DOMAIN}/readers/delete","reader_id":saved["id"],"revision":saved["revision"]})
    assert (await readonly.receive_json())["error"]["code"]=="unauthorized"
    await readonly.send_json({"id":2,"type":f"{DOMAIN}/readers/capture","reader_id":saved["id"]})
    assert (await readonly.receive_json())["error"]["code"]=="unauthorized"
    await client.send_json({"id":2,"type":f"{DOMAIN}/readers/capture","reader_id":saved["id"]})
    assert (await client.receive_json())["success"] is True
    hass.states.async_set("sensor.scanner","captured-code")
    await hass.async_block_till_done()
    event = (await client.receive_json())["event"]
    assert event["code"] == "captured-code" and event["kind"] == "barcode"
    manager = hass.data[DOMAIN]["readers"]
    assert manager.snapshot["pending"] == []
    await client.send_json({"id":3,"type":"unsubscribe_events","subscription":2})
    assert (await client.receive_json())["success"] is True
    assert not manager._captures
    await client.send_json({"id":4,"type":f"{DOMAIN}/readers/capture","reader_id":saved["id"]})
    assert (await client.receive_json())["success"] is True
    await client.close()
    await hass.async_block_till_done()
    assert not manager._captures
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert hass.data[DOMAIN]["readers"].snapshot["readers"][0]["id"]==saved["id"]
    assert hass.data[DOMAIN]["readers"].snapshot["readers"][0]["default_action"]=="add_list"
