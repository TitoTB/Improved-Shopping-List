"""Exact IAN URLs, cache/dictionary priority, spacing and receipt-only commits."""
import asyncio
from copy import deepcopy
import html
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.improved_shopping_list import lidl_catalog as module
from custom_components.improved_shopping_list.lidl_catalog import LidlCatalog, parse_listing, product_data, INTERVAL
from custom_components.improved_shopping_list.ean_links import EANLinks, parse_dictionary
from custom_components.improved_shopping_list.product_references import gtin, merge_reference, normalized_references, matching_reference
from custom_components.improved_shopping_list.store_links import normalize_link
from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.stock import StockManager
from custom_components.improved_shopping_list.receipts import ReceiptManager

WEB="https://www.lidl.es/p/milbona-griego-natural-light/p11139074"
API="https://www.lidl.es/p/api/gridboxes/ES/es?erpNumbers=11139074"
EAN="3017620422003"


def product(code="5720480",erp="11139074",size="8x125 g",future=False):
    price={"packaging":{"text":size},"price":99,"currencyCode":"EUR"}
    return {"ians":[code],"erpNumber":erp,"canonicalPath":f"/p/milbona-griego-natural-light/p{erp}","title":"Griego natural light",
            "brand":{"name":"MILBONA"},"price":{} if future else price,
            "regionsPrices":{"1":{"futurePrices":[{"price":price}]}} if future else {}}


def listing(*products):
    return ('<div data-grid-data="'+html.escape(json.dumps(list(products)),quote=True)+'"></div>').encode()


async def service(hass,monkeypatch,pages=()):
    links=SimpleNamespace(async_find_link=AsyncMock(return_value=None))
    lookup=SimpleNamespace(_before_request=AsyncMock())
    manager=LidlCatalog(hass,links,lookup,SimpleNamespace(record=Mock()));await manager.async_load()
    clock=[time.time()]
    monkeypatch.setattr(module,"time",SimpleNamespace(time=lambda:clock[0]))
    async def wait(delay):clock[0]+=delay
    monkeypatch.setattr(module,"sleep",wait);monkeypatch.setattr(module,"PAGES",pages)
    return manager,links,clock


def test_public_ian_metadata_never_invents_ean_or_copies_web_price():
    data=product_data(product(future=True))
    assert data["ians"]==["5720480"] and data["web_reference_id"]=="11139074"
    assert data["content_quantity"]==1000 and data["content_unit"]=="g" and data["format_provisional"]
    assert data["brand"]=="MILBONA" and "price" not in data and "ean" not in data
    assert parse_listing(listing(product()))[0]["url"]==WEB
    invalid=product();invalid["canonicalPath"]="//evil.test/p11139074"
    assert parse_listing(listing(invalid))==[]


async def test_cache_precedes_dictionary_and_survives_restart(hass,aioclient_mock,monkeypatch):
    manager,links,clock=await service(hass,monkeypatch)
    manager._remember(product_data(product()));await manager._save()
    restored=LidlCatalog(hass,links,manager.lookup,None);await restored.async_load()
    data=await restored.resolve("05720480",EAN)
    assert data["source"]=="cache" and data["url"]==WEB
    links.async_find_link.assert_not_awaited();assert aioclient_mock.call_count==0


async def test_dictionary_precedes_public_pages_and_requires_exact_identity(hass,aioclient_mock,monkeypatch):
    manager,links,clock=await service(hass,monkeypatch,("https://www.lidl.es/c/not-needed",))
    links.async_find_link.return_value=normalize_link("lidl",WEB)
    aioclient_mock.get(API,json=[product()])
    result=await manager.resolve("5720480",EAN)
    links.async_find_link.assert_awaited_once_with("lidl",EAN)
    assert result["source"]=="dictionary" and result["url"]==WEB and aioclient_mock.call_count==1
    assert "price" not in result


async def test_dictionary_lidl_column_is_exact_and_manual_review_can_read_it(hass,aioclient_mock):
    catalog=Catalog(hass);await catalog.async_load();links=EANLinks(hass,catalog);await links.async_load()
    from custom_components.improved_shopping_list.ean_links import URL
    aioclient_mock.get(URL,content=f"EAN,Carrefour,Alcampo,Lidl\n{EAN},,,{WEB}\n".encode())
    assert (await links.async_find_link("lidl",EAN))["url"]==WEB
    assert (await links.async_find_link("lidl","4006381333931")) is None
    assert parse_dictionary(f"EAN,Carrefour,Alcampo,Lidl\n{EAN},,,{WEB}\n".encode())["lidl:"+gtin(EAN)]==WEB
    assert aioclient_mock.call_count==1


