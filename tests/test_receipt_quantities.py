"""Weights belong to purchases; reusable unit rates belong to shop options."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.stock import StockManager
from custom_components.improved_shopping_list.receipts import ReceiptManager, converted_quantity
from custom_components.improved_shopping_list.receipt_quantities import measure_price, estimated_quantity
from custom_components.improved_shopping_list.product_references import reference_from_line
from custom_components.improved_shopping_list.receipt_parser import parse_carrefour
from custom_components.improved_shopping_list.option_lookup import OptionLookup, page_product
from custom_components.improved_shopping_list.price_sources import PriceError

URL="https://www.carrefour.es/supermercado/zanahorias/R-prod1/p"


def rate(price=5):
    return {"price":price,"quantity":1,"unit":"kg","currency":"EUR","checked_at":time.time(),"source":"web"}


def test_rates_convert_measures_and_estimates_use_gross_before_line_discount():
    assert measure_price({**rate(),"price":.5,"quantity":100,"unit":"g"})["price"]==5
    result=estimated_quantity({"amount":1.5,"gross_amount":2.5,"count":2},rate())
    assert result["quantity"]==.5 and result["unit"]=="kg"
    assert converted_quantity({"purchased_quantity":.5,"purchased_unit":"kg","pack_quantity":None,"pack_unit":"","count":2},"g")==500
    for change in ({"price":0},{"price":float("nan")},{"unit":"invalid"}):
        with pytest.raises(ValueError):measure_price({**rate(),**change})


def test_explicit_weight_ticket_is_not_a_fixed_package():
    date=dt_util.now().strftime('%d/%m/%Y %H:%M:%S')
    parsed=parse_carrefour(f'CARREFOUR\nZANAHORIAS\n0,500 kg x ( 5,00 ) 2,50\nSUBTOTAL 2,50\n1 ART. TOTAL A PAGAR : 2,50\n{date}')
    line=parsed["lines"][0]
    assert line["purchased_quantity"]==.5 and line["purchased_unit"]=="kg" and not line["quantity_estimated"]
    assert line["pack_quantity"] is None and line["count"]==1 and line["unit_price"]==2.5


async def environment(hass, *, saved_rate=True, explicit=False, weight_unit_only=False):
    catalog=Catalog(hass);await catalog.async_load()
    ref=reference_from_line("carrefour",{"name":"ZANAHORIAS","reference_id":"R-prod1","url":URL})
    if saved_rate:ref["measure_price"]=rate()
    if weight_unit_only:ref.update(content_unit="g",last_price={"price":5,"currency":"EUR","checked_at":time.time()-3600})
    product=await catalog.async_save_product({"name":"Zanahorias","commercial_references":[ref]})
    stock=StockManager(hass,catalog);await stock.async_load();item=await stock.async_add(product["name"])
    fields=('quantity','unit','mode','days','refill_quantity','reorder_enabled','reorder_at','list_entity','usage_entity','usage_state','usage_amount')
    config={key:item[key] for key in fields};config.update(quantity=0,unit='g',refill_quantity=1000)
    await stock.async_save(item['id'],item['revision'],config)
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={'primary_entity':'todo.main'}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    manager.option_lookup=SimpleNamespace(retrieve=AsyncMock(return_value={"measure_price":rate()}))
    receipt={"id":"weight-ticket","digest":"weight-ticket","store":"carrefour","store_name":"Carrefour","currency":"EUR",
        "purchased_at":(dt_util.now()-timedelta(hours=1)).isoformat(),"total":2.5,"subtotal":2.5,"discount":0,"article_count":1,
        "lines":[{"id":"0","description":"ZANAHORIAS","count":1,"unit_price":2.5,"amount":2.5,"pack_quantity":None,"pack_unit":""}]}
    if explicit:receipt["lines"][0].update(purchased_quantity=.45,purchased_unit="kg",quantity_estimated=False)
    draft=await manager._prepare_preview(receipt,"owner")
    await manager.async_link(draft["token"],"owner",[{"id":"0","product_id":product["id"]}])
    return manager,catalog,stock,product,draft


@pytest.mark.parametrize("saved_rate",[True,False])
async def test_cached_or_web_rate_estimates_without_replacing_pack_or_stock(hass,saved_rate):
    manager,catalog,stock,product,draft=await environment(hass,saved_rate=saved_rate)
    before=deepcopy(stock._items)
    result=await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert result["quantity"]==.5 and result["estimated"]
    assert stock._items==before
    assert manager.option_lookup.retrieve.await_count==(0 if saved_rate else 1)
    ref=next(ref for ref in catalog.products[0]["commercial_references"] if ref["url"]==URL)
    assert ref["measure_price"]["price"]==5 and ref["content_quantity"] is None
    await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert manager.option_lookup.retrieve.await_count==(0 if saved_rate else 1)
    saved=await manager.async_confirm(draft["token"],"owner",[{"id":"0","product_id":product["id"],"replenish":True,"quantity":500,"unit":"g","purchase_id":""}],False)
    assert saved["lines"][0]["purchased_quantity"]==.5 and saved["lines"][0]["quantity_estimated"]
    assert stock.snapshot["items"][0]["quantity"]==500
    ref=next(ref for ref in catalog.products[0]["commercial_references"] if ref["url"]==URL)
    assert ref["measure_price"]["price"]==5 and ref["content_quantity"] is None


async def test_explicit_ticket_weight_wins_and_owner_must_match(hass):
    manager,catalog,stock,product,draft=await environment(hass,explicit=True)
    with pytest.raises(CatalogError):await manager.async_estimate_quantity(draft["token"],"another-user","0",product["id"])
    result=await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert result=={"quantity":.45,"unit":"kg","estimated":False}
    assert manager.option_lookup.retrieve.await_count==0


async def test_estimate_restored_after_close_and_manager_restart_without_lookup(hass):
    manager,catalog,stock,product,draft=await environment(hass,saved_rate=False)
    raw=deepcopy(draft['receipt']);before=deepcopy(stock._items)
    await manager.async_estimate_quantity(draft['token'],'owner','0',product['id'])
    manager.discard(draft['token'],'owner')
    restored=ReceiptManager(hass,stock,manager.automation,manager.prices)
    restored.option_lookup=SimpleNamespace(retrieve=AsyncMock(side_effect=AssertionError('Must use saved quantity')))
    review=await restored._prepare_preview(raw,'owner')
    options=await restored.async_link(review['token'],'owner',[{'id':'0','product_id':product['id']}])
    assert options['quantity_estimates']['0']['quantity']==.5
    assert options['quantity_estimates']['0']['product_id']==product['id']
    restored.option_lookup.retrieve.assert_not_awaited()
    assert stock._items==before and not stock.receipts['history']
    restored.discard(review['token'],'owner')
    changed=deepcopy(raw);changed['lines'][0]['amount']=5
    another=await restored._prepare_preview(changed,'owner')
    options=await restored.async_link(another['token'],'owner',[{'id':'0','product_id':product['id']}])
    assert not options.get('quantity_estimates')


async def test_review_can_save_manual_kg_price_without_changing_receipt_or_stock_quantity(hass):
    manager,catalog,stock,product,draft=await environment(hass,weight_unit_only=True)
    manager._drafts[draft['token']]['receipt']['lines'][0]['reference_id']='R-prod1'
    original=deepcopy(draft['receipt'])
    saved=await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':True,'quantity':500,'unit':'g','purchase_id':'','save_price':True,'manual_measure_price':6.25}],True)
    ref=next(ref for ref in catalog.products[0]['commercial_references'] if ref.get('reference_id')=='R-prod1')
    assert ref['measure_price']['price']==6.25 and ref['measure_price']['source']=='manual'
    assert saved['total']==original['total'] and saved['lines'][0]['amount']==2.5 and saved['lines'][0]['unit_price']==2.5
    assert stock.snapshot['items'][0]['quantity']==500
    assert saved['lines'][0]['manual_measure_price']['price']==6.25
    preview=await manager.async_review_saved(saved['id'],'owner')
    reprocessed=await manager.async_reprocess(preview['token'],'owner',[{'id':'0','product_id':product['id'],'pack_quantity':None,'pack_unit':'g','manual_measure_price':7}])
    assert next(ref for ref in catalog.products[0]['commercial_references'] if ref.get('reference_id')=='R-prod1')['measure_price']['price']==7
    assert reprocessed['total']==original['total'] and stock.snapshot['items'][0]['quantity']==500


@pytest.mark.parametrize('invalid',[0,-1,True,float('nan'),1000001,'6.25'])
async def test_invalid_manual_kg_price_does_not_modify_catalog_or_stock(hass,invalid):
    manager,catalog,stock,product,draft=await environment(hass,weight_unit_only=True)
    before=deepcopy(stock._items)
    with pytest.raises(CatalogError):
        await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':True,'quantity':500,'unit':'g','purchase_id':'','save_price':True,'manual_measure_price':invalid}],True)
    assert stock._items==before and catalog.products[0]['commercial_references'][0]['measure_price']['price']==5


@pytest.mark.parametrize("partial",[False,True])
async def test_shop_pause_stops_web_enrichment_but_allows_receipt_confirmation(hass,partial):
    manager,catalog,stock,product,draft=await environment(hass,saved_rate=False)
    if partial:
        manager.option_lookup.retrieve.return_value={"name":"Zanahorias","retrieval_diagnostics":{"attempts":[{"http_status":403}]}}
    else:
        manager.option_lookup.retrieve.side_effect=PriceError("Carrefour en pausa",response_class="rate_limited",retry_seconds=900)
    result=await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert result["search_paused"] and result["quantity"] is None
    again=await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert again["search_paused"] and manager.option_lookup.retrieve.await_count==1
    assert not catalog.products[0]["commercial_references"][0].get("measure_price")
    saved=await manager.async_confirm(draft["token"],"owner",[{"id":"0","product_id":product["id"],"replenish":True,"quantity":1000,"unit":"g","purchase_id":""}],False)
    assert saved["total"]==2.5 and stock.snapshot["items"][0]["quantity"]==1000


async def test_weight_unit_and_saved_price_estimate_then_preserve_tariff_on_confirm_and_reprocess(hass):
    manager,catalog,stock,product,draft=await environment(hass,saved_rate=False,weight_unit_only=True)
    result=await manager.async_estimate_quantity(draft['token'],'owner','0',product['id'])
    assert result['quantity']==.5 and result['unit']=='kg' and result['estimated']
    manager.option_lookup.retrieve.assert_not_awaited()
    saved=await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':True,
        'quantity':500,'unit':'g','purchase_id':'','save_price':True,'pack_quantity':None,'pack_unit':'g'}],True)
    ref=catalog.products[0]['commercial_references'][0]
    assert ref['content_confirmed'] and ref['content_quantity'] is None and ref['content_unit']=='g'
    assert ref['last_price']['price']==5 and ref['measure_price']['price']==5
    assert saved['lines'][0]['amount']==2.5 and saved['lines'][0]['unit_price']==2.5
    assert saved['lines'][0]['price_saved'] is False
    assert manager.offers_for(catalog.products[0])==[]
    assert stock.snapshot['items'][0]['quantity']==500
    preview=await manager.async_review_saved(saved['id'],'owner')
    reprocessed=await manager.async_reprocess(preview['token'],'owner',[{'id':'0','product_id':product['id'],'pack_quantity':None,'pack_unit':'g'}])
    assert reprocessed['lines'][0]['price_saved'] is False
    assert catalog.products[0]['commercial_references'][0]['last_price']['price']==5


async def test_explicit_ticket_rate_produces_a_per_kg_offer_not_the_paid_amount(hass):
    manager,catalog,stock,product,draft=await environment(hass)
    line=manager._drafts[draft['token']]['receipt']['lines'][0]
    line.update(purchased_quantity=.25,purchased_unit='kg',ticket_measure_price={**rate(10),'source':'ticket'})
    saved=await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':False,
        'quantity':None,'unit':'g','purchase_id':'','save_price':True,'pack_quantity':None,'pack_unit':'kg'}],True)
    assert saved['lines'][0]['price_saved'] and saved['lines'][0]['unit_price']==2.5
    offer=manager.offers_for(catalog.products[0])[0]
    assert offer['price']==10 and offer['pack_quantity']==1 and offer['pack_unit']=='kg'
    assert saved['total']==2.5 and stock.snapshot['items'][0]['quantity']==0


async def test_manual_correction_is_saved_only_for_the_purchase(hass):
    manager,catalog,stock,product,draft=await environment(hass)
    await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    saved=await manager.async_confirm(draft["token"],"owner",[{"id":"0","product_id":product["id"],"replenish":True,"quantity":475,"unit":"g","purchase_id":"","quantity_edited":True}],False)
    assert saved["lines"][0]["purchased_quantity"]==475 and not saved["lines"][0]["quantity_estimated"]
    assert stock.snapshot["items"][0]["quantity"]==475
    assert all(ref["content_quantity"] is None for ref in catalog.products[0]["commercial_references"])


async def test_web_failure_leaves_the_review_usable(hass):
    manager,catalog,stock,product,draft=await environment(hass,saved_rate=False)
    manager.option_lookup.retrieve.side_effect=ValueError("La tienda está en pausa")
    result=await manager.async_estimate_quantity(draft["token"],"owner","0",product["id"])
    assert result["quantity"] is None and "pausa" in result["reason"]
    assert stock.snapshot["items"][0]["quantity"]==0


async def test_estimation_websocket_is_registered_and_checks_draft_owner(hass,hass_ws_client):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'})
    entry.add_to_hass(hass);assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/receipts/estimate_quantity','token':'missing','line_id':'0','product_id':'missing'})
    response=await client.receive_json()
    assert response['error']['code']=='expired'
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unit_price_is_recovered_from_explicit_package_and_requests_stay_serial(hass,aioclient_mock,monkeypatch):
    import json
    lookup=OptionLookup(hass);before=AsyncMock();monkeypatch.setattr(lookup,"_before_request",before)
    html='<script type="application/ld+json">'+json.dumps({"@type":"Product","url":URL,"name":"Zanahorias 500 g","brand":{"name":"Carrefour"},"offers":{"price":"2.5","priceCurrency":"EUR"}})+'</script>'
    aioclient_mock.get(URL,text=html)
    try:
        result=await lookup.retrieve(URL,measure=True)
        assert result["measure_price"]["price"]==5 and result["measure_price"]["unit"]=="kg"
        await lookup.retrieve(URL,measure=True)
        assert before.await_count==1 and aioclient_mock.call_count==1
    finally:lookup.close()


async def test_retry_after_stops_further_queries(hass,aioclient_mock,monkeypatch):
    lookup=OptionLookup(hass);monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    aioclient_mock.get(URL,status=429,headers={"Retry-After":"1200"})
    try:
        with pytest.raises(ValueError,match="pausa"):await lookup.retrieve(URL,measure=True)
        with pytest.raises(ValueError,match="pausa"):await lookup.retrieve(URL.replace("prod1","prod2"),measure=True)
        assert aioclient_mock.call_count==1
    finally:lookup.close()
