"""Archived stores stay inactive without losing saved data or connector code."""
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.alcampo import AlcampoManager
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.dia_prices import DiaPriceManager
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.store_availability import AVAILABLE_STORES
from custom_components.improved_shopping_list.stores import StoreError


async def test_archived_activations_and_favorite_masked_without_erasing_options(hass):
    assert "dia" not in AVAILABLE_STORES and "alcampo" not in AVAILABLE_STORES
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY:"todo.bring"}, options={
        "stores":{store:{"enabled":True} for store in ("carrefour","alcampo","dia")},
        "favorite_store":"dia"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    hass.data[DOMAIN] = {"active":True}
    assert settings.snapshot["favorite_store"] == "carrefour"
    assert {store for store, value in settings.snapshot["stores"].items() if value["enabled"]} == {"carrefour"}
    assert entry.options["stores"]["alcampo"]["enabled"] is True
    assert entry.options["stores"]["dia"]["enabled"] is True
    await settings.async_update_carrefour(False)
    assert settings.snapshot["favorite_store"] == ""
    assert entry.options["stores"]["alcampo"]["enabled"] is True
    assert entry.options["stores"]["dia"]["enabled"] is True
    with pytest.raises(StoreError, match="archivada"):
        await settings.async_toggle_located_store("dia", True)
    await settings.async_update_alcampo(False)
    with pytest.raises(StoreError, match="archivada"):
        await settings.async_update_alcampo(True)


@pytest.mark.parametrize("manager_type", [AlcampoManager, DiaPriceManager])
async def test_archived_schedulers_never_start_even_with_old_refresh_options(hass, manager_type):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name":"Patatas", "barcodes":["8410199023094"],
        "store_links":{"alcampo":"10739","dia":"84892"}})
    settings = SimpleNamespace(snapshot={"stores":{"alcampo":{"enabled":True},"dia":{"enabled":True}}})
    prices = SimpleNamespace(_notify=Mock())
    manager = manager_type(hass, catalog, settings, prices, Mock(), Mock())
    manager._data["refresh_enabled"] = True
    manager.sources.fetch = AsyncMock()
    await manager._save()
    manager.start()
    assert not manager._active and manager._timer is None and manager._task is None
    await manager.async_tick()
    manager.sources.fetch.assert_not_awaited()
    restored = manager_type(hass, catalog, settings, prices, Mock(), Mock())
    await restored.async_load()
    assert restored.snapshot["refresh_enabled"] is True
    assert catalog.products == [product]
    await manager.async_stop()
    await restored.async_stop()
