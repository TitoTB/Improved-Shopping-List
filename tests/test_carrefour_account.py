"""Manual Carrefour access: authorization, private sessions and PDF handoff."""
import base64
import json
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.util import dt as dt_util

from custom_components.improved_shopping_list.carrefour_account import CarrefourAccount, CarrefourAccountError, WEB, API, IDENTITY, OFFSET_KEYS
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY


@pytest.fixture
async def account(hass):
    manager = CarrefourAccount(hass, SimpleNamespace(async_preview=AsyncMock(return_value={"token":"draft"}),async_import_carrefour_purchases=AsyncMock(return_value=0)), SimpleNamespace(record=Mock()))
    await manager.async_load()
    manager._config = {"api_key":"public-key", "client_id":"public-client", "client_secret":"public-config-value"}
    manager.start()
    manager._cookies={"gmid":"test-device"}
    yield manager
    manager.stop()


async def test_start_and_status_never_contact_carrefour(account):
    account._http = AsyncMock()
    assert account.status("owner") == {"connected":False,"email":"","options":{"history_enabled":False,"auto_ticket":False,"public_prices":False},"verification_required":False,"destinations":[],"verification_sent":False}
    account.stop();account.start()
    account._http.assert_not_awaited()


async def test_login_stores_only_session_and_disconnect_forgets_it(account, hass):
    account._http = AsyncMock(return_value={"errorCode":0,"sessionInfo":{"login_token":"PRIVATE_SESSION"},"profile":{"email":"private@example.test"}})
    result = await account.async_login("owner","private@example.test","PRIVATE_PASSWORD")
    assert result["connected"] and "PRIVATE" not in json.dumps(result)
    saved = await account._store.async_load()
    assert saved == {"login_token":"PRIVATE_SESSION","device_cookies":{"gmid":"test-device"},"email":"private@example.test"}
    restored = CarrefourAccount(hass,account.receipts,account.activity);await restored.async_load()
    assert restored.status("owner")["connected"]
    assert account._http.await_args.kwargs["data"]["password"] == "PRIVATE_PASSWORD"
    await account.async_disconnect("owner")
    assert await account._store.async_load() == {}
    assert not account.status("owner")["connected"]


@pytest.mark.parametrize("kind,provider,target_method,targets",[
    ("email","gigyaEmail","getEmails",{"emails":[{"id":"private-id","obfuscated":"a***@example.test"}]}),
    ("phone","gigyaPhone","getRegisteredPhoneNumbers",{"phones":[{"id":"private-id","obfuscated":"***123"}]}),
])
async def test_two_factor_is_owner_bound_and_requires_explicit_send(account,kind,provider,target_method,targets):
    responses = [
        {"errorCode":403101,"regToken":"PRIVATE_REG"},
        {"errorCode":0,"activeProviders":[{"name":provider}]},
        {"errorCode":0,"gigyaAssertion":"PRIVATE_ASSERTION"},
        {"errorCode":0,**targets},
        {"errorCode":0,"phvToken":"PRIVATE_VERIFICATION"},
        {"errorCode":0,"providerAssertion":"PRIVATE_PROVIDER"},
        {"errorCode":0},
        {"errorCode":0,"sessionInfo":{"login_token":"PRIVATE_SESSION"}},
    ]
    account._http=AsyncMock(side_effect=responses)
    status=await account.async_login("owner","test@example.test","PRIVATE_PASSWORD")
    assert status["verification_required"] and not status["verification_sent"]
    assert "PRIVATE" not in json.dumps(status)
    assert not account.status("other")["verification_required"]
    assert not any("sendVerificationCode" in call.args[1] for call in account._http.await_args_list)
    with pytest.raises(CarrefourAccountError,match="caducado"):
        await account.async_send_code("other","0")
    assert (await account.async_send_code("owner","0"))["verification_sent"]
    with pytest.raises(CarrefourAccountError,match="un minuto"):
        await account.async_send_code("owner","0")
    status=await account.async_verify("owner","123456")
    assert status["connected"] and not status["verification_required"]
    assert not account._pending
    assert account._http.await_args_list[3].args[1] == IDENTITY+"/accounts.tfa."+kind+"."+target_method
    assert "PRIVATE_PASSWORD" not in json.dumps(await account._store.async_load())


