"""Shared postcode persistence, public discovery and failure isolation."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.price_sources import PriceError, PriceSources
from custom_components.improved_shopping_list.store_location import _public_location, resolve_location
from custom_components.improved_shopping_list.stores import StoreError


def settings_for(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY:"todo.bring"}, options={
        "unrelated":True, "stores":{"mercadona":{"enabled":True,"postal_code":"28001","warehouse":"mad3"},
            "alcampo":{"enabled":True,"region_id":"aa07ac50-43a9-4870-873b-17881ec9a51a"}}, "favorite_store":"mercadona"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active":True,"settings":settings}
    return settings, entry


async def test_common_postal_saves_partial_errors_without_querying_old_region(hass, monkeypatch):
    settings, entry = settings_for(hass)
    async def resolve(_hass, store, postal, current):
        assert postal == "28024"
        if store == "alcampo":
            raise StoreError("HTTP 403")
        return {"postal_code":postal,"warehouse":"mad1"}
    resolver = AsyncMock(side_effect=resolve)
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.resolve_location", resolver)
    result = await settings.async_store_postal("28024")
    assert result["store_postal_code"] == "28024"
    assert result["stores"]["mercadona"]["warehouse"] == "mad1"
    # Keep the cache scope readable; the location_error prevents requests to it.
    assert result["stores"]["alcampo"]["region_id"] == "aa07ac50-43a9-4870-873b-17881ec9a51a"
    assert result["stores"]["alcampo"]["location_error"] == "HTTP 403"
    assert resolver.await_count == 2
    assert result["favorite_store"] == "mercadona" and entry.options["unrelated"] is True
    restored = ListSettings(hass); restored.attach(entry)
    assert restored.snapshot == result
    gate = AsyncMock()
    sources = PriceSources(hass)
    with pytest.raises(PriceError, match="403"):
        await sources.fetch("alcampo", "123", result["stores"]["alcampo"], gate)
    gate.assert_not_awaited()
    sources.close()


async def test_shared_postal_blank_invalid_and_later_activation(hass, monkeypatch):
    settings, _ = settings_for(hass)
    before = deepcopy(settings.snapshot)
    for bad in ("123", "00000", "28024?", " 28024", "99999"):
        with pytest.raises(StoreError):
            await settings.async_store_postal(bad)
        assert settings.snapshot == before
    resolver = AsyncMock(return_value={"postal_code":"", "sale_point":"005290"})
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.resolve_location", resolver)
    await settings.async_store_postal("")
    assert settings.snapshot["store_postal_code"] == ""
    resolver.reset_mock()
    await settings.async_toggle_located_store("carrefour", True)
    assert resolver.await_args.args[2] == ""
    resolver.reset_mock()
    await settings.async_toggle_located_store("carrefour", False)
    resolver.assert_not_awaited()


async def test_location_resolution_cannot_commit_after_detach(hass, monkeypatch):
    settings, entry = settings_for(hass)
    before = deepcopy(dict(entry.options))
    entered, finish = asyncio.Event(), asyncio.Event()
    async def delayed(*args):
        entered.set(); await finish.wait()
        return {"postal_code":"28024","warehouse":"mad1"}
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.resolve_location", delayed)
    task = asyncio.create_task(settings.async_store_postal("28024"))
    await entered.wait(); settings.detach(); finish.set()
    with pytest.raises(StoreError): await task
    assert entry.options == before


async def test_defaults_and_specific_postal_are_distinct(hass, monkeypatch):
    resolver = AsyncMock(return_value="mad1")
    monkeypatch.setattr("custom_components.improved_shopping_list.store_location.async_resolve_mercadona", resolver)
    await resolve_location(hass, "mercadona", "", {})
    assert resolver.await_args.args[1] == "28001"
    await resolve_location(hass, "mercadona", "28024", {})
    assert resolver.await_args.args[1] == "28024"
    assert await resolve_location(hass, "alcampo", "", {}) == {"postal_code":"","region_id":""}
    assert await resolve_location(hass, "carrefour", "", {}) == {"postal_code":"","sale_point":"005290"}


async def test_carrefour_public_postal_and_bad_center(hass, aioclient_mock):
    url = "https://www.carrefour.es/cloud-api/salepoints/v1/salepoint?id=28024&type=postal_code"
    aioclient_mock.get(url, json={"salepoint":"005704"})
    assert await _public_location(hass, "carrefour", "28024") == {"sale_point":"005704"}
    aioclient_mock.get(url.replace("28024", "28001"), json={"salepoint":"invalid"})
    with pytest.raises(StoreError): await _public_location(hass, "carrefour", "28001")


async def test_alcampo_public_postal_chain_and_no_customer_session(hass, aioclient_mock):
    base = "https://www.compraonline.alcampo.es"
    region = "deb03a69-3104-4451-9ffa-3a55dc156d9f"
    destination = "e836ff03-8f94-4f1c-86ff-f2478e7622b4"
    aioclient_mock.get(base+"/", text='<script>{"session":{"csrf":{"token":"fresh-public-token"}}}</script>',
        headers={"Set-Cookie":"VISITORID=anonymous-test-visitor==; Path=/; Secure"})
    aioclient_mock.put(base+"/api/address/v1/addresses/areas", json=[{"id":"public-area"}])
    aioclient_mock.get(base+"/api/address/v1/addresses/areas/public-area", json={
        "postalCode":"28024","countryCode":"ES","latitude":40.38,"longitude":-3.79,"formattedAddress":"28024 Madrid"})
    aioclient_mock.post(base+"/api/ecomdeliverydestinations/v2/temporary-delivery-destinations", json=destination)
    aioclient_mock.get(base+"/api/ecomdeliverydestinations/v4/delivery-addresses/"+destination,
        json={"postalCode":"28024","resolvedRegionId":region,"deliverability":"DELIVERABLE"})
    assert await _public_location(hass, "alcampo", "28024") == {"region_id":region}
    assert aioclient_mock.call_count == 5
    assert not any("customersessions" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_alcampo_403_is_error_and_does_not_select_default(hass, aioclient_mock):
    aioclient_mock.get("https://www.compraonline.alcampo.es/", text='{"session":{"csrf":{"token":"test-token"}}}',
        headers={"Set-Cookie":"VISITORID=anonymous-test; Path=/; Secure"})
    aioclient_mock.put("https://www.compraonline.alcampo.es/api/address/v1/addresses/areas", status=403)
    with pytest.raises(StoreError, match="403"):
        await resolve_location(hass, "alcampo", "28024", {"region_id":"previous"})
    assert aioclient_mock.call_count == 2


async def test_alcampo_missing_csrf_does_not_send_location(hass, aioclient_mock):
    aioclient_mock.get("https://www.compraonline.alcampo.es/", text="<html>Sin sesión</html>")
    with pytest.raises(StoreError, match="sesión anónima"):
        await resolve_location(hass, "alcampo", "28024", {})
    assert aioclient_mock.call_count == 1


async def test_postal_ws_readonly_cannot_change_location(hass, hass_ws_client, hass_read_only_user, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    await client.send_json({"id":1,"type":f"{DOMAIN}/settings/store_postal","postal_code":"28024"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    await client.send_json({"id":2,"type":f"{DOMAIN}/settings/store_enabled","store":"alcampo","enabled":True})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0
