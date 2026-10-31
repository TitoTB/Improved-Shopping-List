"""Receipt enrichment distinguishes temporary shop pauses from missing data."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("receipt_pause",Path(__file__).parents[1]/"custom_components/improved_shopping_list/receipt_quantities.py")
quantities=importlib.util.module_from_spec(spec);spec.loader.exec_module(quantities)


class LookupPauseTests(unittest.TestCase):
    def test_only_compatible_stock_units_are_summed(self):
        self.assertEqual(quantities.stock_quantity(.5,'kg','g'),500)
        self.assertEqual(quantities.stock_quantity(500,'g','kg'),.5)
        self.assertEqual(quantities.stock_quantity(2,'l','ml'),2000)
        self.assertEqual(quantities.stock_quantity(2,'Latas','latas'),2)
        self.assertIsNone(quantities.stock_quantity(1,'g','uds'))
        self.assertIsNone(quantities.stock_quantity(1,'kg','l'))
    def test_denials_and_retry_pauses_stop_enrichment(self):
        for diagnostics in ({"http_status":403},{"http_status":429},{"http_status":503},
                            {"response_class":"rate_limited"},{"retry_seconds":900},
                            {"attempts":[{"stage":"product_page","http_status":403}]}):
            with self.subTest(diagnostics=diagnostics):
                self.assertTrue(quantities.lookup_paused(diagnostics))

    def test_missing_product_or_format_is_not_a_shop_pause(self):
        for diagnostics in (None,{}, {"http_status":404},{"response_class":"structured_product_missing"},
                            {"retry_seconds":0},{"attempts":[{"response_class":"no_offer"}]}):
            with self.subTest(diagnostics=diagnostics):
                self.assertFalse(quantities.lookup_paused(diagnostics))