async def test_scan_is_daily_spaced_bounded_and_ambiguous_ian_is_not_assigned(hass,aioclient_mock,monkeypatch):
    pages=("https://www.lidl.es/c/first","https://www.lidl.es/c/second")
    manager,links,clock=await service(hass,monkeypatch,pages)
    aioclient_mock.get(pages[0],content=listing(product(),product(code="123",erp="111")))
    aioclient_mock.get(pages[1],content=listing(product(code="123",erp="222")))
    data=await manager.resolve("0005720480")
    assert data["url"]==WEB and aioclient_mock.call_count==2
    assert clock[0]+INTERVAL==manager._data["next_request"]
    assert "reason" in await manager.resolve("123")
    assert "reason" in await manager.resolve("999")
    assert aioclient_mock.call_count==2
    links.async_find_link.assert_not_awaited()
    manager.activity.record.assert_called_once()


async def test_access_denied_pauses_scan_and_keeps_one_diagnostic(hass,aioclient_mock,monkeypatch):
    pages=("https://www.lidl.es/c/first","https://www.lidl.es/c/second")
    manager,links,clock=await service(hass,monkeypatch,pages)
    aioclient_mock.get(pages[0],status=403)
    assert "reason" in await manager.resolve("123")
    assert manager._data["retry_at"]>=clock[0]+900 and aioclient_mock.call_count==1
    assert manager.activity.record.call_args.kwargs["diagnostics"]["errors"][0]["http_status"]==403
    await manager.resolve("456");assert aioclient_mock.call_count==1


async def test_review_commits_web_link_without_replacing_ticket_ian_or_paid_price(hass):
    catalog=Catalog(hass);await catalog.async_load();p=await catalog.async_save_product({"name":"Yogur"})
    stock=StockManager(hass,catalog);await stock.async_load()
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={"primary_entity":"todo.main"}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    manager.lidl_catalog=SimpleNamespace(resolve=AsyncMock(return_value=product_data(product())))
    receipt={"id":"lidl-metadata","digest":"lidl-metadata","store":"lidl","store_name":"Lidl","currency":"EUR","purchased_at":dt_util.now().isoformat(),"total":3.78,"subtotal":3.78,"discount":0,"article_count":2,
        "lines":[{"id":"0","description":"Yogur","count":2,"unit_price":1.89,"amount":3.78,"ean":"","reference_id":"5720480","pack_quantity":None,"pack_unit":""}]}
    draft=await manager._prepare_preview(receipt,"owner")
    await manager.async_link(draft["token"],"owner",[{"id":"0","product_id":p["id"]}])
    before=deepcopy(catalog.products)
    result=await manager.async_lidl_metadata(draft["token"],"owner","0",p["id"])
    assert result["url"]==WEB and catalog.products==before
    with pytest.raises(CatalogError):await manager.async_lidl_metadata(draft["token"],"other","0",p["id"])
    saved=await manager.async_confirm(draft["token"],"owner",[{"id":"0","product_id":p["id"],"replenish":False,"quantity":None,"unit":"uds","purchase_id":"","save_price":True,"pack_quantity":1000,"pack_unit":"g"}],True)
    ref=catalog.products[0]["commercial_references"][0]
    assert ref["reference_id"]=="11139074" and ref["ticket_reference_id"]=="5720480" and ref["url"]==WEB
    assert saved["lines"][0]["reference_id"]=="5720480" and saved["lines"][0]["unit_price"]==1.89
    assert stock.snapshot["items"]==[] and len(ref["ean"])==0
    assert matching_reference(catalog.products[0],"lidl",{"reference_id":"5720480"})["url"]==WEB
    # A subsequent receipt merges into the same alternative and retains its URL.
    rows=deepcopy(catalog.products[0]["commercial_references"])
    merge_reference(rows,"lidl",{"reference_id":"5720480","description":"Yogur","count":1})
    rows=normalized_references(rows)
    assert len(rows)==1 and rows[0]["url"]==WEB and rows[0]["content_quantity"]==1000
    preview=await manager.async_review_saved(saved["id"],"owner")
    await manager.async_lidl_metadata(preview["token"],"owner","0",p["id"])
    await manager.async_reprocess(preview["token"],"owner",[{"id":"0","pack_quantity":750,"pack_unit":"g"}])
    assert len(stock.receipts["history"])==1 and stock.snapshot["items"]==[]
    assert catalog.products[0]["commercial_references"][0]["content_quantity"]==750
    assert manager.offers_for(catalog.products[0])[0]["price"]==1.89
