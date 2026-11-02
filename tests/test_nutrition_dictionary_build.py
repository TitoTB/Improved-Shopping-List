"""Public nutrition metadata stays separate from prices and private catalog data."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import time
import unittest
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nutrition_updater_unit',ROOT/'scripts/update-ean-nutrition.py')
updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)
builder=updater.builder
from ean_common import validate_nutrition, nutrition_from_hint
EAN='08410199023094'


def entry():return {'source':'openfoodfacts','license':'ODbL-1.0','checked_at':int(time.time()),'nutriscore':{'grade':'b','version':'2023'},'nova':3}


class NutritionDictionaryBuildTests(unittest.TestCase):
    def test_validation_rejects_inferred_data_untrusted_sources_and_invalid_values(self):
        self.assertEqual(validate_nutrition(entry()),entry())
        for changed in ({'source':'unknown'},{'checked_at':float('nan')},{'checked_at':time.time()+2*86400},{'nova':True},{'nutriscore':{'grade':'unknown'}},{'nutriscore':{'grade':'a','version':'unknown'}},{'price':1}):
            with self.assertRaises(ValueError):validate_nutrition({**entry(),**changed})
        self.assertEqual(nutrition_from_hint({},time.time()),{})

    def test_off_payload_requires_exact_ean_and_never_guesses_missing_classifications(self):
        payload={'product':{'code':'8410199023094','nutriscore_grade':'b','nutriscore_version':'2023','nova_group':3}}
        self.assertEqual(updater.classify(payload,EAN,time.time())['nova'],3)
        with self.assertRaises(ValueError):updater.classify(payload,'03017620422003',time.time())
        self.assertEqual(updater.classify({'product':{'code':'8410199023094'}},EAN,time.time()),{})

    def test_import_round_trip_preserves_old_format_schema_and_omits_private_fields(self):
        export={'kind':'improved-shopping-list-catalog-export','products':[{'name':'PRIVATE','commercial_references':[{'store':'carrefour','ean':'8410199023094','brand':'Marca'}]}],'nutrition':{EAN:entry()}}
        seed=builder.import_catalog(export);result=builder.build(seed,{'common':{}})
        self.assertEqual(result['nutrition'][EAN],entry());self.assertEqual(result['schema_version'],1)
        self.assertEqual(result['products'][EAN],{'brand':'Marca','origins':['carrefour']})
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual(seed,builder.import_catalog(export,seed))
        newer=deepcopy(export);newer['nutrition'][EAN]['checked_at']-=10
        self.assertEqual(builder.import_catalog(newer,seed)['nutrition'][EAN],entry())
        self.assertNotEqual(builder.build({'products':seed['products']},{'common':{}})['revision'],result['revision'])

    def test_refresh_is_bounded_rate_limited_and_negatively_cached(self):
        now=time.time();calls=[];pauses=[]
        def fetch(code):calls.append(code);return {'product':{'code':code,'nutriscore_grade':'a','nova_group':1}}
        data,summary=updater.refresh({'products':{EAN:[], '03017620422003':[]}}, {},limit=1,fetch=fetch,wait=pauses.append,clock=lambda:now)
        self.assertEqual(summary['requests'],1);self.assertEqual(len(calls),1);self.assertFalse(pauses)
        saved,summary=updater.refresh({'products':{calls[0]:[]}},data,fetch=fetch,wait=pauses.append,clock=lambda:now+10)
        self.assertEqual(summary['requests'],0)
        absent,summary=updater.refresh({'products':{EAN:[]}}, {},fetch=lambda _: {},clock=lambda:now)
        self.assertEqual(updater.refresh({'products':{EAN:[]}},absent,fetch=fetch,clock=lambda:now+10)[1]['requests'],0)
        codes={'products':{EAN:[], '03017620422003':[]}}
        updater.refresh(codes,{},fetch=fetch,wait=pauses.append,clock=lambda:now)
        self.assertEqual(pauses,[4.2])
        with self.assertRaises(ValueError):updater.refresh(codes,{},interval=1)

    def test_block_stops_batch_without_losing_previous_results(self):
        saved={'nutrition':{EAN:entry()},'attempts':{}}
        def blocked(_):raise HTTPError('https://world.openfoodfacts.org',429,'Limited',{},None)
        result,summary=updater.refresh({'products':{'03017620422003':[]}},saved,fetch=blocked)
        self.assertEqual(result['nutrition'][EAN],saved['nutrition'][EAN]);self.assertIn('429',summary['error'])