async def test_expired_session_requires_manual_reconnect_and_never_retries_password(account):
    account._session={"login_token":"expired"}
    account._http=AsyncMock(return_value={"errorCode":403005})
    with pytest.raises(CarrefourAccountError,match="caducado"):
        await account.async_purchases("owner")
    assert not account.status("owner")["connected"]
    assert account._http.await_count == 1
    assert account._http.await_args.args[1].endswith("accounts.getJWT")


async def test_purchases_and_pdf_are_manual_bound_and_never_confirm_stock(account):
    account._session={"login_token":"private","jwt":"private-jwt","jwt_until":time.time()+500}
    cursor=dict.fromkeys(OFFSET_KEYS,0);cursor["ticketOffset"]=10
    row={"purchaseId":"test-ticket-1","purchaseDate":dt_util.now().isoformat(),"amount":3.75,"orderSource":"TICKET","mallName":"Test Carrefour"}
    account._http=AsyncMock(side_effect=[{"purchases":[row,{**row,"purchaseId":"order-1","orderSource":"FOOD"}],"offsets":cursor},b"%PDF-test"])
    result=await account.async_purchases("owner")
    assert result["next_cursor"]==cursor and len(result["purchases"])==2
    assert result["purchases"][0]["reviewable"] and not result["purchases"][1]["reviewable"]
    key=result["purchases"][0]["id"]
    assert "test-ticket-1" not in json.dumps(result)
    with pytest.raises(CarrefourAccountError,match="consultar las compras"):
        await account.async_preview("other",key)
    with pytest.raises(CarrefourAccountError,match="manualmente"):
        await account.async_preview("owner",result["purchases"][1]["id"])
    with pytest.raises(CarrefourAccountError,match="consultar las compras"):
        await account.async_preview("owner","https://other.test/secret")
    assert await account.async_preview("owner",key)=={"token":"draft"}
    assert account._http.await_count==2
    assert account._http.await_args.args[1]==API+"/md-ticketsAccount-v1/tickets/test-ticket-1/pdf"
    encoded,owner=account.receipts.async_preview.await_args.args
    assert owner=="owner" and base64.b64decode(encoded)==b"%PDF-test"
    assert account._http.await_args.kwargs["headers"]["Authorization"]=="Bearer private-jwt"
    account.stop()
    assert not account._purchases


@pytest.mark.parametrize("status",[302,401,403,500])
async def test_transport_failures_keep_safe_technical_diagnostics(account,aioclient_mock,status):
    url=API+"/md-purchasesAccount-v1/purchases"
    aioclient_mock.get(url,status=status,text="PRIVATE_RESPONSE_TOKEN")
    with pytest.raises(CarrefourAccountError) as failure:
        await account._http("GET",url)
    assert failure.value.diagnostics["http_status"]==status
    assert "PRIVATE" not in str(failure.value)
    assert aioclient_mock.call_count==1


async def test_pdf_format_and_size_are_checked_before_parser(account,aioclient_mock):
    url=API+"/md-ticketsAccount-v1/tickets/test/pdf"
    aioclient_mock.get(url,text="<html>login</html>")
    with pytest.raises(CarrefourAccountError,match="PDF válido"):
        await account._http("GET",url,pdf=True)
    account.receipts.async_preview.assert_not_awaited()


async def test_public_config_is_discovered_not_copied_from_har(account,aioclient_mock):
    account._config={}
    aioclient_mock.get(WEB+"/access/resources/config.js",text="var c4apis = {val:'site-key'}; var c4Headers = {clientMD:'site-client',secretMD:'site-secret'};")
    assert (await account._public_config())["api_key"]=="site-key"
    await account._public_config()
    assert aioclient_mock.call_count==1


