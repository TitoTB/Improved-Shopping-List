"""Unconfirmed estimates survive reopening, while changed inputs invalidate them."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]/'custom_components/improved_shopping_list'
package=types.ModuleType('_estimate_tests');package.__path__=[str(ROOT)];sys.modules[package.__name__]=package
spec=importlib.util.spec_from_file_location('_estimate_tests.receipt_estimates',ROOT/'receipt_estimates.py')
cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)


class MemoryStore:
    def __init__(self):self.data={}
    async def async_load(self):return deepcopy(self.data)
    async def async_save(self,data):self.data=deepcopy(data)


class EstimateKeys(unittest.TestCase):
    def test_only_matching_purchase_line_product_and_rate_are_reused(self):
        receipt={'id':'ticket','digest':'digest','store':'carrefour','total':2.5}
        line={'id':'0','amount':2.5,'count':1};ref={'ean':'8410199023094','url':'https://example.test/product'}
        rate={'price':5,'quantity':1,'unit':'kg','currency':'EUR','checked_at':1}
        key=cache.estimate_key(receipt,line,'p',ref,rate)
        self.assertEqual(key,cache.estimate_key(receipt,line,'p',ref,{**rate,'checked_at':999}))
        for args in (({**receipt,'id':'another'},line,'p',ref,rate),(receipt,{**line,'amount':5},'p',ref,rate),
                     (receipt,line,'another',ref,rate),(receipt,line,'p',{**ref,'url':'https://example.test/other'},rate),
                     (receipt,line,'p',ref,{**rate,'price':6})):
            self.assertNotEqual(key,cache.estimate_key(*args))
        self.assertIsNone(cache.estimate_key(receipt,line,'p',ref,None))


class EstimateStorage(unittest.IsolatedAsyncioTestCase):
    async def test_persist_and_restore_with_expiry(self):
        store=MemoryStore();result={'quantity':.5,'unit':'kg','estimated':True};key='a'*64
        with patch.object(cache,'time',types.SimpleNamespace(time=lambda:1800000000)):
            first=cache.ReceiptEstimates(None,store=store);await first.put(key,result)
            restored=cache.ReceiptEstimates(None,store=store)
            self.assertEqual(await restored.get(key),result)
            copy=await restored.get(key);copy['quantity']=999
            self.assertEqual(await restored.get(key),result)
        with patch.object(cache,'time',types.SimpleNamespace(time=lambda:1800000000+cache.TTL+1)):
            self.assertIsNone(await restored.get(key))

    async def test_cache_is_bounded_and_rejects_invalid_proposals(self):
        store=MemoryStore();saved=cache.ReceiptEstimates(None,store=store)
        with patch.object(cache,'LIMIT',2):
            for key in ('a','b','c'):await saved.put(key*64,{'quantity':1,'unit':'kg','estimated':True})
            self.assertIsNone(await saved.get('a'*64));self.assertEqual(len(store.data),2)
        for result in ({'quantity':float('nan'),'unit':'kg','estimated':True},{'quantity':1,'unit':'invalid','estimated':True}):
            await saved.put('d'*64,result)
            self.assertIsNone(await saved.get('d'*64))
