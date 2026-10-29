"""Commercial references persist through receipts, editing and restart."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util
from custom_components.improved_shopping_list.catalog import Catalog, FIELDS
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
    await catalog.async_save_product(edited)
    restored=Catalog(hass);await restored.async_load()
    assert restored.products[0]['commercial_references'][0]['content_quantity']==6
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
