"""Eligibility, forced URL retrieval, spacing, saved progress and safe merges."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import time

from custom_components.improved_shopping_list.catalog import Catalog, FIELDS
from custom_components.improved_shopping_list.pending_information import PendingInformationRefresh, pending, merge_result
from custom_components.improved_shopping_list import pending_information as module
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.store_links import normalize_link

EAN='8410199023094'
OTHER='8410422111086'
URL='https://www.carrefour.es/supermercado/patatas/R-123/p'
URL2='https://www.compraonline.alcampo.es/products/patatas/10739'


def reference(store='carrefour',url=URL,ean=EAN,**fields):
    return {'store':store,'ean':ean,'url':url,'reference_id':normalize_link(store,url)['id'],'name':'Patatas Gourmet',**fields}


def result(url=URL,ean=EAN):
    store='alcampo' if 'alcampo' in url else 'carrefour';link=normalize_link(store,url)
    return {'store':store,'ean':ean,'url':url,'reference_id':link['id'],'name':'Patatas Gourmet 170 g','brand':"Lay's",'content_quantity':170,'content_unit':'g','price':2.89,'currency':'EUR','checked_at':int(time.time())}


def test_only_all_incomplete_options_make_product_pending():
    incomplete=reference(last_price={'price':2,'currency':'EUR'})
    complete={**incomplete,'content_quantity':170,'content_unit':'g'}
    assert pending({'id':'p','commercial_references':[incomplete]})
    assert not pending({'id':'p','commercial_references':[incomplete,complete]})
    assert pending({'id':'p','commercial_references':[incomplete,{**complete,'active':False}]})
    assert pending({'id':'p','commercial_references':[]})
    product={'id':'p','commercial_references':[{**complete,'last_price':None}]}
    offer={'catalog_product_id':'p','store':'carrefour','ean':EAN,'price':2,'currency':'EUR'}
    assert not pending(product,[offer])
    assert pending(product,[{**offer,'ean':OTHER}])


async def setup(hass,monkeypatch,two=True):
    catalog=Catalog(hass);await catalog.async_load()
    refs=[reference()]+([reference('alcampo',URL2)] if two else [])
    product=await catalog.async_save_product({'name':'Patatas','commercial_references':refs})
    lookup=SimpleNamespace(_next=0,_before_request=AsyncMock(),retrieve=AsyncMock())
    prices=SimpleNamespace(prices_for=lambda product:[])
    clock=[time.time()];waits=[]
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]))
    async def advance(seconds):waits.append(seconds);clock[0]+=seconds
    monkeypatch.setattr(module,'sleep',advance)
    activity=Mock()
    manager=PendingInformationRefresh(hass,catalog,lookup,prices,activity);await manager.async_load();manager.start()
    async def retrieve(url,**kwargs):
        assert kwargs['force'] is True
        await kwargs['before_request']()
        return result(url)
    lookup.retrieve.side_effect=retrieve
    return catalog,product,lookup,manager,clock,waits


async def test_batch_only_queues_pending_products_with_urls_and_saves_all_options(hass,monkeypatch):
    catalog,product,lookup,manager,clock,waits=await setup(hass,monkeypatch)
    complete=reference(ean=OTHER,content_quantity=250,content_unit='g',last_price={'price':2,'currency':'EUR','checked_at':int(time.time())})
    await catalog.async_save_product({'name':'Completo','commercial_references':[complete,reference('alcampo',URL2,ean=OTHER)]})
    await catalog.async_save_product({'name':'Sin URL'})
    initial=await manager.async_start();assert initial['total']==2 and initial['products']==[product['id']]
    await manager._task
    assert lookup.retrieve.await_count==2 and waits==[0,20]
    assert manager.snapshot['phase']=='finished' and manager.snapshot['processed']==2
    current=next(p for p in catalog.products if p['id']==product['id'])
    assert all(r['last_price']['price']==2.89 and r['content_quantity']==170 for r in current['commercial_references'])
    assert not pending(current) and manager.snapshot['updated_products']==[product['id']]
    assert manager.activity.record.call_count==1
    restored=PendingInformationRefresh(hass,catalog,lookup,manager.prices,None);await restored.async_load()
    assert restored.snapshot['phase']=='finished' and restored.snapshot['processed']==2
    await manager.async_stop()


async def test_start_reopens_existing_job_without_resetting_it(hass,monkeypatch):
    catalog,product,lookup,manager,clock,waits=await setup(hass,monkeypatch,False)
    entered=asyncio.Event();finish=asyncio.Event()
    async def retrieve(url,**kwargs):
        await kwargs['before_request']();entered.set();await finish.wait();return result(url)
    lookup.retrieve.side_effect=retrieve
    await manager.async_start();await entered.wait();task=manager._task
    state=await manager.async_start()
    assert manager._task is task and state['total']==1 and lookup.retrieve.await_count==1
    finish.set();await task;await manager.async_stop()


async def test_restart_resumes_the_queue_and_preserves_twenty_second_gate(hass,monkeypatch):
    catalog,product,lookup,manager,clock,waits=await setup(hass,monkeypatch,False)
    entered=asyncio.Event()
    async def retrieve(url,**kwargs):
        await kwargs['before_request']();entered.set();await asyncio.Event().wait()
    lookup.retrieve.side_effect=retrieve
    await manager.async_start();await entered.wait();await manager.async_stop()
    restored=PendingInformationRefresh(hass,catalog,lookup,manager.prices,None);await restored.async_load()
    async def finish(url,**kwargs):await kwargs['before_request']();return result(url)
    lookup.retrieve.side_effect=finish
    restored.start();await restored._task
    assert restored.snapshot['processed']==1 and restored.snapshot['phase']=='finished' and waits==[0,20]
    await restored.async_stop()


async def test_concurrent_product_name_edit_survives_refresh(hass,monkeypatch):
    catalog,product,lookup,manager,clock,waits=await setup(hass,monkeypatch,False)
    async def retrieve(url,**kwargs):
        await kwargs['before_request']()
        current={k:v for k,v in catalog.products[0].items() if k in FIELDS};current['name']='Nombre corregido';await catalog.async_save_product(current)
        return result(url)
    lookup.retrieve.side_effect=retrieve
    await manager.async_start();await manager._task
    assert catalog.products[0]['name']=='Nombre corregido'
    assert catalog.products[0]['commercial_references'][0]['last_price']['price']==2.89
    await manager.async_stop()


async def test_blocked_shop_does_not_repeat_remaining_urls(hass,monkeypatch):
    catalog,product,lookup,manager,clock,waits=await setup(hass,monkeypatch,False)
    current={k:v for k,v in catalog.products[0].items() if k in FIELDS};current['commercial_references'].append(reference(url='https://www.carrefour.es/supermercado/patatas/R-456/p'))
    await catalog.async_save_product(current)
    lookup.retrieve.side_effect=PriceError('HTTP 403',http_status=403,retry_seconds=900)
    await manager.async_start();await manager._task
    assert lookup.retrieve.await_count==1 and manager.snapshot['skipped']==1
    assert manager.snapshot['errors'][0]['product']=='Patatas'
    assert all('last_price' not in r for r in catalog.products[0]['commercial_references'])
    await manager.async_start();await manager._task
    assert lookup.retrieve.await_count==1 and manager.snapshot['skipped']==2
    await manager.async_stop()


def test_different_ean_is_kept_as_a_separate_alternative():
    product={'name':'Patatas','store_links':{'carrefour':{'url':URL}},'commercial_references':[{'id':'r',**reference()}]}
    assert merge_result(product,{'reference_id':'r','url':URL},result(ean=OTHER))
    assert product['commercial_references'][0]['ean']==EAN and product['commercial_references'][0]['url']==''
    assert product['commercial_references'][1]['ean']==OTHER


async def test_force_bypasses_the_option_cache(hass,aioclient_mock,monkeypatch):
    import json
    product={'@type':'Product','url':URL,'name':'Patatas 170 g','brand':{'name':"Lay's"},'gtin13':EAN,'offers':{'price':2.89,'priceCurrency':'EUR'}}
    aioclient_mock.get(URL,text='<script type="application/ld+json">'+json.dumps(product)+'</script>')
    lookup=OptionLookup(hass);monkeypatch.setattr(lookup,'_before_request',AsyncMock())
    await lookup.retrieve(URL);await lookup.retrieve(URL)
    assert aioclient_mock.call_count==1
    await lookup.retrieve(URL,force=True)
    assert aioclient_mock.call_count==2
    lookup.close()
