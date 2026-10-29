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
    def test_distinct_packs_remain_separate_and_confirmed_content_survives_later_tickets(self):
        values=[]
        small={"description":"HUEVOS 6 UDS","ean":"4006381333931","brand":"Granja"}
        large={"description":"HUEVOS 12 UDS","ean":"1234567890128"}
        refs.merge_reference(values,"lidl",small,confirmed=True)
        refs.merge_reference(values,"lidl",large,confirmed=True)
        self.assertEqual([ref["content_quantity"] for ref in values],[6,12])
        refs.merge_reference(values,"lidl",{**small,"description":"HUEVOS","brand":""})
        found=refs.matching_reference({"commercial_references":values},"lidl",small)
        self.assertTrue(found["content_confirmed"])
        self.assertEqual(found["content_quantity"],6)
        self.assertEqual(found["brand"],"Granja")
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
