"""Public EAN search, explicit consent, verified metadata and durable bounded calls."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import time

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.catalog_sources import INTERVAL
from custom_components.improved_shopping_list import catalog_sources as base_module, eci_catalog as module
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.eci_catalog import ECIClient, ECICatalog, product_data, BASE, STORE
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.store_links import normalize_link

EAN='8410199023094'
OTHER='8410422111086'
PATH='/supermercado/B001018009401193-lays-gourmet-patatas-fritas-crujientes-original-bolsa-170-g/'
WEB=BASE+PATH


def payload(code=EAN):
    return {'pdp':{'product':{'id':'B001018009401193','description':'Patatas fritas 170 g','brand':{'name':"lay's gourmet"},
        'information_alimentary':{'general':{'ean':code,'netAmount':{'value':'170.0','unitName':'g'}}},
        'priceSpecification':{'price':'2,89','salePrice':'2,89','measurementUnitPrice':'17','pum_description':'Kilo'},
        'promotional_actions':[{'unit_price':'1,93'}]}}}


def test_product_parser_uses_single_item_price_and_exact_ean_not_conditional_promotions():
    data=product_data(payload(),normalize_link(STORE,WEB),EAN)
    assert data['price']==2.89 and data['measure_price']['price']==17
    assert data['brand']=="Lay's gourmet" and data['content_quantity']==170 and data['content_unit']=='g'
    assert data['reference_id']=='B001018009401193'
    with pytest.raises(PriceError):product_data(payload(OTHER),normalize_link(STORE,WEB),EAN)
    with pytest.raises(ValueError):normalize_link(STORE,'https://www.elcorteingles.es.example.org'+PATH)
    with pytest.raises(ValueError):normalize_link(STORE,'B001018009401193')


@pytest.fixture
async def eci_http(monkeypatch):
    class HTTP:
        def __init__(self):self.responses={};self.requests=[];self.clients=[]
        @property
        def call_count(self):return len(self.requests)
        def get(self,url,*,json=None,status=200):self.responses[url]=(json,status)
        def handle(self,request):
            self.requests.append(request)
            headers={"Content-Type":"application/json","Server":"AkamaiGHost"}
            if str(request.url)==BASE+"/supermercado/":
                headers["Set-Cookie"]="public_session=anonymous; Path=/; Secure"
                return httpx.Response(200,text="<html></html>",headers=headers,extensions={"http_version":b"HTTP/2"})
            body,status=self.responses[str(request.url)]
            return httpx.Response(status,json=body if status==200 else None,
                content=None if status==200 else b"Access Denied Reference&#32;#18.abc.123",headers=headers,
                extensions={"http_version":b"HTTP/2"})
        def create(self,hass,**kwargs):
            assert kwargs.pop("alpn_protocols")==module.SSL_ALPN_HTTP11_HTTP2
            assert kwargs.pop("auto_cleanup") is False
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handle),**kwargs)
            self.clients.append(client);return client
    transport=HTTP()
    monkeypatch.setattr(module,"create_async_httpx_client",transport.create)
    yield transport
    for client in transport.clients:await client.aclose()


async def test_public_search_ignores_ads_then_verifies_product_without_cookies(hass,eci_http):
    search=BASE+'/supermercado/buscar/?question='+EAN+'&catalog=supermercado&stype=text_box'
    eci_http.get(search,json={'products':[{'id':'advertisement','url':'https://example.org'},{'id':'B001018009401193','url':PATH}]})
    eci_http.get(WEB,json=payload())
    before=AsyncMock();data=await ECIClient(hass).search(EAN,before)
    assert before.await_count==3 and data['ean']==EAN and eci_http.call_count==3
    for request in eci_http.requests:
        assert request.headers["response_type"]=="json"
        assert "authorization" not in request.headers
    assert "cookie" not in eci_http.requests[0].headers
    assert eci_http.requests[1].headers["cookie"]=="public_session=anonymous"
    assert eci_http.requests[2].headers["cookie"]=="public_session=anonymous"


@pytest.mark.parametrize("rows", [[], [
    {"id":"B001018009401193","url":PATH},
    {"id":"B001018009401194","url":PATH.replace("1193", "1194")},
]])
async def test_no_result_or_ambiguous_results_never_create_an_equivalence(hass,eci_http,rows):
    search=BASE+'/supermercado/buscar/?question='+EAN+'&catalog=supermercado&stype=text_box'
    eci_http.get(search,json={'products':rows})
    assert await ECIClient(hass).search(EAN,AsyncMock()) is None
    assert eci_http.call_count==2


async def test_blocked_search_requests_a_pause_and_does_not_follow_other_endpoints(hass,eci_http):
    search=BASE+'/supermercado/buscar/?question='+EAN+'&catalog=supermercado&stype=text_box'
    eci_http.get(search,status=403)
    with pytest.raises(PriceError) as err:await ECIClient(hass).search(EAN,AsyncMock())
    assert err.value.diagnostics['http_status']==403 and err.value.diagnostics['retry_seconds']>=900
    assert err.value.diagnostics['transport']=='httpx' and err.value.diagnostics['stage']=='search'
    assert err.value.diagnostics['http_version']=='HTTP/2'
    assert err.value.diagnostics['server']=='AkamaiGHost' and err.value.diagnostics['block_reference']=='18.abc.123'
    assert eci_http.call_count==2


async def test_consent_cache_spacing_new_eans_and_manual_data_survive(hass,monkeypatch):
    catalog=Catalog(hass);await catalog.async_load()
    p=await catalog.async_save_product({'name':'Patatas','barcodes':[EAN],'commercial_references':[
        {'store':'carrefour','ean':EAN,'name':'Mi producto','brand':'Marca manual','content_quantity':200,'content_unit':'g','content_confirmed':True}]})
    clock=[time.time()]
    fake_time=SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0])
    monkeypatch.setattr(base_module,'time',fake_time);monkeypatch.setattr(module,'time',fake_time)
    async def sleep(delay):clock[0]+=delay
    monkeypatch.setattr(base_module,'sleep',sleep)
    lookup=SimpleNamespace(_before_request=AsyncMock())
    source=ECICatalog(hass,catalog,lookup,None);await source.async_load()
    calls=[]
    async def search(code,before):
        await before();calls.append(clock[0]);await before();calls.append(clock[0])
        result=product_data(payload(code),normalize_link(STORE,WEB),code);result['checked_at']=clock[0]
        return result
    source.client.search=AsyncMock(side_effect=search)
    source._active=True
    await source.async_run();assert not calls  # Disabled by default.
    source._active=False;await source.async_set_enabled(True);source._active=True
    try:
        await source.async_run()
        assert len(calls)==2 and calls[1]-calls[0]>=INTERVAL
        refs=catalog.products[0]['commercial_references'];new=next(r for r in refs if r['store']==STORE)
        assert new['brand']=='Marca manual' and new['content_quantity']==200 and new['last_price']['price']==2.89
        await source.async_run();assert source.client.search.await_count==1
        await catalog.async_save_product({'name':'Segundo','barcodes':[OTHER]})
        await source.async_run();assert source.client.search.await_count==2
        restored=ECICatalog(hass,catalog,lookup,None);await restored.async_load()
        assert restored.snapshot['enabled'] and gtin(EAN) in restored._data['attempts']
        before=deepcopy(catalog.products)
        await source.async_set_enabled(False);assert catalog.products==before
    finally:await source.async_stop()


async def test_opt_in_is_admin_only_and_independent_of_alcampo(hass,hass_ws_client,hass_admin_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    await client.send_json({'id':1,'type':f'{DOMAIN}/catalog_sources/set','source':STORE,'enabled':True})
    result=await client.receive_json();assert result['success'] and result['result']['enabled']
    assert not hass.data[DOMAIN]['catalog_sources'].snapshot['enabled']
    assert hass.data[DOMAIN]['eci_catalog'].snapshot['enabled']


async def test_blocked_ean_retries_after_pause_instead_of_being_skipped_for_a_day(hass,monkeypatch):
    catalog=Catalog(hass);await catalog.async_load()
    await catalog.async_save_product({"name":"Aceitunas", "barcodes":[EAN]})
    clock=[time.time()]
    monkeypatch.setattr(module,"time",SimpleNamespace(time=lambda:clock[0]))
    source=ECICatalog(hass,catalog,SimpleNamespace(_before_request=AsyncMock()),None)
    await source.async_load();await source.async_set_enabled(True);source._active=True
    source.client.search=AsyncMock(side_effect=[PriceError("Bloqueo",http_status=403,retry_seconds=900),None])
    try:
        await source.async_run()
        assert source.snapshot["phase"]=="paused" and gtin(EAN) not in source._data["attempts"]
        await source.async_run();assert source.client.search.await_count==1
        clock[0]+=901
        await source.async_run();assert source.client.search.await_count==2
        assert source.snapshot["phase"]=="finished" and not source._data["attempts"][gtin(EAN)]["success"]
    finally:await source.async_stop()
