"""Optional catalogs complete missing packages, rather than scanning every barcode."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.improved_shopping_list.catalog_sources import CatalogSources
from custom_components.improved_shopping_list.mercadona_catalog import MercadonaCatalog
from custom_components.improved_shopping_list.public_catalogs import PublicCatalogSource
from custom_components.improved_shopping_list.product_references import gtin

EAN = "8410199023094"
OTHER = "8410422111086"


def option(code=EAN, **changes):
    return {"id": code, "ean": code, "store": "carrefour", "name": "Envase", "reference_id": "1",
            "content_quantity": 170, "content_unit": "g", "last_price": {"price": 2.89, "currency": "EUR"}, **changes}


def source(hass, refs, codes=()):
    catalog = SimpleNamespace(products=[{"id": "p", "name": "Producto", "barcodes": list(codes), "commercial_references": refs}])
    links = SimpleNamespace(async_store_links=AsyncMock(), error="", catalog_stores=set(), enabled_stores=set())
    return CatalogSources(hass, catalog, links, None, None)


def test_each_ean_is_independent_and_one_complete_option_is_enough(hass):
    manager = source(hass, [option(), option(url="", last_price=None), option(OTHER, content_unit="")], [EAN, OTHER])
    assert manager.incomplete_eans() == {gtin(OTHER)}
    manager.catalog.products[0]["commercial_references"][0]["active"] = False
    assert manager.incomplete_eans() == {gtin(EAN), gtin(OTHER)}


def test_visible_store_searches_complete_ean_until_its_own_option_is_complete(hass):
    manager = source(hass, [option()])
    assert manager.eligible_eans() == set()
    manager._data["show_store"] = True
    assert manager.eligible_eans() == {gtin(EAN)}
    manager.catalog.products[0]["commercial_references"].append(option(store="alcampo"))
    assert manager.eligible_eans() == set()
    manager.catalog.products[0]["commercial_references"][-1]["last_price"] = None
    assert manager.eligible_eans() == {gtin(EAN)}


def test_explicitly_removed_store_alternative_is_not_readded(hass):
    manager = source(hass, [option(), option(store="alcampo", active=False)])
    manager._data["show_store"] = True
    assert manager.eligible_eans() == set()


def test_new_ean_in_any_catalog_field_is_eligible_for_visible_store(hass):
    for field in ("barcode", "barcodes", "commercial_references"):
        manager = source(hass, [])
        manager._data["show_store"] = True
        manager.catalog.products[0][field] = EAN if field == "barcode" else [EAN] if field == "barcodes" else [option()]
        assert manager.eligible_eans() == {gtin(EAN)}


@pytest.mark.parametrize("change", [{"last_price": None}, {"content_quantity": None,"content_unit":"uds"}, {"content_unit": ""}])
def test_missing_required_field_keeps_ean_eligible(hass, change):
    assert source(hass, [option(**change)]).incomplete_eans() == {gtin(EAN)}


def test_known_weight_unit_and_price_do_not_require_a_fixed_package(hass):
    for unit in ('g','kg'):
        assert source(hass,[option(content_quantity=None,content_unit=unit)]).incomplete_eans()==set()


async def test_complete_eans_do_not_download_dictionary_or_queue_web_requests(hass):
    manager = source(hass, [option()])
    assert await manager._source_links() == {}
    manager.links.async_store_links.assert_not_awaited()
    assert manager._pending({"alcampo:" + gtin(EAN): {"id": "1", "url": "https://example.test"}}) == []


async def test_mercadona_skips_index_refresh_for_complete_eans(hass):
    base = source(hass, [option()])
    manager = MercadonaCatalog(hass, base.catalog, base.links, None, None)
    manager.index.async_refresh = AsyncMock()
    manager._active = True
    manager._data["enabled"] = True
    await manager.async_run()
    manager.index.async_refresh.assert_not_awaited()
    assert manager.snapshot["total"] == 0
    await manager.async_stop()


@pytest.mark.parametrize("store", ["masymas", "bm", "consum", "lasirena", "eroski"])
async def test_public_catalog_skips_complete_eans_before_discovery(hass, store):
    base = source(hass, [option()])
    discovery = SimpleNamespace(async_find=AsyncMock())
    manager = PublicCatalogSource(hass, base.catalog, base.links, None, None, store, discovery)
    manager._active = True
    manager._data["enabled"] = True
    await manager.async_run()
    discovery.async_find.assert_not_awaited()
    assert manager.snapshot["total"] == 0
    await manager.async_stop()
