"""Universal EAN facts work independently of shop activation and preserve local edits."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_common_index import CommonEANIndex,URL,INITIAL_URL,parse_index
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.product_lookup import ProductLookup

EAN='8410199023094';CODE=gtin(EAN)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_common_eans',ROOT/'scripts/build-ean-common.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def document(fields=None):
    return {'schema_version':1,'revision':'a'*40,'updated_at':'2026-10-31T00:00:00+00:00','products':{CODE:fields or {'brand':'Marca','content_quantity':.5,'content_unit':'kg','pack_count':6,'origins':['carrefour','alcampo']}}}


def test_export_import_publishes_only_explicit_common_facts_and_consensus():
    export={'kind':'improved-shopping-list-catalog-export','products':[{'name':'PRIVATE NAME','notes':'PRIVATE NOTE','commercial_references':[
        {'store':'carrefour','ean':EAN,'brand':'Marca','content_quantity':500,'content_unit':'g','content_confirmed':True,'pack_count':6,'last_price':{'price':9}},
        {'store':'alcampo','ean':EAN,'brand':'marca','content_quantity':.5,'content_unit':'kg','content_confirmed':True,'pack_count':6},
        {'store':'lidl','ean':EAN,'content_quantity':999,'content_unit':'g','content_confirmed':False}]}]}
    seed=builder.import_catalog(export);index=builder.build(seed,{'common':{}})
    raw=json.dumps(index)
    assert 'PRIVATE' not in raw and 'price' not in raw and '999' not in raw
    assert set(index['products'][CODE]['origins'])=={'carrefour','alcampo'}
    assert index['products'][CODE]['content_quantity']==.5
    changed=deepcopy(seed);changed['products'][CODE].append({'store':'bm','content_quantity':1,'content_unit':'kg'})
    row=builder.build(changed,{'common':{}})['products'][CODE]
    assert 'content_quantity' not in row and 'content' in row['conflicts'] and row['brand'].lower()=='marca'


@pytest.mark.parametrize('fields',[{'price':1},{'content_quantity':1,'content_unit':[]},{'pack_count':True},{'brand':'bad\nname'}])
def test_public_common_index_rejects_invalid_or_store_specific_fields(fields):
    with pytest.raises(ValueError):parse_index(json.dumps(document(fields)).encode())


def test_published_dictionary_includes_non_mercadona_common_eans():
    data=parse_index((ROOT/'data/ean-common.json').read_bytes())
    seed=json.loads((ROOT/'data/ean-common-contributions.json').read_text())
    assert len(data['products'])>4000 and len(seed['products'])>50
    assert any(row.get('store') in ('carrefour','alcampo','lidl','lasirena') for rows in seed['products'].values() for row in rows)
    assert all(gtin(code)==code for code in data['products'])


async def test_common_index_fills_all_shops_without_adding_alternatives_or_prices(hass,aioclient_mock):
    catalog=Catalog(hass);await catalog.async_load()
    stores=['carrefour','alcampo','lidl','mercadona','masymas','bm','consum','lasirena','eroski']
    await catalog.async_save_product({'name':'Mi producto','barcodes':[EAN],'commercial_references':[{'store':store,'ean':EAN,'last_price':{'price':i+1,'currency':'EUR','checked_at':time.time()}} for i,store in enumerate(stores)]})
    index=CommonEANIndex(hass,catalog);await index.async_load()
    aioclient_mock.get(URL,content=json.dumps(document()).encode(),headers={'ETag':'"common-1"'})
    await index.async_refresh();assert await catalog.async_apply_common_ean_data(index.entries({CODE}))==1
    refs=catalog.products[0]['commercial_references']
    assert len(refs)==len(stores) and all(ref['content_quantity']==.5 and ref['pack_count']==6 for ref in refs)
    assert [ref['last_price']['price'] for ref in refs]==list(range(1,10))
    assert all(ref['common_sources']['brand']['store']=='community' for ref in refs)
    await index.async_refresh();assert aioclient_mock.call_count==1
    again=CommonEANIndex(hass,catalog);await again.async_load();assert again.entries({CODE})==index.entries({CODE})
    aioclient_mock.clear_requests();again._data['checked_at']=0;again._data['next_attempt']=0;aioclient_mock.get(URL,status=304)
    await again.async_refresh();assert aioclient_mock.mock_calls[0][3]['If-None-Match']=='"common-1"'
    aioclient_mock.clear_requests();again._data['checked_at']=0;again._data['next_attempt']=0;aioclient_mock.get(URL,status=503)
    await again.async_refresh();assert again.entries({CODE}) and aioclient_mock.call_count==1


async def test_generic_common_fields_preserve_weight_mode_manual_units_and_conflicts(hass):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({'name':'Producto','commercial_references':[
        {'store':'carrefour','ean':EAN,'sale_mode':'weight','content_unit':'g'},
        {'store':'alcampo','ean':EAN,'sale_mode':'package','content_unit':'ml'},
        {'store':'lidl','ean':EAN,'brand':'Marca personal','active':False}]})
    index=CommonEANIndex(hass,catalog);index._data['index']=parse_index(json.dumps(document()).encode())
    await catalog.async_apply_common_ean_data(index.entries({CODE}))
    weight,manual,disabled=catalog.products[0]['commercial_references']
    assert weight['content_quantity'] is None and weight['content_unit']=='g' and 'pack_count' not in weight
    assert manual['content_quantity'] is None and manual['content_unit']=='ml'
    assert disabled['brand']=='Marca personal' and disabled['active'] is False


async def test_common_index_uses_main_fallback_and_survives_cache_write_failure(hass,aioclient_mock):
    catalog=Catalog(hass);await catalog.async_load();index=CommonEANIndex(hass,catalog)
    index._store.async_save=AsyncMock(side_effect=OSError('disk'))
    aioclient_mock.get(URL,status=404);aioclient_mock.get(INITIAL_URL,content=json.dumps(document()).encode())
    hint=await index.async_hint(EAN)
    assert hint['brand']=='Marca' and hint['content_quantity']==.5 and aioclient_mock.call_count==2
    assert index.error and index.entries({CODE})


async def test_common_facts_precede_shop_discovery_but_keep_off_product_name(hass):
    lookup=ProductLookup(hass);lookup.common_index=SimpleNamespace(async_hint=AsyncMock(return_value={'brand':'Marca','content_quantity':500,'content_unit':'g'}))
    lookup.catalog_discovery=SimpleNamespace(async_hint=AsyncMock(side_effect=AssertionError('Common data already available')),fingerprint=lambda:'')
    lookup._fetch=AsyncMock(return_value={'status':'found','product_name':'Nombre oficial','brand':'Otra','content_quantity':999,'content_unit':'g'})
    result=await lookup.async_lookup(EAN)
    assert result['product_name']=='Nombre oficial' and result['brand']=='Marca' and result['content_quantity']==500
    lookup.catalog_discovery.async_hint.assert_not_awaited()


async def test_missing_product_name_can_still_come_from_enabled_shop(hass):
    lookup=ProductLookup(hass);lookup.common_index=SimpleNamespace(async_hint=AsyncMock(return_value={'brand':'Marca','content_quantity':500,'content_unit':'g'}))
    lookup.catalog_discovery=SimpleNamespace(async_hint=AsyncMock(return_value={'status':'found','product_name':'Nombre de la tienda','brand':'Otra'}),fingerprint=lambda:'')
    lookup._fetch=AsyncMock(return_value={'status':'not_found'})
    result=await lookup.async_lookup(EAN)
    assert result['product_name']=='Nombre de la tienda' and result['brand']=='Marca' and result['content_quantity']==500
