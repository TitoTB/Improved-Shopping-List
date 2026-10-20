"""Exact EAN offers, warehouse isolation and failure recovery without live HTTP."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.store_products import SEARCH_URL, StoreProducts, exact_offer
from custom_components.improved_shopping_list.stores import StoreError

CODE = "8430543025611"
HIT = {"id": "69938", "ean": CODE, "display_name": "Tomate rallado", "published": True,
       "price_instructions": {"unit_price": "1.45", "reference_price": "5.00", "reference_format": "kg", "approx_size": False}}


def environment(hass):
    hass.data[DOMAIN] = {"active": True}
    settings = SimpleNamespace(snapshot={"stores": {"mercadona": {"enabled": True, "warehouse": "mad3"}}}, entry=object(), _generation=1)
    catalog = SimpleNamespace(products=[{"name": "Tomate", "barcode": CODE, "barcodes": [CODE, "https://example.test"]}])
    return StoreProducts(hass, catalog, settings)


def test_requires_exact_gtin_and_valid_prices():
    offer = exact_offer([HIT], CODE)
    assert offer["price"] == 1.45 and offer["reference_price"] == 5
    assert offer["ean"] == CODE and offer["store_product_id"] == "69938"
    assert exact_offer([HIT], "3017620422003") is None
    assert exact_offer([{**HIT, "ean": CODE.zfill(14)}], CODE) == offer
    for invalid in ("NaN", "Infinity", "-1", "not a number"):
        assert exact_offer([{**HIT, "price_instructions": {"unit_price": invalid}}], CODE) is None
    with pytest.raises(StoreError):
        exact_offer([HIT, {**HIT, "id": "other"}], CODE)


async def test_cache_force_reload_and_catalog_removal(hass, monkeypatch):
    service = environment(hass)
    fetch = AsyncMock(return_value=exact_offer([HIT], CODE))
    monkeypatch.setattr(service, "_fetch", fetch)
    first = await service.async_refresh()
    assert first["products"][0]["name"] == "Tomate"
    assert fetch.await_count == 1
    await service.async_refresh()
    assert fetch.await_count == 1
    await service.async_refresh(True)
    assert fetch.await_count == 2
    restored = StoreProducts(hass, service.catalog, service.settings)
    await restored.async_load()
    assert restored.snapshot()["products"] == service.snapshot()["products"]
    service.catalog.products = []
    assert service.snapshot()["products"] == []


async def test_http_errors_retain_prices_and_back_off(hass, monkeypatch):
    service = environment(hass)
    fetch = AsyncMock(return_value=exact_offer([HIT], CODE))
    monkeypatch.setattr(service, "_fetch", fetch)
    await service.async_refresh()
    before = service.snapshot()["products"]
    fetch.side_effect = StoreError("HTTP 403")
    result = await service.async_refresh(True)
    assert result["products"] == before and result["error"] == "HTTP 403"
    assert (await service.async_refresh(True))["error"]
    assert fetch.await_count == 2
    service.settings.snapshot["stores"]["mercadona"]["warehouse"] = "vlc1"
    assert service.snapshot()["products"] == []
    service.settings.snapshot["stores"]["mercadona"]["enabled"] = False
    await service.async_refresh(True)
    assert fetch.await_count == 2


async def test_missing_product_does_not_invent_a_price(hass, monkeypatch):
    service = environment(hass)
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "_fetch", fetch)
    assert (await service.async_refresh())["products"] == []
    await service.async_refresh()
    assert fetch.await_count == 1


async def test_configuration_change_discards_late_result(hass, monkeypatch):
    service = environment(hass)
    entered, resume = asyncio.Event(), asyncio.Event()

    async def fetch(*args):
        entered.set()
        await resume.wait()
        return exact_offer([HIT], CODE)

    monkeypatch.setattr(service, "_fetch", fetch)
    task = asyncio.create_task(service.async_refresh())
    await entered.wait()
    service.settings._generation += 1
    resume.set()
    with pytest.raises(StoreError):
        await task
    assert service.snapshot()["products"] == []


async def test_fetch_exact_ean(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [HIT]})
    assert (await service._fetch(CODE, "mad3", "Tomate"))["price"] == 1.45
    assert aioclient_mock.call_count == 1


async def test_fetch_tries_name_but_never_uses_a_similar_ean(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [{**HIT, "ean": "3017620422003"}]})
    assert await service._fetch(CODE, "mad3", "Tomate") is None
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize("status", [302, 403, 429, 500])
async def test_fetch_rejects_http_errors(hass, aioclient_mock, status):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, status=status)
    with pytest.raises(StoreError):
        await service._fetch(CODE, "mad3", "Tomate")
