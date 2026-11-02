"""Linear perishable estimates use one baseline across reads and mutations."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.improved_shopping_list import stock as module
from custom_components.improved_shopping_list.stock import StockManager, DEFAULT_CONFIG, DAY, remaining_quantity, remaining_percentage, stock_needs_reorder


class StockDecayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock=1800000000.0
        self.patch=patch.object(module,"time",SimpleNamespace(time=lambda:self.clock));self.patch.start();self.addCleanup(self.patch.stop)
        self.item={**DEFAULT_CONFIG,"id":"pavo","name":"Pavo","catalog_product_id":"","quantity":250,"unit":"g","refill_quantity":250,"mode":"perishable","configured":True,"days":7,"expires_at":self.clock+7*DAY,"revision":1,"quantity_at":self.clock,"reorder_enabled":True,"reorder_percent":20}
        self.stock=StockManager.__new__(StockManager)
        self.stock._items={"pavo":deepcopy(self.item)};self.stock.catalog=SimpleNamespace(products=[])
        self.stock.receipts={"history":{},"aliases":{},"purchases":{},"coverage":{}}
        self.stock._lock=asyncio.Lock();self.stock.activity=None;self.stock.recurrence_coordinated=False
        self.stock._store=SimpleNamespace(async_save=AsyncMock())
        self.stock._listeners=set()

    async def test_quantity_percentage_and_threshold_decrease_together(self):
        self.clock+=DAY
        item=self.stock.snapshot["items"][0]
        self.assertEqual(item["quantity"],214.286)
        self.assertAlmostEqual(remaining_percentage(item),85.7144)
        self.assertEqual(self.stock._items["pavo"]["quantity"],250)
        self.assertFalse(stock_needs_reorder(item))
        self.clock+=4.6*DAY
        self.assertEqual(self.stock.snapshot["items"][0]["quantity"],50)
        self.assertTrue(stock_needs_reorder(self.stock.snapshot["items"][0]))
        self.clock+=2*DAY
        self.assertEqual(self.stock.snapshot["items"][0]["quantity"],0)

    async def test_legacy_records_and_restart_do_not_double_subtract(self):
        self.stock._items["pavo"].pop("quantity_at")
        self.clock+=3.5*DAY
        self.assertEqual(self.stock.snapshot["items"][0]["quantity"],125)
        restored=StockManager.__new__(StockManager);restored.receipts=deepcopy(self.stock.receipts);restored.catalog=self.stock.catalog
        restored._store=SimpleNamespace(async_load=AsyncMock(return_value={"items":deepcopy(self.stock._items)}))
        await restored.async_load()
        self.assertEqual(restored.snapshot["items"][0]["quantity"],125)
        self.assertEqual(restored.snapshot["items"][0]["quantity"],125)

    async def test_unedited_quantity_keeps_original_expiry_when_saving(self):
        self.clock+=DAY
        opened=self.stock.snapshot["items"][0]
        fields=("quantity","unit","mode","days","refill_quantity","reorder_enabled","reorder_at","reorder_percent","list_entity","usage_entity","usage_state","usage_amount")
        config={key:opened[key] for key in fields};config["quantity_changed"]=False
        self.clock+=DAY
        saved=await self.stock.async_save("pavo",1,config)
        self.assertEqual(saved["expires_at"],self.item["expires_at"])
        self.assertEqual(saved["quantity"],178.571)
        self.clock+=DAY
        self.assertAlmostEqual(self.stock.snapshot["items"][0]["quantity"],142.857,places=3)

    async def test_manual_adjustment_and_replenishment_start_from_remaining_quantity(self):
        self.clock+=3.5*DAY
        saved=await self.stock.async_adjust("pavo",-1)
        self.assertEqual(saved["quantity"],124)
        self.assertEqual(saved["expires_at"],self.item["expires_at"])
        self.clock+=1.75*DAY
        self.assertEqual(self.stock.snapshot["items"][0]["quantity"],62)
        waiting=deepcopy(self.stock._items['pavo'])
        self.assertIsNone(await self.stock.async_automatic("pavo",0,"purchase"))
        self.assertEqual(self.stock._items['pavo'],waiting)
        opened=self.stock.snapshot['items'][0]
        fields=('quantity','unit','mode','days','refill_quantity','reorder_enabled','reorder_at','reorder_percent','list_entity','usage_entity','usage_state','usage_amount')
        config={key:opened[key] for key in fields};config['quantity']=opened['quantity']+250
        bought=await self.stock.async_save('pavo',opened['revision'],config)
        self.assertEqual(bought["quantity"],312)
        self.assertEqual(bought["expires_at"],self.clock+7*DAY)
        self.clock+=3.5*DAY
        self.assertEqual(self.stock.snapshot["items"][0]["quantity"],156)

    async def test_manual_and_registered_usage_do_not_decay_with_time(self):
        for mode in ("manual","usage"):
            item={**self.item,"mode":mode}
            self.assertEqual(remaining_quantity(item,self.clock+100*DAY),250)
            self.assertEqual(remaining_percentage(item,self.clock+100*DAY),100)


    async def test_replenishment_total_is_full_reference_and_defaults_do_not_change_it(self):
        self.clock+=3.5*DAY
        opened=self.stock.snapshot['items'][0]
        fields=('quantity','unit','mode','days','refill_quantity','reorder_enabled','reorder_at','reorder_percent','list_entity','usage_entity','usage_state','usage_amount')
        config={key:opened[key] for key in fields};config.update(quantity=325,quantity_changed=True)
        saved=await self.stock.async_save('pavo',opened['revision'],config)
        self.assertEqual(saved['full_quantity'],325)
        self.assertEqual(remaining_percentage(saved,self.clock),100)
        self.clock+=3.5*DAY
        self.assertEqual(self.stock.snapshot['items'][0]['quantity'],162.5)
        self.assertEqual(remaining_percentage(self.stock.snapshot['items'][0],self.clock),50)
        config={key:self.stock.snapshot['items'][0][key] for key in fields};config.update(refill_quantity=900,quantity_changed=False)
        saved=await self.stock.async_save('pavo',saved['revision'],config)
        self.assertEqual(saved['full_quantity'],325)
        self.assertEqual(remaining_percentage(saved,self.clock),50)
        restored=StockManager.__new__(StockManager);restored.receipts=deepcopy(self.stock.receipts);restored.catalog=self.stock.catalog
        restored._store=SimpleNamespace(async_load=AsyncMock(return_value={'items':deepcopy(self.stock._items)}))
        await restored.async_load()
        self.assertEqual(remaining_percentage(restored.snapshot['items'][0],self.clock),50)

    async def test_reader_addition_resets_full_reference_but_consumption_keeps_it(self):
        self.stock._items['pavo'].update(mode='manual',quantity=50,full_quantity=100,refill_quantity=250)
        saved=await self.stock.async_adjust('pavo',1)
        self.assertEqual(saved['full_quantity'],51)
        self.assertEqual(remaining_percentage(saved),100)
        saved=await self.stock.async_adjust('pavo',-1)
        self.assertEqual(saved['full_quantity'],51)
        self.assertAlmostEqual(remaining_percentage(saved),50/51*100)
