"""La Sirena opt-in discovery, exact EAN, cached visibility and completion filter."""
from unittest.mock import AsyncMock
import time

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.public_catalogs import CatalogDiscovery, PublicCatalogSource
from custom_components.improved_shopping_list.product_references import gtin

CODE = "8414532006553"
URL = "https://www.lasirena.es/es/lomos-de-salmon-noruego-premium-655/p"
API = "https://www.lasirena.es/api/catalog_system/pub/products/search"


async def test_disabled_then_exact_search_data_only_visibility_and_no_repeat(hass, aioclient_mock, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    await catalog.async_save_product({"name": "Salmón", "barcodes": [CODE]})
    links = EANLinks(hass, catalog)
    await links.async_load()
    links._data["checked_at"] = time.time()
    lookup = OptionLookup(hass)
    discovery = CatalogDiscovery(hass, catalog, links, lookup)
    await discovery.async_load()
    source = PublicCatalogSource(hass, catalog, links, lookup, None, "lasirena", discovery)
    await source.async_load()
    source._active = True
    discovery.managers = {"lasirena": source}
    monkeypatch.setattr(source, "_before_request", AsyncMock())
    body = [{"productId": "655", "link": URL, "productName": "Lomos salmón", "brand": "La Sirena", "Envase": ["4 x 125 g"],
        "items": [{"itemId": "655", "ean": CODE, "sellers": [{"sellerDefault": True, "commertialOffer": {"Price": 16.99, "IsAvailable": True}}]}]}]
    aioclient_mock.get(API+"?fq=alternateIds_Ean:"+CODE, json=body)
    try:
        await source.async_run()
        assert aioclient_mock.call_count == 0 and not source.snapshot["show_store"]
        await source.async_set_enabled(True)
        await source.async_run()
        assert aioclient_mock.call_count == 1
        assert not any(r["store"] == "lasirena" for r in catalog.products[0]["commercial_references"])
        assert catalog.products[0]["commercial_references"][0]["content_quantity"] == 500
        await source.async_set_show_store(True)
        ref = next(r for r in catalog.products[0]["commercial_references"] if r["store"] == "lasirena")
        assert ref["last_price"]["price"] == 16.99 and ref["url"] == URL and gtin(ref["ean"]) == gtin(CODE)
        await source.async_run()
        assert source.snapshot["total"] == 0 and aioclient_mock.call_count == 1
        await source.async_set_show_store(False)
        assert not any(r["store"] == "lasirena" for r in catalog.products[0]["commercial_references"])
        await source.async_set_show_store(True)
        assert aioclient_mock.call_count == 1
    finally:
        await source.async_stop()
        lookup.close()


async def test_dictionary_url_precedes_search(hass, aioclient_mock, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    await catalog.async_save_product({"name": "Salmón", "barcodes": [CODE]})
    links = EANLinks(hass, catalog)
    await links.async_load()
    links._data.update(links={"lasirena:"+gtin(CODE): URL}, checked_at=time.time())
    lookup = OptionLookup(hass)
    discovery = CatalogDiscovery(hass, catalog, links, lookup)
    source = PublicCatalogSource(hass, catalog, links, lookup, None, "lasirena", discovery)
    await source.async_load()
    source._active = True
    await source.async_set_enabled(True)
    discovery.managers = {"lasirena": source}
    monkeypatch.setattr(source, "_before_request", AsyncMock())
    aioclient_mock.get(API+"?fq=productId:655", json=[{"productId": "655", "brand": "La Sirena", "items": [{"itemId": "655", "ean": CODE}]}])
    try:
        result = await discovery.async_find("lasirena", gtin(CODE), [])
        assert result["url"] == URL and aioclient_mock.call_count == 1
    finally:
        await source.async_stop()
        lookup.close()
