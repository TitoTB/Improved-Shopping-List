"""Pure protocol tests also runnable without a Home Assistant installation."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import types
import unittest
import zlib
import base64

package = types.ModuleType("isl_test_protocol")
package.__path__ = [str(Path(__file__).resolve().parents[1]/"custom_components/improved_shopping_list")]
sys.modules[package.__name__] = package
p = importlib.import_module("isl_test_protocol.community_data")
NOW = 1792600000


def item(name="Arroz"):
    return {"name": name, "name_en": "Rice", "eans": ["8410109115543"],
        "store_links": {"mercadona": {"id": "123", "url": "https://tienda.mercadona.es/product/123"}},
        "icons": ["noto:cooked-rice"], "nutriscore": "a", "prices": [
            {"store": "mercadona", "reference_id": "123", "price": "1.25", "currency": "EUR", "checked_at": NOW-60}]}


def payload(product=None):
    return {"schema": 2, "reference_version": 1, "products": [product or item()]}


class CommunityProtocolTests(unittest.TestCase):
    def test_three_independent_accounts_confirm_without_echo_votes(self):
        state = p.new_registry()
        p.contribute(state, payload(), 1, NOW, 1)
        p.contribute(state, payload(item("arroz")), 2, NOW, 2)
        borrowed = item(); borrowed["borrowed_fields"] = ["name", "name_en", "nutriscore", "eans", "icons", "store_links.mercadona"]
        p.contribute(state, payload(borrowed), 3, NOW, 3)
        result = p.compile_dictionary(state, NOW)["products"][0]
        self.assertNotIn("name", result["confirmed_fields"])
        p.contribute(state, payload(), 4, NOW, 4)
        result = p.compile_dictionary(state, NOW)["products"][0]
        self.assertIn("name", result["confirmed_fields"])
        self.assertIn("store_links.mercadona", result["confirmed_fields"])
        self.assertEqual(result["confirmations"]["name"], 3)

    def test_account_limit_is_rolling_persistent_and_not_per_installation(self):
        state = p.new_registry()
        self.assertTrue(p.contribute(state, payload(), 1, NOW, 1))
        self.assertFalse(p.contribute(state, payload(), 1, NOW+1, 2))
        restored = json.loads(json.dumps(state))
        self.assertFalse(p.contribute(restored, payload(), 1, NOW+86399, 3))
        fresh = item(); fresh["prices"][0]["checked_at"] = NOW+86400
        self.assertTrue(p.contribute(restored, payload(fresh), 1, NOW+86400, 4))
        self.assertEqual(len(p.compile_dictionary(restored, NOW+86400)["products"]), 1)

    def test_first_fresh_price_wins_and_download_never_renews_it(self):
        state = p.new_registry()
        p.contribute(state, payload(), 1, NOW, 1)
        other = item(); other["prices"][0]["price"] = "9.99"
        p.contribute(state, payload(other), 2, NOW+1, 2)
        result = p.compile_dictionary(state, NOW+2)
        self.assertEqual(result["products"][0]["prices"][0]["price"], "1.25")
        self.assertEqual(result["products"][0]["prices"][0]["checked_at"], NOW-60)
        self.assertEqual(p.compile_dictionary(state, NOW+86400)["products"][0]["prices"], [])
        self.assertEqual(p.validate_dictionary(result, NOW+86400)["products"][0]["prices"], [])

    def test_ban_withdraws_votes_prices_and_subsequent_contributions(self):
        state = p.new_registry()
        for user in (1, 2, 3): p.contribute(state, payload(), user, NOW, user)
        result = p.compile_dictionary(state, NOW, banned=[1])["products"][0]
        self.assertNotIn("name", result["confirmed_fields"])
        self.assertEqual(result["prices"], [])
        self.assertFalse(p.contribute(state, payload(), 4, NOW, 4, banned=[4]))

    def test_new_accounts_do_not_manufacture_consensus(self):
        state = p.new_registry()
        for user in (1, 2, 3): p.contribute(state, payload(), user, NOW, user, eligible=False)
        self.assertEqual(p.compile_dictionary(state, NOW)["products"][0]["confirmed_fields"], [])

    def test_image_popularity_does_not_invent_license(self):
        state = p.new_registry()
        for user in (1, 2, 3): p.contribute(state, payload(), user, NOW, user)
        self.assertEqual(p.compile_dictionary(state, NOW)["products"][0]["icons"], [])
        info = {"author": "Google", "license": "Apache-2.0", "license_url": "https://www.apache.org/licenses/LICENSE-2.0"}
        result = p.compile_dictionary(state, NOW, icon_metadata={"noto:cooked-rice": info})
        self.assertEqual(result["products"][0]["icons"][0]["confirmations"], 3)
        p.validate_dictionary(result, NOW)

    def test_strict_allowlist_rejects_private_fields_and_foreign_links(self):
        for field in ("nfc_tags", "stock", "notes", "reader_actions", "category", "postal_code", "token"):
            raw = item(); raw[field] = "PRIVATE"
            with self.assertRaises(ValueError): p.validate_product(raw, NOW)
        for address in ("http://127.0.0.1/a", "https://tienda.mercadona.es@evil.test/product/123", "https://tienda.mercadona.es/product/123?token=secret"):
            raw = item(); raw["store_links"]["mercadona"]["url"] = address
            if "?" in address:
                self.assertNotIn("?", p.validate_product(raw, NOW)["store_links"]["mercadona"]["url"])
            else:
                with self.assertRaises(ValueError): p.validate_product(raw, NOW)

    def test_price_reference_currency_dates_and_invalid_amounts(self):
        for field, value in (("reference_id", "456"), ("currency", "USD"), ("price", "NaN"), ("price", "-1"),
                             ("price", "1.123"), ("checked_at", NOW+3600), ("checked_at", NOW-86401)):
            raw = item(); raw["prices"][0][field] = value
            with self.assertRaises(ValueError): p.validate_product(raw, NOW)

    def test_multipart_roundtrip_corruption_and_bounded_decompression(self):
        original = payload()
        manifest, parts = p.pack(original)
        self.assertEqual(p.unpack(manifest, parts), original)
        bad = deepcopy(manifest); bad["digest"] = "0"*64
        with self.assertRaises(ValueError): p.unpack(bad, parts)
        with self.assertRaises(ValueError): p.unpack(manifest, [])
        with self.assertRaises(ValueError): p.unpack({"schema":2, "parts":1, "digest":"0"*64}, ["bm90LXpsaWI="])
        bomb = base64.b64encode(zlib.compress(b"x"*(p.MAX_BYTES+1))).decode()
        with self.assertRaises(ValueError): p.unpack({"schema":2, "parts":1, "digest":"0"*64}, [bomb])

    def test_same_name_does_not_merge_different_variants(self):
        state = p.new_registry()
        first = item(); first["eans"] = []; first["prices"] = []
        other = deepcopy(first); other["store_links"]["mercadona"] = {"id":"456", "url":"https://tienda.mercadona.es/product/456"}
        p.contribute(state, payload(first), 1, NOW, 1)
        p.contribute(state, payload(other), 2, NOW, 2)
        self.assertEqual(len(p.compile_dictionary(state, NOW)["products"]), 2)

    def test_large_price_change_waits_for_three_independent_accounts(self):
        state = p.new_registry()
        p.contribute(state, payload(), 1, NOW, 1)
        revised = item(); revised["prices"][0].update(price="5.00", checked_at=NOW+86400)
        for user in (2, 3):
            p.contribute(state, payload(revised), user, NOW+86400, user)
            self.assertEqual(p.compile_dictionary(state, NOW+86400)["products"][0]["prices"], [])
        self.assertFalse(p.contribute(state, payload(revised), 2, NOW+86401, 20))
        p.contribute(state, payload(revised), 4, NOW+86400, 4)
        saved = p.compile_dictionary(state, NOW+86400)["products"][0]["prices"][0]
        self.assertEqual(saved["price"], "5.00")
        self.assertEqual(saved["checked_at"], NOW+86400)

    def test_normal_price_change_is_accepted_and_history_is_preserved(self):
        state = p.new_registry()
        p.contribute(state, payload(), 1, NOW, 1)
        revised = item(); revised["prices"][0].update(price="1.50", checked_at=NOW+86400)
        p.contribute(state, payload(revised), 2, NOW+86400, 2)
        record = next(iter(state["records"].values()))
        self.assertEqual(record["prices"]["mercadona"]["price"], "1.50")
        self.assertEqual(record["price_history"]["mercadona"][0]["price"], "1.25")

    def test_recovery_withdraws_replaced_price_and_retains_daily_account_limits(self):
        state = p.new_registry()
        p.contribute(state, payload(), 1, NOW, 1)
        trusted = deepcopy(state)
        revised = item(); revised["prices"][0].update(price="1.50", checked_at=NOW+86400)
        p.contribute(state, payload(revised), 2, NOW+86400, 2)
        bad = next(iter(state["records"].values()))["prices"]["mercadona"]
        restored = p.restore_registry(trusted, state)
        self.assertIn(p.price_fingerprint(bad), p.compile_dictionary(restored, NOW+86400)["revoked_prices"])
        self.assertEqual(next(iter(restored["records"].values()))["prices"]["mercadona"]["price"], "1.25")
        self.assertFalse(p.contribute(restored, payload(revised), 2, NOW+86401, 3))

    def test_compaction_deduplicates_selections_without_changing_consensus(self):
        state = p.new_registry()
        for user in range(1, 11): p.contribute(state, payload(), user, NOW, user)
        expected = p.compile_dictionary(state, NOW)
        p.compact_registry(state)
        record = next(iter(state["records"].values()))
        self.assertEqual(len(record["choices"]), 1)
        self.assertEqual(len(record["votes"]), 10)
        self.assertEqual(p.compile_dictionary(state, NOW), expected)

    def test_explicit_community_icon_choice_counts_preference_without_echo_confirmation(self):
        state = p.new_registry()
        for user in (1,2,3): p.contribute(state, payload(), user, NOW, user)
        selected = item(); selected["borrowed_fields"] = ["icons"]
        p.contribute(state, payload(selected), 4, NOW, 4)
        info = {"author":"Google", "license":"Apache-2.0", "license_url":"https://www.apache.org/licenses/LICENSE-2.0"}
        icon = p.compile_dictionary(state, NOW, icon_metadata={"noto:cooked-rice":info})["products"][0]["icons"][0]
        self.assertEqual(icon["selections"], 4)
        self.assertEqual(icon["confirmations"], 3)


if __name__ == "__main__":
    unittest.main()
