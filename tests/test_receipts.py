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
from homeassistant.util import dt as dt_util

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.receipt_parser import parse_carrefour, parse_carrefour_invoice, extract_receipt, extract_carrefour_account_ticket
from custom_components.improved_shopping_list.receipts import ReceiptManager, converted_quantity
from custom_components.improved_shopping_list.stock import StockManager


def receipt_text():
    date = (dt_util.now()-timedelta(hours=2)).strftime('%d/%m/%Y %H:%M:%S')
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
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica'),NameObject('/Encoding'):NameObject('/WinAnsiEncoding')})
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
    prices._data['offers']['retired-web-offer']={'store':'carrefour','price':3,'checked_at':datetime.now().timestamp(),'source':'web'}
    assert prices.prices_for(product)[0]['source']=='receipt'
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
    for i,operation in enumerate(['options','link'],4):
        await client.send_json({'id':i,'type':f'{DOMAIN}/receipts/{operation}','token':'missing',**({'lines':[]} if operation=='link' else {})})
        assert (await client.receive_json())['error']['code']=='unauthorized'
    await client.close()
    admin=await hass_ws_client(hass)
    await admin.send_json({'id':1,'type':f'{DOMAIN}/receipts/get'})
    assert (await admin.receive_json())['result']=={'receipts':[]}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await admin.send_json({'id':2,'type':f'{DOMAIN}/receipts/get'})
    assert (await admin.receive_json())['error']['code']=='not_loaded'


async def test_links_survive_without_stock_prices_or_finishing_the_ticket(hass):
    env=await setup_manager(hass)
    cereal=await env.stock.catalog.async_save_product({'name':'Flautines'})
    draft=await preview(env);before=deepcopy(env.stock.snapshot)
    links=[{'id':line['id'],'product_id':env.product['id'] if index==0 else cereal['id'] if index==1 else ''} for index,line in enumerate(draft['receipt']['lines'])]
    await env.manager.async_link(draft['token'],'owner',links)
    env.manager.discard(draft['token'],'owner')
    assert env.stock.snapshot==before and env.manager.snapshot['receipts']==[]
    assert env.manager.offers_for(env.product)==[]
    restored=StockManager(hass,env.stock.catalog);await restored.async_load()
    manager=ReceiptManager(hass,restored,env.automation,env.manager.prices)
    next_draft=await manager.async_preview(base64.b64encode(pdf_bytes(receipt_text())).decode(),'owner')
    assert next_draft['receipt']['lines'][1]['product_id']==cereal['id']
    assert next_draft['receipt']['lines'][1]['replenish'] is False
    assert next_draft['receipt']['lines'][0]['quantity']==250


async def test_product_can_only_be_linked_to_one_line_in_a_ticket(hass):
    env=await setup_manager(hass);draft=await preview(env)
    links=[{'id':line['id'],'product_id':env.product['id'] if index<2 else ''} for index,line in enumerate(draft['receipt']['lines'])]
    before=deepcopy(env.stock.receipts)
    with pytest.raises(CatalogError,match='Dos líneas'):
        await env.manager.async_link(draft['token'],'owner',links)
    edits=[{**line,'replenish':False,'quantity':None,'purchase_id':'','save_price':True} for line in links]
    with pytest.raises(CatalogError,match='Dos líneas'):
        await env.manager.async_confirm(draft['token'],'owner',edits,True)
    assert env.stock.receipts==before


async def test_new_stock_and_individually_selected_prices_are_atomic(hass,monkeypatch):
    env=await setup_manager(hass)
    cereal=await env.stock.catalog.async_save_product({'name':'Flautines'})
    nuts=await env.stock.catalog.async_save_product({'name':'Anacardos'})
    draft=await preview(env)
    products=[env.product,cereal,nuts]
    links=[{'id':line['id'],'product_id':products[index]['id']} for index,line in enumerate(draft['receipt']['lines'])]
    await env.manager.async_link(draft['token'],'owner',links)
    edits=[{**link,'replenish':index==1,'quantity':2 if index==1 else None,'unit':'uds','purchase_id':'','save_price':index!=1} for index,link in enumerate(links)]
    before=deepcopy(env.stock.snapshot);save=env.stock._store.async_save
    monkeypatch.setattr(env.stock._store,'async_save',AsyncMock(side_effect=OSError('disk')))
    with pytest.raises(OSError):
        await env.manager.async_confirm(draft['token'],'owner',edits,True)
    assert env.stock.snapshot==before and env.manager.snapshot['receipts']==[]
    monkeypatch.setattr(env.stock._store,'async_save',save)
    await env.manager.async_confirm(draft['token'],'owner',edits,True)
    item=env.stock.item_for(cereal)
    assert item['quantity']==2 and item['unit']=='uds' and item['refill_quantity']==2
    assert env.stock.item_for(env.product)['quantity']==20 and env.stock.item_for(nuts) is None
    assert env.manager.offers_for(cereal)==[]
    assert env.manager.offers_for(env.product)[0]['price']==2.65
    assert env.manager.offers_for(nuts)[0]['price']==2.69


