"""Package identity, review and costing; runnable without Home Assistant."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).parents[1]/"custom_components/improved_shopping_list"
PACKAGE="_reference_tests"
package=types.ModuleType(PACKAGE);package.__path__=[str(ROOT)];sys.modules[PACKAGE]=package
spec=importlib.util.spec_from_file_location(PACKAGE+".product_references",ROOT/"product_references.py")
refs=importlib.util.module_from_spec(spec);spec.loader.exec_module(refs)


class ReferenceTests(unittest.TestCase):
    def test_explicit_sale_mode_preserves_package_and_weight_choices(self):
        base={'store':'carrefour','ean':'8410199023094','name':'Alternativa','content_quantity':None,'content_unit':'g','content_confirmed':False}
        package=refs.normalized_references([{**base,'sale_mode':'package'}])[0]
        self.assertFalse(package['content_confirmed'])
        self.assertFalse(refs.weight_format(package))
        weight=refs.normalized_references([{**base,'sale_mode':'weight','content_quantity':500,'pack_count':6}])[0]
        self.assertTrue(weight['content_confirmed']);self.assertIsNone(weight['content_quantity']);self.assertNotIn('pack_count',weight)
        self.assertEqual(refs.normalized_references([weight])[0],weight)
        for option in ({**base,'sale_mode':'invalid'},{**base,'sale_mode':'weight','content_unit':'uds'}):
            with self.assertRaises(ValueError):refs.normalized_references([option])
        values=refs.normalized_references([{**base,'sale_mode':'package','content_quantity':500,'content_confirmed':True}])
        refs.merge_reference(values,'carrefour',{'ean':base['ean'],'description':'Producto','count':1,'unit_price':2,'amount':2},confirmed=False)
        self.assertEqual(values[0]['sale_mode'],'package');self.assertEqual(values[0]['content_quantity'],500)

    def test_partial_optional_package_fields_persist_without_confirming_a_format(self):
        for quantity, unit in [(None, ''), (250, ''), (None, 'uds')]:
            with self.subTest(quantity=quantity, unit=unit):
                raw={'store':'carrefour','ean':'8410199023094','content_quantity':quantity,'content_unit':unit,'content_confirmed':False}
                saved=refs.normalized_references([raw])[0]
                self.assertEqual((saved['content_quantity'],saved['content_unit']),(quantity,unit))
                self.assertFalse(saved['content_confirmed'])
                self.assertNotIn('pack_count',saved)
                self.assertEqual(refs.normalized_references([saved])[0],saved)
                with self.assertRaises(ValueError):
                    refs.normalized_references([{**raw,'content_confirmed':True}])
        for quantity,unit in [(0,''),(-1,''),(True,''),(250,'boxes'),(None,[])]:
            with self.assertRaises(ValueError):
                refs.normalized_references([{'store':'carrefour','ean':'8410199023094','content_quantity':quantity,'content_unit':unit}])

    def test_weight_unit_confirms_a_variable_format_and_receipts_keep_the_rate(self):
        from _reference_tests.receipt_quantities import price_from_option, estimated_quantity, receipt_catalog_price
        for unit in ('g','kg'):
            values=refs.normalized_references([{'store':'carrefour','ean':'8410199023094','content_quantity':None,'content_unit':unit,
                'content_confirmed':False,'last_price':{'price':10,'currency':'EUR','checked_at':100}}])
            self.assertTrue(values[0]['content_confirmed'])
            price=price_from_option(values[0]);self.assertEqual((price['price'],price['unit']),(10,'kg'))
            self.assertEqual(estimated_quantity({'amount':2.5},price)['quantity'],.25)
            line={'description':'Fruta al peso','ean':'8410199023094','count':1,'amount':2.5,'unit_price':2.5,
                'purchased_quantity':.25,'purchased_unit':'kg','quantity_estimated':True,'price_saved':True,
                'last_price':{'price':2.5,'currency':'EUR','checked_at':200}}
            self.assertIsNone(receipt_catalog_price(line,values[0]))
            refs.merge_reference(values,'carrefour',line,confirmed=True)
            self.assertEqual(values[0]['last_price']['price'],10)
            self.assertEqual((values[0]['content_quantity'],values[0]['content_unit']),(None,unit))
            self.assertTrue(values[0]['content_confirmed'])
            line.update(quantity_estimated=False, ticket_measure_price={'price':12,'quantity':1,'unit':'kg','currency':'EUR','checked_at':300,'source':'ticket'})
            self.assertEqual(receipt_catalog_price(line,values[0]),12)
            refs.merge_reference(values,'carrefour',line,confirmed=True)
            self.assertEqual(values[0]['last_price']['price'],12)
            self.assertEqual(values[0]['measure_price']['price'],12)
            offer=refs.format_observation({'commercial_references':values},'carrefour',{'ean':line['ean'],'price':12})
            self.assertEqual((offer['pack_quantity'],offer['pack_unit']),(1,'kg'))

    def test_brand_initial_is_uppercase_without_lowercasing_the_rest(self):
        for raw, expected in [("carrefour", "Carrefour"), ("marca API", "Marca API"), ("DIA", "DIA"), (' "nestlé" ', '"Nestlé"'), ("", "")]:
            self.assertEqual(refs.brand_name(raw), expected)

    def test_distinct_packs_remain_separate_and_confirmed_content_survives_later_tickets(self):
        values=[]
        small={"description":"HUEVOS 6 UDS","ean":"4006381333931","brand":"granja","image_url":"https://example.com/eggs.png"}
        large={"description":"HUEVOS 12 UDS","ean":"1234567890128"}
        refs.merge_reference(values,"lidl",small,confirmed=True)
        refs.merge_reference(values,"lidl",large,confirmed=True)
        self.assertEqual([ref["content_quantity"] for ref in values],[6,12])
        refs.merge_reference(values,"lidl",{**small,"description":"HUEVOS","brand":"","image_url":""})
        found=refs.matching_reference({"commercial_references":values},"lidl",small)
        self.assertTrue(found["content_confirmed"])
        self.assertEqual(found["content_quantity"],6)
        self.assertEqual(found["brand"],"Granja")
        self.assertEqual(found["image_url"],small["image_url"])
        self.assertEqual(refs.normalized_references(values)[-1]["image_url"],small["image_url"])
        self.assertEqual(refs.normalized_references(values)[-1]["brand"],"Granja")
        self.assertEqual(len(refs.normalized_references(values)),2)

    def test_pending_content_does_not_borrow_stock_and_corrections_apply_to_observations(self):
        values=[];line={"description":"HUEVOS 12 UDS","reference_id":"egg12","pack_quantity":12,"pack_unit":"uds"}
        refs.merge_reference(values,"lidl",line)
        product={"commercial_references":values,"unit_quantity":250,"refill_quantity":500}
        observed=refs.format_observation(product,"lidl",line)
        self.assertTrue(observed["format_pending"]);self.assertIsNone(observed["pack_quantity"])
        values[0].update(content_confirmed=True,content_quantity=6)
        observed=refs.format_observation(product,"lidl",line)
        self.assertFalse(observed["format_pending"]);self.assertEqual(observed["pack_quantity"],6)

    def test_whole_packages_and_unit_conversions(self):
        self.assertEqual(refs.package_cost({"pack_quantity":12,"pack_unit":"uds","price":3},6,"uds"),3)
        self.assertEqual(refs.package_cost({"pack_quantity":6,"pack_unit":"uds","price":1.8},12,"uds"),3.6)
        self.assertEqual(refs.package_cost({"pack_quantity":1,"pack_unit":"kg","price":6},500,"g"),6)
        self.assertIsNone(refs.package_cost({"pack_quantity":12,"pack_unit":"uds","price":3,"format_pending":True},6,"uds"))
        self.assertIsNone(refs.package_cost({"pack_quantity":12,"pack_unit":"uds","price":3},6,"kg"))

    def test_invalid_and_ambiguous_formats_are_not_accepted(self):
        for image in ['javascript:alert(1)','https://user:password@example.com/a.png','//example.com/a.png']:
            with self.assertRaises(ValueError):refs.normalized_references([{"store":"lidl","reference_id":"eggs","image_url":image}])
        for value,unit in [(float('nan'),'g'),(True,'g'),(-1,'g'),(1.5,'uds'),(6,'boxes')]:
            with self.assertRaises(ValueError):refs.content(value,unit)
        self.assertEqual(refs.inferred_content({"description":"ANACARDO CRUDO 200"}),(None,""))
        self.assertEqual(refs.inferred_content({"description":"HUEVOS 12 UDS"}),(12,'uds'))
        self.assertEqual(refs.inferred_content({"description":"PACK 2 X 6 UDS"}),(12,'uds'))
        with self.assertRaises(ValueError):refs.normalized_references([{"store":"lidl","ean":"invalid"}])
        with self.assertRaises(ValueError):refs.normalized_references([{"store":"lidl","reference_id":"a","url":"https://example.com/a"}])

    def test_unlinking_a_reference_excludes_prices_but_keeps_the_historical_identity(self):
        values=[];line={"description":"HUEVOS 12 UDS","reference_id":"twelve"}
        refs.merge_reference(values,"lidl",line,confirmed=True)
        values[0]["active"]=False
        observation=refs.format_observation({"commercial_references":values},"lidl",line)
        self.assertTrue(observation['reference_excluded'])
        self.assertEqual(observation['description'],line['description'])


if __name__=="__main__":unittest.main()
