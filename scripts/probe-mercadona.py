"""Explicit live check using the installed Home Assistant HTTP helper and parser.

Run manually in an isolated HA Core image; not part of the offline test suite.
No Home Assistant account, shopping lists, credentials or user data are accessed.
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

from homeassistant.core import HomeAssistant
from homeassistant.components.network.network import async_get_network

root=Path(__file__).resolve().parents[1]/"custom_components/improved_shopping_list"
package=types.ModuleType("_mercadona_probe")
package.__path__=[str(root)]
sys.modules[package.__name__]=package
provider=importlib.import_module("_mercadona_probe.mercadona_catalog")


async def main():
    print(json.dumps({"python":sys.version.split()[0],"openssl":ssl.OPENSSL_VERSION}),flush=True)
    with TemporaryDirectory() as directory:
        hass=HomeAssistant(directory)
        await async_get_network(hass)
        last=0
        async def before():
            nonlocal last
            await asyncio.sleep(max(0,20-(time.monotonic()-last)))
            last=time.monotonic()
        try:
            if "--index-only" in sys.argv:
                index=provider.MercadonaIndex(hass)
                await index.async_load()
                await index.async_refresh()
                assert not index.error and len(index.products)>1000
                assert index.products.get("08430543025611")=="69938"
                assert index.has_common_data
                common=index.common_data({"08430543025611","08411700011302"})
                assert common["08430543025611"]["content_quantity"]==.29
                assert common["08411700011302"]["brand"]=="Puleva"
                assert all("price" not in item and item["source"]["observed_at"]>0 for item in common.values())
                print(json.dumps({"public_index":index.status,"common_examples":common},ensure_ascii=False),flush=True)
                return
            for identity,ean in (("69938","8430543025611"),("10282","8411700011302")):
                data=await provider.retrieve(hass,f"https://tienda.mercadona.es/product/{identity}",before,ean)
                assert data["ean"]==ean and data["price"]>=0
                assert data["content_quantity"]>0 and data["content_unit"]
                assert data["measure_price"]["price"]>0
                if identity=="10282":assert data["brand"]
                print(json.dumps(data,ensure_ascii=False),flush=True)
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
