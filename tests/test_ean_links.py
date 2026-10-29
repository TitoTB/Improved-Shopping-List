"""Exact EAN links, conditional public downloads and preservation of user choices."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import csv
import io
import json
import time

import pytest
from homeassistant.util import dt as dt_util
from homeassistant.core import is_callback
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks, URL, DAY, enrich_product, parse_dictionary, redirect_product
from custom_components.improved_shopping_list.product_references import gtin, reference_from_line
from custom_components.improved_shopping_list.store_links import normalize_link

EAN = "3560071237950"
WEB = "https://www.carrefour.es/supermercado/anacardo/R-VC4AECOMM-491998/p"
AWIN = "https://www.awin1.com/pclick.php?p=35556761179&a=1535625&m=25399"
CSV = f"EAN,Carrefour\n{EAN},{AWIN}\n".encode()


async def test_startup_timer_launches_resolution_on_the_home_assistant_event_loop(hass, aioclient_mock):
    catalog = Catalog(hass); await catalog.async_load()
    await catalog.async_save_product({"name":"Anacardos", "barcodes":[EAN]})
    manager = EANLinks(hass, catalog); await manager.async_load(); catalog.ean_links = manager
    aioclient_mock.get(URL, content=CSV)
    aioclient_mock.head(AWIN, status=302, headers={"Location":WEB})
    try:
        manager.start()
        assert is_callback(manager._queue) and is_callback(manager._launch)
        # Fire the actual HA timer instead of calling async_sync directly.
        async_fire_time_changed(hass, dt_util.utcnow()+timedelta(seconds=2))
        await hass.async_block_till_done()
        assert manager._task is not None
        await manager._task
        assert aioclient_mock.call_count == 2
        assert catalog.products[0]["commercial_references"][0]["url"] == WEB
    finally:
        await manager.async_stop()


def test_published_initial_dictionary_has_only_ean_and_shop_links():
    raw = (Path(__file__).resolve().parents[1]/"data/ean-links.csv").read_bytes()
    data = parse_dictionary(raw)
    assert len([key for key in data if not key.startswith('alcampo:')]) == 15764 and data[gtin(EAN)] == AWIN
    assert raw.splitlines()[0] == b"EAN,Carrefour,Alcampo"
    # Installed Carrefour-only clients still require a nonempty Carrefour URL on every row.
    assert all(row['Carrefour'] for row in csv.DictReader(io.StringIO(raw.decode())))
    extended = parse_dictionary((Path(__file__).resolve().parents[1]/'data/ean-links-v2.csv').read_bytes())
    evidence = json.loads((Path(__file__).resolve().parents[1]/'data/alcampo-verification.json').read_text())
    assert len(extended) == 15764+11
    assert len(evidence['links']) == 11
    for item in evidence['links']:
        assert extended['alcampo:'+gtin(item['ean'])] == item['url']
    assert all(extended[key] == value for key,value in data.items())


async def test_alcampo_only_rows_resolve_locally_restore_and_preserve_user_choices(hass, aioclient_mock):
    code = '8410422111086'
    web = 'https://www.compraonline.alcampo.es/products/allioli/722018'
    catalog = Catalog(hass); await catalog.async_load()
    await catalog.async_save_product({'name':'Allioli', 'barcodes':[code]})
    manager = EANLinks(hass, catalog); await manager.async_load(); manager._active = True
    manager.enabled_stores.add('alcampo')
    catalog.ean_links = manager
    aioclient_mock.get(URL, content=f'EAN,Carrefour,Alcampo\n{code},,{web}\n'.encode())
    try:
        await manager.async_sync()
        assert aioclient_mock.call_count == 1  # Official URLs need no additional request to the shop.
        ref = catalog.products[0]['commercial_references'][0]
        assert ref['store'] == 'alcampo' and ref['ean'] == code and ref['url'] == web
        restored = EANLinks(hass, catalog); await restored.async_load()
        restored.enabled_stores.add('alcampo')
        assert restored.resolved == manager.resolved
        product = catalog.products[0]
        product['commercial_references'][0]['url'] = ''
        product['commercial_references'][0]['active'] = False
        assert not enrich_product(product, restored.resolved)
        product['commercial_references'][0]['active'] = True
        product['commercial_references'][0]['url'] = web.replace('722018', '12345')
        assert not enrich_product(product, restored.resolved)
        assert not enrich_product({'name':'Otro', 'barcodes':[EAN]}, restored.resolved)
    finally:
        await manager.async_stop()


def test_alcampo_urls_are_strictly_scoped_and_can_coexist_with_carrefour():
    key = gtin(EAN)
    web = 'https://www.compraonline.alcampo.es/products/prueba/722018'
    values = parse_dictionary(f'EAN,Carrefour,Alcampo\n{EAN},{WEB},{web}\n'.encode())
    assert values[key] == WEB and values['alcampo:'+key] == web
    product = {'name':'Producto', 'barcodes':[EAN]}
    assert enrich_product(product, {key:normalize_link('carrefour',WEB),'alcampo:'+key:normalize_link('alcampo',web)})
    assert {ref['store'] for ref in product['commercial_references']} == {'carrefour','alcampo'}
    for url in (WEB, 'https://evil.test/products/prueba/722018', AWIN):
        with pytest.raises(ValueError):
            parse_dictionary(f'EAN,Carrefour,Alcampo\n{EAN},,{url}\n'.encode())


def test_invalid_ambiguous_entries_and_redirects_cannot_be_followed():
    for raw in (b"EAN,Carrefour\n123,https://evil.test\n", CSV+f"{EAN},{WEB}\n".encode(),
                f"EAN,Carrefour\n{EAN},https://www.awin1.com/pclick.php?p=1&a=1535625&m=1\n".encode()):
        with pytest.raises(ValueError):
            parse_dictionary(raw)
    for location in ("https://evil.test/", WEB+" "+WEB.replace("491998", "491999"), "http://www.carrefour.es/supermercado/R-1/p"):
        with pytest.raises(ValueError):
            redirect_product(location)
    assert redirect_product("https://ad.doubleclick.net/track?"+WEB+"?tracking=abc") == normalize_link("carrefour", WEB)


def test_exact_links_preserve_prices_formats_and_user_urls_and_exclusions():
    ref = reference_from_line("carrefour", {"ean":EAN, "description":"ANACARDO 200 G"})
    ref.update(content_confirmed=True, last_price={"price":2.69,"currency":"EUR","checked_at":time.time()})
    product = {"name":"Frutos secos", "barcodes":[EAN], "commercial_references":[ref]}
    previous = deepcopy(ref)
    assert enrich_product(product, {gtin(EAN):normalize_link("carrefour", WEB)})
    result = product["commercial_references"][0]
    assert result["url"] == WEB and result["content_quantity"] == 200 and result["content_confirmed"]
    assert result["last_price"] == previous["last_price"]
    assert not enrich_product(product, {gtin(EAN):normalize_link("carrefour", WEB.replace("491998", "other"))})
    result["active"] = False; result["url"] = ""
    assert not enrich_product(product, {gtin(EAN):normalize_link("carrefour", WEB)})
    assert not enrich_product({"name":"Otro", "barcodes":["4006381333931"]}, {gtin(EAN):normalize_link("carrefour", WEB)})


async def test_download_resolve_apply_cache_and_conditional_refresh(hass, aioclient_mock):
    catalog = Catalog(hass); await catalog.async_load()
    product = await catalog.async_save_product({"name":"Anacardos", "barcodes":[EAN]})
    manager = EANLinks(hass, catalog); await manager.async_load(); catalog.ean_links = manager
    manager._active = True
    aioclient_mock.get(URL, content=CSV, headers={"ETag":'"v1"'})
    aioclient_mock.head(AWIN, status=302, headers={"Location":"https://ad.doubleclick.net/track?"+WEB+"?tracking=abc"})
    try:
        await manager.async_sync()
        assert aioclient_mock.call_count == 2
        updated = catalog.products[0]
        assert updated["commercial_references"][0]["url"] == WEB
        assert updated["revision"] == product["revision"]+1
        await manager.async_sync()
        assert aioclient_mock.call_count == 2
        cached = EANLinks(hass,catalog); await cached.async_load()
        assert cached.resolved == manager.resolved
        # New exact associations in a ticket reuse the local result immediately.
        await catalog.async_bind_receipt_eans([(product["id"],EAN)], references=[(product["id"],"carrefour",{"ean":EAN,"description":"ANACARDO"},False)])
        assert catalog.products[0]["commercial_references"][0]["url"] == WEB
        manager._data["checked_at"] -= DAY+1; manager._next_download = 0
        aioclient_mock.clear_requests(); aioclient_mock.get(URL, status=304)
        await manager.async_sync()
        assert aioclient_mock.call_count == 1
        assert aioclient_mock.mock_calls[0][3]["If-None-Match"] == '"v1"'
        assert manager.resolved[gtin(EAN)]["url"] == WEB
    finally:
        await manager.async_stop()


async def test_offline_cache_keeps_links_and_unknown_or_failed_eans_do_not_loop(hass, aioclient_mock):
    catalog = Catalog(hass); await catalog.async_load()
    await catalog.async_save_product({"name":"Anacardos", "barcodes":[EAN]})
    manager = EANLinks(hass,catalog); manager._active = True
    manager._data.update(links={gtin(EAN):AWIN}, resolved={gtin(EAN):normalize_link("carrefour",WEB)})
    aioclient_mock.get(URL,status=503)
    try:
        await manager.async_sync()
        assert catalog.products[0]["commercial_references"][0]["url"] == WEB
        await manager.async_sync()
        assert aioclient_mock.call_count == 1
    finally:
        await manager.async_stop()
    manager = EANLinks(hass,catalog); manager._active = True
    manager._data.update(links={gtin(EAN):AWIN}, checked_at=time.time())
    aioclient_mock.head(AWIN,status=404)
    try:
        await manager.async_sync(); await manager.async_sync()
        assert manager._data["failed"][gtin(EAN)] > time.time()
        assert not manager._pending()
    finally:
        await manager.async_stop()