async def test_link_step_checks_owner_and_unique_preview_proposals(hass):
    env=await setup_manager(hass)
    draft=await preview(env)
    with pytest.raises(CatalogError,match='caducado'):
        await env.manager.async_options(draft['token'],'someone-else')
    links=[{'id':line['id'],'product_id':''} for line in draft['receipt']['lines']]
    with pytest.raises(CatalogError,match='caducado'):
        await env.manager.async_link(draft['token'],'someone-else',links)
    ids=[line['product_id'] for line in draft['receipt']['lines'] if line['product_id']]
    assert len(ids)==len(set(ids))


async def test_receipt_link_choices_include_catalog_image_and_icon(hass):
    env = await setup_manager(hass)
    current = next(product for product in env.stock.catalog.products if product["id"] == env.product["id"])
    await env.stock.catalog.async_save_product({"id": current["id"], "revision": current["revision"], "name": "Seitán", "image_url": "/local/seitan.png", "icon": "mdi:food"})
    draft = await preview(env)
    choices = await env.manager.async_options(draft["token"], "owner")
    product = next(product for product in choices["products"] if product["id"] == env.product["id"])
    assert product["image_url"] == "/local/seitan.png"
    assert product["icon"] == "mdi:food"


def invoice_text():
    date = (dt_util.now()-timedelta(days=1)).strftime('%d/%m/%Y')
    return f'''Carrefour
FACTURA Nº: TEST-INVOICE-0001 NOMBRE: PRIVATE_CUSTOMER
FECHA FACTURA: {date} CIF/NIF: PRIVATE_TAX_ID
PEDIDO Nº: PRIVATE_ORDER DIRECCIÓN: PRIVATE_ADDRESS
FECHA PEDIDO: 01/01/2020
EAN DESCRIPCIÓN CANTIDAD PVP DESCUENTO TOTAL PVP BASE % IVA
1234567890128 PRODUCTO ALFA 250 G 2,000 6,58 0,00 6,58 5,98 10,00
4006381333931 PRODUCTO BETA 3,000 9,75 -3,25 6,50 5,37 21,00
8410109115543 PRODUCTO GAMMA 1,000 2,65 -2,65 0,00 0,00 4,00
EAN DESCRIPCIÓN CANTIDAD PVP DESCUENTO TOTAL PVP BASE % IVA
TOTAL IMPUESTOS INCLUIDOS 13,08 EUR
BASE IMPONIBLE GASTOS DE ENVÍO 3,30 EUR
IVA GASTOS DE ENVÍO 21,00% 0,69 EUR
TOTAL GASTOS DE ENVÍO 3,99 EUR
OTROS DESCUENTOS/BONIF. FACTURA 0,00 EUR
TOTAL FACTURA 17,07 EUR
Pago con Tarjeta PRIVATE_PAYMENT
C.C. CARREFOUR, S.A.
'''


def test_carrefour_invoice_ean_line_prices_promotions_shipping_and_privacy():
    receipt = parse_carrefour_invoice(invoice_text())
    assert receipt['document_type'] == 'invoice'
    assert receipt['subtotal'] == 13.08 and receipt['shipping'] == 3.99 and receipt['total'] == 17.07
    assert receipt['article_count'] == 6 and len(receipt['lines']) == 3
    first, promotion, free = receipt['lines']
    assert first['ean'] == '1234567890128' and first['count'] == 2 and first['unit_price'] == 3.29
    assert converted_quantity(first, 'g') == 500
    assert promotion['unit_price'] == 3.25 and promotion['amount'] == 6.5 and promotion['line_discount'] == 3.25
    assert free['amount'] == 0 and free['unit_price'] == 2.65
    assert 'PRIVATE_' not in str(receipt)
    assert receipt['purchased_at'].startswith((dt_util.now()-timedelta(days=1)).strftime('%Y-%m-%d'))
    assert extract_receipt(pdf_bytes(invoice_text()))['document_type'] == 'invoice'


