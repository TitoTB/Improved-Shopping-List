"""The public export contains five fields, and failed exports never replace it."""

import base64
import csv
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from shopping_feed import build, protocol
from publish_shopping_data import GitHubDataPublisher


def product(ean="8431876279146", price="1.35"):
    return {"ean": ean, "name": "Alcaparras", "price": price, "currency": "EUR",
            "affiliate_url": "https://www.awin1.com/pclick.php?p=123&a=1535625&m=25399"}


def source(path, products, merchant="25399"):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["merchant_id", "merchant_product_id", "product_name",
            "search_price", "currency", "aw_deep_link", "description", "merchant_image_url"])
        writer.writeheader()
        for item in products:
            writer.writerow({"merchant_id": merchant, "merchant_product_id": item["ean"],
                "product_name": item["name"], "search_price": item["price"], "currency": item["currency"],
                "aw_deep_link": item["affiliate_url"], "description": "PRIVATE EXTRA", "merchant_image_url": "PRIVATE IMAGE"})


class FeedExportTest(unittest.TestCase):
    def test_whitelist_and_canonical_codes(self):
        self.assertEqual(protocol.gtin("8431876279146"), "08431876279146")
        self.assertEqual(protocol.gtin("08431876279146"), "08431876279146")
        self.assertEqual(set(protocol.record(product())), protocol.FIELDS)
        for item in [dict(product(), nutriscore="a"), dict(product(), ean="8431876279145"),
                     dict(product(), price="NaN"), dict(product(), price="1.234"),
                     dict(product(), affiliate_url="https://evil.test/image.svg"),
                     dict(product(), affiliate_url="https://www.awin1.com@evil.test/pclick.php")]:
            with self.assertRaises(ValueError):
                protocol.record(item)
        with self.assertRaises(ValueError):
            protocol.snapshot([product(), product("08431876279146")])

    def test_snapshot_delta_and_failed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feed, output = root / "feed.gz", root / "public"
            source(feed, [product(), product("8721201901058")])
            first = build(feed, output, "first")
            initial = protocol.read_snapshot((output / first["snapshot"]["path"]).read_bytes())
            source(feed, [product(price="1.55"), product("8721201901249")])
            second = build(feed, output, "second")
            delta = (output / second["delta"]["path"]).read_bytes()
            result = protocol.apply_delta(initial, delta, first["version"], second["version"])
            self.assertEqual(set(result), {protocol.gtin("8431876279146"), protocol.gtin("8721201901249")})
            self.assertEqual(result[protocol.gtin("8431876279146")]["price"], "1.55")
            self.assertNotIn(b"PRIVATE", (output / second["snapshot"]["path"]).read_bytes())
            with self.assertRaises(ValueError):
                protocol.apply_delta(initial, delta, "wrong-base", second["version"])
            before = (output / "manifest.json").read_bytes()
            source(feed, [product()], merchant="other")
            with self.assertRaises(ValueError):
                build(feed, output)
            self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_publisher_creates_only_orphan_data_and_never_a_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source(root / "feed.gz", [product()])
            build(root / "feed.gz", root / "public")
            publisher = GitHubDataPublisher("owner/repository", "PRIVATE TOKEN")
            def request(method, path, body=None, **kwargs):
                if method == "GET":
                    return None
                return {"sha": "created"}
            publisher.request = Mock(side_effect=request)
            self.assertEqual(publisher.publish(root / "public"), "created")
            calls = publisher.request.call_args_list
            tree = next(call.args[2] for call in calls if call.args[1] == "/git/trees")
            self.assertNotIn("base_tree", tree)
            self.assertTrue(all(item["path"].startswith("carrefour/") for item in tree["tree"]))
            commit = next(call.args[2] for call in calls if call.args[1] == "/git/commits")
            self.assertEqual(commit["parents"], [])
            for call in calls:
                self.assertNotIn("releases", call.args[1])
                self.assertNotIn("PRIVATE TOKEN", str(call))
                if call.args[1] == "/git/blobs":
                    self.assertNotIn(b"PRIVATE", base64.b64decode(call.args[2]["content"]))


if __name__ == "__main__":
    unittest.main()
