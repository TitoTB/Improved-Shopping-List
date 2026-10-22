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
    def test_only_names_and_icons_survive_legacy_commercial_payloads(self):
        clean=p.validate_product(item(),NOW)
        self.assertEqual(clean["eans"],[])
        self.assertEqual(clean["store_links"],{})
        self.assertEqual(clean["prices"],[])
        self.assertEqual(clean["nutriscore"],"")
        self.assertEqual(clean["icons"],["noto:cooked-rice"])

    def test_three_independent_accounts_confirm_icons(self):
        state=p.new_registry()
        for user in (1,2):p.contribute(state,payload(),user,NOW,user)
        metadata={"noto:cooked-rice":{"author":"Google","license":"Apache-2.0","license_url":"https://example.test/license"}}
        self.assertEqual(p.compile_dictionary(state,NOW,icon_metadata=metadata)["products"][0]["icons"],[])
        p.contribute(state,payload(),3,NOW,3)
        data=p.compile_dictionary(state,NOW,icon_metadata=metadata)
        self.assertEqual(data["products"][0]["icons"][0]["confirmations"],3)
        self.assertEqual(data["products"][0]["prices"],[])
        self.assertEqual(data["products"][0]["eans"],[])
        self.assertEqual(data["products"][0]["store_links"],{})
        p.validate_dictionary(data,NOW)

    def test_account_limit_is_persistent(self):
        state=p.new_registry()
        self.assertTrue(p.contribute(state,payload(),1,NOW,1))
        self.assertFalse(p.contribute(state,payload(),1,NOW+1,2))
        self.assertTrue(p.contribute(state,payload(),1,NOW+86400,3))
        self.assertEqual(len(next(iter(state["records"].values()))["votes"]),1)

    def test_bans_withdraw_icon_votes_and_stop_new_submissions(self):
        state=p.new_registry()
        for user in (1,2,3):p.contribute(state,payload(),user,NOW,user)
        result=p.compile_dictionary(state,NOW,banned=(1,))
        self.assertNotIn("name",result["products"][0]["confirmed_fields"])
        self.assertFalse(p.contribute(state,payload(),1,NOW+86400,4,banned=(1,)))

    def test_unlicensed_icons_are_never_published(self):
        state=p.new_registry()
        for user in (1,2,3):p.contribute(state,payload(),user,NOW,user)
        self.assertEqual(p.compile_dictionary(state,NOW)["products"][0]["icons"],[])

    def test_terms_and_multiple_images_do_not_depend_on_barcode(self):
        state=p.new_registry()
        for user in range(1,7):
            candidate=item("Arroz" if user<4 else "Cereal de arroz")
            candidate["eans"]=["1234567890128"] if user<4 else []
            candidate["icons"]=["noto:cooked-rice" if user<4 else "twemoji:cooked-rice"]
            p.contribute(state,payload(candidate),user,NOW,user)
        info={icon:{"author":"Author","license":"CC-BY","license_url":"https://example.test/license"} for icon in ("noto:cooked-rice","twemoji:cooked-rice")}
        data=p.compile_dictionary(state,NOW,icon_metadata=info)
        self.assertEqual(len(data["products"]),1)
        self.assertEqual(len(data["products"][0]["icons"]),2)
        self.assertIn("Cereal de arroz",data["products"][0]["terms"])

    def test_compaction_removes_old_prices_codes_and_references(self):
        candidate=item();state=p.new_registry()
        state["records"]["a"*32]={"identities":["ean:8410109115543"],"term":"rice","prices":{"mercadona":{"price":"1.25"}},"price_history":{"mercadona":[{"price":"1.00"}]},"votes":{"1":{"item":candidate,"eligible":True}}}
        p.compact_registry(state)
        raw=json.dumps(state)
        self.assertNotIn("8410109115543",raw)
        self.assertNotIn("tienda.mercadona.es",raw)
        self.assertNotIn('"1.25"',raw)
        self.assertNotIn("price_history",raw)

    def test_old_dictionary_is_sanitized_on_read(self):
        state=p.new_registry();p.contribute(state,payload(),1,NOW,1)
        data=p.compile_dictionary(state,NOW);data["products"][0].update(eans=["8410109115543"],store_links=item()["store_links"],prices=item()["prices"],nutriscore="a")
        clean=p.validate_dictionary(data,NOW)["products"][0]
        self.assertEqual(clean["prices"],[]);self.assertEqual(clean["eans"],[])
        self.assertEqual(clean["store_links"],{});self.assertEqual(clean["nutriscore"],"")

    def test_allowlist_and_multipart_limits_remain_enforced(self):
        candidate=item();candidate["password"]="PRIVATE"
        with self.assertRaises(ValueError):p.validate_product(candidate,NOW)
        candidate=item();candidate["icons"]=["https://untrusted.test/image.svg"]
        with self.assertRaises(ValueError):p.validate_product(candidate,NOW)
        manifest,parts=p.pack(payload())
        self.assertEqual(p.unpack(manifest,parts),payload())
        broken=deepcopy(manifest);broken["digest"]="0"*64
        with self.assertRaises(ValueError):p.unpack(broken,parts)


if __name__=="__main__":
    unittest.main()