async def test_account_websocket_commands_require_admin_and_setup_never_fetches(hass,hass_ws_client,hass_read_only_user,aioclient_mock):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.main"});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    client=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    actions=[("status",{}),("login",{"username":"test","password":"secret"}),("send_code",{"destination":"0"}),
        ("verify",{"code":"123456"}),("disconnect",{}),("purchases",{}),("sync_history",{}),("options",{"options":{}}),("preview",{"purchase_id":"id"})]
    for i,(action,fields) in enumerate(actions,1):
        await client.send_json({"id":i,"type":f"{DOMAIN}/carrefour_account/"+action,**fields})
        assert (await client.receive_json())["error"]["code"]=="unauthorized"
    await client.close()
    assert aioclient_mock.call_count==0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_identity_bootstrap_keeps_provider_device_cookie(account,monkeypatch):
    from http.cookies import SimpleCookie
    account._cookies={}
    class Response:
        status=200
        def __init__(self,data,cookies=""):
            self.data=json.dumps(data).encode()
            self.cookies=SimpleCookie(cookies)
            self.content=self
        async def __aenter__(self):return self
        async def __aexit__(self,*_args):pass
        async def iter_chunked(self,_size):yield self.data
    class Session:
        async def __aenter__(self):return self
        async def __aexit__(self,*_args):pass
    session=Session()
    session.request=Mock(side_effect=[
        Response({"errorCode":0},"gmid=device-issued-by-provider; Path=/; Secure; HttpOnly"),
        Response({"errorCode":0,"sessionInfo":{"login_token":"session"}}),
    ])
    monkeypatch.setattr("custom_components.improved_shopping_list.carrefour_account.async_create_clientsession",Mock(return_value=session))
    result=await account.async_login("owner","test@example.test","password")
    assert result["connected"] and session.request.call_count==2
    assert account._cookies["gmid"]=="device-issued-by-provider"
    assert session.request.call_args.kwargs["headers"]["Cookie"]=="gmid=device-issued-by-provider"


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_pdf_server_error_uses_detail_once_without_reauthenticating(account, status):
    account._session={"login_token":"private", "jwt":"private-jwt", "jwt_until":time.time()+500}
    row={"purchaseId":"test-ticket-1", "purchaseDate":dt_util.now().isoformat(), "amount":5.22, "orderSource":"TICKET"}
    detail={"ticketId":"test-ticket-1", "header":{"netAmount":5.22}, "lines":["private printable lines"]}
    error=CarrefourAccountError("PDF no disponible", "pdf", status=status)
    account._http=AsyncMock(side_effect=[{"purchases":[row]}, error, detail])
    draft={"token":"detail-draft", "receipt":{"lines":[{}]}}
    account.receipts.async_preview_carrefour_ticket=AsyncMock(return_value=draft)
    result=await account.async_purchases("owner")
    assert await account.async_preview("owner",result["purchases"][0]["id"])==draft
    assert [request.args[1] for request in account._http.await_args_list[1:]]==[
        API+"/md-ticketsAccount-v1/tickets/test-ticket-1/pdf", API+"/md-ticketsAccount-v1/tickets/test-ticket-1"]
    account.receipts.async_preview_carrefour_ticket.assert_awaited_once_with(detail,"test-ticket-1",5.22,"owner")
    account.receipts.async_preview.assert_not_awaited()
    assert account.activity.record.call_args.kwargs["diagnostics"]=={"pdf_http_status":status,"fallback":"ticket_detail","products":1}
    assert "private" not in str(account.activity.record.call_args)


@pytest.mark.parametrize("status", [401,403,404])
async def test_pdf_access_errors_never_try_the_detail_endpoint(account,status):
    account._session={"login_token":"private", "jwt":"private-jwt", "jwt_until":time.time()+500}
    row={"purchaseId":"test-ticket-1", "purchaseDate":dt_util.now().isoformat(), "amount":5.22, "orderSource":"TICKET"}
    account._http=AsyncMock(side_effect=[{"purchases":[row]},CarrefourAccountError("Acceso rechazado","pdf",status=status)])
    result=await account.async_purchases("owner")
    with pytest.raises(CarrefourAccountError):
        await account.async_preview("owner",result["purchases"][0]["id"])
    assert account._http.await_count==2


