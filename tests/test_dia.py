"""DIA postal isolation, ordinary urllib transport and HA executor use."""

from copy import deepcopy
from io import BytesIO
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.error import HTTPError

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list import dia as module
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.dia import DiaClient, DiaError, NoRedirect, product_offer, request_json
from custom_components.improved_shopping_list.regional_stores import async_resolve_areas
from custom_components.improved_shopping_list.price_sources import PriceSources, PriceError
from custom_components.improved_shopping_list.store_links import normalize_link

CONFIG={"postal_code":"28024","area_id":"28024","zone":"28024"}
URL="https://www.dia.es/aperitivos-y-frutos-secos/patatas-fritas/p/84892"
PRODUCT={"sku_id":"84892","object_id":"84892","display_name":"Lay's Gourmet 170 g","units_in_stock":10,
    "url":"/aperitivos-y-frutos-secos/patatas-fritas/p/84892",
    "prices":{"currency":"EUR","price":2.84,"price_per_unit":16.71,"measure_unit":"KILO","is_club_price":False}}
DATA={"cart":{"postal_code":"28024"},"search_items":[PRODUCT]}


def test_exact_reference_and_real_link_even_when_search_returns_other_products():
    data=deepcopy(DATA);data["search_items"].insert(0,{**PRODUCT,"sku_id":"999"})
    result=product_offer(data,normalize_link("dia","84892"),"28024")
    assert result["price"]=="2.84" and result["reference_price"]=="16.71" and result["url"]==URL
    assert result["ean"]==""  # Internal reference is never a scanner code.
    assert product_offer(DATA,normalize_link("dia","999"),"28024") is None


@pytest.mark.parametrize("change",["postal","currency","negative","nan","duplicate","object_id","url"])
def test_ambiguous_or_wrong_context_is_rejected(change):
    data=deepcopy(DATA);p=data["search_items"][0]
    if change=="postal":data["cart"]["postal_code"]="28041"
    elif change=="duplicate":data["search_items"].append(deepcopy(p))
    elif change=="object_id":p["object_id"]="wrong"
    elif change=="url":p["url"]="/aperitivos/p/999"
    elif change=="currency":p["prices"]["currency"]="USD"
    else:p["prices"]["price"]=-1 if change=="negative" else "NaN"
    with pytest.raises(DiaError):product_offer(data,normalize_link("dia","84892"),"28024")


@pytest.mark.parametrize("change",["club","stock"])
def test_no_conditional_club_price_or_unavailable_product(change):
    data=deepcopy(DATA)
    if change=="club":data["search_items"][0]["prices"]["is_club_price"]=True
    else:data["search_items"][0]["units_in_stock"]=0
    assert product_offer(data,normalize_link("dia","84892"),"28024") is None


def test_links_accept_ids_and_official_product_paths_without_tracking():
    assert normalize_link("dia",URL+"?tracking=1")["url"]==URL
    assert normalize_link("dia","84892")["id"]=="84892"
    for value in (URL.replace("https:","http:"),URL.replace("www.dia.es","evil.example"),URL.replace("/p/84892","/p/../84892")):
        with pytest.raises(ValueError):normalize_link("dia",value)


async def test_sync_transport_runs_in_executor_and_each_request_uses_gate(hass,monkeypatch):
    owner=get_ident();calls=[];opener=object()
    def factory():
        assert get_ident()!=owner
        return opener
    def request(given,path,*,postal=False):
        assert get_ident()!=owner and given is opener
        calls.append((path,postal));return None if postal else deepcopy(DATA)
    monkeypatch.setattr(module,"anonymous_opener",factory)
    monkeypatch.setattr(module,"request_json",request)
    client=DiaClient(hass);gate=AsyncMock()
    assert (await client.fetch(normalize_link("dia","84892"),CONFIG,gate))["price"]=="2.84"
    assert len(calls)==2 and calls[0][1] is True and gate.await_count==2
    await client.fetch(normalize_link("dia","84892"),CONFIG,gate)
    assert len(calls)==3 and gate.await_count==3
    client.close();assert client.opener is None and client.postal is None


