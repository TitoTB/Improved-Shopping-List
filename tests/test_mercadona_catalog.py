"""Exact Mercadona dictionary matches, package data and opt-in source lifecycle."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.ean_links import EANLinks, parse_dictionary
from custom_components.improved_shopping_list.mercadona_catalog import MercadonaCatalog, product_data
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.store_links import normalize_link

EAN='8430543025611'
OTHER='8410199023094'
WEB='https://tienda.mercadona.es/product/69938'
API='https://tienda.mercadona.es/api/products/69938/?lang=es&wh=mad1'

def payload():
    return {'id':'69938','ean':EAN,'display_name':'Tomate rallado','brand':None,'details':{'brand':'marca'},
        'published':True,'is_bulk':False,'is_variable_weight':False,
        'price_instructions':{'unit_price':'1.45','unit_size':.29,'size_format':'kg','approx_size':False,
            'reference_price':'5.000','reference_format':'kg','is_pack':False}}


def test_product_fields_use_sellable_package_and_missing_brand_is_not_invented():
    p=payload();d=product_data(p,normalize_link('mercadona',WEB),EAN)
    assert d['price']==1.45 and d['brand']=='Marca'
    assert d['content_quantity']==.29 and d['content_unit']=='kg'
    assert d['measure_price']['price']==5 and d['measure_price']['unit']=='kg'
    p['details']={}
    assert product_data(p,normalize_link('mercadona',WEB))['brand']==''
    p['is_variable_weight']=True
    d=product_data(p,normalize_link('mercadona',WEB))
    assert 'content_quantity' not in d and d['measure_price']['price']==5
    p['is_variable_weight']=False
    p['price_instructions'].update(is_pack=True,pack_size=.037,total_units=4,unit_size=.148)
    assert product_data(p,normalize_link('mercadona',WEB))['content_quantity']==.148


@pytest.mark.parametrize('change',[{'ean':OTHER},{'ean':''},{'id':'999'}])
def test_unverified_or_mismatched_product_never_becomes_an_option(change):
    p=payload();p.update(change)
    with pytest.raises(PriceError):product_data(p,normalize_link('mercadona',WEB),EAN)


async def test_manual_lookup_uses_one_public_api_and_preserves_exact_identity(hass,aioclient_mock,monkeypatch):
    lookup=OptionLookup(hass)
    monkeypatch.setattr(lookup,'_before_request',AsyncMock())
    aioclient_mock.get(API,json=payload())
    try:
        data=await lookup.retrieve(WEB,'mercadona',EAN)
        assert data['ean']==EAN and data['price']==1.45 and data['content_quantity']==.29
        assert lookup._before_request.await_count==1 and aioclient_mock.call_count==1
        assert await lookup.retrieve(WEB,'mercadona',EAN)==data
        with pytest.raises(PriceError):await lookup.retrieve(WEB,'mercadona',OTHER)
        assert aioclient_mock.call_count==1
    finally:lookup.close()


async def setup(hass):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({'name':'Tomate','barcodes':[EAN]})
    links=EANLinks(hass,catalog);await links.async_load()
    links._data.update(links={'mercadona:'+gtin(EAN):WEB},checked_at=time.time())
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={},retrieve=AsyncMock(return_value=product_data(payload(),normalize_link('mercadona',WEB))))
    source=MercadonaCatalog(hass,catalog,links,lookup,None);await source.async_load()
    return catalog,links,lookup,source


async def test_opt_in_dictionary_only_merge_visibility_restart_and_exclusions(hass):
    catalog,links,lookup,source=await setup(hass)
    source._active=True
    await source.async_run();lookup.retrieve.assert_not_awaited()
    source._active=False
    await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run();source._active=False
        assert not any(r['store']=='mercadona' for r in catalog.products[0]['commercial_references'])
        assert catalog.products[0]['commercial_references'][0]['content_quantity']==.29
        assert 'last_price' not in catalog.products[0]['commercial_references'][0]
        assert 'mercadona' in links.catalog_stores and 'mercadona' not in links.enabled_stores
        await source.async_set_show_store(True)
        option=next(r for r in catalog.products[0]['commercial_references'] if r['store']=='mercadona')
        assert option['last_price']['price']==1.45 and option['catalog_source']
        await source.async_set_show_store(False)
        assert not any(r['store']=='mercadona' for r in catalog.products[0]['commercial_references'])
        again=Catalog(hass);await again.async_load()
        restored=MercadonaCatalog(hass,again,links,lookup,None);await restored.async_load()
        await restored.async_set_show_store(True)
        assert next(r for r in again.products[0]['commercial_references'] if r['store']=='mercadona')['last_price']['price']==1.45
        assert lookup.retrieve.await_count==1
        await restored.async_stop()
        await source.async_set_show_store(True)
        current=catalog.products[0];refs=deepcopy(current['commercial_references'])
        for ref in refs:
            if ref['store']=='mercadona':ref['active']=False
        await catalog.async_save_product({'id':current['id'],'revision':current['revision'],'name':current['name'],'barcodes':[EAN],'commercial_references':refs})
        source._active=True;await source.async_run()
        assert not next(r for r in catalog.products[0]['commercial_references'] if r['store']=='mercadona')['active']
        assert lookup.retrieve.await_count==1
    finally:await source.async_stop()


async def test_missing_or_wrong_ean_is_not_saved_even_with_dictionary_link(hass):
    catalog,links,lookup,source=await setup(hass)
    data=lookup.retrieve.return_value;data['ean']=OTHER
    await source.async_set_enabled(True);await source.async_set_show_store(True);source._active=True
    try:
        await source.async_run()
        assert source.snapshot['errors']
        assert not any('last_price' in r for r in catalog.products[0]['commercial_references'])
    finally:await source.async_stop()


async def test_status_read_does_not_restart_and_consent_is_independent(hass,hass_ws_client):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    source=hass.data[DOMAIN]['mercadona_catalog'];source.async_run=AsyncMock()
    assert not source.snapshot['enabled']
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/catalog_sources/set','source':'mercadona','enabled':True})
    assert (await client.receive_json())['result']['enabled']
    await client.send_json({'id':2,'type':f'{DOMAIN}/catalog_sources/status','source':'mercadona'})
    assert (await client.receive_json())['result']['enabled']
    assert not hass.data[DOMAIN]['catalog_sources'].snapshot['enabled']
    source.async_run.assert_not_awaited()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_api_rejection_honors_retry_after_and_preserves_retryable_attempt(hass,aioclient_mock):
    catalog,links,lookup,source=await setup(hass)
    real=OptionLookup(hass);source.lookup=real
    aioclient_mock.get(API,status=403,headers={'Retry-After':'3600'})
    await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run()
        assert source.snapshot['phase']=='paused' and source.snapshot['retry_at']>time.time()+3500
        assert source.snapshot['errors'][0]['diagnostics']['http_status']==403
        assert next(iter(source._data['attempts'].values()))['at']==0
        await source.async_run()
        assert aioclient_mock.call_count==1
        assert not any('last_price' in r for r in catalog.products[0]['commercial_references'])
    finally:
        await source.async_stop();real.close()


def test_dictionary_accepts_mercadona_only_rows_and_rejects_foreign_domains():
    rows=f'EAN,Carrefour,Alcampo,Lidl,Mercadona\n{EAN},,,,{WEB}\n'.encode()
    assert parse_dictionary(rows)=={'mercadona:'+gtin(EAN):WEB}
    with pytest.raises(ValueError):parse_dictionary(rows.replace(b'tienda.mercadona.es',b'example.org'))
