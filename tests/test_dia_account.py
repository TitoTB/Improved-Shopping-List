"""DIA structured tickets, private session persistence and guarded account access."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import io
import json
import urllib.error

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.catalog import CatalogError
from custom_components.improved_shopping_list.dia_account import DiaAccount, DiaAccountHTTP, DiaAccountError, API
from custom_components.improved_shopping_list.dia_receipts import summary, reference_id, extract_dia_account_ticket
from custom_components.improved_shopping_list.receipts import ReceiptManager
from custom_components.improved_shopping_list.ticket_accounts import TicketAccounts


def fixture_ticket():
    when=dt_util.utcnow().replace(microsecond=0)
    params={"ticket":"123","begin":str(int(when.timestamp()*1000)),"business":"1","country":"ES","pos":"2","store":"12345"}
    raw={"submitted_date":when.isoformat(),"total_amount":4.91,"detail_params":params,"online":False,"return":False}
    detail={"header":{"code":123,"store_code":12345,"pos":2,"submitted_date":when.isoformat(),"ticket_unique_code":"private-id","store_address":"PRIVATE_ADDRESS"},
        "currency":"EUR","amount":{"total_amount":4.91,"total_amount_without_discounts":5.78,"total_discounts":-.87,"shipping_amount":0},
        "corporate":{"amount":4.91,"items":[{"code":111111,"name":"PRODUCTO A 500 G","amount":4.49,"price_per_unit":4.49,"quantity":1,"weight":0,"variable_weight":False,"discounts":[{"amount":-.68,"description":"Oferta"}]},
            {"code":222222,"name":"PRODUCTO B","amount":1.29,"price_per_unit":1.29,"quantity":1,"weight":0,"variable_weight":False,"discounts":[{"amount":-.19}]}]},
        "payment":{"private":"PRIVATE_PAYMENT"},"tef":{"lines":["PRIVATE_CARD"]},"return":False,"void":False}
    return params,raw,detail


def test_dia_ticket_net_prices_identity_validation_and_no_ean_or_private_data():
    params,raw,detail=fixture_ticket()
    assert summary(raw)["params"]==params
    receipt=extract_dia_account_ticket(detail,params,4.91)
    assert receipt["store"]=="dia" and receipt["total"]==4.91 and receipt["discount"]==0
    assert [line["unit_price"] for line in receipt["lines"]]==[3.81,1.1]
    assert receipt["lines"][0]["pack_quantity"]==500 and receipt["article_count"]==2
    assert all(line["ean"]=="" for line in receipt["lines"])
    assert [line["reference_id"] for line in receipt["lines"]]==["111111","222222"]
    assert "PRIVATE" not in json.dumps(receipt) and "private-id" not in json.dumps(receipt)
    assert extract_dia_account_ticket(detail,params,4.91)["id"]==receipt["id"]
    for changes in ({"header":{**detail["header"],"code":999}},{"return":True},{"void":True},{"currency":"USD"},
                    {"amount":{**detail["amount"],"total_amount":4.0}}):
        with pytest.raises(CatalogError):extract_dia_account_ticket({**detail,**changes},params,4.91)
    with pytest.raises(CatalogError):extract_dia_account_ticket(detail,{**params,"begin":str(int(params["begin"])-86400000)},4.91)
    with pytest.raises(CatalogError):extract_dia_account_ticket(detail,params,100)


def test_dia_weighted_quantities_and_canceled_lines():
    params,raw,detail=fixture_ticket()
    row={"code":123456,"name":"FRUTA","amount":3,"price_per_unit":2,"quantity":1,"weight":1.5,"variable_weight":True,"discounts":[]}
    detail["corporate"]={"amount":3,"items":[row,{**row,"cancel":True}]}
    detail["amount"]={"total_amount":3,"total_amount_without_discounts":3,"total_discounts":0,"shipping_amount":0}
    receipt=extract_dia_account_ticket(detail,params,3)
    assert len(receipt["lines"])==1 and receipt["lines"][0]["pack_unit"]=="kg" and receipt["lines"][0]["pack_quantity"]==1.5
    detail["corporate"]["items"][0]["weight"]=float("nan")
    with pytest.raises(CatalogError):extract_dia_account_ticket(detail,params,3)


@pytest.fixture
async def account(hass):
    receipts=SimpleNamespace(_account_key=ReceiptManager._account_key,async_import_account_purchases=AsyncMock(return_value=0),
        async_preview_dia_ticket=AsyncMock(return_value={"token":"draft"}),account_ticket_available=Mock(return_value=False),
        async_archive_account_ticket=AsyncMock(),discard=Mock(),stock=SimpleNamespace(receipts={"history":{}}))
    manager=DiaAccount(hass,receipts,SimpleNamespace(record=Mock()))
    await manager.async_load();manager.settings=SimpleNamespace(snapshot={"price_update_time":"00:00"});manager.start()
    yield manager
    await manager.async_stop()


async def test_dia_login_status_optional_credentials_restart_and_reconnect(account,hass):
    async def provider(path,body=None):
        if path.endswith("check-email"):return {"personal_info":{"are_legal_conditions_accepted":True,"are_consents_accepted":False}}
        assert path.endswith("login") and body["are_consents_accepted"] is False
        account._session["cookies"]=[{"name":"private-cookie","value":"SECRET"}]
        return {"user_tokens":{"access_token":"SECRET_ACCESS","id_token":"SECRET_ID","refresh_token":"SECRET_REFRESH"}}
    account._http=AsyncMock(side_effect=provider)
    result=await account.async_login("owner","test@example.test","SECRET_PASSWORD",True)
    assert result["connected"] and result["credentials_saved"] and "SECRET" not in json.dumps(result)
    restored=DiaAccount(hass,account.receipts,account.activity);await restored.async_load();restored.start()
    assert restored.status("owner")["connected"]
    assert (await restored._store.async_load())["cookies"][0]["value"]=="SECRET"
    assert (await restored._credentials_store.async_load())["password"]=="SECRET_PASSWORD"
    await restored.async_stop()
    await account.async_disconnect("owner")
    assert not account.status("owner")["connected"]
    await account.async_login("owner","test@example.test","",True)
    assert account.status("owner")["connected"]
    await account.async_login("owner","test@example.test","SECRET_PASSWORD",False)
    assert not account.status("owner")["credentials_saved"] and await account._credentials_store.async_load()=={}


async def test_dia_block_preserves_session_and_401_reauth_is_bounded(account):
    account._session={"email":"test@example.test","access_token":"SECRET"}
    account._http=AsyncMock(side_effect=DiaAccountError("Bloqueo","tickets",http_status=403,response_class="access_denied"))
    with pytest.raises(DiaAccountError):await account._request(API+"/customer/current/tickets")
    assert account.status("owner")["connected"]
    account._credentials={"username":"test@example.test","password":"SECRET_PASSWORD"}
    account._login=AsyncMock()
    account._http=AsyncMock(side_effect=[DiaAccountError("Caducado","tickets",http_status=401),{"tickets":[]}])
    assert await account._request(API+"/customer/current/tickets")=={"tickets":[]}
    assert account._login.await_count==1 and account._http.await_count==2
    account._credentials={};account._http=AsyncMock(side_effect=DiaAccountError("Caducado","tickets",http_status=401))
    with pytest.raises(DiaAccountError):await account._request(API+"/customer/current/tickets")
    assert not account.status("owner")["connected"]


async def test_dia_history_pagination_saved_reference_and_detail_does_not_import_stock(account,hass):
    params,raw,detail=fixture_ticket()
    account._session={"email":"test@example.test","access_token":"SECRET"}
    account._request=AsyncMock(return_value={"tickets":[raw],"total_tickets":21,"pagination":{}})
    result=await account.async_purchases("owner",import_summaries=True)
    assert result["next_cursor"]=={"offset":1} and len(result["purchases"])==1
    identifier=result["purchases"][0]["id"]
    assert identifier==ReceiptManager._account_key(reference_id(params),"dia")
    assert identifier!=ReceiptManager._account_key(reference_id(params),"carrefour")
    assert "SECRET" not in json.dumps(result) and "detail_params" not in json.dumps(result)
    account._request=AsyncMock(return_value=detail)
    await account.async_preview("owner",identifier)
    account.receipts.async_preview_dia_ticket.assert_awaited_once_with(detail,params,4.91,"owner")
    restored=DiaAccount(hass,account.receipts,account.activity);await restored.async_load()
    assert identifier in restored._session["purchase_refs"]
    with pytest.raises(DiaAccountError):await account.async_purchases("owner",{"offset":True})


def test_dia_transport_limits_first_party_cookies_and_reports_403_without_response_body():
    client=DiaAccountHTTP([{"domain":"evil.test","name":"bad","value":"secret","path":"/"}])
    assert not list(client.jar)
    response=urllib.error.HTTPError("https://www.dia.es/test",403,"Forbidden",{"Content-Type":"text/html"},io.BytesIO(b"Access denied SECRET"))
    client.opener.open=Mock(side_effect=response)
    with pytest.raises(DiaAccountError) as caught:client.request(API+"/customer/current/tickets")
    assert caught.value.diagnostics["response_class"]=="access_denied" and "SECRET" not in str(caught.value)


async def test_dia_websocket_admin_only_and_no_password_or_token_in_results(hass,hass_ws_client,hass_read_only_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    manager=hass.data[DOMAIN]["dia_account"]
    manager._session={"email":"test@example.test","access_token":"SECRET"}
    writer=await hass_ws_client(hass)
    await writer.send_json({"id":1,"type":f"{DOMAIN}/dia_account/status"})
    result=await writer.receive_json();assert result["success"] and result["result"]["connected"] and "SECRET" not in json.dumps(result)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    reader=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    for i,action in enumerate(("status","login","disconnect","options","purchases","sync_history","preview","preview_saved"),1):
        fields={"login":{"username":"test@example.test","password":"SECRET"},"options":{"options":{"history_enabled":True,"auto_ticket":False}},"preview":{"purchase_id":"id"},"preview_saved":{"receipt_id":"id"}}.get(action,{})
        await reader.send_json({"id":i,"type":f"{DOMAIN}/dia_account/{action}",**fields})
        assert (await reader.receive_json())["error"]["code"]=="unauthorized"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_ticket_accounts_share_zone_favorite_order_and_stop_after_confirmation():
    calls=[]
    def make(store):
        async def fetch(now,detected):calls.append(store);return True
        return SimpleNamespace(_save_options=AsyncMock(),automatic_due=lambda *a:True,async_automatic_ticket=fetch)
    detection=SimpleNamespace(enabled=False,pending_for_today=False,ticket_search_order=lambda sources:["dia","carrefour"])
    manager=TicketAccounts({"carrefour":make("carrefour"),"dia":make("dia")},SimpleNamespace(record=Mock()));manager.purchase_detection=detection
    await manager.async_check()
    assert calls==["dia"]


async def test_dia_review_pending_import_is_explicit_and_preserves_one_history_entry(hass):
    import asyncio
    from custom_components.improved_shopping_list.catalog import Catalog
    from custom_components.improved_shopping_list.stock import StockManager
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({"name":"Producto A"})
    stock=StockManager(hass,catalog);await stock.async_load()
    item=await stock.async_add(product["name"])
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={"primary_entity":"todo.main"}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=Mock()))
    params,raw,detail=fixture_ticket()
    await manager.async_import_account_purchases([{"purchaseId":reference_id(params),"purchaseDate":raw["submitted_date"],"amount":4.91}],"dia")
    assert len(manager.snapshot["receipts"])==1 and stock.snapshot["items"][0]["quantity"]==0
    draft=await manager.async_preview_dia_ticket(detail,params,4.91,"automatic")
    pending=await manager.async_archive_account_ticket(draft["token"],"automatic")
    assert pending["pending_review"] and len(manager.snapshot["receipts"])==1
    assert stock.snapshot["items"][0]["quantity"]==0 and not manager.offers_for(product)
    review=await manager.async_review_saved(pending["id"],"owner")
    choices=[{"id":line["id"],"product_id":product["id"] if i==0 else "","replenish":i==0,"quantity":1 if i==0 else None,"unit":"uds","purchase_id":"","save_price":i==0} for i,line in enumerate(review["receipt"]["lines"])]
    receipt=await manager.async_confirm(review["token"],"owner",choices,True)
    assert len(manager.snapshot["receipts"])==1 and not receipt.get("pending_review")
    assert stock.snapshot["items"][0]["quantity"]==1
    assert manager.offers_for(product)[0]["price"]==3.81
    assert manager.offers_for(product)[0]["reference_id"]=="111111"
    assert catalog.products[0].get("barcodes",[])==[]
    assert stock.receipt_stores[product["id"]]==["dia"]
    with pytest.raises(CatalogError,match="ya se ha importado"):
        await manager.async_preview_dia_ticket(detail,params,4.91,"owner")


async def test_dia_automatic_download_once_per_day_and_stays_pending(account):
    params,raw,detail=fixture_ticket()
    account._session={"email":"test@example.test","access_token":"SECRET"}
    account._options.update(auto_ticket=True,completion_at=dt_util.utcnow().timestamp())
    account._request=AsyncMock(side_effect=[{"tickets":[raw],"total_tickets":1},detail])
    await account.async_automatic_ticket(dt_util.now(),True)
    account.receipts.async_archive_account_ticket.assert_awaited_once_with("draft","automatic_dia")
    await account.async_automatic_ticket(dt_util.now(),True)
    assert account._request.await_count==2
