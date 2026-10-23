"""Alcampo opt-in discovery, exact EAN confirmation and durable paced refreshes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import json

import pytest

# Preserve coverage of dormant connectors for a possible future reactivation.
pytestmark = pytest.mark.usefixtures("archived_store_capabilities")

from custom_components.improved_shopping_list.alcampo import (
    AlcampoManager, DAY, REQUEST_INTERVAL, search_terms, search_candidates, valid_ean, linked_commercial_names)
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.price_manager import PriceManager
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.store_links import normalize_link
from custom_components.improved_shopping_list import alcampo as module


@pytest.fixture
async def env(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name":"Patatas","barcodes":["8410199023094"]})
    settings = SimpleNamespace(snapshot={"stores":{"alcampo":{"enabled":True}}, "price_updates_enabled":True})
    receipts = SimpleNamespace(stock=SimpleNamespace(receipts={"history":{"purchase":{
        "store":"carrefour","purchased_at":"2026-10-22T12:00:00","lines":[
            {"product_id":product["id"],"description":"LAY'S Gourmet Patatas fritas 170 g."}]}}}), offers_for=lambda p:[])
    prices = PriceManager(hass,catalog,settings,Mock())
    prices.receipts = receipts
    activity = SimpleNamespace(record=Mock())
    manager = AlcampoManager(hass,catalog,settings,prices,receipts,activity)
    await manager.async_load()
    prices.alcampo = manager
    clock = [1000000.0]
    monkeypatch.setattr(module,"time",SimpleNamespace(time=lambda:clock[0]))
    async def search(term, *, manual=False):
        await manager._before_request(manual=manual)
        return ["10739"]
    async def fetch(identifier):
        await manager._before_request()
        return {"store":"alcampo","reference_id":identifier,"url":normalize_link("alcampo",identifier)["url"],
            "ean":"8410199023094","price":"2.65","currency":"EUR","store_name":"LAY'S Gourmet"}
    manager._search = AsyncMock(side_effect=search)
    manager._fetch = AsyncMock(side_effect=fetch)
    yield SimpleNamespace(manager=manager,product=product,catalog=catalog,prices=prices,
        receipts=receipts,settings=settings,activity=activity,clock=clock)
    await manager.async_stop()


def test_terms_never_fall_back_to_generic_names_and_are_bounded():
    assert search_terms([], "Patatas") == []
    assert search_terms(["Patatas"], "Patatas") == []
    terms = search_terms(["LAY'S Gourmet 170 g.", "Otra marca comercial", "Tercera marca"], "Patatas")
    assert terms == ["LAY'S Gourmet 170 g.", "Otra marca comercial"]
    assert len(search_terms(["LAY'S Gourmet 170 g."], "Patatas")) == 2
    assert valid_ean("8410199023094") and not valid_ean("8410199023095")
    assert not valid_ean("https://example.test")


def test_search_results_only_use_first_three_actual_candidates():
    state = {"data":{"search":{"catalogue":{"data":{"productGroups":[
        {"products":["one","two","three","four"]}]}}},"products":{"productEntities":{
        key:{"retailerProductId":str(index)} for index,key in enumerate(["one","two","three","four","recommendation"],1)}}}}
    html = '<script>window.__INITIAL_STATE__='+json.dumps(state)+'</script>'
    assert search_candidates(html) == ["1","2","3"]
    with pytest.raises(PriceError):
        search_candidates('<script>alert("not a catalogue")</script>')


async def test_exact_match_is_paced_persisted_and_does_not_replace_manual_link(env,hass):
    manager=env.manager
    await manager.async_options({"search_enabled":True,"refresh_enabled":False,"days":30})
    manager._active=True
    await manager.async_tick()
    assert manager._search.await_count == 1 and manager._fetch.await_count == 0
    await manager.async_tick()
    assert manager._fetch.await_count == 0
    env.clock[0]+=REQUEST_INTERVAL
    await manager.async_tick()
    product=env.catalog.products[0]
    assert product["store_links"]["alcampo"]["id"] == "10739"
    assert env.prices.prices_for(product)[0]["price"] == "2.65"
    restored=AlcampoManager(hass,env.catalog,env.settings,env.prices,env.receipts,env.activity)
    await restored.async_load()
    assert restored.offer_for(product)["price"] == "2.65"
    assert restored._data["next_request"] == env.clock[0]+REQUEST_INTERVAL
    restored.sources.close()
    assert not await env.catalog.async_bind_alcampo(product["id"],"8410199023094",normalize_link("alcampo","999"))
    assert env.catalog.products[0]["store_links"]["alcampo"]["id"] == "10739"


async def test_search_budget_and_candidates_never_exceed_limits(env):
    manager=env.manager
    await manager.async_options({"search_enabled":True,"refresh_enabled":False,"days":30})
    async def search(term):
        await manager._before_request()
        return [str(100+manager._search.await_count*10+i) for i in range(9)]
    async def fetch(identifier):
        await manager._before_request()
        return {"ean":"3596710387427"}
    manager._search.side_effect=search
    manager._fetch.side_effect=fetch
    manager._active=True
    for _ in range(15):
        await manager.async_tick()
        env.clock[0]+=REQUEST_INTERVAL
    assert manager._search.await_count == 2
    assert manager._fetch.await_count == 6
    assert manager._data["attempts"]["8410199023094"]["done"]
    assert not env.catalog.products[0]["store_links"]


async def test_no_generic_search_and_new_ean_is_discovered_later(env):
    manager=env.manager
    env.receipts.stock.receipts["history"]={}
    await manager.async_options({"search_enabled":True,"refresh_enabled":False,"days":30})
    manager._active=True
    await manager.async_tick()
    manager._search.assert_not_awaited()
    env.receipts.stock.receipts["history"]={"new":{"store":"carrefour","purchased_at":"2026-10-22",
        "lines":[{"product_id":env.product["id"],"description":"LAY'S Gourmet 170 g."}]}}
    await manager.async_tick()
    manager._search.assert_awaited_once()


async def test_block_preserves_candidate_and_price_with_growing_pause(env):
    manager=env.manager
    await manager.async_options({"search_enabled":True,"refresh_enabled":False,"days":30})
    manager._active=True
    await manager.async_tick()
    env.clock[0]+=REQUEST_INTERVAL
    async def blocked(identifier):
        await manager._before_request()
        raise PriceError("Alcampo HTTP 429",http_status=429,retry_seconds=600)
    manager._fetch.side_effect=blocked
    await manager.async_tick()
    assert manager._data["attempts"]["8410199023094"]["candidates"] == ["10739"]
    retry=manager._data["retry_at"]
    assert retry == env.clock[0]+3600
    await manager.async_tick()
    assert manager._fetch.await_count == 1
    env.clock[0]=retry
    await manager.async_tick()
    assert manager._data["retry_at"] == env.clock[0]+7200
    assert env.activity.record.call_args.kwargs["diagnostics"]["http_status"] == 429


async def test_refreshes_are_distributed_and_only_run_when_opted_in(env):
    for number in range(3):
        await env.catalog.async_save_product({"name":"Manual "+str(number),
            "store_links":{"alcampo":normalize_link("alcampo",str(100+number))}})
    manager=env.manager
    manager._active=True
    await manager.async_tick()
    manager._fetch.assert_not_awaited()
    manager._active=False
    await manager.async_options({"search_enabled":False,"refresh_enabled":True,"days":30})
    manager._active=True
    await manager.async_tick()
    assert manager._fetch.await_count == 1
    future=[due for due in manager._data["due"].values() if due<env.clock[0]+30*DAY]
    assert sorted(future) == [env.clock[0]+10*DAY,env.clock[0]+20*DAY]
    env.clock[0]+=REQUEST_INTERVAL
    await manager.async_tick()
    assert manager._fetch.await_count == 1
    env.settings.snapshot["stores"]["alcampo"]["enabled"]=False
    env.clock[0]+=20*DAY
    await manager.async_tick()
    assert manager._fetch.await_count == 1


async def test_alcampo_search_transport_and_response_validation(env,aioclient_mock):
    manager=env.manager
    del manager._search
    manager._active=True
    html='<script>window.__INITIAL_STATE__='+json.dumps({"data":{"search":{"catalogue":{"data":{"productGroups":[]}}},"products":{"productEntities":{}}}})+'</script>'
    aioclient_mock.get("https://www.compraonline.alcampo.es/search?q=Test",text=html)
    assert await manager._search("Test") == []
    assert aioclient_mock.call_count == 1
    assert manager._data["next_request"] == env.clock[0]+300


def test_linked_commercial_names_use_only_official_product_slugs():
    product={"store_links":{"carrefour":normalize_link("carrefour",
        "https://www.carrefour.es/supermercado/anacardo-crudo-original-carrefour-200-g/R-VC4AECOMM-491998/p"),
        "alcampo":normalize_link("alcampo","10739"),"consum":normalize_link("consum","123")}}
    assert linked_commercial_names(product) == ["anacardo crudo original carrefour 200 g"]
    assert linked_commercial_names({"store_links":{"carrefour":normalize_link("carrefour","R-prod123")}}) == []


async def test_new_match_does_not_immediately_fetch_the_same_price_again(env):
    manager=env.manager
    await manager.async_options({"search_enabled":True,"refresh_enabled":True,"days":30})
    manager._active=True
    await manager.async_tick()
    env.clock[0]+=REQUEST_INTERVAL
    await manager.async_tick()
    assert manager._fetch.await_count == 1
    env.clock[0]+=REQUEST_INTERVAL
    await manager.async_tick()
    assert manager._fetch.await_count == 1


async def test_manual_search_returns_candidates_logs_and_preserves_links_and_cooldown(env,hass):
    manager=env.manager;manager._active=True
    env.settings.snapshot['price_updates_enabled']=False  # Explicit diagnostics do not enable automatic updates.
    result=await manager.async_test_search(env.product['id'])
    assert result['status']=='candidates' and result['http_status']==200 and result['http_requests']==1
    assert result['term']=="LAY'S Gourmet Patatas fritas 170 g."
    assert result['eans']==['8410199023094'] and result['candidates'][0]['reference_id']=='10739'
    assert env.catalog.products[0]['store_links']=={} and manager._data['attempts']=={}
    assert manager._fetch.await_count==0
    assert env.activity.record.call_args.args[0]=='stores.search_test'
    paused=await manager.async_test_search(env.product['id'])
    assert paused['status']=='paused' and paused['http_requests']==0 and manager._search.await_count==1
    restored=AlcampoManager(hass,env.catalog,env.settings,env.prices,env.receipts,env.activity);await restored.async_load()
    assert restored._data['next_request']==env.clock[0]+REQUEST_INTERVAL
    restored.sources.close()


async def test_manual_search_requires_commercial_name_and_valid_ean(env):
    env.manager._active=True
    env.receipts.stock.receipts['history']={}
    result=await env.manager.async_test_search(env.product['id'])
    assert result['status']=='skipped' and 'nombre comercial' in result['message']
    product=await env.catalog.async_save_product({'name':'Sin código'})
    result=await env.manager.async_test_search(product['id'])
    assert result['status']=='skipped' and 'EAN válido' in result['message']
    env.manager._search.assert_not_awaited()


async def test_manual_search_http_failure_keeps_shared_backoff(env):
    manager=env.manager;manager._active=True
    async def fail(term, *, manual=False):
        await manager._before_request(manual=manual)
        raise PriceError('Alcampo: búsqueda rechazada (HTTP 403).',http_status=403)
    manager._search.side_effect=fail
    result=await manager.async_test_search(env.product['id'])
    assert result['status']=='error' and result['diagnostics']['http_status']==403
    assert result['next_request']==env.clock[0]+3600
    assert (await manager.async_test_search(env.product['id']))['http_requests']==0


async def test_manual_search_websocket_requires_admin(hass,hass_ws_client,hass_read_only_user,monkeypatch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    manager=hass.data[DOMAIN]['alcampo']
    operation=AsyncMock(return_value={'status':'not_found','candidates':[]})
    monkeypatch.setattr(manager,'async_test_search',operation)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id='http://test.local')
    readonly=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await readonly.send_json({'id':1,'type':f'{DOMAIN}/alcampo/test_search','product_id':'test'})
    assert (await readonly.receive_json())['error']['code']=='unauthorized'
    operation.assert_not_awaited()
    admin=await hass_ws_client(hass)
    await admin.send_json({'id':1,'type':f'{DOMAIN}/alcampo/test_search','product_id':'test'})
    assert (await admin.receive_json())['result']=={'status':'not_found','candidates':[]}
    operation.assert_awaited_once_with('test')
