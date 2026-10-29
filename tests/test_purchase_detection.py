"""Daily purchase detection: genuine transitions, restart safety and receipt reconciliation."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

# Preserve coverage of dormant connectors for a possible future reactivation.
pytestmark = pytest.mark.usefixtures("archived_store_capabilities")
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


async def test_receipt_needs_no_product_overlap_and_keeps_actual_ticket_contents(env):
    for uid in "abc":complete(env,uid)
    await env.manager.async_check();identifier=next(iter(env.stock.receipts["history"]))
    env.stock.receipts["history"]["old"]=ticket(env,"old",purchased_at=(env.clock[0]-timedelta(days=1)).isoformat())
    env.stock.receipts["history"]["summary"]=ticket(env,"summary",pending_review=False,lines=[])
    await env.manager.async_check();assert identifier in env.stock.receipts["history"]
    actual=[{"description":"Producto adicional sin catálogo","count":2,"amount":20}]
    env.stock.receipts["history"]["actual"]=ticket(env,"actual",lines=actual,article_count=2)
    await env.manager.async_check()
    assert identifier not in env.stock.receipts["history"]
    saved=env.stock.receipts["history"]["actual"]
    assert saved["detection_id"]==identifier and saved["lines"]==actual and saved["article_count"]==2
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


async def test_user_confirmed_store_and_amount_reconcile_one_existing_summary_without_duplicate_expense(env):
    for uid in "abc":complete(env,uid)
    await env.manager.async_check();identifier=next(iter(env.stock.receipts["history"]))
    summary=ticket(env,"summary",lines=[])
    env.stock.receipts["history"]["summary"]=summary
    result=await env.receipts.async_complete_detected_purchase(identifier,"carrefour",20)
    assert result["id"]=="summary" and result["detection_id"]==identifier
    assert len(env.stock.receipts["history"])==1
    complete(env,"d");await env.manager.async_check()
    assert len(env.stock.receipts["history"])==1



def zone_setup(env, hass):
    env.settings.snapshot["purchase_detection"].update(zone_assignment=True,persons=["person.ana"],
        store_zones={"carrefour":["zone.carrefour","zone.carrefour_2"],"alcampo":["zone.alcampo"]})
    env.settings.snapshot["stores"]={"carrefour":{"enabled":True},"alcampo":{"enabled":True}}
    for zone in ("carrefour","carrefour_2","alcampo"):
        hass.states.async_set("zone."+zone,"0",{"friendly_name":zone.title()})


def visit(env, hass, person, zone):
    from homeassistant.core import State
    env.manager._presence_changed(SimpleNamespace(data={"entity_id":person,"new_state":State(person,zone)}))


async def test_zone_visits_precede_purchase_survive_restart_and_remain_provisional(env,hass):
    zone_setup(env,hass)
    visit(env,hass,"person.ana","Carrefour")
    await env.manager.async_check()
    await env.manager.async_stop()
    restored=PurchaseDetection(hass,env.settings,env.receipts,env.stock.activity,env.carrefour)
    await restored.async_load();restored.start();env.manager=restored
    for uid in "abc":complete(env,uid)
    await restored.async_check()
    receipt=next(iter(env.stock.receipts["history"].values()))
    assert receipt["store"]=="carrefour" and receipt["provisional_store"] and receipt["needs_details"]
    assert receipt["total"] is None and receipt["zone_candidates"]==["carrefour"]
    stored=await restored._store.async_load()
    assert stored["days"][env.clock[0].date().isoformat()]["visits"]=={"zone.carrefour":["person.ana"]}
    assert "latitude" not in str(stored) and env.stock._items=={}


async def test_multiple_store_visits_offer_choices_but_not_unselected_people_or_disabled_stores(env,hass):
    zone_setup(env,hass)
    visit(env,hass,"person.other","Alcampo")
    visit(env,hass,"person.ana","Carrefour")
    visit(env,hass,"person.ana","Carrefour_2")
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    receipt=next(iter(env.stock.receipts["history"].values()))
    assert receipt["zone_candidates"]==["carrefour"]
    visit(env,hass,"person.ana","Alcampo")
    await env.manager.async_check()
    receipt=env.stock.receipts["history"][receipt["id"]]
    assert receipt["store"]=="unknown" and not receipt["provisional_store"]
    assert receipt["zone_candidates"]==["alcampo","carrefour"]
    env.settings.snapshot["stores"]["alcampo"]["enabled"]=False
    await env.manager.async_check()
    assert env.stock.receipts["history"][receipt["id"]]["store"]=="carrefour"


async def test_confirmed_store_is_not_overwritten_and_ticket_can_override_provisional_zone(env,hass):
    zone_setup(env,hass)
    visit(env,hass,"person.ana","Alcampo")
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    receipt=next(iter(env.stock.receipts["history"].values()))
    assert receipt["store"]=="alcampo"
    env.stock.receipts["history"]["matching"]=ticket(env,"matching")
    await env.manager.async_check()
    assert receipt["id"] not in env.stock.receipts["history"]
    assert env.stock.receipts["history"]["matching"]["detection_id"]==receipt["id"]
    env.clock[0]+=timedelta(days=1)
    visit(env,hass,"person.ana","Carrefour")
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    identifier="detected:"+env.clock[0].date().isoformat()
    await env.receipts.async_complete_detected_purchase(identifier,"alcampo",20)
    visit(env,hass,"person.ana","Alcampo")
    await env.manager.async_check()
    assert env.stock.receipts["history"][identifier]["store"]=="alcampo"
    assert not env.stock.receipts["history"][identifier]["provisional_store"]


async def test_zone_day_boundary_disabled_mode_and_geo_precedence(env,hass):
    from homeassistant.core import State
    zone_setup(env,hass)
    zone=State("zone.carrefour","0",{"latitude":40,"longitude":-3,"radius":100,"friendly_name":"Carrefour"})
    assert env.manager._inside_zone(State("person.ana","not_home",{"latitude":40,"longitude":-3}),zone)
    assert not env.manager._inside_zone(State("person.ana","Carrefour",{"latitude":41,"longitude":-3}),zone)
    assert not env.manager._inside_zone(State("person.ana","Carrefour",{"latitude":float("nan"),"longitude":-3}),zone)
    visit(env,hass,"person.ana","Carrefour");await env.manager.async_check()
    env.clock[0]+=timedelta(days=1)
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    receipt=next(iter(env.stock.receipts["history"].values()))
    assert receipt["store"]=="unknown" and not receipt["zone_candidates"]
    visit(env,hass,"person.ana","Carrefour");await env.manager.async_check()
    env.settings.snapshot["purchase_detection"]["zone_assignment"]=False
    await env.manager.async_check()
    assert env.stock.receipts["history"][receipt["id"]]["store"]=="unknown"


async def test_ticket_sources_prioritize_visited_store_stop_after_match_and_continue_after_failure(env,hass):
    zone_setup(env,hass)
    visit(env,hass,"person.ana","Carrefour")
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    calls=[]
    async def matching():
        calls.append("carrefour")
        env.stock.receipts["history"]["matched"]=ticket(env,"matched")
    async def other():calls.append("alcampo")
    await env.manager.async_search_ticket_sources({"alcampo":other,"carrefour":matching})
    assert calls==["carrefour"] and env.manager._today_identified()
    await env.manager.async_search_ticket_sources({"alcampo":other,"carrefour":matching})
    assert calls==["carrefour"]
    env.stock.receipts["history"]["matched"].pop("detection_id")
    async def broken():
        calls.append("failed")
        raise CatalogError("No disponible")
    await env.manager.async_search_ticket_sources({"alcampo":other,"carrefour":broken})
    # Reconciliation needs a pending detection; the previous match must not be recreated.
    assert calls==["carrefour","failed","alcampo"]


async def test_ticket_order_favorite_fallback_without_unavailable_sources(env,hass):
    env.settings.snapshot["favorite_store"]="carrefour"
    assert env.manager.ticket_search_order(["dia","alcampo","carrefour"])==["carrefour","alcampo","dia"]
    assert env.manager.ticket_search_order(["dia","alcampo"])==["alcampo","dia"]
    zone_setup(env,hass)
    visit(env,hass,"person.ana","Alcampo")
    await env.manager.async_check()
    assert env.manager.ticket_search_order(["dia","alcampo","carrefour"])==["alcampo","carrefour","dia"]
    visit(env,hass,"person.ana","Carrefour")
    await env.manager.async_check()
    assert env.manager.ticket_search_order(["dia","alcampo","carrefour"])==["carrefour","alcampo","dia"]
    env.settings.snapshot["purchase_detection"]["zone_assignment"]=False
    assert env.manager.ticket_search_order(["dia","alcampo","carrefour"])==["carrefour","alcampo","dia"]


@pytest.mark.parametrize("visited",[False,True])
async def test_ticket_search_tries_favorite_after_unsuccessful_zone_then_stops(env,hass,visited):
    env.settings.snapshot["favorite_store"]="carrefour"
    if visited:
        zone_setup(env,hass)
        visit(env,hass,"person.ana","Alcampo")
    for uid in "abc":complete(env,uid)
    await env.manager.async_check()
    calls=[]
    async def no_match():calls.append("alcampo")
    async def favorite_match():
        calls.append("carrefour")
        env.stock.receipts["history"]["favorite-ticket"]=ticket(env,"favorite-ticket")
    async def unused():calls.append("dia")
    await env.manager.async_search_ticket_sources({"dia":unused,"alcampo":no_match,"carrefour":favorite_match})
    assert calls==(["alcampo","carrefour"] if visited else ["carrefour"])
    assert env.manager._today_identified()
