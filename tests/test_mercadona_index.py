"""Full public index, bounded downloads, offline cache and exact local matches."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from custom_components.improved_shopping_list import mercadona_index as module
from custom_components.improved_shopping_list.mercadona_index import MercadonaIndex, URL, INITIAL_URL, parse_index
from custom_components.improved_shopping_list.mercadona_catalog import MercadonaCatalog
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks, DAY
from custom_components.improved_shopping_list.product_references import gtin

EAN='8430543025611'
OTHER='8410199023094'
WEB='https://tienda.mercadona.es/product/69938'
REV='a'*40


def payload(products=None):
    return {'schema_version':1,'source_revision':REV,'products':products if products is not None else {gtin(EAN):'69938'}}


@pytest.mark.parametrize('products',[{}, {'':'69938'}, {'123':'69938'}, {gtin(EAN):'https://evil.test'}, {gtin(EAN):True}, {gtin(EAN):'1/../2'}, {EAN:'69938'}])
def test_invalid_or_noncanonical_index_cannot_generate_links(products):
    with pytest.raises(ValueError):parse_index(json.dumps(payload(products)).encode())


async def test_one_daily_download_etag_and_durable_cache(hass,aioclient_mock,monkeypatch):
    clock=[time.time()]
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock[0]))
    index=MercadonaIndex(hass);await index.async_load()
    aioclient_mock.get(URL,content=json.dumps(payload()).encode(),headers={'ETag':'"first"'})
    await index.async_refresh();await index.async_refresh()
    assert aioclient_mock.call_count==1 and index.products=={gtin(EAN):'69938'}
    restored=MercadonaIndex(hass);await restored.async_load()
    await restored.async_refresh();assert aioclient_mock.call_count==1
    clock[0]+=DAY+1;aioclient_mock.clear_requests();aioclient_mock.get(URL,status=304)
    await restored.async_refresh()
    assert aioclient_mock.call_count==1 and aioclient_mock.mock_calls[0][3]['If-None-Match']=='"first"'
    assert restored.products=={gtin(EAN):'69938'} and not restored.error


async def test_download_failure_or_invalid_replacement_preserves_last_index(hass,aioclient_mock,monkeypatch):
    clock=[time.time()]
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock[0]))
    index=MercadonaIndex(hass)
    aioclient_mock.get(URL,content=json.dumps(payload()).encode())
    await index.async_refresh();before=deepcopy(index.products)
    clock[0]+=DAY+1;aioclient_mock.clear_requests();aioclient_mock.get(URL,content=b'{"schema_version":1,"products":{}}')
    await index.async_refresh()
    assert index.products==before and index.error and index.status['cached_fallback']
    await index.async_refresh();assert aioclient_mock.call_count==1
    restored=MercadonaIndex(hass);await restored.async_load()
    assert restored.products==before


async def test_first_install_can_use_seed_if_data_branch_has_not_been_published(hass,aioclient_mock):
    aioclient_mock.get(URL,status=404)
    aioclient_mock.get(INITIAL_URL,content=json.dumps(payload()).encode())
    index=MercadonaIndex(hass);await index.async_refresh()
    assert index.products=={gtin(EAN):'69938'} and aioclient_mock.call_count==2


async def test_full_index_matches_only_user_eans_and_new_eans_are_processed_without_redownload(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Tomate','barcodes':[EAN]})
    links=EANLinks(hass,catalog);await links.async_load();links._data['checked_at']=time.time()
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={},retrieve=AsyncMock())
    async def retrieve(url,store,code,**kwargs):
        return {'store':store,'ean':code,'reference_id':url.rsplit('/',1)[-1],'url':url,'price':1.45,'currency':'EUR','content_quantity':.29,'content_unit':'kg'}
    lookup.retrieve.side_effect=retrieve
    source=MercadonaCatalog(hass,catalog,links,lookup,None);await source.async_load()
    source.index._data.update(index=payload({gtin(EAN):'69938',gtin(OTHER):'10739'}),checked_at=time.time())
    refresh=AsyncMock(wraps=source.index.async_refresh);source.index.async_refresh=refresh
    await source.async_set_show_store(True);await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run()
        assert len(catalog.products)==1 and lookup.retrieve.await_count==1
        option=next(ref for ref in catalog.products[0]['commercial_references'] if ref['store']=='mercadona')
        assert option['store']=='mercadona' and option['url']==WEB and option['last_price']['price']==1.45
        assert 'mercadona' not in links.enabled_stores
        await catalog.async_save_product({'name':'Patatas','barcodes':[OTHER]})
        await source.async_run()
        assert len(catalog.products)==2 and lookup.retrieve.await_count==2
        assert source.snapshot['public_index']['entries']==2
        assert lookup.retrieve.call_args.args[2]==gtin(OTHER)
    finally:await source.async_stop()


def test_published_full_index_is_not_limited_to_carrefour_dictionary():
    root=Path(__file__).resolve().parents[1]
    data=parse_index((root/'data/mercadona-index.json').read_bytes())
    assert len(data['products'])>5000
    assert data['products'][gtin(EAN)]=='69938'


def test_index_builder_excludes_ambiguous_and_invalid_eans_and_refuses_empty_update():
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('mercadona_index_builder',root/'scripts/build-mercadona-index.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    rows=[('1',{'id':'1','ean':EAN}),('2',{'id':'2','ean':EAN}),('3',{'id':'3','ean':OTHER}),('4',{'id':'4','ean':'123'})]
    data=builder.build(rows,REV,'2026-10-26',minimum=1)
    assert data['products']=={gtin(OTHER):'3'} and data['excluded']=={'invalid':1,'ambiguous':1}
    assert parse_index(json.dumps(data).encode())['products']==data['products']
    with pytest.raises(ValueError):builder.build([],REV,'2026-10-26')
