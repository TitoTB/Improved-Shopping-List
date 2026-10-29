"""Consent, exact identities, durable spacing, cancellation and safe merges."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.catalog_sources import CatalogSources, INTERVAL
from custom_components.improved_shopping_list import catalog_sources as module
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.product_references import gtin, reference_from_line
from custom_components.improved_shopping_list.store_links import normalize_link

EAN = '8410422111086'
OTHER = '8410199023094'
WEB = 'https://www.compraonline.alcampo.es/products/allioli/722018'
WEB2 = 'https://www.compraonline.alcampo.es/products/patatas/10739'


async def setup(hass):
    catalog=Catalog(hass); await catalog.async_load()
    product=await catalog.async_save_product({'name':'Allioli','barcodes':[EAN]})
    links=EANLinks(hass,catalog); await links.async_load(); catalog.ean_links=links
    links._data['links']={'alcampo:'+gtin(EAN):WEB}
    links._data['checked_at']=time.time()
    lookup=SimpleNamespace(_before_request=AsyncMock(),_blocked_until={})
    sources=CatalogSources(hass,catalog,links,lookup,None); await sources.async_load()
    return catalog,product,links,lookup,sources


async def test_disabled_source_never_associates_or_queries(hass):
    catalog,product,links,lookup,sources=await setup(hass)
    links._data['resolved']={'alcampo:'+gtin(EAN):normalize_link('alcampo',WEB)}
    await catalog.async_apply_ean_links(links.resolved)
    sources._active=True
    await sources.async_run()
    assert not sources.snapshot['enabled'] and not links.resolved
    assert not catalog.products[0]['commercial_references']
    lookup._before_request.assert_not_awaited()
    await sources.async_stop()


async def test_exact_completion_shared_ean_missing_fields_only_and_persistent_spacing(hass,monkeypatch):
    catalog,product,links,lookup,sources=await setup(hass)
    ref=reference_from_line('carrefour',{'ean':EAN,'description':'Allioli 70 ml'})
    ref.update(brand='Marca manual',content_confirmed=True,last_price={'price':1,'currency':'EUR','checked_at':1})
    await catalog.async_save_product({'id':product['id'],'revision':product['revision'],'name':'Allioli','barcodes':[EAN],'commercial_references':[ref]})
    await catalog.async_save_product({'name':'Patatas','barcodes':[OTHER]})
    links._data['links']['alcampo:'+gtin(OTHER)]=WEB2
    clock=[time.time()]; requests=[]
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]))
    async def wait(delay): clock[0]+=delay
    monkeypatch.setattr(module,'sleep',wait)
    async def retrieve(url,store,code,*,before_request):
        await before_request();requests.append(clock[0])
        return {'store':store,'reference_id':normalize_link(store,url)['id'],'ean':code,'name':'Nombre comercial',
                'brand':'marca web','content_quantity':500,'content_unit':'g','price':2.5,'currency':'EUR','nutriscore':'b'}
    lookup.retrieve=AsyncMock(side_effect=retrieve)
    await sources.async_set_enabled(True); sources._active=True
    try:
        await sources.async_run()
        assert len(requests)==2 and requests[1]-requests[0]>=INTERVAL
        current=next(p for p in catalog.products if p['id']==product['id'])
        old=next(ref for ref in current['commercial_references'] if ref['store']=='carrefour')
        new=next(ref for ref in current['commercial_references'] if ref['store']=='alcampo')
        assert old['brand']=='Marca manual' and old['content_quantity']==70 and old['last_price']['price']==1
        assert new['brand']=='Marca manual' and new['last_price']['price']==2.5 and new['content_quantity']==70
        assert new['content_unit']=='ml'
        assert old['nutriscore']['grade']=='b'
        assert sources.snapshot['processed']==2 and sources.snapshot['phase']=='finished'
        restored=CatalogSources(hass,catalog,links,lookup,None); await restored.async_load()
        assert restored.snapshot['enabled'] and restored.snapshot['next_request']==sources.snapshot['next_request']
        # No repeat fetch when ordinary catalog writes trigger another scan.
        await sources.async_run();assert lookup.retrieve.await_count==2
    finally:
        await sources.async_stop()


async def test_disabling_cancels_inflight_and_retains_existing_options(hass):
    catalog,product,links,lookup,sources=await setup(hass)
    entered=asyncio.Event()
    async def retrieve(*args,**kwargs):
        entered.set();await asyncio.Event().wait()
    lookup.retrieve=AsyncMock(side_effect=retrieve)
    await sources.async_set_enabled(True); sources._active=True
    sources._task=hass.async_create_task(sources.async_run())
    await entered.wait()
    await sources.async_set_enabled(False)
    assert not sources.snapshot['enabled'] and not sources.snapshot['running']
    assert len(catalog.products[0]['commercial_references'])==1
    assert 'last_price' not in catalog.products[0]['commercial_references'][0]
    await sources.async_stop()


async def test_mismatched_ean_cannot_save_price(hass):
    catalog,product,links,lookup,sources=await setup(hass)
    lookup.retrieve=AsyncMock(return_value={'store':'alcampo','reference_id':'722018','ean':OTHER,'price':9,'currency':'EUR'})
    await sources.async_set_enabled(True);sources._active=True
    try:
        await sources.async_run()
        assert sources.snapshot['errors'] and 'last_price' not in catalog.products[0]['commercial_references'][0]
    finally:
        await sources.async_stop()


async def test_source_commands_registered_consent_permissions_and_unload(hass,hass_ws_client,hass_read_only_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'})
    entry.add_to_hass(hass);assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/catalog_sources/subscribe'})
    assert (await client.receive_json())['success']
    assert (await client.receive_json())['event']['enabled'] is False
    await client.send_json({'id':2,'type':f'{DOMAIN}/catalog_sources/set','enabled':True})
    # The subscription update and response can arrive in either order.
    messages=[await client.receive_json(),await client.receive_json()]
    assert any(m.get('result',{}).get('enabled') for m in messages)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id='http://test.local')
    reader=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await reader.send_json({'id':1,'type':f'{DOMAIN}/catalog_sources/set','enabled':False})
    assert not (await reader.receive_json())['success']
    assert await hass.config_entries.async_unload(entry.entry_id)
    await reader.send_json({'id':2,'type':f'{DOMAIN}/catalog_sources/status'})
    assert (await reader.receive_json())['error']['code']=='not_loaded'
