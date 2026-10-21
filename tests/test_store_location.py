"""Fixed reference migration, isolation and authenticated activation."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings, DEFAULT_STORES
from custom_components.improved_shopping_list.store_location import REFERENCE_LOCATIONS, reference_location
from custom_components.improved_shopping_list.stores import StoreError


def configured(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options=options or {})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active": True}
    return settings, entry


async def test_migration_replaces_user_locations_and_errors_without_losing_preferences(hass, aioclient_mock):
    settings, entry = configured(hass, {
        "store_postal_code": "28024", "favorite_store": "consum", "unrelated": {"keep": True},
        "price_update_time": "03:15", "todo_entities": ["todo.bring"],
        "stores": {"consum": {"enabled": True, "postal_code": "28024", "area_id": "999D",
            "location_error": "Sin cobertura", "location_diagnostics": {"http_status": 403}},
            "mercadona": {"enabled": True, "warehouse": "mad3"}, "lidl": {"enabled": True}},
    })
    assert "store_postal_code" not in entry.options and "store_postal_code" not in settings.snapshot
    assert entry.options["unrelated"] == {"keep": True}
    assert settings.snapshot["favorite_store"] == "consum"
    assert settings.snapshot["price_update_time"] == "03:15"
    assert settings.snapshot["stores"]["consum"] == {"enabled": True, **reference_location("consum")}
    assert settings.snapshot["stores"]["mercadona"]["warehouse"] == "mad1"
    assert "lidl" not in settings.snapshot["stores"]
    assert aioclient_mock.call_count == 0
    before = dict(entry.options)
    settings.attach(entry)
    assert dict(entry.options) == before


@pytest.mark.parametrize("store", tuple(REFERENCE_LOCATIONS))
async def test_activation_repair_reload_and_disable_are_local(hass, aioclient_mock, store):
    settings, entry = configured(hass)
    await settings.async_toggle_located_store(store, True)
    assert await settings.async_ensure_store_location(store) == {"enabled": True, **reference_location(store)}
    assert settings.snapshot["favorite_store"] == store
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot["stores"] == settings.snapshot["stores"]
    await restored.async_toggle_located_store(store, False)
    assert restored.snapshot["stores"][store] == DEFAULT_STORES[store]
    assert restored.snapshot["favorite_store"] == ""
    with pytest.raises(StoreError):
        await restored.async_ensure_store_location(store)
    assert aioclient_mock.call_count == 0


async def test_legacy_configuration_cannot_override_reference_locations(hass, aioclient_mock):
    settings, entry = configured(hass)
    await settings.async_update_store(True, "46001", True)
    await settings.async_update_carrefour(True, "012345")
    await settings.async_update_alcampo(True, "invalid")
    await settings.async_update_regional("consum", True, "28024", "999D", True)
    for store in ("mercadona", "carrefour", "alcampo", "consum"):
        assert entry.options["stores"][store] == {"enabled": True, **reference_location(store)}
    assert aioclient_mock.call_count == 0


async def test_queued_activation_after_detach_cannot_write(hass):
    settings, entry = configured(hass)
    async with settings._stores_lock:
        task = asyncio.create_task(settings.async_toggle_located_store("consum", True))
        await asyncio.sleep(0)
        settings.detach()
        settings.attach(entry)
    with pytest.raises(StoreError):
        await task
    assert not settings.snapshot["stores"]["consum"]["enabled"]


def test_reference_configuration_is_not_shared_with_callers():
    location = reference_location("consum")
    location["area_id"] = "999D"
    assert reference_location("consum")["area_id"] == "301D"
    assert REFERENCE_LOCATIONS["carrefour"]["sale_point"] == "005704"


async def test_user_can_activate_fixed_store_but_cannot_set_a_shared_postcode(hass, hass_ws_client, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/store_enabled", "store": "consum", "enabled": True})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["stores"]["consum"]["postal_code"] == "46409"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/settings/store_postal", "postal_code": "28024"})
    assert not (await client.receive_json())["success"]
    assert aioclient_mock.call_count == 0


async def test_read_only_user_cannot_toggle_reference_store(hass, hass_ws_client, hass_read_only_user, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/store_enabled", "store": "consum", "enabled": True})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0
