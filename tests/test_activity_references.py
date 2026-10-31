"""Option enrichment is one update, even when its generated identity changes."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).parents[1]/"custom_components/improved_shopping_list"
PACKAGE="_activity_reference_tests"
package=types.ModuleType(PACKAGE);package.__path__=[str(ROOT)];sys.modules[PACKAGE]=package
spec=importlib.util.spec_from_file_location(PACKAGE+".activity_references",ROOT/"activity_references.py")
activity=importlib.util.module_from_spec(spec);spec.loader.exec_module(activity)


class ReferenceActivityTests(unittest.TestCase):
    def test_enriching_fuet_logs_only_new_reference_and_url(self):
        old={"store":"carrefour","name":"Fuet","ean":"8410762005014","brand":"Marca","content_quantity":150,"content_unit":"g"}
        old["id"]=activity.reference_key(old["store"],old)
        new={**old,"reference_id":"R-fuet","url":"https://www.carrefour.es/supermercado/fuet/R-fuet/p"}
        new["id"]=activity.reference_key(new["store"],new)
        before,after=deepcopy(old),deepcopy(new)
        changes=activity.reference_changes([old],[new])
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["action"],"updated")
        self.assertEqual(changes[0]["added_fields"],["reference_id","url"])
        self.assertEqual(changes[0]["updated_fields"],[])
        self.assertEqual(changes[0]["removed_fields"],[])
        self.assertEqual((old,new),(before,after))

    def test_exact_ean_pairing_accepts_zero_padding_and_keeps_real_changes(self):
        old={"id":"old","store":"carrefour","ean":"8410762005014","brand":"Anterior","name":"Fuet"}
        new={**old,"id":"new","ean":"08410762005014","brand":"Nueva","url":"https://example.test/fuet"}
        change=activity.reference_changes([old],[new])[0]
        self.assertEqual(change["action"],"updated")
        self.assertEqual(change["updated_fields"],["ean","brand"])

    def test_different_shops_and_different_eans_are_still_removal_and_addition(self):
        old={"id":"old","store":"carrefour","ean":"8410762005014","name":"Fuet"}
        for new in ({**old,"id":"new","store":"alcampo"},{**old,"id":"new","ean":"8410199023094"}):
            self.assertEqual([c["action"] for c in activity.reference_changes([old],[new])],["removed","added"])

    def test_ambiguous_options_are_not_guessed_and_stable_ids_are_matched_first(self):
        base={"store":"carrefour","ean":"8410762005014","name":"Fuet"}
        old=[{**base,"id":"a"},{**base,"id":"b"}]
        new=[{**base,"id":"c"},{**base,"id":"d"}]
        self.assertEqual([c["action"] for c in activity.reference_changes(old,new)],["removed","removed","added","added"])
        changes=activity.reference_changes(old,[old[0],{**base,"id":"c","url":"https://example.test/fuet"}])
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["action"],"updated")
        self.assertEqual(changes[0]["added_fields"],["url"])

    def test_check_dates_and_reordering_do_not_create_changes(self):
        old=[{"id":"a","store":"carrefour","ean":"8410762005014","last_price":{"price":2,"currency":"EUR","checked_at":1}},
             {"id":"b","store":"alcampo","ean":"8410762005014"}]
        new=deepcopy(old);new[0]["last_price"]["checked_at"]=2;new.reverse()
        self.assertEqual(activity.reference_changes(old,new),[])
