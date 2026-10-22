"""Daily purchase detection: genuine transitions, restart safety and receipt reconciliation."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.improved_shopping_list.purchase_detection import PurchaseDetection
from custom_components.improved_shopping_list import purchase_detection as module
from custom_components.improved_shopping_list.receipts import ReceiptManager
from custom_components.improved_shopping_list.catalog import CatalogError


class Ledger:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._items = {}
        self.receipts = {"history":{},"aliases":{},"purchases":{},"coverage":{}}
        self.catalog = SimpleNamespace(products=[{"id":"cacao","name":"Cacao"},{"id":"milk","name":"Leche"}])
        self.activity = SimpleNamespace(record=Mock())
        self.listeners = set()

    def subscribe(self, listener):
        self.listeners.add(listener)
        return lambda:self.listeners.discard(listener)

    async def _persist(self, items, *, receipts):
        self.receipts = receipts
        for listener in tuple(self.listeners):
            listener()


@pytest.fixture
async def env(hass, monkeypatch):
    clock = [dt_util.now().replace(hour=12,minute=0,second=0,microsecond=0)]
    monkeypatch.setattr(module,"dt_util",SimpleNamespace(now=lambda:clock[0]))
    stock = Ledger()
    settings = SimpleNamespace(snapshot={"entities":["todo.one","todo.two"],"purchase_detection":{"enabled":True,"threshold":2}},subscribe=lambda listener:lambda:None)
    receipts = ReceiptManager(hass,stock,None,None)
    activity = stock.activity
    carrefour = SimpleNamespace(note_completion=Mock())
    manager = PurchaseDetection(hass,settings,receipts,activity,carrefour)
    await manager.async_load();manager.start()
    result=SimpleNamespace(manager=manager,stock=stock,receipts=receipts,settings=settings,carrefour=carrefour,clock=clock)
    yield result
    await result.manager.async_stop()


def complete(env, uid, entity="todo.one", name="Cacao"):
    env.manager.note_completion(entity,{"uid":uid,"summary":name},{"quantity":250,"unit":"g"})


async def test_strict_threshold_combines_lists_counts_each_uid_once_and_stays_one_per_day(env):
    complete(env,"a");complete(env,"b",entity="todo.two")
    await env.manager.async_check()
    assert not env.stock.receipts["history"]
    complete(env,"a")  # Undo/redo does not count a second time.
    await env.manager.async_check();assert not env.stock.receipts["history"]
    complete(env,"c")
    await env.manager.async_check()
    receipt=next(iter(env.stock.receipts["history"].values()))
    assert receipt["article_count"]==3 and receipt["total"] is None and receipt["needs_details"]
    assert receipt["store"]=="unknown" and env.carrefour.note_completion.call_count==1
    complete(env,"d")
    await env.manager.async_check()
    assert len(env.stock.receipts["history"])==1
    assert next(iter(env.stock.receipts["history"].values()))["article_count"]==4
    assert env.carrefour.note_completion.call_count==1


async def test_restart_keeps_counter_and_does_not_recreate_discarded_detection(env,hass):
    complete(env,"a");complete(env,"b");await env.manager.async_check()
    await env.manager.async_stop()
    restored=PurchaseDetection(hass,env.settings,env.receipts,env.stock.activity,env.carrefour)
    await restored.async_load();restored.start();env.manager=restored
    complete(env,"a");await restored.async_check();assert not env.stock.receipts["history"]
    complete(env,"c");await restored.async_check()
    identifier=next(iter(env.stock.receipts["history"]))
    await env.receipts.async_discard_detected_purchase(identifier)
    complete(env,"d");await restored.async_check()
    assert not env.stock.receipts["history"]


async def test_new_local_day_has_new_threshold_and_disabled_or_gateway_entries_do_not_count(env):
    complete(env,"a",entity="todo.gateway")
    env.settings.snapshot["purchase_detection"]["enabled"]=False
    complete(env,"b");await env.manager.async_check();assert not env.manager._days
    env.settings.snapshot["purchase_detection"]["enabled"]=True
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    env.clock[0]+=timedelta(days=1)
    for uid in "ab":complete(env,uid)
    await env.manager.async_check();assert len(env.stock.receipts["history"])==1
    complete(env,"c");await env.manager.async_check()
    assert len(env.stock.receipts["history"])==2


async def test_manual_details_add_no_stock_or_prices_and_are_preserved_when_count_grows(env):
    for uid in "abc":complete(env,uid)
    await env.manager.async_check();identifier=next(iter(env.stock.receipts["history"]))
    await env.receipts.async_complete_detected_purchase(identifier,"carrefour",42.55)
    complete(env,"d");await env.manager.async_check()
    receipt=env.stock.receipts["history"][identifier]
    assert receipt["store"]=="carrefour" and receipt["total"]==42.55 and not receipt["needs_details"]
    assert env.stock._items=={} and env.stock.receipts["purchases"]=={} and receipt["lines"]==[]
    for store,total,name in [("invalid",1,""),("other",1,""),("carrefour",float("nan"),""),("carrefour",True,""),("carrefour",1.234,"")]:
        with pytest.raises(CatalogError):
            await env.receipts.async_complete_detected_purchase(identifier,store,total,name)
    receipt=await env.receipts.async_complete_detected_purchase(identifier,"other",10,"Mi tienda")
    assert receipt["store_name"]=="Mi tienda" and receipt["store"].startswith("other:")


def ticket(env, identifier="ticket", **changes):
    return {"id":identifier,"digest":identifier,"store":"carrefour","store_name":"Carrefour","total":20,
        "purchased_at":env.clock[0].isoformat(),"summary_only":True,"pending_review":True,
        "lines":[{"product_id":"cacao","matched":True}],**changes}


async def test_receipt_requires_same_day_and_confirmed_overlap_and_merges_only_once(env):
    for uid in "abc":complete(env,uid)
    await env.manager.async_check();identifier=next(iter(env.stock.receipts["history"]))
    env.stock.receipts["history"]["unrelated"]=ticket(env,"unrelated",lines=[{"product_id":"milk","matched":True}])
    env.stock.receipts["history"]["old"]=ticket(env,"old",purchased_at=(env.clock[0]-timedelta(days=1)).isoformat())
    env.stock.receipts["history"]["proposed"]=ticket(env,"proposed",lines=[{"product_id":"cacao","matched":False}])
    await env.manager.async_check();assert identifier in env.stock.receipts["history"]
    env.stock.receipts["history"]["matching"]=ticket(env,"matching")
    await env.manager.async_check()
    assert identifier not in env.stock.receipts["history"]
    assert env.stock.receipts["history"]["matching"]["detection_id"]==identifier
    complete(env,"d");await env.manager.async_check()
    assert identifier not in env.stock.receipts["history"]


async def test_ambiguous_receipts_or_conflicting_manual_details_stay_unidentified(env):
    for uid in "abc":complete(env,uid)
    await env.manager.async_check();identifier=next(iter(env.stock.receipts["history"]))
    env.stock.receipts["history"].update(first=ticket(env,"first"),second=ticket(env,"second"))
    await env.manager.async_check();assert identifier in env.stock.receipts["history"]
    env.stock.receipts["history"].pop("second")
    await env.receipts.async_complete_detected_purchase(identifier,"alcampo",20)
    await env.manager.async_check();assert identifier in env.stock.receipts["history"]
