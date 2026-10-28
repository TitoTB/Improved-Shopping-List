"""Persisted list membership, principal selection and authenticated settings API."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITIES, CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import DEFAULT_APPEARANCE, DEFAULT_STORES, DEFAULT_PURCHASE_DETECTION, ListSettings, ListSettingsError, normalize_appearance
from custom_components.improved_shopping_list import list_settings as settings_module
from custom_components.improved_shopping_list.stores import StoreError
from custom_components.improved_shopping_list.notification_settings import DEFAULT_NOTIFICATIONS


async def test_bring_name_policy_uses_registry_and_persists_explicit_overrides(hass):
    from homeassistant.helpers import entity_registry as er
    registry=er.async_get(hass)
    bring=registry.async_get_or_create('todo','bring','two-line-list',suggested_object_id='my_groceries')
    local=registry.async_get_or_create('todo','shopping_list','local-list',suggested_object_id='local_notes')
    for entity_id in (bring.entity_id,local.entity_id):hass.states.async_set(entity_id,'0')
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:bring.entity_id},options={CONF_TODO_ENTITIES:[bring.entity_id,local.entity_id]})
    entry.add_to_hass(hass)
    settings=ListSettings(hass);settings.attach(entry)
    assert settings.snapshot['description_as_name'] == {bring.entity_id:True}
    settings.update_name_mode(bring.entity_id,False)
    settings.update_name_mode(local.entity_id,True)
    restored=ListSettings(hass);restored.attach(entry)
    assert restored.snapshot['description_as_name'] == {bring.entity_id:False,local.entity_id:True}
    with pytest.raises(ListSettingsError):restored.update_name_mode('todo.missing',True)
    with pytest.raises(ListSettingsError):restored.update_name_mode(local.entity_id,1)


async def test_price_preferences_random_once_and_persisted(hass,monkeypatch):
    monkeypatch.setattr(settings_module,"randbelow",lambda maximum:1439)
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    settings=ListSettings(hass);settings.attach(entry)
    assert settings.snapshot["price_update_time"] == "23:59"
    settings.update_price_schedule("04:17",False,3)
    monkeypatch.setattr(settings_module,"randbelow",lambda maximum:0)
    restored=ListSettings(hass);restored.attach(entry)
    assert restored.snapshot["price_update_time"] == "04:17"
    assert restored.snapshot["price_updates_enabled"] is False and restored.snapshot["price_update_days"] == 3
    for days in (0,-1,True,1.5,3651):
        with pytest.raises(StoreError):restored.update_price_schedule("04:17",True,days)
    fresh=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.other"});fresh.add_to_hass(hass)
    another=ListSettings(hass);another.attach(fresh)
    assert another.snapshot["price_update_time"] == "00:00"


async def test_settings_migrate_persist_remove_and_restore(hass):
    hass.states.async_set("todo.bring", "1")
    hass.states.async_set("todo.local", "unavailable")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options={"unrelated": True,"price_update_time":"01:00","price_updates_enabled":True,"price_update_days":1})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    assert settings.snapshot == {"entities": ["todo.bring", "todo.local"], "primary_entity": "todo.bring", "gateway_lists": [], "purchase_detection":DEFAULT_PURCHASE_DETECTION, "notifications": DEFAULT_NOTIFICATIONS, "appearance": DEFAULT_APPEARANCE, "stores": DEFAULT_STORES, "favorite_store": "", "price_update_time":"01:00","price_updates_enabled":True,"price_update_days":1}
    settings.update("primary", "todo.local")
    settings.update("remove", "todo.bring")
    assert hass.states.get("todo.bring").state == "1"
    assert entry.options["unrelated"] is True
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot == {"entities": ["todo.local"], "primary_entity": "todo.local", "gateway_lists": [], "purchase_detection":DEFAULT_PURCHASE_DETECTION, "notifications": DEFAULT_NOTIFICATIONS, "appearance": DEFAULT_APPEARANCE, "stores": DEFAULT_STORES, "favorite_store": "", "price_update_time":"01:00","price_updates_enabled":True,"price_update_days":1}
    restored.update("add", "todo.bring")
    restored.update("add", "todo.bring")
    assert len(restored.snapshot["entities"]) == 2
    restored.update("remove", "todo.local")
    assert restored.snapshot["primary_entity"] == "todo.bring"
    restored.update("remove", "todo.bring")
    assert restored.snapshot == {"entities": [], "primary_entity": "", "gateway_lists": [], "purchase_detection":DEFAULT_PURCHASE_DETECTION, "notifications": DEFAULT_NOTIFICATIONS, "appearance": DEFAULT_APPEARANCE, "stores": DEFAULT_STORES, "favorite_store": "", "price_update_time":"01:00","price_updates_enabled":True,"price_update_days":1}
    empty = ListSettings(hass)
    empty.attach(entry)
    assert empty.snapshot == restored.snapshot  # Do not re-add deliberately removed lists on reload.
    empty.update("add", "todo.local")
    assert empty.snapshot["primary_entity"] == "todo.local"


async def test_settings_validate_and_snapshot_isolated(hass):
    hass.states.async_set("sensor.fake", "1")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.starting"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    snapshot = settings.snapshot
    snapshot["entities"].clear()
    assert settings.snapshot["entities"] == ["todo.starting"]
    for action, entity in [("add", "sensor.fake"), ("add", "todo.missing"), ("primary", "todo.other")]:
        with pytest.raises(ListSettingsError):
            settings.update(action, entity)
    assert settings.snapshot["primary_entity"] == "todo.starting"


async def test_settings_websocket_admin_push_and_unload(hass, hass_ws_client):
    hass.states.async_set("todo.bring", "1")
    hass.states.async_set("todo.local", "0")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"]["primary_entity"] == "todo.bring"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/settings/update", "action": "primary", "entity_id": "todo.local"})
    events = []
    while True:
        message = await client.receive_json()
        if message["id"] == 2:
            assert message["success"]
            assert message["result"]["primary_entity"] == "todo.local"
            break
        events.append(message)
    assert events[0]["event"]["primary_entity"] == "todo.local"
    await hass.async_block_till_done()
    assert entry.options[CONF_TODO_ENTITIES] == ["todo.bring", "todo.local"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 3, "type": f"{DOMAIN}/settings/get"})
    while (message := await client.receive_json())["id"] != 3:
        pass
    assert message["error"]["code"] == "not_loaded"


async def test_settings_cannot_be_changed_by_non_admin(hass, hass_ws_client, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    refresh_token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    access_token = hass.auth.async_create_access_token(refresh_token)
    client = await hass_ws_client(hass, access_token)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/get"})
    assert (await client.receive_json())["success"]
    await client.send_json({"id": 2, "type": f"{DOMAIN}/settings/update", "action": "remove", "entity_id": "todo.bring"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert entry.options[CONF_TODO_ENTITY] == "todo.bring"
    await client.send_json({"id": 3, "type": f"{DOMAIN}/settings/personalization", "appearance": DEFAULT_APPEARANCE})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("changes", [
    {"columns": 0}, {"columns": 7}, {"columns": True}, {"columns": "3"},
    {"mobile_columns": 5}, {"gradient_start": "red;display:none"}, {"gradient_end": "#123"},
    {"completed_gradient_start": "blue"}, {"completed_gradient_end": "#123"},
    {"stock_gradient_start": "red"}, {"stock_gradient_end": "#123"},
    {"extra": "value"},
])
def test_personalization_validation(changes):
    with pytest.raises(ListSettingsError):
        normalize_appearance({**DEFAULT_APPEARANCE, **changes})


async def test_personalization_persists_without_changing_lists(hass):
    hass.states.async_set("todo.bring", "1")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    changed = {"gradient_start": "#ABCDEF", "gradient_end": "#123456", "columns": 4, "mobile_columns": 2}
    settings.update_appearance(changed)
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot["appearance"] == {**DEFAULT_APPEARANCE, **changed, "gradient_start": "#abcdef"}
    assert restored.snapshot["entities"] == ["todo.bring"]
    restored.snapshot["appearance"]["columns"] = 1
    assert restored.snapshot["appearance"]["columns"] == 4
    settings.update("remove", "todo.bring")
    assert settings.snapshot["appearance"]["columns"] == 4


async def test_legacy_personalization_keeps_colors_and_gains_completed_defaults(hass):
    legacy = {"gradient_start": "#123456", "gradient_end": "#abcdef", "columns": 2, "mobile_columns": 2}
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options={"appearance": legacy})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    assert settings.snapshot["appearance"] == {**DEFAULT_APPEARANCE, **legacy}
    saved = {**settings.snapshot["appearance"], "completed_gradient_start": "#80cbc4", "completed_gradient_end": "#26a69a", "stock_gradient_start": "#ffcc80", "stock_gradient_end": "#ef6c00"}
    settings.update_appearance(saved)
    settings.update_appearance({**legacy, "columns": 4})  # An older open panel must retain the new colors.
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot["appearance"] == {**saved, "columns": 4}


async def test_personalization_websocket_push_validation_and_reload(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    writer = await hass_ws_client(hass)
    reader = await hass_ws_client(hass)
    await reader.send_json({"id": 1, "type": f"{DOMAIN}/settings/subscribe"})
    assert (await reader.receive_json())["success"]
    assert (await reader.receive_json())["event"]["appearance"] == DEFAULT_APPEARANCE
    appearance = {**DEFAULT_APPEARANCE, "columns": 5, "mobile_columns": 2}
    await writer.send_json({"id": 1, "type": f"{DOMAIN}/settings/personalization", "appearance": appearance})
    assert (await writer.receive_json())["result"]["appearance"] == appearance
    assert (await reader.receive_json())["event"]["appearance"] == appearance
    await writer.send_json({"id": 2, "type": f"{DOMAIN}/settings/personalization", "appearance": {**appearance, "columns": 0}})
    assert (await writer.receive_json())["error"]["code"] == "invalid_appearance"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert hass.data[DOMAIN]["settings"].snapshot["appearance"] == appearance


async def test_purchase_detection_configuration_validation_persistence_and_permissions(hass,hass_ws_client,hass_read_only_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    writer=await hass_ws_client(hass)
    await writer.send_json({"id":1,"type":f"{DOMAIN}/settings/purchase_detection","config":{"enabled":True,"threshold":7}})
    assert (await writer.receive_json())["result"]["purchase_detection"]=={**DEFAULT_PURCHASE_DETECTION,"enabled":True,"threshold":7}
    for index,value in enumerate((0,1001,True,1.5),start=2):
        await writer.send_json({"id":index,"type":f"{DOMAIN}/settings/purchase_detection","config":{"enabled":True,"threshold":value}})
        assert (await writer.receive_json())["error"]["code"]=="invalid_purchase_detection"
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    reader=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await reader.send_json({"id":1,"type":f"{DOMAIN}/settings/purchase_detection","config":{"enabled":False,"threshold":2}})
    assert (await reader.receive_json())["error"]["code"]=="unauthorized"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert hass.data[DOMAIN]["settings"].snapshot["purchase_detection"]=={**DEFAULT_PURCHASE_DETECTION,"enabled":True,"threshold":7}


async def test_purchase_zone_settings_validate_and_preserve_saved_mapping(hass):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    settings=ListSettings(hass);settings.entry=entry
    config={"enabled":True,"threshold":5,"zone_assignment":True,"persons":["person.ana","person.ana"],
        "store_zones":{"carrefour":["zone.market","zone.market"],"alcampo":[]}}
    result=settings.update_purchase_detection(config)["purchase_detection"]
    assert result["persons"]==["person.ana"] and result["store_zones"]["carrefour"]==["zone.market"]
    assert settings.update_purchase_detection({"enabled":True,"threshold":8})["purchase_detection"]["store_zones"]==result["store_zones"]
    for invalid in ({"persons":[]},{"persons":["sensor.phone"]},{"persons":"person.ana"},
                    {"zone_assignment":"yes"},{"store_zones":{"carrefour":["person.ana"]}},
                    {"store_zones":{"unknown":["zone.market"]}},{"store_zones":{"carrefour":"zone.market"}}):
        with pytest.raises(ListSettingsError):
            settings.update_purchase_detection({**config,**invalid})
