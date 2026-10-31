"""The published EAN dictionary contains facts only, not users' catalogs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('common_builder_unit',ROOT/'scripts/build-ean-common.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class CommonEANBuildTests(unittest.TestCase):
    def test_import_omits_private_fields_prices_and_unconfirmed_content(self):
        export={'kind':'improved-shopping-list-catalog-export','products':[{'name':'PRIVATE','image_url':'PRIVATE','notes':'PRIVATE','commercial_references':[
            {'store':'carrefour','ean':'8410199023094','brand':'Marca','content_quantity':500,'content_unit':'g','content_confirmed':True,'pack_count':6,'last_price':{'price':99}},
            {'store':'alcampo','ean':'8410199023094','brand':'marca','content_quantity':.5,'content_unit':'kg','content_confirmed':True,'pack_count':6},
            {'store':'lidl','ean':'8410199023094','content_quantity':999,'content_unit':'g','content_confirmed':False}]}]}
        seed=builder.import_catalog(export);index=builder.build(seed,{'common':{}})
        self.assertEqual(seed,builder.import_catalog(export,seed))
        raw=json.dumps(index);self.assertNotIn('PRIVATE',raw);self.assertNotIn('price',raw);self.assertNotIn('999',raw)
        row=index['products']['08410199023094']
        self.assertEqual(row['content_quantity'],.5);self.assertEqual(set(row['origins']),{'carrefour','alcampo'})
        conflicting=deepcopy(seed);conflicting['products']['08410199023094'].append({'store':'consum','content_quantity':1,'content_unit':'kg'})
        row=builder.build(conflicting,{'common':{}})['products']['08410199023094']
        self.assertNotIn('content_quantity',row);self.assertIn('content',row['conflicts']);self.assertEqual(row['pack_count'],6)

    def test_weight_mode_does_not_publish_a_fixed_package(self):
        export={'kind':'improved-shopping-list-catalog-export','products':[{'commercial_references':[{'store':'carrefour','ean':'8410199023094','brand':'Marca','sale_mode':'weight','content_quantity':500,'content_unit':'g','pack_count':6,'content_confirmed':True}]}]}
        row=builder.import_catalog(export)['products']['08410199023094'][0]
        self.assertEqual(row,{'store':'carrefour','brand':'Marca'})

    def test_current_files_match_their_inputs_and_have_other_shop_data(self):
        seed=json.loads((ROOT/'data/ean-common-contributions.json').read_text(encoding='utf-8'))
        mercadona=json.loads((ROOT/'data/mercadona-index.json').read_text(encoding='utf-8'))
        published=json.loads((ROOT/'data/ean-common.json').read_text(encoding='utf-8'))
        built=builder.build(seed,mercadona)
        self.assertEqual(built['products'],published['products']);self.assertEqual(built['revision'],published['revision'])
        self.assertGreater(len(published['products']),4000)
        self.assertTrue(any('carrefour' in row['origins'] for row in published['products'].values()))
