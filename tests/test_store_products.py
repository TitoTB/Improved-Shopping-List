"""Exact EAN offers, warehouse isolation and failure recovery without live HTTP."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.store_products import SEARCH_URL, StoreProducts, exact_offer
from custom_components.improved_shopping_list.stores import StoreError
from custom_components.improved_shopping_list import store_products as module

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


async def test_all_requests_are_paced_including_name_fallback(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    clock, waits = [100.0], []
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1800000000 + clock[0], monotonic=lambda: clock[0]))

    async def advance(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(module, "sleep", advance)
    aioclient_mock.post(SEARCH_URL, json={"hits": []})
    await service._fetch(CODE, "mad3", "Tomate")
    await service._fetch(CODE, "mad3", "Tomate")
    assert aioclient_mock.call_count == 4
    assert waits == pytest.approx([2, 2, 2])


async def test_403_persists_cooldown_and_logs_safe_diagnostics(hass, aioclient_mock, monkeypatch, caplog):
    service = environment(hass)
    service.activity = SimpleNamespace(record=Mock())
    aioclient_mock.post(SEARCH_URL, status=403,
        text="<html>Uso indebido del servicio. description: 0.aabbccdd.1792508361.1234abcd client_ip: 192.0.2.10 token=private-body</html>",
        headers={"Content-Type": "text/html", "Set-Cookie": "session=private-cookie", "x-request-id": "safe-reference"})
    result = await service.async_refresh(True)
    assert result["processed"] == 0 and result["remaining"] == 1
    assert result["retry_at"] - module.time.time() >= 899
    records = service.activity.record.call_args_list
    error = next(call for call in records if call.args[0] == "stores.error")
    diagnostics = error.kwargs["diagnostics"]
    assert diagnostics["http_status"] == 403
    assert diagnostics["response_class"] == "service_misuse"
    assert diagnostics["x-request-id"] == "safe-reference"
    assert diagnostics["block_reference"] == "0.aabbccdd.1792508361.1234abcd"
    assert diagnostics["query_type"] == "ean" and diagnostics["request_number"] == 1
    assert diagnostics["retry_seconds"] == 900
    assert "private-cookie" not in str(records) + caplog.text
    assert "private-body" not in str(records) + caplog.text
    assert "192.0.2.10" not in str(records) + caplog.text
    restored = StoreProducts(hass, service.catalog, service.settings)
    await restored.async_load()
    fetch = AsyncMock(side_effect=AssertionError("Restart must not bypass cooldown"))
    monkeypatch.setattr(restored, "_fetch", fetch)
    blocked = await restored.async_refresh(True)
    assert blocked["retry_at"] == result["retry_at"]
    assert "HTTP 403" in blocked["error"]
    assert fetch.await_count == 0
    assert aioclient_mock.call_count == 1


@pytest.mark.parametrize("status", [403, 429])
async def test_respects_server_retry_after(hass, aioclient_mock, status):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, status=status, headers={"Retry-After": "1800"})
    result = await service.async_refresh(True)
    assert result["retry_at"] - module.time.time() >= 1799
    assert service._last_diagnostics["server_retry_seconds"] == 1800


def test_retry_after_dates_and_invalid_values(monkeypatch):
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1000))
    assert module.retry_seconds("Thu, 01 Jan 1970 00:36:40 GMT") == 1200
    assert module.retry_seconds("200000") == 86400
    assert module.retry_seconds("invalid") == 0


async def test_invalid_json_has_technical_context(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, text="not JSON")
    result = await service.async_refresh(True)
    assert "JSON" in result["error"]
    assert service._last_diagnostics["response_class"] == "invalid_json"
    assert service._last_diagnostics["http_status"] == 200


async def test_timeout_has_technical_context(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, exc=asyncio.TimeoutError())
    await service.async_refresh(True)
    assert service._last_diagnostics["response_class"] == "timeout"
    assert service._last_diagnostics["exception_type"] == "TimeoutError"
