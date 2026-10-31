"""Meals consume once per person/day, with durable stock and conservative presence."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.stock import StockManager, DEFAULT_CONFIG
from custom_components.improved_shopping_list import stock as stock_module, meal_routines as module
from custom_components.improved_shopping_list.meal_routines import MealRoutines, normalize_rules, normalize_routine


def routine(**changes):
    return {'name':'En casa','persons':['person.one','person.two'],'minimum_minutes':15,'enabled':True,
            'meals':[{'id':name,'name':name,'time':time,'days':list(range(7)),'enabled':True} for name,time in [('desayuno','08:00'),('comida','14:00'),('cena','21:00')]],**changes}


@pytest.fixture
async def env(hass,monkeypatch):
    clock=[datetime(2026,11,2,7,tzinfo=timezone.utc)]
    monkeypatch.setattr(module,'dt_util',SimpleNamespace(now=lambda:clock[0],utcnow=lambda:clock[0]))
    monkeypatch.setattr(stock_module,'time',SimpleNamespace(time=lambda:clock[0].timestamp()))
    catalog=Catalog(hass);await catalog.async_load();await catalog.async_save_product({'name':'Chocolate'})
    stock=StockManager(hass,catalog);await stock.async_load();item=await stock.async_add('Chocolate')
    activity=SimpleNamespace(record=Mock());stock.activity=activity
    manager=MealRoutines(hass,stock,activity);await manager.async_load();saved=await manager.async_save(routine())
    rules=[{'routine_id':saved['id'],'meal_id':m['id'],'amount':1,'person_amounts':{}} for m in saved['meals']]
    config={key:deepcopy(DEFAULT_CONFIG[key]) for key in ('unit','mode','days','refill_quantity','reorder_enabled','reorder_at','reorder_percent','list_entity','usage_entity','usage_state','usage_amount')}
    item=await stock.async_save(item['id'],item['revision'],{**config,'quantity':20,'mode':'meals','meal_rules':rules})
    manager._active=True;manager._started_at=clock[0].timestamp()
    manager._presence={p:deque([(clock[0].timestamp()-3600,'home')],maxlen=256) for p in saved['persons']}
    yield SimpleNamespace(clock=clock,manager=manager,stock=stock,catalog=catalog,routine=saved,item=item,config=config,rules=rules,hass=hass)
    await manager.async_stop()


async def test_multiple_people_only_consume_meals_at_home_once(env):
    env.manager._presence['person.two']=deque([(env.clock[0].timestamp(),'not_home')],maxlen=256)
    env.clock[0]=env.clock[0].replace(hour=8,second=30);await env.manager.async_check();await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19
    env.manager._presence['person.two'].append((env.clock[0].replace(hour=13).timestamp(),'home'))
    env.clock[0]=env.clock[0].replace(hour=14);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==17
    env.manager._presence['person.one'].append((env.clock[0].replace(hour=20).timestamp(),'not_home'))
    env.clock[0]=env.clock[0].replace(hour=21);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==16
    assert len(env.stock.receipts['meal_events'])==6
    assert env.stock.activity.record.call_args.kwargs['diagnostics']['comidas']


async def test_unknown_presence_short_stay_and_arriving_after_meal_do_not_consume(env):
    at=env.clock[0].replace(hour=8).timestamp()
    env.manager._presence={'person.one':deque([(at-600,'home')]),'person.two':deque([(at-3600,'unavailable')])}
    env.clock[0]=env.clock[0].replace(hour=8,second=20);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==20
    env.manager._presence['person.one'].append((at+25,'home'));env.manager._presence['person.two'].append((at+25,'home'))
    env.clock[0]+=timedelta(seconds=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==20


async def test_presence_at_scheduled_time_not_at_processing_time(env):
    at=env.clock[0].replace(hour=8).timestamp()
    env.manager._presence['person.one'].append((at+10,'not_home'))
    env.manager._presence['person.two']=deque([(at-600,'not_home'),(at+5,'home')])
    env.clock[0]=env.clock[0].replace(hour=8,second=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19


async def test_restart_storage_failure_and_reconfiguration_cannot_repeat_meal(env,monkeypatch):
    env.clock[0]=env.clock[0].replace(hour=8,second=15)
    original=env.stock._store.async_save
    monkeypatch.setattr(env.stock._store,'async_save',AsyncMock(side_effect=OSError('disk')))
    await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==20 and not env.stock.receipts.get('meal_events')
    monkeypatch.setattr(env.stock._store,'async_save',original);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==18
    restored=StockManager(env.hass,env.catalog);await restored.async_load()
    again=MealRoutines(env.hass,restored,None);await again.async_load();again._active=True
    # Even a process that retains the original start anchor has the durable ledger.
    again._started_at=env.manager._started_at;again._presence=deepcopy(env.manager._presence)
    await again.async_check();assert restored.snapshot['items'][0]['quantity']==18
    again._started_at=env.clock[0].timestamp();await again.async_check()
    assert restored.snapshot['items'][0]['quantity']==18
    await again.async_stop()


async def test_person_quantities_weekdays_and_disabled_meals(env):
    item=env.stock.snapshot['items'][0];rules=deepcopy(env.rules);rules[0]['person_amounts']={'person.one':2.5,'person.two':.5}
    await env.stock.async_save(item['id'],item['revision'],{**env.config,'mode':'meals','quantity':20,'meal_rules':rules})
    env.clock[0]=env.clock[0].replace(hour=8,second=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==17
    row=deepcopy(env.routine);row.pop('updated_at');row['meals'][1]['days']=[5,6];row['meals'][2]['enabled']=False
    await env.manager.async_save(row)
    env.clock[0]=env.clock[0].replace(hour=14);await env.manager.async_check()
    env.clock[0]=env.clock[0].replace(hour=21);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==17


async def test_startup_does_not_backfill_and_absent_entities_are_not_home(env):
    env.manager._presence={};env.clock[0]=env.clock[0].replace(hour=8,second=20);env.manager._started_at=env.clock[0].timestamp()
    await env.manager.async_check();assert env.stock.snapshot['items'][0]['quantity']==20
    env.clock[0]=env.clock[0].replace(hour=14);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==20
    assert len(env.stock.receipts['meal_events'])==2


@pytest.mark.parametrize('changes',[{'persons':[]},{'persons':['sensor.one']},{'minimum_minutes':-1},{'minimum_minutes':True},{'meals':[]},{'enabled':1}])
def test_invalid_routine(changes):
    with pytest.raises(CatalogError):normalize_routine(routine(**changes))


@pytest.mark.parametrize('rules',[[{'routine_id':'r','meal_id':'m','amount':-1}], [{'routine_id':'r','meal_id':'m','amount':True}], [{'routine_id':'r','meal_id':'m','amount':1,'person_amounts':{'sensor.one':1}}]])
def test_invalid_meal_quantities(rules):
    with pytest.raises(CatalogError):normalize_rules(rules)


async def test_routine_api_permissions_and_restart(hass,hass_ws_client,hass_read_only_user):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.bring'})
    entry.add_to_hass(hass);assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/routines/save','routine':routine()})
    result=await client.receive_json();assert result['success']
    saved=result['result']['routines'][0]
    manager=hass.data[DOMAIN]['meal_routines'];restored=MealRoutines(hass,manager.stock,None);await restored.async_load()
    assert restored.snapshot==manager.snapshot
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id='http://test.local')
    readonly=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await readonly.send_json({'id':1,'type':f'{DOMAIN}/routines/delete','routine_id':saved['id'],'revision':saved['revision']})
    assert (await readonly.receive_json())['error']['code']=='unauthorized'
    await client.send_json({'id':2,'type':f'{DOMAIN}/routines/delete','routine_id':saved['id'],'revision':saved['revision']})
    assert (await client.receive_json())['result']=={'routines':[]}
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not manager._active and not manager._stops
