"""Exact EAN offers, warehouse isolation and failure recovery without live HTTP."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.store_products import StoreProducts, exact_offer, search_url
from custom_components.improved_shopping_list.stores import StoreError
from custom_components.improved_shopping_list import store_products as module

CODE = "8430543025611"
SEARCH_URL = search_url("mad3")
DETAIL_URL = module.PRODUCT_URL.format(identifier="69938", warehouse="mad3")
HIT = {"id": "69938", "ean": CODE, "display_name": "Tomate rallado", "published": True,
       "price_instructions": {"unit_price": "1.45", "reference_price": "5.00", "reference_format": "kg", "approx_size": False}}


@pytest.fixture(autouse=True)
def no_real_network_wait(monkeypatch):
    monkeypatch.setattr(module, "sleep", AsyncMock())


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
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": "69938", "ean": "untrusted-search-field"}]})
    aioclient_mock.get(DETAIL_URL, json=HIT)
    assert (await service._fetch(CODE, "mad3", "Tomate"))["price"] == 1.45
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize("cancel", [False, True])
async def test_progress_is_pushed_before_refresh_finishes_and_on_cancellation(hass, monkeypatch, cancel):
    service = environment(hass)
    service.catalog.products.append({"name": "Otro", "barcode": "3017620422003"})
    events, entered, resume = [], asyncio.Event(), asyncio.Event()
    stop = service.subscribe(lambda: events.append(dict(service.progress)))
    calls = 0

    async def fetch(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            await resume.wait()
        return None

    monkeypatch.setattr(service, "_fetch", fetch)
    task = asyncio.create_task(service.async_refresh(True))
    await entered.wait()
    assert not task.done()
    assert events[0]["running"] and events[0]["total"] == 2
    assert events[-1]["processed"] == 1 and events[-1]["running"]
    assert 0 < events[-1]["estimated_seconds"] <= 35
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        resume.set()
        result = await task
        assert result["processed"] == 2 and result["remaining"] == 0
        assert events[-1]["processed"] == 2
    assert not events[-1]["running"] and events[-1]["estimated_seconds"] == 0
    stop()
    before = len(events)
    service._update_progress(phase="ignored")
    assert len(events) == before


async def test_fetch_tries_name_but_never_uses_a_similar_ean(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [HIT]})
    aioclient_mock.get(DETAIL_URL, json={**HIT, "ean": "3017620422003"})
    assert await service._fetch(CODE, "mad3", "Tomate") is None
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize("status", [302, 403, 429, 500])
async def test_fetch_rejects_http_errors(hass, aioclient_mock, status):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, status=status)
    with pytest.raises(StoreError):
        await service._fetch(CODE, "mad3", "Tomate")


async def test_search_and_detail_requests_are_all_paced(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    clock, waits = [100.0], []
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1800000000 + clock[0], monotonic=lambda: clock[0]))

    async def advance(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(module, "sleep", advance)
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": "69938"}]})
    aioclient_mock.get(DETAIL_URL, json=HIT)
    await service._fetch(CODE, "mad3", "Tomate")
    service._details.clear()
    await service._fetch(CODE, "mad3", "Tomate")
    assert aioclient_mock.call_count == 4
    assert waits == pytest.approx([5, 5, 5])


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
    assert diagnostics["query_type"] == "name" and diagnostics["request_number"] == 1
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


async def test_opening_view_after_403_does_not_retry_after_cooldown_or_restart(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, status=403)
    first = await service.async_refresh(True)
    assert first["automatic_refresh_blocked"]
    service._retry_after = 0  # The minimum cooldown has elapsed.
    await service._persist()
    restored = environment(hass)
    await restored.async_load()
    for _ in range(3):
        result = await restored.async_refresh(False)
        assert result["automatic_refresh_blocked"] and result["remaining"] == 1
    assert aioclient_mock.call_count == 1
    # Only a deliberate manual action can retry; it still respects future cooldowns.
    manual = await restored.async_refresh(True)
    assert aioclient_mock.call_count == 2
    assert manual["retry_at"] - module.time.time() >= 1799
    restored._retry_after = 0
    monkeypatch.setattr(restored, "_fetch", AsyncMock(return_value=None))
    recovered = await restored.async_refresh(True)
    assert not recovered["automatic_refresh_blocked"] and not recovered["error"]


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


async def test_no_candidates_is_a_success_without_backoff(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [], "nbPages": 0})
    result = await service.async_refresh(True)
    assert result["processed"] == 1 and result["remaining"] == 0
    assert result["not_found"] == 1 and not result["products"]
    assert not result["error"] and result["retry_at"] == 0
    assert aioclient_mock.call_count == 1


async def test_known_reference_updates_directly_and_rechecks_its_ean(hass, aioclient_mock):
    service = environment(hass)
    service._cache[f"mad3:{CODE.zfill(14)}"] = {"offer": exact_offer([HIT], CODE), "checked_at": 0}
    aioclient_mock.get(DETAIL_URL, json={**HIT, "price_instructions": {"unit_price": "1.65"}})
    result = await service.async_refresh(True)
    assert result["products"][0]["price"] == 1.65
    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][0] == "GET"


async def test_pagination_checks_all_candidates_not_only_first_page(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    search = AsyncMock(side_effect=[
        ({"hits": [{"id": "123"}], "page": 0, "nbPages": 2}, {}),
        ({"hits": [{"id": "69938"}], "page": 1, "nbPages": 2}, {}),
    ])
    monkeypatch.setattr(service, "_search", search)
    aioclient_mock.get(module.PRODUCT_URL.format(identifier="123", warehouse="mad3"), json={**HIT, "id": "123", "ean": "3017620422003"})
    aioclient_mock.get(DETAIL_URL, json=HIT)
    assert (await service.async_refresh(True))["products"][0]["ean"] == CODE
    assert [call.args[-1] for call in search.await_args_list] == [0, 1]
    assert aioclient_mock.call_count == 2


async def test_duplicate_exact_references_are_not_silently_chosen(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": "69938"}, {"id": "123"}]})
    aioclient_mock.get(DETAIL_URL, json=HIT)
    aioclient_mock.get(module.PRODUCT_URL.format(identifier="123", warehouse="mad3"), json={**HIT, "id": "123"})
    result = await service.async_refresh(True)
    assert "varias referencias" in result["error"]
    assert not result["products"] and result["not_found"] == 0


async def test_candidate_scan_resumes_after_restart_without_recording_a_false_miss(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1800000000 + clock[0], monotonic=lambda: clock[0]))

    async def advance(seconds):
        clock[0] += seconds

    monkeypatch.setattr(module, "sleep", advance)
    ids = [str(100 + index) for index in range(8)]
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": identifier} for identifier in ids]})
    for index, identifier in enumerate(ids):
        aioclient_mock.get(module.PRODUCT_URL.format(identifier=identifier, warehouse="mad3"),
            json={**HIT, "id": identifier, "ean": CODE if index == 0 else "3017620422003"})
    partial = await service._async_refresh(True)  # Inspect the persisted internal checkpoint.
    assert partial["remaining"] == 1 and partial["processed"] == 0
    assert not partial["error"] and partial["retry_at"] == 0 and partial["not_found"] == 0
    assert not partial["products"]  # Don't publish until ambiguity has also been checked.
    checked = service._lookups[f"mad3:{CODE.zfill(14)}"]["cursor"]
    assert 0 < checked < 8
    restored = environment(hass)
    await restored.async_load()
    result = await restored.async_refresh(True)
    assert result["processed"] == 1 and result["remaining"] == 0
    assert result["products"][0]["ean"] == CODE
    assert aioclient_mock.call_count == 9  # One search and eight distinct detail requests.
    assert restored._lookups == {}


@pytest.mark.parametrize("force", [False, True])
async def test_all_codes_are_reviewed_in_one_call_with_continuous_progress(hass, monkeypatch, force):
    service = environment(hass)
    products = []
    for index in range(21):
        prefix = f"84300000{index:04}"
        checksum = (10 - sum(int(digit) * (3 if position % 2 == 0 else 1)
            for position, digit in enumerate(reversed(prefix))) % 10) % 10
        products.append({"name": f"Producto {index}", "barcode": prefix + str(checksum)})
    service.catalog.products = products
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "_fetch", fetch)
    events = []
    service.subscribe(lambda: events.append(dict(service.progress)))
    result = await service.async_refresh(force)
    assert result["processed"] == 21 and result["remaining"] == 0 and result["total"] == 21
    assert fetch.await_count == 21
    running = [event for event in events if event["running"]]
    assert all(event["total"] == 21 for event in running)
    assert [event["processed"] for event in running] == sorted(event["processed"] for event in running)
    assert events[-1]["processed"] == 21 and not events[-1]["running"]


async def test_full_refresh_continues_past_time_checkpoints_without_extra_calls(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1800000000+clock[0], monotonic=lambda:clock[0]))

    async def advance(seconds):
        clock[0] += seconds

    monkeypatch.setattr(module, "sleep", advance)
    ids = [str(200+index) for index in range(16)]
    aioclient_mock.post(SEARCH_URL, json={"hits":[{"id":identifier} for identifier in ids]})
    for index, identifier in enumerate(ids):
        aioclient_mock.get(module.PRODUCT_URL.format(identifier=identifier,warehouse="mad3"),
            json={**HIT,"id":identifier,"ean":CODE if index==15 else "3017620422003"})
    events = []
    service.subscribe(lambda: events.append(dict(service.progress)))
    result = await service.async_refresh(True)
    assert result["remaining"] == 0 and result["processed"] == 1
    assert result["products"][0]["ean"] == CODE
    assert aioclient_mock.call_count == 17
    assert clock[0] >= 175  # Multiple checkpoints, all requests still paced.
    assert any(event.get("phase") == "continuation" for event in events)
    assert [event["candidates"] for event in events] == sorted(event["candidates"] for event in events)
    assert events[-1]["candidates"] == 16


async def test_removed_candidate_is_not_a_network_failure(hass, aioclient_mock):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": "69938"}]})
    aioclient_mock.get(DETAIL_URL, status=404)
    result = await service.async_refresh(True)
    assert not result["error"] and result["not_found"] == 1 and result["retry_at"] == 0


async def test_legacy_403_does_not_block_the_new_provider(hass, aioclient_mock):
    service = environment(hass)
    await service._store.async_save({"offers": {}, "retry_after": module.time.time() + 3600,
        "last_error": "HTTP 403", "failures": 3, "last_diagnostics": {"endpoint": module.LEGACY_SEARCH_URL, "http_status": 403}})
    await service.async_load()
    aioclient_mock.post(SEARCH_URL, json={"hits": []})
    result = await service.async_refresh(True)
    assert not result["error"] and not result["automatic_refresh_blocked"]
    assert result["processed"] == 1 and result["retry_at"] == 0
    assert aioclient_mock.call_count == 1


async def test_entry_change_during_pause_stops_before_the_next_request(hass, aioclient_mock, monkeypatch):
    service = environment(hass)
    aioclient_mock.post(SEARCH_URL, json={"hits": [{"id": "69938"}]})

    async def change_entry(seconds):
        service.settings._generation += 1

    monkeypatch.setattr(module, "sleep", change_entry)
    with pytest.raises(StoreError, match="configuración"):
        await service.async_refresh(True)
    assert aioclient_mock.call_count == 1
    assert not service.snapshot()["products"] and not service.progress["running"]
