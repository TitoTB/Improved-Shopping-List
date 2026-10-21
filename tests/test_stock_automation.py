"""Pantry expiry, observed uses, actual purchases and safe native-list replenishment."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus, serialize_todo_item
from homeassistant.core import SupportsResponse

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.stock import StockManager, DEFAULT_CONFIG, DAY
from custom_components.improved_shopping_list.stock_automation import StockAutomation
from custom_components.improved_shopping_list import stock as stock_module, stock_automation as module


class Todo:
    def __init__(self):
        self.todo_items = []
        self.listeners = []

    def async_subscribe_updates(self, listener):
        self.listeners.append(listener)
        return lambda:self.listeners.remove(listener)

    def publish(self):
        for listener in tuple(self.listeners):
            listener(self.todo_items)


def config(item, **overrides):
    fields = ("quantity","unit","mode","days","refill_quantity","reorder_enabled","reorder_at",
        "list_entity","usage_entity","usage_state","usage_amount")
    return {**{field:item.get(field,DEFAULT_CONFIG.get(field)) for field in fields},**overrides}


@pytest.fixture
async def env(hass, monkeypatch):
    clock = [1800000000.0]
    monkeypatch.setattr(stock_module,"time",SimpleNamespace(time=lambda:clock[0]))
    monkeypatch.setattr(module,"time",SimpleNamespace(time=lambda:clock[0]))
    catalog = Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({"name":"Cacao"})
    stock = StockManager(hass,catalog);await stock.async_load()
    item = await stock.async_add("Cacao")
    activity = SimpleNamespace(record=Mock());stock.activity=activity
    settings = SimpleNamespace(snapshot={"entities":["todo.main"],"primary_entity":"todo.main"})
    todo = Todo()
    component = SimpleNamespace(get_entity=lambda entity:todo if entity=="todo.main" else None)
    hass.data[DATA_COMPONENT] = component
    hass.states.async_set("todo.main","0",{"supported_features":5})
    manager = StockAutomation(hass,stock,settings,activity,asyncio.Lock());manager._active=True
    monkeypatch.setattr(manager,"_queue",Mock())
    calls = []
    async def get_items(call):
        return {"todo.main":{"items":[serialize_todo_item(item) for item in todo.todo_items]}}
    async def add_item(call):
        calls.append(("add",dict(call.data)))
        todo.todo_items.append(TodoItem(summary=call.data["item"],uid=f"p{len(calls)}",status=TodoItemStatus.NEEDS_ACTION));todo.publish()
    async def update_item(call):
        calls.append(("update",dict(call.data)))
        target = next(item for item in todo.todo_items if item.uid==call.data["item"])
        target.status=TodoItemStatus(call.data["status"]);todo.publish()
    hass.services.async_register("todo","get_items",get_items,supports_response=SupportsResponse.ONLY)
    hass.services.async_register("todo","add_item",add_item)
    hass.services.async_register("todo","update_item",update_item)
    state = SimpleNamespace(stock=stock,item=item,manager=manager,settings=settings,todo=todo,clock=clock,calls=calls,activity=activity)
    manager._sync_lists()
    yield state
    await manager.async_stop()


async def test_perishable_expires_reorders_and_purchase_refills_once(env):
    item = await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,
        mode="perishable",days=2,refill_quantity=4,list_entity="todo.main",quantity=3))
    await env.manager.async_check()
    assert env.calls==[] and item["expires_at"]==env.clock[0]+2*DAY
    env.clock[0]+=2*DAY
    await env.manager.async_check()
    expired = env.stock.snapshot["items"][0]
    assert expired["quantity"]==0 and expired["expired"] is True
    assert len(env.todo.todo_items)==1 and len(env.calls)==1
    await env.manager.async_check();assert len(env.calls)==1
    env.todo.todo_items[0].status=TodoItemStatus.COMPLETED;env.todo.publish()
    await env.manager.async_check()
    bought = env.stock.snapshot["items"][0]
    assert bought["quantity"]==4 and not bought["expired"]
    assert bought["expires_at"]==env.clock[0]+2*DAY
    env.todo.publish();await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==4
    restored = StockManager(env.stock.hass,env.stock.catalog);await restored.async_load()
    assert restored.snapshot==env.stock.snapshot
    env.clock[0]+=2*DAY
    await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==0
    assert len(env.todo.todo_items)==1 and env.calls[-1][0]=="update"


async def test_usage_counts_state_entries_not_attributes_startup_or_reconnect(env):
    await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,quantity=2,
        mode="usage",unit="kg",usage_entity="sensor.washer",usage_state="running",usage_amount=0.25,
        reorder_enabled=True,reorder_at=1.5,list_entity="todo.main"))
    def event(old, new, entity="sensor.washer"):
        env.manager._state_changed(SimpleNamespace(data={"entity_id":entity,
            "old_state":SimpleNamespace(state=old) if old is not None else None,
            "new_state":SimpleNamespace(state=new)}))
    for old,new in [(None,"running"),("unknown","running"),("unavailable","running"),("running","running")]:
        event(old,new)
    event("off","running","sensor.other")
    await env.manager.async_check();assert env.stock.snapshot["items"][0]["quantity"]==2
    event("idle","running");await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==1.75 and env.calls==[]
    event("idle","running");await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==1.5 and len(env.calls)==1
    for _ in range(10):event("idle","running")
    await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==0 and len(env.calls)==1


async def test_existing_completed_items_and_new_subscription_do_not_fabricate_purchases(env):
    await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,refill_quantity=3))
    env.todo.todo_items=[TodoItem(summary="Cacao",uid="one",status=TodoItemStatus.COMPLETED)]
    env.manager._snapshots.clear();env.todo.publish()
    await env.manager.async_check();assert env.stock.snapshot["items"][0]["quantity"]==1
    env.todo.todo_items[0].status=TodoItemStatus.NEEDS_ACTION;env.todo.publish()
    env.todo.todo_items[0].status=TodoItemStatus.COMPLETED;env.todo.publish()
    await env.manager.async_check();assert env.stock.snapshot["items"][0]["quantity"]==4
    env.manager._snapshots.clear();env.todo.publish()
    await env.manager.async_check();assert env.stock.snapshot["items"][0]["quantity"]==4


async def test_consumption_retry_and_reconfiguration_do_not_lose_or_repeat_changes(env,monkeypatch):
    item=await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,
        mode="usage",usage_entity="sensor.use",usage_state="on",quantity=4))
    env.manager._events.append((item["id"],item["config_revision"],"usage"))
    save=env.stock._store.async_save
    monkeypatch.setattr(env.stock._store,"async_save",AsyncMock(side_effect=OSError("disk")))
    await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==4 and len(env.manager._events)==1
    monkeypatch.setattr(env.stock._store,"async_save",save)
    env.clock[0]+=301;await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==3 and not env.manager._events
    env.manager._events.append((item["id"],item["config_revision"],"usage"))
    latest=env.stock.snapshot["items"][0]
    await env.stock.async_save(latest["id"],latest["revision"],config(latest,mode="manual"))
    await env.manager.async_check();assert env.stock.snapshot["items"][0]["quantity"]==3


async def test_native_list_matching_permissions_and_unconfigured_items(env,hass):
    await env.manager.async_check();assert env.calls==[]
    item=await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,
        reorder_enabled=True,reorder_at=1,list_entity="todo.main"))
    env.todo.todo_items=[TodoItem(summary=" CACAO ",uid="existing",status=TodoItemStatus.NEEDS_ACTION)];env.todo.publish()
    await env.manager.async_check();assert env.calls==[]
    env.todo.todo_items=[];env.todo.publish()
    hass.states.async_set("todo.main","0",{"supported_features":0})
    await env.manager.async_check();assert env.calls==[]
    assert any(call.args[0]=="stock.error" for call in env.activity.record.call_args_list)
    env.clock[0]+=301;hass.states.async_set("todo.main","0",{"supported_features":5})
    await env.manager.async_check();assert len(env.calls)==1


async def test_quantity_unit_validation_and_reader_updates_keep_configuration(env):
    item=await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,quantity=0.75,unit="Latas",refill_quantity=2.5))
    changed=await env.stock.async_adjust(item["id"],1)
    assert changed["quantity"]==1.75 and changed["unit"]=="Latas" and changed["refill_quantity"]==2.5
    for bad in [True,-1,float("nan"),float("inf"),0.1234]:
        with pytest.raises(CatalogError):
            await env.stock.async_save(changed["id"],changed["revision"],config(changed,quantity=bad))
    with pytest.raises(CatalogError,match="cambiado"):
        await env.stock.async_save(item["id"],item["revision"],config(item))
    with pytest.raises(CatalogError):
        await env.stock.async_save(changed["id"],changed["revision"],config(changed,unit="x"*33))


async def test_purchase_arriving_during_list_read_does_not_restore_it_as_pending(env,hass,monkeypatch):
    await env.stock.async_save(env.item["id"],env.item["revision"],config(env.item,
        quantity=0,reorder_enabled=True,reorder_at=0,refill_quantity=4,list_entity="todo.main"))
    env.todo.todo_items=[TodoItem(summary="Cacao",uid="one",status=TodoItemStatus.NEEDS_ACTION)]
    env.todo.publish()
    async def get_items(*args,**kwargs):
        env.todo.todo_items[0].status=TodoItemStatus.COMPLETED;env.todo.publish()
        return {"todo.main":{"items":[serialize_todo_item(item) for item in env.todo.todo_items]}}
    monkeypatch.setattr(hass.services,"async_call",AsyncMock(side_effect=get_items))
    await env.manager.async_check()
    assert env.calls==[] and env.todo.todo_items[0].status==TodoItemStatus.COMPLETED
    await env.manager.async_check()
    assert env.stock.snapshot["items"][0]["quantity"]==4 and env.calls==[]
