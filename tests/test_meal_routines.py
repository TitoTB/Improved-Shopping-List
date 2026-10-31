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
    return {'name':'En casa','persons':['person.one','person.two'],'enabled':True,
            'meals':[{'id':name,'name':name,'start_time':start,'end_time':end,'days':list(range(7)),'enabled':True} for name,start,end in [('desayuno','08:00','09:00'),('comida','14:00','15:00'),('cena','21:00','22:00')]],**changes}


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
    assert len(env.stock.receipts['meal_events'])==4
    assert env.stock.activity.record.call_args.kwargs['diagnostics']['comidas']


async def test_any_home_presence_counts_and_later_arrivals_count_once(env):
    at=env.clock[0].replace(hour=8).timestamp()
    env.manager._presence={'person.one':deque([(at-600,'home')]),'person.two':deque([(at-3600,'unavailable')])}
    env.clock[0]=env.clock[0].replace(hour=8,second=20);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19
    env.manager._presence['person.one'].append((at+25,'home'));env.manager._presence['person.two'].append((at+25,'home'))
    env.clock[0]+=timedelta(seconds=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==18


async def test_presence_anywhere_in_window_not_only_at_start_or_check(env):
    at=env.clock[0].replace(hour=8).timestamp()
    env.manager._presence['person.one'].append((at+10,'not_home'))
    env.manager._presence['person.two']=deque([(at-600,'not_home'),(at+5,'home')])
    env.clock[0]=env.clock[0].replace(hour=8,second=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==18


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
    assert not env.stock.receipts.get('meal_events')


async def test_short_visit_near_end_is_seen_even_after_the_window_closes(env):
    start=env.clock[0].replace(hour=8).timestamp();end=start+3600
    env.manager._presence={
        'person.one':deque([(start-100,'not_home'),(end-.2,'home'),(end+.2,'not_home')]),
        'person.two':deque([(start-100,'not_home'),(end,'home')])}
    env.clock[0]=env.clock[0].replace(hour=9,second=10);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19
    await env.manager.async_check();assert env.stock.snapshot['items'][0]['quantity']==19


async def test_presence_events_queue_even_a_brief_visit(env,monkeypatch):
    queued=Mock();monkeypatch.setattr(env.manager,'_queue',queued)
    start=env.clock[0].replace(hour=8,minute=15)
    env.manager._presence={person:deque([(env.clock[0].timestamp(),'not_home')]) for person in env.routine['persons']}
    away=SimpleNamespace(state='not_home',last_changed=env.clock[0])
    home=SimpleNamespace(state='home',last_changed=start)
    left=SimpleNamespace(state='not_home',last_changed=start+timedelta(milliseconds=200))
    for old,new in [(away,home),(home,left)]:
        env.manager._state_changed(SimpleNamespace(data={'entity_id':'person.one','old_state':old,'new_state':new}))
    assert queued.call_count==2
    env.clock[0]=start+timedelta(seconds=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19


async def test_overnight_window_uses_start_day_and_counts_each_person_once(env):
    row=deepcopy(env.routine);row.pop('updated_at')
    row['meals']=[{'id':'night','name':'Cena','start_time':'23:00','end_time':'01:00','days':[0],'enabled':True}]
    await env.manager.async_save(row)
    item=env.stock.snapshot['items'][0]
    await env.stock.async_save(item['id'],item['revision'],{**env.config,'quantity':20,'mode':'meals',
        'meal_rules':[{'routine_id':row['id'],'meal_id':'night','amount':1,'person_amounts':{}}]})
    env.manager._presence['person.one']=deque([(env.clock[0].timestamp(),'not_home')])
    env.clock[0]=env.clock[0].replace(hour=23,minute=30);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19
    env.clock[0]+=timedelta(hours=1);env.manager._presence['person.one'].append((env.clock[0].timestamp(),'home'))
    await env.manager.async_check();await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==18
    assert all(key.endswith('2026-11-02') for key in env.stock.receipts['meal_events'])
    env.clock[0]=env.clock[0].replace(hour=23);await env.manager.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==18


async def test_restart_in_active_window_counts_presence_but_closed_windows_do_not(env):
    env.clock[0]=env.clock[0].replace(hour=8,minute=30);env.manager._started_at=env.clock[0].timestamp()
    await env.manager.async_check();assert env.stock.snapshot['items'][0]['quantity']==18
    await env.manager.async_check();assert env.stock.snapshot['items'][0]['quantity']==18
    # Lunch has ended before this restart; being home now cannot backfill it.
    env.clock[0]=env.clock[0].replace(hour=16);env.manager._started_at=env.clock[0].timestamp()
    await env.manager.async_check();assert env.stock.snapshot['items'][0]['quantity']==18


async def test_legacy_routine_migration_keeps_ids_and_old_positive_ledger(env):
    legacy={'id':env.routine['id'],'revision':env.routine['revision'],'updated_at':env.routine['updated_at'],
        'name':'Anterior','persons':['person.one','person.two'],'minimum_minutes':15,'enabled':True,
        'meals':[{'id':'desayuno','name':'Desayuno','time':'08:00','days':list(range(7)),'enabled':True}]}
    await env.manager._store.async_save({'routines':{legacy['id']:legacy}})
    migrated=MealRoutines(env.hass,env.stock,None);await migrated.async_load()
    saved=migrated.snapshot['routines'][0]
    assert saved['id']==legacy['id'] and saved['revision']==legacy['revision'] and 'minimum_minutes' not in saved
    assert saved['meals'][0]['id']=='desayuno' and saved['meals'][0]['start_time']=='08:00' and saved['meals'][0]['end_time']=='09:00'
    # A previous skipped check must not block a later arrival under the new rule.
    item=env.stock.snapshot['items'][0];day='2026-11-02'
    keys={person:'|'.join([item['id'],legacy['id'],'desayuno',person,day]) for person in legacy['persons']}
    env.stock.receipts['meal_events']={keys['person.one']:{'amount':1,'at':env.clock[0].timestamp()},keys['person.two']:{'amount':0,'at':env.clock[0].timestamp()}}
    migrated._active=True;migrated._started_at=env.manager._started_at;migrated._presence=deepcopy(env.manager._presence)
    env.clock[0]=env.clock[0].replace(hour=8,minute=30);await migrated.async_check()
    assert env.stock.snapshot['items'][0]['quantity']==19
    await migrated.async_stop()


async def test_older_open_editor_cannot_erase_a_custom_window(env):
    current=deepcopy(env.routine);current.pop('updated_at');current['meals'][0]['end_time']='10:30'
    saved=await env.manager.async_save(current)
    legacy={k:v for k,v in saved.items() if k!='updated_at'};legacy['minimum_minutes']=15
    legacy['meals']=[{'id':m['id'],'name':m['name'],'time':m['start_time'],'days':m['days'],'enabled':m['enabled']} for m in saved['meals']]
    legacy['name']='Nombre corregido'
    saved=await env.manager.async_save(legacy)
    assert saved['meals'][0]['end_time']=='10:30' and 'minimum_minutes' not in saved


@pytest.mark.parametrize('changes',[{'persons':[]},{'persons':['sensor.one']},{'minimum_minutes':-1},{'minimum_minutes':True},{'meals':[]},{'enabled':1}])
def test_invalid_routine(changes):
    with pytest.raises(CatalogError):normalize_routine(routine(**changes))


@pytest.mark.parametrize('start,end',[('08:00','08:00'),('25:00','09:00'),('08:00','09:60'),('8:00','09:00')])
def test_invalid_window(start,end):
    data=routine();data['meals'][0].update(start_time=start,end_time=end)
    with pytest.raises(CatalogError):normalize_routine(data)


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