async def test_history_sync_reads_all_pages_of_last_year_and_imports_only_summaries(account):
    account._session={"login_token":"private","jwt":"private-jwt","jwt_until":time.time()+500}
    cursor=dict.fromkeys(OFFSET_KEYS,0);cursor["ticketOffset"]=10
    def row(identifier, days):
        return {"purchaseId":identifier,"purchaseDate":(dt_util.now()-timedelta(days=days)).isoformat(),"amount":5.22,"orderSource":"TICKET"}
    account._http=AsyncMock(side_effect=[{"purchases":[row("a",300)],"offsets":cursor},
                                        {"purchases":[row("b",10),row("too-old",400)],"offsets":cursor}])
    account.receipts.async_import_carrefour_purchases.side_effect=[1,1]
    result=await account.async_sync_history("owner")
    assert result=={"added":2,"available":2,"complete":True}
    assert account._http.await_count==2
    assert all(request.args[1]==API+"/md-purchasesAccount-v1/purchases" for request in account._http.await_args_list)
    first=account._http.await_args_list[0].kwargs["params"]
    assert (dt_util.utcnow()-dt_util.parse_datetime(first["from"])).days==365
    assert [[row["purchaseId"] for row in call.args[0]] for call in account.receipts.async_import_carrefour_purchases.await_args_list]==[["a"],["b"]]
    account.receipts.async_preview.assert_not_awaited()


async def test_carrefour_options_require_connection_except_public_prices(account):
    account._queue_background=Mock()
    with pytest.raises(CarrefourAccountError,match="Conecta"):
        await account.async_options("owner",{"history_enabled":True,"auto_ticket":False,"public_prices":False})
    status=await account.async_options("owner",{"history_enabled":False,"auto_ticket":False,"public_prices":True})
    assert status["options"]["public_prices"] and not status["connected"]
    account._session={"login_token":"private","email":"account@example.test"}
    account.async_sync_history=AsyncMock()
    status=await account.async_options("owner",{"history_enabled":True,"auto_ticket":False,"public_prices":True})
    account.async_sync_history.assert_awaited_once_with("owner")
    assert status["email"]=="account@example.test"
    await account.async_disconnect("owner")
    assert account.status("owner")["options"]=={"history_enabled":False,"auto_ticket":False,"public_prices":True}


async def test_automatic_download_requires_completion_and_runs_once_per_day(account):
    account._session={"login_token":"private"}
    account.settings=SimpleNamespace(snapshot={"price_update_time":"00:00"})
    account._options["auto_ticket"]=True
    account.async_purchases=AsyncMock(return_value={"purchases":[{"id":"key","purchased_at":dt_util.now().isoformat(),"reviewable":True}]})
    account._purchases={"key":{"id":"real-ticket"}}
    account.async_preview=AsyncMock(return_value={"token":"draft"})
    account.receipts.account_ticket_available=Mock(return_value=False)
    account.receipts.async_archive_account_ticket=AsyncMock()
    await account._run_background()
    account.async_purchases.assert_not_awaited()
    account._options["completion_at"]=time.time()
    await account._run_background()
    account.receipts.async_archive_account_ticket.assert_awaited_once_with("draft","automatic_carrefour")
    account._options["completion_at"]+=1
    await account._run_background()
    account.async_purchases.assert_awaited_once()
    account.receipts.async_preview.assert_not_awaited()


async def test_completions_are_ignored_until_automatic_download_is_enabled(account):
    account._session={"login_token":"private"}
    account._queue_background=Mock()
    account.note_completion()
    assert account._options["completion_at"]==0
    account._options["auto_ticket"]=True
    account.note_completion()
    assert account._options["completion_at"]>0
    account._queue_background.assert_called_once()
