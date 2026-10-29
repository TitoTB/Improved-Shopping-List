"""Actual observation times, private data projection and durable bounded history."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.price_history import PriceHistory, RETENTION, stamp
from custom_components.improved_shopping_list import price_history as module


def offer(at, price='2.65'):
    return {'store':'alcampo','reference_id':'10739','checked_at':at,'price':price,'currency':'EUR','ean':'8410199023094','reference_price':'15.59','reference_unit':'kg','name':'Patatas 170 g'}


async def test_history_persists_actual_times_limits_retention_and_survives_storage_failure(hass,monkeypatch):
    now=time.time();history=PriceHistory(hass);await history.async_load()
    await history.async_record(offer(now-30,3))
    await history.async_record(offer(now-30,3))
    await history.async_record(offer(now,2))
    assert len(history._entries)==2
    restored=PriceHistory(hass);await restored.async_load()
    assert restored._entries==history._entries
    before=deepcopy(history._entries)
    save=history._store.async_save
    monkeypatch.setattr(history._store,'async_save',AsyncMock(side_effect=OSError('disk')))
    with pytest.raises(OSError):await history.async_record(offer(now+1,1))
    assert history._entries==before
    monkeypatch.setattr(history._store,'async_save',save)
    monkeypatch.setattr(module,'MAX_OBSERVATIONS',2)
    await history.async_record(offer(now+2,1));assert len(history._entries)==2
    history._entries.insert(0,{**history._entries[0],'at':now-RETENTION-1})
    await history.async_record(offer(now+3,0));assert all(entry['at']>now-RETENTION for entry in history._entries)
    for invalid in [None,True,-1,float('nan'),'not a price']:
        await history.async_record(offer(now+10,invalid))
    assert len(history._entries)==2


async def test_comparison_projection_uses_reviewed_selected_receipt_prices_without_private_fields(hass):
    now=time.time();catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Patatas','store_links':{'alcampo':'10739'}})
    history=PriceHistory(hass);await history.async_load();await history.async_record(offer(now))
    date='2026-10-01T10:00:00+02:00'
    receipt={'id':'receipt','store':'carrefour','store_name':'Carrefour','purchased_at':date,'total':5,'currency':'EUR','identity':'PRIVATE_ORDER','account_key':'PRIVATE_ACCOUNT','lines':[
        {'id':'l','product_id':product['id'],'description':'PATATAS','count':2,'amount':5,'unit_price':2.5,'ean':'8410199023094','pack_quantity':170,'pack_unit':'g','price_saved':True},
        {'id':'unknown','product_id':'deleted','description':'OTRO','count':1,'amount':1,'unit_price':1,'price_saved':False}]}
    receipts=SimpleNamespace(stock=SimpleNamespace(receipts={'history':{'r':receipt,'pending':{**receipt,'id':'pending','pending_review':True},'summary':{**receipt,'id':'summary','summary_only':True}}}))
    settings=SimpleNamespace(snapshot={'stores':{'carrefour':{'enabled':True},'alcampo':{'enabled':True}}})
    data=history.comparison_data(catalog,settings,receipts,[])
    assert len(data['purchases'])==1 and len(data['observations'])==2
    assert data['purchases'][0]['lines'][1]['product_id']==''
    assert next(o for o in data['observations'] if o['source']=='receipt')['at']==stamp(date)
    assert next(o for o in data['observations'] if o['source']=='web')['at']==now
    assert 'PRIVATE_' not in str(data) and 'account_key' not in str(data)
    settings.snapshot['stores']['alcampo']['enabled']=False
    result=history.comparison_data(catalog,settings,receipts,[])
    assert set(result['stores'])=={'carrefour','alcampo'}
    assert len(result['observations'])==2


async def test_comparison_command_read_only_and_global_price_setting(hass,hass_ws_client):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/analytics/comparison'})
    result=await client.receive_json();assert result['success'] and result['result']['observations']==[]
    hass.data[DOMAIN]['settings'].update_price_schedule('01:00',False,1)
    await client.send_json({'id':2,'type':f'{DOMAIN}/analytics/comparison'})
    result=await client.receive_json();assert result['success'] and result['result']['enabled'] is False


async def test_comparison_includes_saved_alternative_prices_without_enabled_account(hass,hass_ws_client):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    data=hass.data[DOMAIN]
    await data['catalog'].async_save_product({'name':'Patatas','commercial_references':[
        {'store':'alcampo','reference_id':'10739','ean':'8410199023094','name':'Patatas 170 g','url':'https://www.compraonline.alcampo.es/products/patatas/10739','content_quantity':170,'content_unit':'g','content_confirmed':True,'last_price':{'price':2.5,'currency':'EUR','checked_at':time.time()}},
        {'store':'carrefour','reference_id':'R-prod123','ean':'8410199023094','name':'Patatas 170 g','url':'https://www.carrefour.es/supermercado/patatas/R-prod123/p','content_quantity':170,'content_unit':'g','content_confirmed':True,'last_price':{'price':3,'currency':'EUR','checked_at':time.time()}}
    ]})
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/analytics/comparison'})
    response=await client.receive_json();assert response['success']
    assert set(response['result']['stores'])=={'alcampo','carrefour'}
    assert {o['store']:o['price'] for o in response['result']['observations']}=={'alcampo':2.5,'carrefour':3}
    assert all(o['pack_quantity']==170 and not o['format_pending'] for o in response['result']['observations'])
