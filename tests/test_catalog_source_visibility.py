"""A data source does not become a buying alternative without explicit consent."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.catalog_sources import CatalogSources
from custom_components.improved_shopping_list.eci_catalog import ECICatalog
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.store_links import normalize_link

EAN="8410199023094"
URLS={"alcampo":"https://www.compraonline.alcampo.es/products/patatas/10739",
      "elcorteingles":"https://www.elcorteingles.es/supermercado/B001018009401193-patatas/"}


@pytest.mark.parametrize("store",tuple(URLS))
async def test_source_only_mode_cached_visibility_and_restart_preserve_shared_data(hass,store):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({"name":"Patatas","barcodes":[EAN]})
    links=EANLinks(hass,catalog);await links.async_load()
    links._data["links"]={"alcampo:"+gtin(EAN):URLS["alcampo"]};links._data["checked_at"]=time.time()
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={})
    data={"ean":EAN,"store":store,"reference_id":normalize_link(store,URLS[store])["id"],"url":URLS[store],
          "name":"Patatas de marca","brand":"Marca","content_quantity":170,"content_unit":"g",
          "price":2.89,"currency":"EUR","checked_at":int(time.time())}
    source=CatalogSources(hass,catalog,links,lookup,None) if store=="alcampo" else ECICatalog(hass,catalog,lookup,None)
    await source.async_load()
    query=AsyncMock(return_value=deepcopy(data))
    if store=="alcampo":lookup.retrieve=query
    else:source.client.search=query
    assert not source.snapshot["show_store"]
    await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run();source._active=False
        refs=catalog.products[0]["commercial_references"]
        assert not any(ref["store"]==store for ref in refs)
        assert refs[0]["brand"]=="Marca" and refs[0]["content_quantity"]==170
        assert "last_price" not in refs[0] and not refs[0]["store"]
        assert query.await_count==1
        await source.async_set_show_store(True)
        option=next(r for r in catalog.products[0]["commercial_references"] if r["store"]==store)
        assert option["last_price"]["price"]==2.89 and option["catalog_source"]
        # Keep later manual edits intact while hiding and showing automatic alternatives.
        current=catalog.products[0]
        changed=deepcopy(current["commercial_references"])
        target=next(r for r in changed if r["store"]==store)
        target["last_price"]={"price":3.5,"currency":"EUR","checked_at":int(time.time())+60}
        await catalog.async_save_product({"id":current["id"],"revision":current["revision"],"name":current["name"],"barcodes":[EAN],"commercial_references":changed})
        await source.async_set_show_store(False)
        assert not any(r["store"]==store for r in catalog.products[0]["commercial_references"])
        restarted=Catalog(hass);await restarted.async_load()
        again=CatalogSources(hass,restarted,links,lookup,None) if store=="alcampo" else ECICatalog(hass,restarted,lookup,None)
        await again.async_load();assert not again.snapshot["show_store"]
        await again.async_set_show_store(True)
        restored=next(r for r in restarted.products[0]["commercial_references"] if r["store"]==store)
        assert restored["last_price"]["price"]==3.5 and query.await_count==1
        assert restored["brand"]=="Marca" and restored["content_quantity"]==170
        await again.async_stop()
    finally:await source.async_stop()


async def test_data_only_source_fills_missing_metadata_without_hiding_manual_shop(hass):
    catalog=Catalog(hass);await catalog.async_load()
    url=URLS["alcampo"]
    product=await catalog.async_save_product({"name":"Patatas","barcodes":[EAN],"commercial_references":[
        {"store":"alcampo","ean":EAN,"name":"Opción manual","url":url,"brand":"Mi marca",
         "last_price":{"price":9,"currency":"EUR","checked_at":time.time()}}]})
    await catalog.async_complete_store_option("alcampo",EAN,url,{"ean":EAN,"brand":"Otra marca","content_quantity":170,
        "content_unit":"g","price":2,"currency":"EUR"},create=True,show_store=False,catalog_source=True)
    await catalog.async_source_visibility("alcampo",False)
    option=catalog.products[0]["commercial_references"][0]
    assert option["store"]=="alcampo" and option["brand"]=="Mi marca" and option["last_price"]["price"]==9
    assert option["content_quantity"]==170 and not option.get("catalog_source")
