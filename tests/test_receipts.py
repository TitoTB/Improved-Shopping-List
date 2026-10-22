"""Receipts: verified quantities, private previews and atomic purchase reconciliation."""

import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.receipt_parser import parse_carrefour, extract_receipt
from custom_components.improved_shopping_list.receipts import ReceiptManager, converted_quantity
from custom_components.improved_shopping_list.stock import StockManager


def receipt_text():
    date = (datetime.now()-timedelta(hours=2)).strftime('%d/%m/%Y %H:%M:%S')
    return f'''Centros Comerciales Carrefour S.A
SEITAN 250 G 2,65
FLAUTIN CEREALES
2 x ( 0,44 ) 0,88
ANACARDO CRUDO 200 2,69
SUBTOTAL 6,22
DTO. CUPON 4X60 EUR -1,00
4 ART. TOTAL A PAGAR : 5,22
NRF: TEST0001
{date}
VISA CONTACTLESS
PAN: PRIVATE_PAYMENT_DATA
SOCIO CLUB: PRIVATE_CUSTOMER
'''


def pdf_bytes(text):
    writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    content=DecodedStreamObject()
    lines=[line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)') for line in text.splitlines()]
    content.set_data(('BT /F1 10 Tf 20 760 Td 14 TL '+ ' '.join(f'({line}) Tj T*' for line in lines)+' ET').encode('latin1'))
    page[NameObject('/Contents')]=writer._add_object(content)
    output=BytesIO();writer.write(output);return output.getvalue()


def test_carrefour_parser_pack_units_coupons_and_multiples():
    receipt=parse_carrefour(receipt_text())
    assert receipt['total']==5.22 and receipt['subtotal']==6.22 and receipt['discount']==1
    assert receipt['article_count']==4 and len(receipt['lines'])==3
    assert converted_quantity(receipt['lines'][0],'g')==250
    assert converted_quantity(receipt['lines'][0],'kg')==.25
    assert converted_quantity(receipt['lines'][0],'l') is None
    assert receipt['lines'][1]['count']==2 and receipt['lines'][1]['unit_price']==.44
    assert receipt['lines'][2]['pack_quantity'] is None
    assert 'PRIVATE_' not in str(receipt)
    with pytest.raises(CatalogError,match='subtotal'):
        parse_carrefour(receipt_text().replace('SUBTOTAL 6,22','SUBTOTAL 8,22'))
    with pytest.raises(CatalogError,match='artículos'):
        parse_carrefour(receipt_text().replace('4 ART.','5 ART.'))


def test_pdf_text_and_no_ocr_or_invalid_upload():
    assert extract_receipt(pdf_bytes(receipt_text()))['total']==5.22
    with pytest.raises(CatalogError,match='PDF'):
        extract_receipt(b'not a pdf')
    with pytest.raises(CatalogError,match='OCR'):
        extract_receipt(pdf_bytes(''))
    with pytest.raises(CatalogError,match='todavía'):
        parse_carrefour(receipt_text().replace('Carrefour','Another shop'))


async def setup_manager(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Seitán'})
    stock=StockManager(hass,catalog);await stock.async_load()
    item=await stock.async_add('Seitán')
    fields=('quantity','unit','mode','days','refill_quantity','reorder_enabled','reorder_at','list_entity','usage_entity','usage_state','usage_amount')
    config={key:item[key] for key in fields};config.update(quantity=20,unit='g',refill_quantity=250)
    item=await stock.async_save(item['id'],item['revision'],config)
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={
        'todo.main':{'uid1':{'status':'needs_action','summary':'Seitan'}}},settings=SimpleNamespace(snapshot={'primary_entity':'todo.main'}))
    prices=SimpleNamespace(_notify=lambda:None)
    manager=ReceiptManager(hass,stock,automation,prices)
    return SimpleNamespace(manager=manager,stock=stock,item=item,product=product,automation=automation)


async def preview(env):
    return await env.manager.async_preview(base64.b64encode(pdf_bytes(receipt_text())).decode(),'owner')


def selections(draft, product, quantity=250, purchase_id=''):
    return [{'id':line['id'],'product_id':product['id'] if index==0 else '',
        'replenish':index==0,'quantity':quantity if index==0 else None,'purchase_id':purchase_id if index==0 else ''}
        for index,line in enumerate(draft['receipt']['lines'])]


async def test_preview_confirm_atomic_history_restart_and_later_purchase(hass):
    env=await setup_manager(hass);draft=await preview(env)
    assert env.stock.snapshot['items'][0]['quantity']==20 and not env.manager.snapshot['receipts']
    assert draft['receipt']['lines'][0]['replenish'] is False  # Similarity is a proposal, not a proven match.
    with pytest.raises(CatalogError,match='caducado'):
        await env.manager.async_confirm(draft['token'],'different-owner',selections(draft,env.product),True)
    receipt=await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),True)
    assert env.stock.snapshot['items'][0]['quantity']==270
    assert receipt['total']==5.22 and len(env.manager.snapshot['receipts'])==1
    assert env.manager.offers_for(env.product)[0]['price']==2.65
    assert 'PRIVATE_' not in str(env.stock.receipts)
    restored=StockManager(hass,env.stock.catalog);await restored.async_load()
    assert restored.receipts==env.stock.receipts and restored.snapshot==env.stock.snapshot
    item=env.stock.snapshot['items'][0]
    event={'id':'completion-1','at':datetime.now().timestamp(),'list_entity':'todo.main','uid':'uid1'}
    await env.stock.async_automatic(item['id'],item['config_revision'],'purchase',event)
    assert env.stock.snapshot['items'][0]['quantity']==270
    await env.stock.async_automatic(item['id'],item['config_revision'],'purchase',event)
    assert env.stock.snapshot['items'][0]['quantity']==270
    with pytest.raises(CatalogError,match='ya se ha importado'):
        await preview(env)
    assert len(env.manager.snapshot['receipts'])==1


