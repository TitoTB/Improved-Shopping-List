"""Mercadona discovery, persistence and authenticated writes without live HTTP."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.stores import POSTAL_URL, StoreError, async_resolve_mercadona


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


async def test_store_persists_preserves_other_settings_and_failed_reconfiguration(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"}, options={"unrelated": True})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active": True}
    resolver = AsyncMock(return_value="mad3")
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.async_resolve_mercadona", resolver)
    result = await settings.async_update_store(True, "28001")
    assert result["stores"]["mercadona"]["warehouse"] == "mad3"
    assert result["stores"]["mercadona"]["checked_at"] > 0
    assert result["favorite_store"] == "mercadona"
    result["stores"]["mercadona"]["warehouse"] = "tampered"
    assert settings.snapshot["stores"]["mercadona"]["warehouse"] == "mad3"
    resolver.side_effect = StoreError("Unavailable")
    with pytest.raises(StoreError):
        await settings.async_update_store(True, "46001")
    assert settings.snapshot["stores"]["mercadona"]["postal_code"] == "28001"
    settings.update("remove", "todo.bring")
    restored = ListSettings(hass)
    restored.attach(entry)
    assert restored.snapshot["stores"] == settings.snapshot["stores"]
    disabled = await restored.async_update_store(False, "")
    assert disabled["favorite_store"] == ""
    assert disabled["stores"]["mercadona"]["enabled"] is False
    assert disabled["stores"]["mercadona"]["warehouse"] == "mad3"
    assert resolver.await_count == 2  # Disabling is entirely local.
    assert entry.options["unrelated"] is True


async def test_late_response_after_reload_is_not_saved(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active": True}
    entered, resume = asyncio.Event(), asyncio.Event()

    async def resolve(*args):
        entered.set()
        await resume.wait()
        return "mad3"

    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.async_resolve_mercadona", resolve)
    task = asyncio.create_task(settings.async_update_store(True, "28001"))
    await entered.wait()
    settings.detach()
    settings.attach(entry)
    resume.set()
    with pytest.raises(StoreError):
        await task
    assert settings.snapshot["stores"]["mercadona"]["enabled"] is False


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
    assert (await reader.receive_json())["event"]["stores"]["mercadona"]["warehouse"] == "mad3"
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
