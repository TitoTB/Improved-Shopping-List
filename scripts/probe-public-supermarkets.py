"""Bounded, read-only public API checks in a real Home Assistant Core image.

Uses the integration's HTTP helper and parsers without loading its catalog,
credentials, storage or config entry. This diagnostic is never auto-scheduled.
"""
import asyncio
import importlib
import json
from pathlib import Path
import ssl
import sys
from tempfile import TemporaryDirectory
import time
import types
from urllib.parse import urlencode

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.components.network.network import async_get_network
from homeassistant.helpers.aiohttp_client import async_create_clientsession

package = types.ModuleType("_public_shop_probe")
package.__path__ = [str(Path(sys.argv[1]).resolve()/"custom_components/improved_shopping_list")]
sys.modules[package.__name__] = package
sources = importlib.import_module(package.__name__+".price_sources")
lookup = importlib.import_module(package.__name__+".option_lookup")
references = importlib.import_module(package.__name__+".product_references")
public = importlib.import_module(package.__name__+".public_catalogs")

EAN = "8410199023094"
NEGATIVE = "9999999999994"
STORES = (
    ("masymas", "https://tienda.masymas.com", "29446"),
    ("bm", "https://www.online.bmsupermercados.es", "20073"),
    ("consum", "https://tienda.consum.es", "7394260"),
)


async def check_store(hass, name, base, code):
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
    provider = sources.PriceSources(hass)
    next_request = 0
    responses = []

    async def before():
        nonlocal next_request
        await asyncio.sleep(max(0, next_request-time.monotonic()))
        next_request = time.monotonic()+20

    async def fetch(path, stage):
        data = await public.request(hass,name,path,before)
        if not isinstance(data, dict):
            raise ValueError("Expected a product JSON object")
        responses.append(stage)
        return data

    def exact(products):
        return [product for product in products if references.gtin(str(product.get("ean", ""))) == references.gtin(EAN)]

    result = {"store": name, "transport":"HA async_create_clientsession + new integration public_catalogs.request/shop_product"}
    try:
        for stage, query in (("ean_search", EAN), ("commercial_name_search", "patatas fritas gourmet"), ("negative_control", NEGATIVE)):
            path = "/api/rest/V1.0/catalog/searcher/products?"+urlencode({"q":query, "limit":5, "offset":0})
            data = await fetch(path, stage)
            catalog = data.get("catalog", {})
            products = catalog.get("products", [])
            if not isinstance(products, list):
                raise ValueError("Invalid search result shape")
            matches = exact(products)
            result[stage] = {"total":catalog.get("totalCount"), "exact_matches":len(matches),
                "references":[{"id":str(p.get("code", "")),"ean":p.get("ean"),"url":p.get("productData", {}).get("url")} for p in matches]}
            if stage == "commercial_name_search":
                assert len(matches) == 1 and str(matches[0]["code"]) == code
            elif stage == "negative_control":
                assert not products
            elif name == "masymas":
                assert len(matches) == 1 and str(matches[0]["code"]) == code
            print(json.dumps({"store":name,"stage":stage,**result[stage]},ensure_ascii=False),flush=True)
        detail = await fetch("/api/rest/V1.0/catalog/product/code/"+code+"?showRecommendations=false", "product_detail")
        offer = sources.consum_offer(detail, {"id":code})
        assert offer and references.gtin(offer["ean"]) == references.gtin(EAN)
        parsed = lookup.metadata(offer)
        assert parsed["content_quantity"] == 170 and parsed["content_unit"] == "g"
        assert parsed["brand"] and float(offer["price"]) > 0
        production=public.shop_product(name,detail,EAN)
        assert production["content_quantity"]==170 and production["content_unit"]=="g"
        assert production["measure_price"]["unit"]=="kg" and production["price"]>0
        result["detail"] = {"reference":code,"ean":offer["ean"],"price":offer["price"],"currency":offer["currency"],
            "reference_price":offer["reference_price"],"reference_unit":offer["reference_unit"], **parsed}
        result["success"] = True
    except Exception as err:
        result.update(success=False,error_type=type(err).__name__,message=str(err),diagnostics=getattr(err,"diagnostics",{}))
    finally:
        result["completed_requests"] = responses
        session.detach()
        provider.close()
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


async def main():
    print(json.dumps({"python":sys.version.split()[0],"openssl":ssl.OPENSSL_VERSION,"request_interval_seconds_per_host":20}),flush=True)
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        await async_get_network(hass)
        try:
            results = await asyncio.gather(*(check_store(hass,*store) for store in STORES))
            Path("/tmp/public-supermarket-probe-result.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
            assert all(result["success"] for result in results), "At least one live store check failed; inspect per-store diagnostics"
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