async def test_receipt_adjusts_previous_refill_preserving_subsequent_consumption(hass):
    env=await setup_manager(hass)
    event={'id':'previous','at':datetime.now().timestamp(),'list_entity':'todo.main','uid':'uid1'}
    await env.stock.async_automatic(env.item['id'],env.item['config_revision'],'purchase',event)
    await env.stock.async_adjust(env.item['id'],-1)
    assert env.stock.snapshot['items'][0]['quantity']==269
    draft=await preview(env)
    assert draft['purchases'][0]['id']=='previous'
    await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product,500,'previous'),False)
    assert env.stock.snapshot['items'][0]['quantity']==519
    assert env.manager.offers_for(env.product)==[]
    draft2=deepcopy(draft)
    env.manager._drafts[draft2['token']]={'receipt':draft2['receipt'],'owner':'owner','expires':datetime.now().timestamp()+100,'products':draft2['products']}
    with pytest.raises(CatalogError,match='ya se ha importado'):
        await env.manager.async_confirm(draft2['token'],'owner',selections(draft2,env.product),False)


async def test_import_disk_failure_stale_stock_and_confirmed_alias(hass,monkeypatch):
    env=await setup_manager(hass);draft=await preview(env)
    before=deepcopy(env.stock.snapshot)
    save=env.stock._store.async_save
    monkeypatch.setattr(env.stock._store,'async_save',AsyncMock(side_effect=OSError('disk')))
    with pytest.raises(OSError):
        await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),True)
    assert env.stock.snapshot==before and env.manager.snapshot['receipts']==[]
    monkeypatch.setattr(env.stock._store,'async_save',save)
    await env.stock.async_adjust(env.item['id'],-1)
    with pytest.raises(CatalogError,match='stock ha cambiado'):
        await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),True)
    draft=await preview(env)
    await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),True)
    # A different receipt with the same label reuses only the explicitly confirmed conversion.
    text=receipt_text().replace('TEST0001','TEST0002')
    next_draft=await env.manager.async_preview(base64.b64encode(pdf_bytes(text)).decode(),'owner')
    assert next_draft['receipt']['lines'][0]['quantity']==250
    assert next_draft['receipt']['lines'][0]['replenish'] is True


async def test_purchase_queued_during_receipt_review_does_not_double_stock(hass):
    env=await setup_manager(hass);draft=await preview(env)
    env.automation._events=[(env.item['id'],env.item['config_revision'],'purchase',{'id':'arriving'})]
    with pytest.raises(CatalogError,match='acaba de registrar'):
        await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),False)
    assert env.stock.snapshot['items'][0]['quantity']==20
    assert env.manager.snapshot['receipts']==[]


async def test_receipt_prices_only_replace_older_observations_and_respect_disable(hass):
    from custom_components.improved_shopping_list.price_manager import PriceManager
    env=await setup_manager(hass);draft=await preview(env)
    await env.manager.async_confirm(draft['token'],'owner',selections(draft,env.product),True)
    settings=SimpleNamespace(snapshot={'stores':{'carrefour':{'enabled':True,'sale_point':'005704'}},'price_updates_enabled':True})
    prices=PriceManager(hass,env.stock.catalog,settings,None);prices.receipts=env.manager
    assert prices.prices_for(env.product)[0]['source']=='receipt'
    product={**env.product,'store_links':{'carrefour':{'id':'R-test','url':'https://www.carrefour.es/test'}}}
    key=prices.key('carrefour',product['store_links']['carrefour'],prices.scope('carrefour'))
    prices._data['offers'][key]={'store':'carrefour','price':3,'checked_at':datetime.now().timestamp(),'source':'web'}
    assert prices.prices_for(product)[0]['source']=='web'
    prices._data['offers'][key]['checked_at']=0
    assert prices.prices_for(product)[0]['price']==2.65
    settings.snapshot['price_updates_enabled']=False
    assert prices.prices_for(product)==[]


async def test_receipt_api_is_admin_only_and_inactive_guard(hass,hass_ws_client,hass_read_only_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:'todo.bring'})
    entry.add_to_hass(hass);assert await hass.config_entries.async_setup(entry.entry_id)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id='http://test.local')
    client=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    for i,operation in enumerate(['get','subscribe','preview'],1):
        await client.send_json({'id':i,'type':f'{DOMAIN}/receipts/{operation}',**({'pdf':'invalid'} if operation=='preview' else {})})
        assert (await client.receive_json())['error']['code']=='unauthorized'
    await client.close()
    admin=await hass_ws_client(hass)
    await admin.send_json({'id':1,'type':f'{DOMAIN}/receipts/get'})
    assert (await admin.receive_json())['result']=={'receipts':[]}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await admin.send_json({'id':2,'type':f'{DOMAIN}/receipts/get'})
    assert (await admin.receive_json())['error']['code']=='not_loaded'