@pytest.mark.parametrize(('before', 'after'), [
    ('1234567890128', '1234567890129'),
    ('2,000 6,58', '0,000 6,58'),
    ('6,50 5,37', '6,61 5,37'),
    ('TOTAL IMPUESTOS INCLUIDOS 13,08', 'TOTAL IMPUESTOS INCLUIDOS 14,08'),
    ('TOTAL GASTOS DE ENVÍO 3,99', 'TOTAL GASTOS DE ENVÍO 2,99'),
    ('TOTAL FACTURA 17,07', 'TOTAL FACTURA 18,07'),
])
def test_carrefour_invoice_rejects_unbalanced_or_invalid_lines(before, after):
    with pytest.raises(CatalogError):
        parse_carrefour_invoice(invoice_text().replace(before, after))


async def test_invoice_matches_saved_ean_confirms_stock_prices_and_duplicate(hass):
    env = await setup_manager(hass)
    current = next(p for p in env.stock.catalog.products if p['id'] == env.product['id'])
    await env.stock.catalog.async_save_product({'id':current['id'], 'revision':current['revision'], 'name':'Seitán', 'barcodes':['01234567890128']})
    encoded = base64.b64encode(pdf_bytes(invoice_text())).decode()
    draft = await env.manager.async_preview(encoded, 'owner')
    first = draft['receipt']['lines'][0]
    assert first['product_id'] == env.product['id'] and first['matched'] is True
    assert first['quantity'] == 500 and first['replenish'] is True
    confirmed = await env.manager.async_confirm(draft['token'], 'owner', selections(draft, env.product, 500), True)
    assert confirmed['total'] == 17.07 and confirmed['shipping'] == 3.99
    assert env.stock.snapshot['items'][0]['quantity'] == 520
    assert env.manager.offers_for(env.product)[0]['price'] == 3.29
    assert 'PRIVATE_' not in str(env.stock.receipts)
    # Same invoice identity is rejected even if PDF bytes change.
    with pytest.raises(CatalogError, match='ya se ha importado'):
        await env.manager.async_preview(base64.b64encode(pdf_bytes(invoice_text()+'\n')).decode(), 'owner')


def test_account_ticket_detail_matches_pdf_identity_and_keeps_no_personal_data():
    text=receipt_text()
    detail={"ticketId":"test-ticket", "header":{"netAmount":5.22}, "lines":text.splitlines(),
            "clientId":"PRIVATE_CUSTOMER", "cardNumber":"PRIVATE_PAYMENT"}
    receipt=extract_carrefour_account_ticket(detail,"test-ticket",5.22)
    pdf=extract_receipt(pdf_bytes(text))
    assert receipt["id"]==pdf["id"]
    assert receipt["lines"]==pdf["lines"]
    assert receipt["total"]==5.22
    assert "PRIVATE" not in str(receipt)
    for bad,reference,total in [({**detail,"ticketId":"other"},"test-ticket",5.22),
        ({**detail,"header":{"netAmount":8}},"test-ticket",5.22),
        (detail,"test-ticket",7),({**detail,"lines":[{}]},"test-ticket",5.22),
        ({**detail,"lines":["x"*2001]},"test-ticket",5.22),
        ({**detail,"lines":text.replace("SUBTOTAL 6,22","SUBTOTAL 8,00").splitlines()},"test-ticket",5.22)]:
        with pytest.raises(CatalogError):
            extract_carrefour_account_ticket(bad,reference,total)


