"""Lidl renewable accounts, private OAuth and validated printed receipts."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit, urlencode
import json
import time

import pytest
from homeassistant.util import dt as dt_util
from custom_components.improved_shopping_list.catalog import CatalogError
from custom_components.improved_shopping_list.lidl_account import LidlAccount, LidlAccountError
from custom_components.improved_shopping_list import lidl_account as module
from custom_components.improved_shopping_list.lidl_receipts import extract_lidl_ticket
from custom_components.improved_shopping_list.receipts import ReceiptManager


def fixture_ticket():
    when = dt_util.utcnow().replace(microsecond=0).isoformat()
    html = '''<span class="article" data-art-id="1234567" data-art-description="PAN" data-unit-price="1,00">PAN 1,00 A</span>
<span class="article" data-art-id="2345678" data-art-description="FRUTA" data-unit-price="4,00" data-art-quantity="0,500">FRUTA 2,00 A</span>
<span class="article" data-art-id="2345678" data-art-description="FRUTA" data-unit-price="4,00" data-art-quantity="0,500">0,500 kg x 4,00 EUR/kg</span>
<span class="purchase_summary">\nTotal          3,00\n</span><span>PRIVATE_PAYMENT</span>'''
    return {"id":"safe-receipt-id", "date":when, "totalAmount":0, "htmlPrintedReceipt":html}, when


def test_lidl_receipt_weight_continuation_zero_header_and_private_fields():
    detail, when = fixture_ticket()
    receipt = extract_lidl_ticket(detail, detail['id'], 3, when)
    assert len(receipt['lines']) == 2 and receipt['total'] == 3
    fruit = receipt['lines'][1]
    assert fruit['count'] == 1 and fruit['pack_quantity'] == .5 and fruit['pack_unit'] == 'kg'
    assert fruit['unit_price'] == 2 and fruit['reference_id'] == '2345678' and fruit['ean'] == ''
    assert 'PRIVATE' not in json.dumps(receipt) and 'htmlPrintedReceipt' not in receipt
    for altered in ({**detail,'id':'other'}, {**detail,'isDeleted':True}, {**detail,'htmlPrintedReceipt':detail['htmlPrintedReceipt'].replace('FRUTA 2,00','FRUTA 9,00')}):
        with pytest.raises(CatalogError):extract_lidl_ticket(altered, detail['id'], 3, when)
    with pytest.raises(CatalogError):extract_lidl_ticket(detail, detail['id'], 10, when)


@pytest.fixture
async def account(hass):
    receipts = SimpleNamespace(_account_key=ReceiptManager._account_key, async_import_account_purchases=AsyncMock(return_value=0),
        async_preview_lidl_ticket=AsyncMock(return_value={'token':'draft'}), account_ticket_available=Mock(return_value=False),
        async_archive_account_ticket=AsyncMock(), discard=Mock(), stock=SimpleNamespace(receipts={'history':{}}))
    manager = LidlAccount(hass, receipts, SimpleNamespace(record=Mock()))
    await manager.async_load();manager.settings=SimpleNamespace(snapshot={'price_update_time':'00:00'});manager.start()
    yield manager
    await manager.async_stop()


def authorize(manager, owner='admin'):
    url=manager.begin(owner)['authorization_url'];params=parse_qs(urlsplit(url).query)
    return 'com.lidlplus.app://callback?'+urlencode({'state':params['state'][0],'code':'PRIVATE_CODE'}),params


async def test_lidl_pkce_owner_binding_persistence_and_rotated_refresh(account,hass,monkeypatch):
    replies=[{'access_token':'PRIVATE_ACCESS','refresh_token':'PRIVATE_REFRESH','expires_in':1200},
        {'access_token':'NEW_ACCESS','refresh_token':'ROTATED_REFRESH','expires_in':1200}]
    request=Mock(side_effect=lambda *_args:replies.pop(0));monkeypatch.setattr(module,'request_json',request)
    callback, params=authorize(account)
    assert params['code_challenge_method']==['S256'] and params['prompt']==['login'] and 'max_age' not in params
    with pytest.raises(LidlAccountError):await account.async_finish('different-admin',callback)
    status=await account.async_finish('admin',callback)
    assert status['connected'] and 'PRIVATE' not in json.dumps(status)
    assert request.call_args.args[1]['code_verifier']
    restored=LidlAccount(hass,account.receipts,account.activity);await restored.async_load();restored.start()
    try:
        assert restored.status('admin')['connected']
        await restored._refresh()
        assert restored._session['refresh_token']=='ROTATED_REFRESH'
        again=LidlAccount(hass,account.receipts,account.activity);await again.async_load()
        assert again._session['refresh_token']=='ROTATED_REFRESH'
        await restored.async_disconnect('admin')
        assert not restored.status('admin')['connected']
        with pytest.raises(LidlAccountError):await account.async_finish('admin',callback)
    finally:await restored.async_stop()


async def test_lidl_transient_refresh_preserves_session_but_revocation_clears(account,monkeypatch):
    account._session={'access_token':'old','refresh_token':'refresh','expires_at':0}
    def failed(*_args):raise LidlAccountError('Unavailable','token',http_status=503)
    monkeypatch.setattr(module,'request_json',failed)
    with pytest.raises(LidlAccountError):await account._refresh()
    assert account.status('a')['connected']
    def revoked(*_args):raise LidlAccountError('Expired','token',oauth_error='invalid_grant',http_status=400)
    monkeypatch.setattr(module,'request_json',revoked)
    with pytest.raises(LidlAccountError):await account._refresh()
    assert not account.status('a')['connected']


async def test_lidl_history_pages_import_and_saved_preview(account):
    detail,when=fixture_ticket()
    account._session={'access_token':'access','refresh_token':'refresh','expires_at':time.time()+1200}
    account._request=AsyncMock(return_value={'tickets':[{'id':detail['id'],'date':when,'totalAmount':3}], 'totalCount':26,'size':25})
    result=await account.async_purchases('a',import_summaries=True)
    assert result['next_cursor']=={'page':2} and len(result['purchases'])==1
    assert account.receipts.async_import_account_purchases.call_args.args[1]=='lidl'
    key=result['purchases'][0]['id'];account.receipts.stock.receipts['history']['saved']={'store':'lidl','summary_only':True,'account_key':key}
    account._request=AsyncMock(return_value=detail)
    assert await account.async_preview_saved('a','saved')=={'token':'draft'}
    assert account._request.call_args.args[0].startswith('/api/v3/ES/tickets/')
    assert account.receipts.async_preview_lidl_ticket.call_args.args[1]==detail['id']
    with pytest.raises(LidlAccountError):await account.async_purchases('a',{'page':True})


async def test_lidl_automatic_pending_review_and_daily_limit(account):
    detail,when=fixture_ticket();now=dt_util.now()
    account._session={'access_token':'access','refresh_token':'refresh','purchase_refs':{'key':{'reference':detail['id']}}}
    account._options.update(auto_ticket=True,completion_at=time.time())
    account.async_purchases=AsyncMock(return_value={'purchases':[{'id':'key','purchased_at':when}]})
    account.async_preview=AsyncMock(return_value={'token':'draft'})
    assert await account.async_automatic_ticket(now,True)
    account.receipts.async_archive_account_ticket.assert_awaited_once_with('draft','automatic_lidl')
    assert not account.automatic_due(now,True)
    account.receipts.async_preview_lidl_ticket.assert_not_awaited()


async def test_lidl_options_require_connection_and_do_not_enable_on_invalid_input(account):
    with pytest.raises(LidlAccountError):await account.async_options('a',{'history_enabled':True,'auto_ticket':False})
    with pytest.raises(LidlAccountError):await account.async_options('a',{'history_enabled':1,'auto_ticket':False})
    assert not account._options['history_enabled']

async def test_lidl_account_commands_are_admin_only_and_never_return_tokens(hass,hass_ws_client,hass_read_only_user):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.main'});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    manager=hass.data[DOMAIN]['lidl_account'];manager._session={'access_token':'PRIVATE_ACCESS','refresh_token':'PRIVATE_REFRESH'}
    writer=await hass_ws_client(hass)
    await writer.send_json({'id':1,'type':f'{DOMAIN}/lidl_account/status'})
    result=await writer.receive_json();assert result['success'] and result['result']['connected'] and 'PRIVATE' not in json.dumps(result)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id='http://test.local')
    reader=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    for i,action in enumerate(('status','begin','finish','disconnect','options','purchases','sync_history','preview','preview_saved'),1):
        fields={'finish':{'callback':'com.lidlplus.app://callback?code=x'},'options':{'options':{'history_enabled':True,'auto_ticket':False}},'preview':{'purchase_id':'id'},'preview_saved':{'receipt_id':'id'}}.get(action,{})
        await reader.send_json({'id':i,'type':f'{DOMAIN}/lidl_account/{action}',**fields})
        assert (await reader.receive_json())['error']['code']=='unauthorized'
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_lidl_saved_summary_review_and_confirm_preserve_stock_until_confirmation(hass):
    from custom_components.improved_shopping_list.catalog import Catalog
    from custom_components.improved_shopping_list.stock import StockManager
    catalog=Catalog(hass);await catalog.async_load();product=await catalog.async_save_product({'name':'Pan'})
    stock=StockManager(hass,catalog);await stock.async_load();item=await stock.async_add('Pan')
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={'primary_entity':'todo.main'}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=Mock()))
    detail,when=fixture_ticket()
    await manager.async_import_account_purchases([{'purchaseId':detail['id'],'purchaseDate':when,'amount':3}],'lidl')
    draft=await manager.async_preview_lidl_ticket(detail,detail['id'],3,when,'automatic')
    pending=await manager.async_archive_account_ticket(draft['token'],'automatic')
    assert pending['pending_review'] and len(manager.snapshot['receipts'])==1
    assert stock.snapshot['items'][0]['quantity']==item['quantity'] and not manager.offers_for(product)
    review=await manager.async_review_saved(pending['id'],'owner')
    choices=[{'id':line['id'],'product_id':product['id'] if i==0 else '', 'replenish':i==0,'quantity':1 if i==0 else None,'unit':'uds','purchase_id':'','save_price':i==0} for i,line in enumerate(review['receipt']['lines'])]
    await manager.async_confirm(review['token'],'owner',choices,True)
    assert stock.snapshot['items'][0]['quantity']==item['quantity']+1
    assert len(manager.snapshot['receipts'])==1 and manager.offers_for(product)[0]['price']==1
    assert catalog.products[0].get('barcodes',[])==[] and stock.receipt_stores[product['id']]==['lidl']
