"""Retiring a store must preserve products, scanner codes and other providers."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.price_sources import PriceSources
from custom_components.improved_shopping_list.store_links import normalize_link


@pytest.mark.parametrize("other_enabled,expected_favorite", [(True,"carrefour"),(False,"")])
async def test_retired_store_settings_migrate_without_losing_lists(hass,other_enabled,expected_favorite):
    entry = MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"},options={
        "stores":{"lidl":{"enabled":True,"region_id":"28"},
                  "carrefour":{"enabled":other_enabled,"sale_point":"012345"}},
        "favorite_store":"lidl","other_setting":"preserved"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass); settings.attach(entry)
    assert set(settings.snapshot["stores"]) == {"mercadona","carrefour","alcampo"}
    assert settings.snapshot["favorite_store"] == expected_favorite
    assert settings.snapshot["stores"]["carrefour"]["sale_point"] == "012345"
    assert settings.snapshot["primary_entity"] == "todo.bring"
    assert entry.options["other_setting"] == "preserved"
    assert "lidl" not in entry.options["stores"]


async def test_retired_binding_removed_without_deleting_catalog_product(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name":"Cacao","barcode":"0012345",
        "store_links":{"carrefour":"R-VC4AECOMM-491998"}})
    catalog._products[product["id"]]["store_links"]["lidl"] = {
        "id":"11107037","url":"https://www.lidl.es/p/queso/p11107037"}
    await catalog._persist(catalog._products,catalog._categories)
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products == [product]
    assert restored.find_by_code("barcode","0012345")["id"] == product["id"]
    stored = await restored._store.async_load()
    assert "lidl" not in stored["products"][product["id"]]["store_links"]
    # A cached older client cannot silently reintroduce the removed provider.
    with pytest.raises(CatalogError):
        await restored.async_save_product({"name":"Cacao","store_links":{"lidl":"11107037"}})
    assert restored.products == [product]


async def test_retired_reference_is_rejected_before_any_http(hass,aioclient_mock):
    before = AsyncMock()
    with pytest.raises(ValueError):
        normalize_link("lidl","11107037")
    with pytest.raises(ValueError):
        await PriceSources(hass).fetch("lidl",{"id":"11107037","url":"https://www.lidl.es/p/p11107037"},{},before)
    before.assert_not_awaited()
    assert aioclient_mock.call_count == 0
