"""Mercadona discovery, persistence and authenticated writes without live HTTP."""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings, DEFAULT_STORES
from custom_components.improved_shopping_list.stores import POSTAL_URL, StoreError, async_resolve_mercadona


async def test_carrefour_migration_and_favorite_do_not_erase_mercadona(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options={
        "stores": {"mercadona": {"enabled": True, "postal_code": "28001", "warehouse": "mad3"}},
        "favorite_store": "mercadona", "unrelated": True})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active": True}
    assert settings.snapshot["stores"]["carrefour"] == DEFAULT_STORES["carrefour"]
    await settings.async_update_carrefour(True)
    assert settings.snapshot["favorite_store"] == "mercadona"
    await settings.async_favorite_store("carrefour")
    assert settings.snapshot["favorite_store"] == "carrefour"
    await settings.async_update_carrefour(False)
    assert settings.snapshot["favorite_store"] == "mercadona"
    assert settings.snapshot["stores"]["mercadona"]["warehouse"] == "mad1"
    assert entry.options["unrelated"] is True
    with pytest.raises(StoreError):
        await settings.async_favorite_store("carrefour")


async def test_resolves_header_even_when_warehouse_changed_is_false(hass, aioclient_mock):
    aioclient_mock.put(POSTAL_URL, json={"warehouse_changed": False},
                      headers={"x-customer-wh": "mad3", "x-customer-pc": "28001"})
    assert await async_resolve_mercadona(hass, "28001") == "mad3"
    request = aioclient_mock.mock_calls[0]
    assert request[0] == "PUT"
    assert str(request[1]) == POSTAL_URL


@pytest.mark.parametrize("postal", ["", "2801", "280001", "00000", "53001", "２８００１", "28001?x=1"])
async def test_invalid_postals_do_not_make_requests(hass, aioclient_mock, postal):
    with pytest.raises(StoreError):
        await async_resolve_mercadona(hass, postal)
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(("status", "body", "headers"), [
    (400, {}, {}), (404, {}, {}), (422, {}, {}), (429, {}, {}), (500, {}, {}), (302, {}, {}),
    (200, {}, {"x-customer-wh": "mad3"}),
    (200, {"warehouse_changed": False}, {}),
    (200, {"warehouse_changed": False}, {"x-customer-wh": "../invalid"}),
    (200, {"warehouse_changed": False}, {"x-customer-wh": "mad3", "x-customer-pc": "46001"}),
])
async def test_errors_never_fall_back_to_a_default_warehouse(hass, aioclient_mock, status, body, headers):
    aioclient_mock.put(POSTAL_URL, json=body, headers=headers, status=status)
    with pytest.raises(StoreError):
        await async_resolve_mercadona(hass, "28001")


async def test_timeout(hass, aioclient_mock):
    aioclient_mock.put(POSTAL_URL, exc=asyncio.TimeoutError())
    with pytest.raises(StoreError):
        await async_resolve_mercadona(hass, "28001")


@pytest.mark.parametrize("body", ["not json", "x" * 65537])
async def test_malformed_or_oversized_body(hass, aioclient_mock, body):
    aioclient_mock.put(POSTAL_URL, text=body)
    with pytest.raises(StoreError):
        await async_resolve_mercadona(hass, "28001")


async def test_store_ws_admin_push_unload(hass, hass_ws_client, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    aioclient_mock.put(POSTAL_URL, json={"warehouse_changed": False}, headers={"x-customer-wh": "mad3"})
    writer, reader = await hass_ws_client(hass), await hass_ws_client(hass)
    await reader.send_json({"id": 1, "type": f"{DOMAIN}/settings/subscribe"})
    assert (await reader.receive_json())["success"]
    await reader.receive_json()
    await writer.send_json({"id": 1, "type": f"{DOMAIN}/settings/store", "store": "mercadona", "enabled": True, "postal_code": "28001"})
    assert (await writer.receive_json())["result"]["favorite_store"] == "mercadona"
    assert (await reader.receive_json())["event"]["stores"]["mercadona"]["warehouse"] == "mad1"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await writer.send_json({"id": 2, "type": f"{DOMAIN}/settings/store", "store": "mercadona", "enabled": False})
    assert (await writer.receive_json())["error"]["code"] == "not_loaded"


async def test_store_ws_requires_admin(hass, hass_ws_client, hass_read_only_user, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    refresh = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/store", "store": "mercadona", "enabled": True, "postal_code": "28001"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0
    await client.send_json({"id": 2, "type": f"{DOMAIN}/settings/store_products", "force": True})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 3, "type": f"{DOMAIN}/settings/store_products"})
    assert (await client.receive_json())["result"]["products"] == []
    await client.send_json({"id": 4, "type": f"{DOMAIN}/settings/store", "store": "carrefour", "enabled": True})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 5, "type": f"{DOMAIN}/settings/favorite_store", "store": "carrefour"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 6, "type": f"{DOMAIN}/settings/carrefour_products", "force": True})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 7, "type": f"{DOMAIN}/settings/carrefour_products"})
    assert (await client.receive_json())["result"]["products"] == []
    await client.send_json({"id": 8, "type": f"{DOMAIN}/settings/price_schedule", "time":"02:30"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id": 9, "type": f"{DOMAIN}/catalog/store_prices"})
    assert (await client.receive_json())["result"]["products"] == []
    await client.send_json({"id": 10, "type": f"{DOMAIN}/settings/refresh_prices", "store":"alcampo"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0


async def test_store_progress_subscription_and_cleanup(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    service = hass.data[DOMAIN]["store_products"]
    background_listeners = set(service.manager._listeners)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/settings/store_progress"})
    assert (await client.receive_json())["success"]
    assert not (await client.receive_json())["event"]["running"]
    service.manager._data.update(pending=[{}]*17, total=20, processed=3)
    service.manager._notify()
    event = (await client.receive_json())["event"]
    assert event["processed"] == 0 and event["total"] == 0 and not event["running"]
    await client.send_json({"id": 2, "type": "unsubscribe_events", "subscription": 1})
    assert (await client.receive_json())["success"]
    assert service.manager._listeners == background_listeners
