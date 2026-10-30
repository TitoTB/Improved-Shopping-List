"""Commercial references persist through receipts, editing and restart."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util
from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, FIELDS
from custom_components.improved_shopping_list.stock import StockManager
from custom_components.improved_shopping_list.receipts import ReceiptManager
from custom_components.improved_shopping_list.price_history import PriceHistory


async def test_receipt_formats_survive_restart_and_correct_comparisons_without_stock_changes(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Huevos','unit_quantity':250})
    stock=StockManager(hass,catalog);await stock.async_load()
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={'primary_entity':'todo.main'}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    receipt={'id':'test-eggs','digest':'test-eggs','store':'lidl','store_name':'Lidl','currency':'EUR','purchased_at':dt_util.now().isoformat(),
        'total':3,'subtotal':3,'discount':0,'article_count':1,'lines':[{'id':'0','description':'HUEVOS 12 UDS','count':1,'unit_price':3,'amount':3,'ean':'1234567890128','reference_id':'egg12','pack_quantity':None,'pack_unit':''}]}
    draft=await manager._prepare_preview(receipt,'owner')
    await manager.async_link(draft['token'],'owner',[{'id':'0','product_id':product['id']}])
    refs=catalog.products[0]['commercial_references']
    assert len(refs)==1 and refs[0]['content_quantity']==12 and not refs[0]['content_confirmed']
    assert stock.snapshot['items']==[]
    saved=await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':True,'pack_quantity':12,'pack_unit':'uds'}],True)
    product=catalog.products[0]
    assert product['commercial_references'][0]['content_confirmed']
    assert product['unit_quantity']==250 and stock.snapshot['items']==[]
    offer=manager.offers_for(product)[0]
    assert offer['price']==3 and offer['pack_quantity']==12 and not offer['format_pending']
    edited={key:value for key,value in product.items() if key in FIELDS}
    edited['commercial_references'][0]['content_quantity']=6
    edited['commercial_references'][0]['brand']='Granja'
    await catalog.async_save_product(edited)
    restored=Catalog(hass);await restored.async_load()
    assert restored.products[0]['commercial_references'][0]['content_quantity']==6
    assert restored.products[0]['commercial_references'][0]['brand']=='Granja'
    history=PriceHistory(hass)
    comparison=history.comparison_data(restored,SimpleNamespace(snapshot={'stores':{'lidl':{'enabled':True}}}),manager,[])
    assert comparison['observations'][0]['pack_quantity']==6
    assert comparison['purchases'][0]['lines'][0]['pack_quantity']==6
    assert saved['lines'][0]['count']==1 and saved['total']==3


async def test_reference_migration_is_conservative_idempotent_and_preserves_all_formats(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Huevos'})
    catalog._products[product['id']].pop('commercial_references')
    data={'history':{'a':{'store':'lidl','lines':[{'product_id':product['id'],'description':'HUEVOS 6 UDS','reference_id':'six'}]},
                     'b':{'store':'lidl','lines':[{'product_id':product['id'],'description':'HUEVOS 12 UDS','reference_id':'twelve'}]}},'aliases':{}}
    await catalog.async_migrate_references(data)
    references=catalog.products[0]['commercial_references']
    assert len(references)==2 and {r['content_quantity'] for r in references}=={6,12}
    assert all(not r['content_confirmed'] for r in references)
    revision=catalog.products[0]['revision']
    await catalog.async_migrate_references(data)
    assert catalog.products[0]['revision']==revision


async def test_receipt_contents_are_per_ean_including_multipacks_not_purchase_count(hass):
    catalog=Catalog(hass);await catalog.async_load()
    coffee=await catalog.async_save_product({'name':'Café'})
    drink=await catalog.async_save_product({'name':'Bebida'})
    stock=StockManager(hass,catalog);await stock.async_load()
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=SimpleNamespace(snapshot={'primary_entity':'todo.main'}))
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    receipt={'id':'formats','digest':'formats','store':'carrefour','store_name':'Carrefour','currency':'EUR','purchased_at':dt_util.now().isoformat(),
        'total':28,'subtotal':28,'discount':0,'article_count':5,'lines':[
        {'id':'0','description':'CAFE 500 G','count':2,'unit_price':5,'amount':10,'ean':'3017620422003','pack_quantity':500,'pack_unit':'g'},
        {'id':'1','description':'PACK 6 X 330 ML','count':3,'unit_price':6,'amount':18,'ean':'4006381333931','pack_quantity':330,'pack_unit':'ml'}]}
    draft=await manager._prepare_preview(receipt,'owner')
    assert [(line['pack_quantity'],line['pack_unit']) for line in draft['receipt']['lines']]==[(500,'g'),(1980,'ml')]
    saved=await manager.async_confirm(draft['token'],'owner',[
        {'id':'0','product_id':coffee['id'],'replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':True,'pack_quantity':500,'pack_unit':'g'},
        {'id':'1','product_id':drink['id'],'replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':True,'pack_quantity':1980,'pack_unit':'ml'}],True)
    by_id={product['id']:product for product in catalog.products}
    for product,quantity,price in [(by_id[coffee['id']],500,5),(by_id[drink['id']],1980,6)]:
        offer=manager.offers_for(product)[0]
        assert offer['pack_quantity']==quantity and offer['price']==price
        assert product['commercial_references'][0]['content_quantity']==quantity
    assert [line['count'] for line in saved['lines']]==[2,3] and stock.snapshot['items']==[]


async def test_reprocess_restores_ticket_price_without_web_or_package_and_preserves_newer_price(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({'name':'Producto Lidl'})
    stock=StockManager(hass,catalog);await stock.async_load()
    settings=SimpleNamespace(snapshot={'primary_entity':'todo.main','price_updates_enabled':True})
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=settings)
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    receipt={'id':'reprocess-price','digest':'reprocess-price','store':'lidl','store_name':'Lidl','currency':'EUR','purchased_at':'2026-10-01T12:00:00+02:00',
        'total':4,'subtotal':4,'discount':0,'article_count':2,'lines':[{'id':'0','description':'PRODUCTO','count':2,'unit_price':2,'amount':4,'ean':'','reference_id':'12345','pack_quantity':None,'pack_unit':''}]}
    draft=await manager._prepare_preview(receipt,'owner')
    saved=await manager.async_confirm(draft['token'],'owner',[{'id':'0','product_id':product['id'],'replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':False,'pack_quantity':None,'pack_unit':''}],True)
    assert not saved['lines'][0]['price_saved'] and not manager.offers_for(catalog.products[0])
    preview=await manager.async_review_saved(saved['id'],'owner')
    result=await manager.async_reprocess(preview['token'],'owner',[{'id':'0','pack_quantity':None,'pack_unit':''}])
    ref=catalog.products[0]['commercial_references'][0]
    assert ref['reference_id']=='12345' and ref['last_price']['price']==2
    assert ref['last_price']['checked_at']==dt_util.parse_datetime(receipt['purchased_at']).timestamp()
    assert ref['content_quantity'] is None and not ref['url']
    assert result['lines'][0]['price_saved'] and manager.offers_for(catalog.products[0])[0]['price']==2
    assert stock.snapshot['items']==[] and len(stock.receipts['history'])==1
    edited={key:value for key,value in catalog.products[0].items() if key in FIELDS}
    edited['commercial_references'][0]['last_price']={'price':3,'currency':'EUR','checked_at':dt_util.parse_datetime('2026-10-02T12:00:00+02:00').timestamp()}
    await catalog.async_save_product(edited)
    preview=await manager.async_review_saved(saved['id'],'owner')
    await manager.async_reprocess(preview['token'],'owner',[{'id':'0','pack_quantity':6,'pack_unit':'uds'}])
    restored=Catalog(hass);await restored.async_load()
    ref=restored.products[0]['commercial_references'][0]
    assert ref['last_price']['price']==3 and ref['content_quantity']==6 and ref['content_confirmed']
    settings.snapshot['price_updates_enabled']=False
    edited={key:value for key,value in catalog.products[0].items() if key in FIELDS}
    del edited['commercial_references'][0]['last_price']
    await catalog.async_save_product(edited)
    preview=await manager.async_review_saved(saved['id'],'owner')
    await manager.async_reprocess(preview['token'],'owner',[{'id':'0','pack_quantity':6,'pack_unit':'uds'}])
    assert 'last_price' not in catalog.products[0]['commercial_references'][0]


async def test_reprocess_keeps_all_lines_and_can_bind_a_previously_ignored_weighted_item(hass):
    from copy import deepcopy
    catalog=Catalog(hass);await catalog.async_load()
    bread=await catalog.async_save_product({'name':'Pan'})
    tomato=await catalog.async_save_product({'name':'Tomate'})
    stock=StockManager(hass,catalog);await stock.async_load()
    settings=SimpleNamespace(snapshot={'primary_entity':'todo.main','price_updates_enabled':True})
    automation=SimpleNamespace(_lock=asyncio.Lock(),async_check=AsyncMock(),_snapshots={},settings=settings)
    manager=ReceiptManager(hass,stock,automation,SimpleNamespace(_notify=lambda:None))
    at=dt_util.now().isoformat()
    receipt={'id':'all-lines','digest':'all-lines','identity':'original-ticket','account_key':manager._account_key('original-ticket','lidl'),'store':'lidl','store_name':'Lidl','currency':'EUR','purchased_at':at,
        'total':2.83,'subtotal':2.83,'discount':0,'article_count':2,'lines':[
        {'id':'0','description':'PAN','count':1,'unit_price':1,'amount':1,'ean':'','reference_id':'12345','pack_quantity':None,'pack_unit':''},
        {'id':'1','description':'TOMATE SWEET','count':1,'unit_price':1.83,'amount':1.83,'ean':'','reference_id':'83695','pack_quantity':.464,'pack_unit':'kg'}]}
    draft=await manager._prepare_preview(receipt,'owner')
    saved=await manager.async_confirm(draft['token'],'owner',[
        {'id':'0','product_id':bread['id'],'replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':True,'pack_quantity':None,'pack_unit':''},
        {'id':'1','product_id':'','replenish':False,'quantity':None,'unit':'uds','purchase_id':'','save_price':False,'pack_quantity':None,'pack_unit':''}],True)
    original=deepcopy(stock.receipts)
    fresh=deepcopy(receipt)
    fresh['lines'][1].update(pack_quantity=None,pack_unit='',purchased_quantity=.464,purchased_unit='kg',quantity_estimated=False,
        ticket_measure_price={'price':3.95,'quantity':1,'unit':'kg','currency':'EUR','checked_at':dt_util.parse_datetime(at).timestamp(),'source':'ticket'})
    manager.lidl_account=SimpleNamespace(status=lambda owner:{'connected':True},async_reprocess_receipt=AsyncMock(return_value=fresh))
    preview=await manager.async_review_saved(saved['id'],'owner')
    assert len(preview['receipt']['lines'])==2 and preview['receipt']['lines'][1]['purchased_quantity']==.464
    assert stock.receipts==original
    result=await manager.async_reprocess(preview['token'],'owner',[
        {'id':'0','product_id':bread['id'],'pack_quantity':None,'pack_unit':''},
        {'id':'1','product_id':tomato['id'],'pack_quantity':None,'pack_unit':''}])
    ref=next(p for p in catalog.products if p['id']==tomato['id'])['commercial_references'][0]
    assert ref['measure_price']['price']==3.95 and ref['measure_price']['unit']=='kg'
    assert ref['content_quantity'] is None and not ref['content_confirmed']
    assert result['lines'][1]['product_id']==tomato['id'] and result['lines'][1]['purchased_quantity']==.464
    assert len(stock.receipts['history'])==1 and stock.snapshot['items']==[]
    assert stock.receipts['purchases']==original['purchases']
    manager.lidl_account.async_reprocess_receipt=AsyncMock(side_effect=CatalogError('Sin conexión'))
    preview=await manager.async_review_saved(saved['id'],'owner')
    assert preview['warning'] and len(preview['receipt']['lines'])==2
