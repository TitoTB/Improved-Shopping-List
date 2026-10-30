"""Public-shop consent, exact identity, lookup priority and persistent spacing."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time
from urllib.parse import urlencode

import pytest

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.product_lookup import ProductLookup, FIELDS
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.public_catalogs import CatalogDiscovery, PublicCatalogSource, PUBLIC_SHOPS, RequestGate, shop_product, commercial_terms
from custom_components.improved_shopping_list import public_catalogs as module
from custom_components.improved_shopping_list.store_links import normalize_link

EAN='8410199023094'
CODE=gtin(EAN)
OTHER='8410422111086'
IDS={'masymas':'29446','bm':'20073','consum':'7394260'}
URLS={store:host+'/es/p/patatas-fritas-gourmet/'+IDS[store] for store,host in PUBLIC_SHOPS.items()}


def payload(store,ean=EAN):
    return {'code':IDS[store],'ean':ean,'productData':{'name':'Patatas fritas Gourmet','description':'Patatas fritas Gourmet 170 g','brand':{'name':"Lay's"},'url':URLS[store]},
        'priceData':{'prices':[{'id':'PRICE','value':{'centAmount':2.89,'centUnitAmount':17}}],'unitPriceUnitType':'KILO'}}


def search_url(store,query):
    return PUBLIC_SHOPS[store]+'/api/rest/V1.0/catalog/searcher/products?'+urlencode({'q':query,'limit':5,'offset':0})


async def setup(hass,monkeypatch,enabled=()):
    monkeypatch.setattr(module,'HTTP_INTERVAL',0)
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Patatas fritas','barcodes':[EAN]})
    links=EANLinks(hass,catalog);await links.async_load();links._data['checked_at']=time.time()
    lookup=OptionLookup(hass)
    discovery=CatalogDiscovery(hass,catalog,links,lookup);await discovery.async_load()
    for store in PUBLIC_SHOPS:
        source=PublicCatalogSource(hass,catalog,links,lookup,None,store,discovery)
        await source.async_load()
        await source.async_set_enabled(store in enabled)
        source._active=True
        monkeypatch.setattr(source,'_before_request',AsyncMock())
        discovery.managers[store]=source
    return catalog,product,links,lookup,discovery


@pytest.mark.parametrize('store',PUBLIC_SHOPS)
def test_product_metadata_requires_same_ean_and_internal_reference(store):
    result=shop_product(store,payload(store),EAN)
    assert result['ean']==EAN and result['content_quantity']==170 and result['content_unit']=='g'
    assert result['price']==2.89 and result['measure_price']['unit']=='kg'
    assert normalize_link(store,URLS[store]+'?tracking=1')['url']==URLS[store]
    with pytest.raises(ValueError):shop_product(store,payload(store,OTHER),EAN)
    wrong=payload(store);wrong['productData']['url']='https://example.test/private'
    with pytest.raises(ValueError):shop_product(store,wrong,EAN)


async def test_disabled_catalogs_never_query_or_resolve(hass,monkeypatch):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch)
    download=AsyncMock();monkeypatch.setattr(links,'_download',download)
    request=AsyncMock();monkeypatch.setattr(module,'request',request)
    assert await discovery.async_hint(EAN) is None
    await discovery.managers['masymas'].async_run()
    request.assert_not_awaited();download.assert_not_awaited()
    assert catalog.products[0]==product


async def test_dictionary_for_any_enabled_store_precedes_direct_ean_search(hass,monkeypatch,aioclient_mock):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch,PUBLIC_SHOPS)
    links._data['links']['bm:'+CODE]=URLS['bm']
    aioclient_mock.get(PUBLIC_SHOPS['bm']+'/api/rest/V1.0/catalog/product/code/20073?showRecommendations=false',json=payload('bm'))
    result=await discovery.async_hint(EAN)
    assert result['source']=='BM' and result['ean']==EAN
    assert aioclient_mock.call_count==1
    restored=CatalogDiscovery(hass,catalog,links,lookup);await restored.async_load();restored.managers=discovery.managers
    assert (await restored.async_hint(EAN))['reference_id']=='20073'
    assert aioclient_mock.call_count==1


async def test_direct_ean_search_runs_before_commercial_name_search(hass,monkeypatch,aioclient_mock):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch,('masymas','bm'))
    aioclient_mock.get(search_url('masymas',EAN),json={'catalog':{'products':[]}})
    aioclient_mock.get(search_url('bm','Patatas fritas gourmet'),json={'catalog':{'products':[payload('bm'),payload('bm',OTHER)]}})
    result=await discovery.async_find('bm',CODE,['Patatas fritas gourmet'])
    assert result['ean']==EAN and result['reference_id']=='20073'
    assert aioclient_mock.call_count==2
    assert str(aioclient_mock.mock_calls[0][1]).startswith(PUBLIC_SHOPS['masymas'])
    assert str(aioclient_mock.mock_calls[1][1]).startswith(PUBLIC_SHOPS['bm'])


async def test_wrong_ean_is_not_associated_and_negative_result_is_cached(hass,monkeypatch,aioclient_mock):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch,('masymas',))
    aioclient_mock.get(search_url('masymas',EAN),json={'catalog':{'products':[payload('masymas',OTHER)]}})
    source=discovery.managers['masymas']
    await source.async_set_show_store(True)
    await source.async_run()
    await source.async_run()
    assert catalog.products[0]==product and aioclient_mock.call_count==1
    assert source.snapshot['phase']=='finished' and source.snapshot['processed']==1
    await source.async_stop()


async def test_data_only_completion_then_visibility_uses_saved_match_without_query(hass,monkeypatch,aioclient_mock):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch,('masymas',))
    aioclient_mock.get(search_url('masymas',EAN),json={'catalog':{'products':[payload('masymas')]}})
    source=discovery.managers['masymas']
    await source.async_run()
    rows=catalog.products[0]['commercial_references']
    assert len(catalog.products)==1 and rows[0]['store']=='' and rows[0]['content_quantity']==170
    assert not rows[0].get('last_price')
    await source.async_set_show_store(True)
    rows=catalog.products[0]['commercial_references']
    assert any(r['store']=='masymas' and r['last_price']['price']==2.89 for r in rows)
    assert aioclient_mock.call_count==1
    await source.async_set_show_store(False)
    assert not any(r['store']=='masymas' for r in catalog.products[0]['commercial_references'])
    await source.async_stop()


async def test_http_block_pauses_source_without_erasing_previous_data(hass,monkeypatch,aioclient_mock):
    catalog,product,links,lookup,discovery=await setup(hass,monkeypatch,('masymas',))
    aioclient_mock.get(search_url('masymas',EAN),status=403)
    source=discovery.managers['masymas'];await source.async_run()
    assert source.snapshot['phase']=='paused' and source.snapshot['retry_at']>time.time()
    assert source.snapshot['errors'][0]['diagnostics']['http_status']==403
    await source.async_run();assert aioclient_mock.call_count==1
    await source.async_stop()


async def test_scan_uses_catalog_before_open_food_facts(hass,monkeypatch):
    lookup=ProductLookup(hass)
    lookup.catalog_discovery=SimpleNamespace(async_hint=AsyncMock(return_value={'status':'found','name':'Nombre comercial','source':'Masymas','ean':EAN,'url':URLS['masymas']}))
    fetch=AsyncMock();monkeypatch.setattr(lookup,'_fetch',fetch)
    assert (await lookup.async_lookup(EAN))['source']=='Masymas'
    fetch.assert_not_awaited()
    lookup.catalog_discovery.async_hint.return_value=None
    fetch.return_value={'status':'not_found'}
    assert (await lookup.async_lookup(OTHER))['status']=='not_found'
    fetch.assert_awaited_once()


def test_name_queries_only_use_existing_commercial_references():
    product={'name':'Patatas fritas','commercial_references':[{'store':'carrefour','ean':EAN,'name':'Patatas fritas','brand':"Lay's"}]}
    assert commercial_terms([product],CODE)==[]
    product['commercial_references'][0]['name']='Patatas fritas Gourmet 170 g'
    assert commercial_terms([product],CODE)==['Patatas fritas Gourmet 170 g','Patatas fritas Gourmet']
    product['commercial_references'][0]['ean']=OTHER
    assert commercial_terms([product],CODE)==[]


async def test_http_gate_keeps_twenty_second_spacing_after_reload(hass,monkeypatch):
    clock=[1000.0];waits=[]
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock[0]))
    async def advance(delay):waits.append(delay);clock[0]+=delay
    monkeypatch.setattr(module,'sleep',advance)
    gate=RequestGate(hass);await gate.before('bm')
    restored=RequestGate(hass);await restored.before('bm')
    assert waits==[0,20]
    await restored.pause('bm',900)
    again=RequestGate(hass)
    with pytest.raises(ValueError,match='pausa de reintento'):
        await again.before('bm')
    assert waits==[0,20]  # A block never silently sleeps through a batch.


async def test_enabling_catalog_rechecks_a_previously_cached_general_hint(hass,monkeypatch):
    lookup=ProductLookup(hass)
    lookup._cache[CODE]={'expires':time.time()+86400,'fields':FIELDS,'result':{'status':'found','name':'Nombre previo'}}
    assert lookup.is_fresh(EAN)
    lookup.catalog_discovery=SimpleNamespace(fingerprint=lambda:'masymas',async_hint=AsyncMock(return_value={'status':'found','name':'Nombre comercial','source':'Masymas','ean':EAN,'url':URLS['masymas']}))
    assert not lookup.is_fresh(EAN)
    assert (await lookup.async_lookup(EAN))['source']=='Masymas'
    assert lookup.is_fresh(EAN)