async def test_postal_validation_works_with_no_matching_products(hass,monkeypatch):
    owner=get_ident();calls=[]
    monkeypatch.setattr(module,"anonymous_opener",lambda:object())
    def request(opener,path,*,postal=False):
        assert get_ident()!=owner
        calls.append(path)
        return None if postal else {"cart":{"postal_code":"28024"},"search_items":[]}
    monkeypatch.setattr(module,"request_json",request)
    result=await async_resolve_areas(hass,"dia","28024")
    assert result["areas"]==[{"id":"28024","zone":"28024","name":"Código postal 28024"}]
    assert len(calls)==2


async def test_invalid_configuration_makes_no_request():
    request=AsyncMock();hass=SimpleNamespace(async_add_executor_job=request)
    with pytest.raises(DiaError):await DiaClient(hass).fetch(normalize_link("dia","84892"),{**CONFIG,"area_id":"28041"},AsyncMock())
    request.assert_not_awaited()


@pytest.mark.parametrize("raw",[b'not json', b'x'*(module.MAX_RESPONSE+1)])
def test_invalid_or_oversized_response(raw):
    class Opener:
        def open(self,request,timeout):return Response(raw)
    with pytest.raises(DiaError):request_json(Opener(),"/api/example")


async def test_failed_or_wrong_postal_clears_client_and_keeps_price_as_error(hass,monkeypatch):
    monkeypatch.setattr(module,"anonymous_opener",lambda:object())
    def request(opener,path,*,postal=False):
        if postal:return None
        return {"cart":{"postal_code":"28041"},"search_items":[]}
    monkeypatch.setattr(module,"request_json",request)
    source=PriceSources(hass)
    with pytest.raises(PriceError) as err:await source.fetch("dia",normalize_link("dia","84892"),CONFIG,AsyncMock())
    assert err.value.diagnostics["response_class"]=="invalid_region"
    assert source.dia.opener is None


class Response(BytesIO):
    status=200


def test_bounded_stdlib_response_and_redirects_are_not_followed():
    class Opener:
        def open(self,request,timeout):
            assert request.full_url.startswith("https://www.dia.es/") and timeout==25
            assert not request.has_header("User-agent")  # Opener adds urllib's real default.
            return Response(b'{}')
    assert request_json(Opener(),"/api/example")=={}
    assert NoRedirect().redirect_request(None,None,302,"",{},"https://evil.example") is None


@pytest.mark.parametrize(("status","kind"),[(403,"access_denied"),(429,"rate_limited"),(302,"http_error")])
def test_http_diagnostics_are_preserved(status,kind):
    class Opener:
        def open(self,request,timeout):raise HTTPError(request.full_url,status,"Rejected",{"Retry-After":"600"},BytesIO(b'blocked'))
    with pytest.raises(DiaError) as err:request_json(Opener(),"/api/example")
    assert err.value.diagnostics["http_status"]==status
    assert err.value.diagnostics["response_class"]==kind and err.value.diagnostics["retry_seconds"]==600


async def test_dia_ws_postal_save_and_read_only_cannot_trigger_network(hass,hass_ws_client,hass_read_only_user,monkeypatch):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    calls=[]
    def resolve(postal):calls.append(postal);return {"postal_code":postal,"areas":[{"id":postal,"zone":postal,"name":"Zona postal"}]}
    monkeypatch.setattr("custom_components.improved_shopping_list.regional_stores.resolve_dia_postal",resolve)
    client=await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/settings/store","store":"dia","enabled":False,"postal_code":"28024","area_id":"28024","verify":True})
    assert (await client.receive_json())["result"]["stores"]["dia"]["zone"]=="28024"
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    reader=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await reader.send_json({"id":1,"type":f"{DOMAIN}/settings/resolve_store","store":"dia","postal_code":"28024"})
    assert (await reader.receive_json())["error"]["code"]=="unauthorized"
    assert calls==[]  # Reference activation no longer discovers coverage.
