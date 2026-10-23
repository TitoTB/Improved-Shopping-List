"""Manual DIA bindings: durable paced refreshes, no EAN discovery or login."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.improved_shopping_list import alcampo as clock_module
from custom_components.improved_shopping_list import dia_prices as module
from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.dia_prices import DiaPriceManager
from custom_components.improved_shopping_list.price_manager import PriceManager
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.store_links import normalize_link


@pytest.fixture
async def env(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    first = await catalog.async_save_product({"name":"Patatas", "store_links":{"dia":"84892"}})
    await catalog.async_save_product({"name":"Sin vincular", "barcodes":["8410199023094"]})
    settings = SimpleNamespace(snapshot={"stores":{"dia":{"enabled":True}}, "price_updates_enabled":True})
    receipts = SimpleNamespace(offers_for=lambda product: [])
    activity = SimpleNamespace(record=Mock())
    prices = PriceManager(hass, catalog, settings, activity)
    prices.receipts = receipts
    manager = DiaPriceManager(hass, catalog, settings, prices, receipts, activity)
    await manager.async_load()
    prices.dia_prices = manager
    clock = [1000000.0]
    monkeypatch.setattr(clock_module, "time", SimpleNamespace(time=lambda:clock[0]))
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda:clock[0]))
    async def fetch(store, link, config, gate):
        await gate()
        return {"store":store,"reference_id":link["id"],"url":link["url"],
            "ean":"","price":"2.84","currency":"EUR","store_name":"Lay's Gourmet 170 g"}
    manager.sources.fetch = AsyncMock(side_effect=fetch)
    manager._active = True
    yield SimpleNamespace(manager=manager,catalog=catalog,first=first,clock=clock,
        prices=prices,settings=settings,activity=activity)
    await manager.async_stop()


async def test_only_manual_links_are_refreshed_persisted_and_exposed(env, hass):
    manager = env.manager
    await manager.async_options({"refresh_enabled":True,"days":30})
    # Options wake the running manager; wait for that task before inspecting.
    if manager._task:
        await manager._task
    await manager.async_tick()
    manager.sources.fetch.assert_awaited_once()
    assert manager.sources.fetch.call_args.args[:2] == ("dia", normalize_link("dia", "84892"))
    assert env.prices.prices_for(env.first)[0]["price"] == "2.84"
    assert env.catalog.products[0]["barcodes"] == []
    assert not manager._data["attempts"]
    restored = DiaPriceManager(hass, env.catalog, env.settings, env.prices, manager.receipts, env.activity)
    await restored.async_load()
    assert restored.offer_for(env.first)["reference_id"] == "84892"
    assert restored.snapshot["days"] == 30
    assert restored._data["due"] == manager._data["due"]
    restored.sources.close()


async def test_403_retains_previous_price_and_logs_dia_backoff(env):
    manager = env.manager
    manager._data["refresh_enabled"] = True
    await manager.async_tick()
    env.clock[0] += 31*86400
    manager.sources.fetch.side_effect = PriceError("DIA: consulta rechazada (HTTP 403).", http_status=403)
    await manager.async_tick()
    assert manager.offer_for(env.first)["price"] == "2.84"
    assert manager.snapshot["retry_at"] > env.clock[0]
    assert env.activity.record.call_args.kwargs["diagnostics"]["provider"] == "dia"
    await manager.async_tick()
    assert manager.sources.fetch.await_count == 2


async def test_disabled_store_and_global_switch_prevent_requests(env):
    env.manager._data["refresh_enabled"] = True
    env.settings.snapshot["stores"]["dia"]["enabled"] = False
    await env.manager.async_tick()
    env.settings.snapshot["stores"]["dia"]["enabled"] = True
    env.settings.snapshot["price_updates_enabled"] = False
    await env.manager.async_tick()
    env.manager.sources.fetch.assert_not_awaited()


async def test_each_http_request_obeys_interval_and_options_reject_discovery(env, monkeypatch):
    manager = env.manager
    manager._data["refresh_enabled"] = True
    async def sleep(seconds):
        env.clock[0] += seconds
    pause = AsyncMock(side_effect=sleep)
    monkeypatch.setattr(module.asyncio, "sleep", pause)
    await manager._before_request()
    await manager._before_request()
    pause.assert_awaited_once_with(300)
    with pytest.raises(CatalogError):
        await manager.async_options({"refresh_enabled":True,"days":30,"search_enabled":True})
    with pytest.raises(CatalogError):
        await manager.async_options({"refresh_enabled":True,"days":0})