async def test_account_ticket_detail_only_previews_and_cannot_reimport_pdf(hass):
    env=await setup_manager(hass)
    text=receipt_text()
    detail={"ticketId":"test-ticket", "header":{"netAmount":5.22}, "lines":text.splitlines()}
    draft=await env.manager.async_preview_carrefour_ticket(detail,"test-ticket",5.22,"owner")
    assert env.stock.snapshot["items"][0]["quantity"]==20
    assert env.manager.snapshot["receipts"]==[]
    await env.manager.async_confirm(draft["token"],"owner",selections(draft,env.product),False)
    with pytest.raises(CatalogError,match="ya se ha importado"):
        await env.manager.async_preview(base64.b64encode(pdf_bytes(text)).decode(),"owner")


async def test_account_summaries_persist_without_stock_prices_and_upgrade_once(hass):
    env=await setup_manager(hass)
    text=receipt_text()
    parsed=parse_carrefour(text)
    purchase={"purchaseId":"private-account-reference","purchaseDate":parsed["purchased_at"],"amount":5.22}
    assert await env.manager.async_import_carrefour_purchases([purchase])==1
    assert await env.manager.async_import_carrefour_purchases([purchase])==0
    basic=env.manager.snapshot["receipts"]
    assert len(basic)==1 and basic[0]["summary_only"]
    assert basic[0]["article_count"] is None and basic[0]["lines"]==[]
    assert "private-account-reference" not in str(env.stock.receipts)
    assert env.stock.snapshot["items"][0]["quantity"]==20
    assert env.manager.offers_for(env.product)==[]
    reloaded=StockManager(hass,env.stock.catalog);await reloaded.async_load()
    assert reloaded.receipts["history"]==env.stock.receipts["history"]
    # A manually uploaded PDF upgrades the summary by date/amount; it is not a duplicate.
    draft=await env.manager.async_preview(base64.b64encode(pdf_bytes(text)).decode(),"owner")
    assert len(env.manager.snapshot["receipts"])==1
    confirmed=await env.manager.async_confirm(draft["token"],"owner",selections(draft,env.product),False)
    assert not confirmed.get("summary_only") and confirmed["article_count"]==4
    assert len(env.manager.snapshot["receipts"])==1
    assert env.stock.snapshot["items"][0]["quantity"]==270
    assert await env.manager.async_import_carrefour_purchases([purchase])==0
    assert len(env.manager.snapshot["receipts"])==1
    with pytest.raises(CatalogError,match="ya se ha importado"):
        await env.manager.async_preview(base64.b64encode(pdf_bytes(text)).decode(),"owner",account_reference=purchase["purchaseId"])


async def test_summary_sync_after_review_does_not_duplicate_existing_purchase(hass):
    env=await setup_manager(hass)
    draft=await preview(env)
    receipt=await env.manager.async_confirm(draft["token"],"owner",selections(draft,env.product),False)
    purchase={"purchaseId":"account-id","purchaseDate":receipt["purchased_at"],"amount":receipt["total"]}
    assert await env.manager.async_import_carrefour_purchases([purchase])==0
    assert len(env.manager.snapshot["receipts"])==1
    assert env.stock.snapshot["items"][0]["quantity"]==270
    assert env.manager.snapshot["receipts"][0]["account_key"]==env.manager._account_key("account-id")


async def test_downloaded_ticket_waits_for_review_and_survives_summary_sync(hass):
    env=await setup_manager(hass)
    draft=await env.manager.async_preview(base64.b64encode(pdf_bytes(receipt_text())).decode(),"automatic_carrefour",account_reference="account-ticket")
    saved=await env.manager.async_archive_account_ticket(draft["token"],"automatic_carrefour")
    assert saved["pending_review"] and saved["summary_only"]
    assert env.stock.snapshot["items"][0]["quantity"]==20
    assert env.manager.offers_for(env.product)==[]
    await env.manager.async_import_carrefour_purchases([{"purchaseId":"account-ticket","purchaseDate":saved["purchased_at"],"amount":saved["total"]}])
    assert env.manager.snapshot["receipts"][0]["pending_review"]
    assert env.manager.account_ticket_available("account-ticket")
    reviewed=await env.manager.async_review_saved(saved["id"],"owner")
    assert not reviewed["receipt"].get("summary_only")
    await env.manager.async_confirm(reviewed["token"],"owner",selections(reviewed,env.product),False)
    assert len(env.manager.snapshot["receipts"])==1
    assert not env.manager.snapshot["receipts"][0].get("pending_review")
    assert env.stock.snapshot["items"][0]["quantity"]==270
