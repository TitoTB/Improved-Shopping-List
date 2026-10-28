"""Qualified visits, separate stores, restart safety and automatic request scopes."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.improved_shopping_list import purchase_visits, purchase_detection
from custom_components.improved_shopping_list.purchase_detection import PurchaseDetection
from custom_components.improved_shopping_list.receipts import ReceiptManager
from custom_components.improved_shopping_list.carrefour_account import CarrefourAccount
from custom_components.improved_shopping_list.catalog import CatalogError
from custom_components.improved_shopping_list.shopping_places import normalize_places


@pytest.fixture
async def visit_env(hass, monkeypatch):
    clock=[dt_util.now().replace(hour=12,minute=0,second=0,microsecond=0)]
    dates=SimpleNamespace(now=lambda:clock[0],parse_datetime=dt_util.parse_datetime)
    monkeypatch.setattr(purchase_visits,'dt_util',dates)
    monkeypatch.setattr(purchase_detection,'dt_util',dates)
    shops=[{'id':'a','name':'Mi Carrefour','account':'carrefour','image_url':'','color':'#123456','zones':['zone.a']},
           {'id':'b','name':'Frutería','account':'','image_url':'','color':'#654321','zones':['zone.b']}]
    config={'enabled':True,'threshold':1,'zone_assignment':True,'persons':['person.one'],'store_zones':{},'minimum_minutes':2,'shops':shops}
    settings=SimpleNamespace(snapshot={'entities':['todo.one'],'purchase_detection':config},subscribe=lambda cb:lambda:None)
    activity=SimpleNamespace(record=Mock())
    stock=SimpleNamespace(_lock=asyncio.Lock(),_items={},receipts={'history':{},'aliases':{},'purchases':{},'coverage':{}},
        catalog=SimpleNamespace(products=[{'id':'cacao','name':'Cacao'},{'id':'milk','name':'Leche'}]),activity=activity)
    async def persist(items,*,receipts):stock.receipts=receipts
    stock._persist=persist
    receipts=ReceiptManager(hass,stock,None,None);receipts.settings=settings
    accounts=SimpleNamespace(note_completion=Mock())
    manager=PurchaseDetection(hass,settings,receipts,activity,accounts)
    await manager.async_load();manager._active=True;manager._queue=Mock()
    for zone in ('a','b'):hass.states.async_set('zone.'+zone,'0',{'friendly_name':zone.upper()})
    hass.states.async_set('person.one','A')
    return SimpleNamespace(hass=hass,clock=clock,manager=manager,settings=settings,receipts=receipts,stock=stock,accounts=accounts)


def complete(env,uid,name='Cacao'):
    env.manager.note_completion('todo.one',{'uid':uid,'summary':name})


async def test_minimum_dwell_and_two_stores_do_not_duplicate_products(visit_env):
    e=visit_env
    await e.manager.async_check()
    e.clock[0]+=timedelta(seconds=119)
    complete(e,'one');complete(e,'two','Leche')
    await e.manager.async_check()
    assert not e.manager.qualified_places()
    assert e.stock.receipts['history']['detected:'+e.clock[0].date().isoformat()]['store']=='unknown'
    e.clock[0]+=timedelta(seconds=1)
    await e.manager.async_check()
    first=next(r for r in e.stock.receipts['history'].values() if r.get('shop_id')=='a')
    assert first['shoppers']==['person.one'] and len(first['completed_products'])==2
    assert len(e.stock.receipts['history'])==1
    e.hass.states.async_set('person.one','away');await e.manager.async_check()
    e.clock[0]+=timedelta(seconds=10)
    e.hass.states.async_set('person.one','B');await e.manager.async_check()
    e.clock[0]+=timedelta(seconds=60);complete(e,'three')
    e.clock[0]+=timedelta(seconds=60);await e.manager.async_check()
    records=list(e.stock.receipts['history'].values())
    assert {r['shop_id'] for r in records}=={'a','b'}
    keys=[p['key'] for r in records for p in r['completed_products']]
    assert len(keys)==len(set(keys))==3
    second=next(r for r in records if r['shop_id']=='b')
    assert second['store']=='shop:b' and second['account']==''
    assert e.manager.ticket_scope('carrefour')==[first['id']]


async def test_passing_through_or_unknown_presence_does_not_qualify(visit_env):
    e=visit_env;await e.manager.async_check()
    e.clock[0]+=timedelta(seconds=60)
    e.hass.states.async_set('person.one','away');await e.manager.async_check()
    e.clock[0]+=timedelta(minutes=10);await e.manager.async_check()
    assert not e.manager.qualified_places()
    e.hass.states.async_set('person.one','A');await e.manager.async_check()
    e.clock[0]+=timedelta(minutes=3)
    e.hass.states.async_set('person.one','unavailable');await e.manager.async_check()
    assert not e.manager.qualified_places()


async def test_restart_keeps_qualified_visits_but_never_counts_offline_dwell(visit_env):
    e=visit_env;await e.manager.async_check();e.clock[0]+=timedelta(minutes=1)
    await e.manager.async_check()
    restored=PurchaseDetection(e.hass,e.settings,e.receipts,e.stock.activity,e.accounts)
    await restored.async_load();restored._active=True;restored._queue=Mock()
    e.clock[0]+=timedelta(hours=1);await restored.async_check()
    assert not restored.qualified_places()
    e.clock[0]+=timedelta(minutes=2);await restored.async_check()
    assert restored.qualified_places()


async def test_manual_allocation_and_discard_survive_future_checks(visit_env):
    e=visit_env;await e.manager.async_check();e.clock[0]+=timedelta(minutes=2)
    complete(e,'one');complete(e,'two');await e.manager.async_check()
    receipt=next(iter(e.stock.receipts['history'].values()))
    keys=[p['key'] for p in receipt['candidate_products']]
    await e.receipts.async_complete_detected_purchase(receipt['id'],'shop:a',5.5,product_keys=keys,shoppers=['person.one'])
    await e.manager.async_check()
    assert e.stock.receipts['history'][receipt['id']]['total']==5.5
    await e.receipts.async_discard_detected_purchase(receipt['id'])
    await e.manager.async_check()
    assert receipt['id'] not in e.stock.receipts['history']


async def test_carrefour_one_attempt_per_detected_purchase_with_durable_scopes(hass):
    account=CarrefourAccount(hass,Mock(),Mock())
    account._active=True;account._session={'login_token':'synthetic'};account._options['auto_ticket']=True
    now=dt_util.now();identifiers=['detected:'+now.date().isoformat()+':a']
    account.purchase_detection=SimpleNamespace(enabled=True,zone_config={'shops':[]},ticket_scope=lambda provider:identifiers)
    account._download_automatic_ticket=AsyncMock(return_value=True)
    assert account.automatic_due(now,True)
    await account.async_automatic_ticket(now,True)
    assert not account.automatic_due(now,True)
    restored=CarrefourAccount(hass,Mock(),Mock());await restored.async_load()
    assert restored._options['ticket_scopes']==identifiers
    identifiers.append('detected:'+now.date().isoformat()+':b')
    assert account.automatic_due(now,True)
    await account.async_automatic_ticket(now,True)
    assert account._download_automatic_ticket.await_count==2


def test_physical_store_validation_rejects_unsafe_images_accounts_and_duplicate_ids():
    shop={'id':'shop','name':'Frutería','zones':['zone.shop'],'color':'#123456'}
    assert normalize_places([shop])[0]['account']==''
    for data in ([shop,shop],[{**shop,'account':'dia'}],[{**shop,'image_url':'javascript:alert(1)'}]):
        with pytest.raises(ValueError):normalize_places(data)
