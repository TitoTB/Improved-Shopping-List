"""Shared EAN facts preserve package identity, user edits and store-specific prices."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from custom_components.improved_shopping_list.ean_common import extract, consensus, validate, observed_at
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.mercadona_catalog import MercadonaCatalog
from custom_components.improved_shopping_list.mercadona_index import MercadonaIndex, URL, parse_index
from custom_components.improved_shopping_list.product_references import gtin, normalized_references, merge_reference

EAN='8430543025611'
OTHER='8410199023094'
CODE=gtin(EAN)
DATE='2026-10-26T23:31:58+00:00'
SOURCE={'store':'mercadona','url':'https://tienda.mercadona.es/product/69938','revision':'a'*40,'observed_at':observed_at(DATE)}


def record(**prices):
    return {'brand':'puleva','is_bulk':False,'is_variable_weight':False,'price_instructions':{
        'unit_size':1.2,'size_format':'l','is_pack':True,'total_units':6,'pack_size':.2,**prices}}


def test_extract_uses_total_content_and_explicit_pack_count_without_prices():
    data=extract(record(unit_price='3.50'))
    assert data=={'brand':'Puleva','content_quantity':1.2,'content_unit':'l','pack_count':6}
    variable=record();variable['is_variable_weight']=True
    assert 'content_quantity' not in extract(variable)
    approximate=record(approx_size=True)
    assert 'content_quantity' not in extract(approximate)
    assert 'content_quantity' not in extract(record(unit_size=1.5))


def test_field_conflicts_leave_only_disputed_fields_pending_and_accept_equivalent_units():
    first=record(is_pack=False,unit_size=500,size_format='g')
    second=record(is_pack=False,unit_size=.5,size_format='kg');second['brand']='PULEVA'
    result=consensus([first,second])
    assert result['content_quantity']==.5 and result['content_unit']=='kg' and 'conflicts' not in result
    second['price_instructions']['unit_size']=.25
    result=consensus([first,second])
    assert result['conflicts']==['content'] and result['brand']=='PULEVA'
    assert 'content_quantity' not in result
    second['brand']='Otra'
    result=consensus([first,second])
    assert set(result['conflicts'])=={'brand','content'} and 'brand' not in result


@pytest.mark.parametrize('data',[{'price':1},{'content_quantity':1,'content_unit':[]},{'pack_count':True},{'brand':'bad\nbrand'},{'content_quantity':float('nan'),'content_unit':'g'}])
def test_invalid_or_store_specific_data_is_rejected(data):
    with pytest.raises(ValueError):validate(data)


async def test_common_data_fills_all_matching_shops_preserves_prices_and_survives_restart(hass):
    catalog=Catalog(hass);await catalog.async_load()
    p=await catalog.async_save_product({'name':'Mi producto','barcodes':[EAN],'commercial_references':[
        {'store':store,'ean':EAN,'name':'Envase','last_price':{'price':price,'currency':'EUR','checked_at':time.time()}}
        for store,price in [('carrefour',2),('alcampo',3)]]})
    common={CODE:{**extract(record()),'source':SOURCE}}
    assert await catalog.async_apply_common_ean_data(common)==1
    rows=catalog.products[0]['commercial_references']
    assert {r['store'] for r in rows}=={'carrefour','alcampo'} and catalog.products[0]['name']=='Mi producto'
    assert [r['last_price']['price'] for r in rows]==[2,3]
    assert all(r['brand']=='Puleva' and r['content_quantity']==1.2 and r['pack_count']==6 for r in rows)
    assert all(r['common_sources']['brand']==SOURCE for r in rows)
    assert await catalog.async_apply_common_ean_data(common)==0
    again=Catalog(hass);await again.async_load()
    assert again.products==catalog.products
    copied=deepcopy(rows)
    merge_reference(copied,'carrefour',{'ean':EAN,'name':'Envase'},confirmed=False)
    saved=next(r for r in normalized_references(copied) if r['store']=='carrefour')
    assert saved['pack_count']==6 and saved['common_sources']['brand']==SOURCE


async def test_manual_conflicts_exclusions_and_other_eans_are_preserved(hass):
    catalog=Catalog(hass);await catalog.async_load()
    p=await catalog.async_save_product({'name':'Producto','barcodes':[EAN],'commercial_references':[
        {'store':'carrefour','ean':EAN,'name':'Envase','brand':'Marca manual','content_quantity':500,'content_unit':'g','content_confirmed':True,'pack_count':12},
        {'store':'alcampo','ean':EAN,'name':'Envase'},
        {'store':'lidl','ean':EAN,'name':'Envase','active':False},
        {'store':'mercadona','ean':OTHER,'name':'Otro envase'}]})
    entry={'brand':'Puleva','content_quantity':.5,'content_unit':'kg','pack_count':6,'source':SOURCE}
    await catalog.async_apply_common_ean_data({CODE:entry})
    rows=catalog.products[0]['commercial_references']
    assert rows[0]['brand']=='Marca manual' and rows[0]['content_quantity']==500 and rows[0]['pack_count']==12
    assert not rows[1]['brand'] and rows[1]['content_quantity']==.5 and 'pack_count' not in rows[1]
    assert not rows[2]['active'] and rows[2]['content_quantity'] is None
    assert rows[3]['content_quantity'] is None
    before=deepcopy(catalog.products)
    await catalog.async_apply_common_ean_data({CODE:{'conflicts':['brand','content','pack_count'],'source':SOURCE}})
    assert catalog.products==before


async def test_data_only_source_completes_from_dictionary_without_shop_requests(hass):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({'name':'Mi producto','barcodes':[EAN],'commercial_references':[{'store':'carrefour','ean':EAN,'name':'Envase'}]})
    links=EANLinks(hass,catalog);await links.async_load()
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={},retrieve=AsyncMock(side_effect=AssertionError('Data-only must not query Mercadona')))
    source=MercadonaCatalog(hass,catalog,links,lookup,None);await source.async_load()
    value={'schema_version':1,'source_revision':'a'*40,'source_updated_at':DATE,'products':{CODE:'69938'},'common_schema_version':1,'common':{CODE:extract(record())}}
    source.index._data.update(index=parse_index(json.dumps(value).encode()),checked_at=time.time())
    await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run()
        assert source.snapshot['common_updated']==1 and source.snapshot['updated']==1 and source.snapshot['total']==0
        assert source.snapshot['ean_summary']=={'catalog_eans':1,'matched_eans':1}
        row=catalog.products[0]['commercial_references'][0]
        assert row['store']=='carrefour' and row['content_quantity']==1.2 and row['pack_count']==6
        assert 'last_price' not in row and len(catalog.products)==1
        lookup.retrieve.assert_not_awaited();lookup._before_request.assert_not_awaited()
    finally:await source.async_stop()


async def test_old_cache_keeps_links_but_fetches_the_new_common_fields(hass,aioclient_mock):
    index=MercadonaIndex(hass)
    await index._store.async_save({'index':{'schema_version':1,'source_revision':'a'*40,'products':{CODE:'69938'}},'checked_at':time.time(),'etag':'"old"'})
    await index.async_load()
    assert index.products=={CODE:'69938'} and index._data['checked_at']==0
    value={'schema_version':1,'source_revision':'a'*40,'source_updated_at':DATE,'products':{CODE:'69938'},'common_schema_version':1,'common':{CODE:extract(record())}}
    aioclient_mock.get(URL,content=json.dumps(value).encode())
    await index.async_refresh()
    assert aioclient_mock.call_count==1 and index.has_common_data
    assert index.common_data({CODE})[CODE]['pack_count']==6
    assert index.common_data({CODE})[CODE]['source']==SOURCE


async def test_manual_api_edit_removes_only_the_changed_field_provenance(hass):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({'name':'Producto','barcodes':[EAN]})
    await catalog.async_apply_common_ean_data({CODE:{**extract(record()),'source':SOURCE}})
    current=catalog.products[0];refs=deepcopy(current['commercial_references']);refs[0]['brand']='Manual'
    await catalog.async_save_product({'id':current['id'],'revision':current['revision'],'name':current['name'],'barcodes':[EAN],'commercial_references':refs})
    row=catalog.products[0]['commercial_references'][0]
    assert row['brand']=='Manual' and 'brand' not in row['common_sources']
    assert row['common_sources']['content_quantity']==SOURCE and row['pack_count']==6


async def test_no_matching_ean_is_reported_without_querying_shop(hass):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({'name':'Producto','barcodes':[OTHER]})
    links=EANLinks(hass,catalog);await links.async_load()
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={},retrieve=AsyncMock())
    source=MercadonaCatalog(hass,catalog,links,lookup,None);await source.async_load()
    value={'schema_version':1,'source_revision':'a'*40,'source_updated_at':DATE,'products':{CODE:'69938'},'common_schema_version':1,'common':{CODE:extract(record())}}
    source.index._data.update(index=parse_index(json.dumps(value).encode()),checked_at=time.time())
    await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run()
        assert source.snapshot['ean_summary']=={'catalog_eans':1,'matched_eans':0}
        assert source.snapshot['phase']=='finished' and source.snapshot['updated']==0
        lookup.retrieve.assert_not_awaited()
    finally:await source.async_stop()
