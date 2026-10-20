"""Persisted list membership, principal selection and authenticated settings API."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITIES, CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings, ListSettingsError


async def test_settings_migrate_persist_remove_and_restore(hass):
    hass.states.async_set("todo.bring", "1")
    hass.states.async_set("todo.local", "unavailable")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options={"unrelated": True})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    assert settings.snapshot == {"entities": ["todo.bring", "todo.local"], "primary_entity": "todo.bring"}
    settings.update("primary", "todo.local")
    settings.update("remove", "todo.bring")
    assert hass.states.get("todo.bring").state == "1"
    assert entry.options["unrelated"] is True
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot == {"entities": ["todo.local"], "primary_entity": "todo.local"}
    restored.update("add", "todo.bring")
    restored.update("add", "todo.bring")
    assert len(restored.snapshot["entities"]) == 2
    restored.update("remove", "todo.local")
    assert restored.snapshot["primary_entity"] == "todo.bring"
    restored.update("remove", "todo.bring")
    assert restored.snapshot == {"entities": [], "primary_entity": ""}
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
