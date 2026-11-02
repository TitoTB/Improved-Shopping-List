"""OFF requests, cache durability and failure isolation; no live network requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list import product_lookup as module
from custom_components.improved_shopping_list.product_lookup import BASE_URL, ProductLookup, is_product_barcode, product_hint
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN

CODE = "3017620422003"
PAYLOAD = {"product":{"code":CODE,"generic_name_es":" Crema de avellanas ","generic_name":"Hazelnut spread",
                      "product_name_es":"Nutella","brands":"Ferrero","quantity":"400 g"}}


@pytest.mark.parametrize(("code","expected"), [(CODE,True),("03017620422003",True),("8410109115543",True),
                                               ("https://example.test/product",False),("AA:BB:CC:DD",False),
                                               ("3017620422004",False),("３０１７６２０４２２００３",False),("",False)])
def test_only_valid_numeric_product_codes(code, expected):
    assert is_product_barcode(code) is expected


def test_prefers_common_spanish_name_and_checks_returned_code():
    hint = product_hint(PAYLOAD,CODE)
    assert hint["name"] == "Crema de avellanas"
    assert hint["brand"] == "Ferrero"
    assert hint["content_quantity"] == 400 and hint["content_unit"] == "g"
    assert hint["url"] == f"{BASE_URL}/product/{CODE}"
    assert product_hint({"product":{"code":CODE,"product_name_es":"Nombre comercial"}},CODE)["name"] == "Nombre comercial"
    assert product_hint({"product":{"code":CODE}},CODE) == {"status":"not_found"}
    with pytest.raises(ValueError):
        product_hint({"product":{"code":"8410109115543","generic_name":"Otro"}},CODE)


async def test_cache_deduplicates_aliases_and_survives_reload(hass, monkeypatch):
    lookup=ProductLookup(hass)
    await lookup.async_load()
    fetch=AsyncMock(return_value=product_hint(PAYLOAD,CODE))
    monkeypatch.setattr(lookup,"_fetch",fetch)
    first,second=await asyncio.gather(lookup.async_lookup(CODE),lookup.async_lookup("03017620422003"))
    assert first == second and fetch.await_count == 1
    first["name"]="Changed"
    assert lookup.cached(CODE)["name"] == "Crema de avellanas"
    restored=ProductLookup(hass)
    await restored.async_load()
    monkeypatch.setattr(restored,"_fetch",AsyncMock(side_effect=AssertionError("Cache must avoid requests")))
    assert (await restored.async_lookup(CODE))["name"] == "Crema de avellanas"
    assert (await restored.async_lookup("https://example.test/private"))["status"] == "unsupported"


async def test_persisted_format_cache_precedes_shop_discovery(hass, monkeypatch):
    discovery=SimpleNamespace(fingerprint=lambda:'enabled-shops',async_hint=AsyncMock(return_value={
        'status':'found','content_quantity':500,'content_unit':'g'}))
    lookup=ProductLookup(hass);lookup.catalog_discovery=discovery
    assert (await lookup.async_lookup(CODE))['content_quantity']==500
    restored=ProductLookup(hass);restored.catalog_discovery=discovery
    await restored.async_load()
    discovery.async_hint.reset_mock()
    monkeypatch.setattr(restored,'_fetch',AsyncMock(side_effect=AssertionError('Must use cached format')))
    assert (await restored.async_lookup('0'+CODE))['content_quantity']==500
    discovery.async_hint.assert_not_awaited()
    discovery.fingerprint=lambda:'different-shops'
    await restored.async_lookup(CODE)
    discovery.async_hint.assert_awaited_once()


async def test_serialises_reads_and_spaces_requests(hass, monkeypatch):
    clock=[1000.0]
    waits=[]
    monkeypatch.setattr(module,"time",SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]))
    async def advance(seconds):
        waits.append(seconds)
        clock[0]+=seconds
    monkeypatch.setattr(module,"sleep",advance)
    lookup=ProductLookup(hass)
    monkeypatch.setattr(lookup,"_fetch",AsyncMock(return_value={"status":"not_found"}))
    await asyncio.gather(lookup.async_lookup(CODE),lookup.async_lookup("8410109115543"))
    assert waits == pytest.approx([4.1])


async def test_errors_cached_briefly_and_retry_after_expiry(hass, monkeypatch):
    lookup=ProductLookup(hass)
    fetch=AsyncMock(side_effect=ClientError("Offline"))
    monkeypatch.setattr(lookup,"_fetch",fetch)
    assert (await lookup.async_lookup(CODE))["status"] == "error"
    assert (await lookup.async_lookup(CODE))["status"] == "error"
    assert fetch.await_count == 1
    lookup._cache[CODE.zfill(14)]["expires"]=0
    lookup._next_request=0
    fetch.side_effect=None
    fetch.return_value=product_hint(PAYLOAD,CODE)
    assert (await lookup.async_lookup(CODE))["status"] == "found"
    assert fetch.await_count == 2


@pytest.mark.parametrize(("status","body","expected"), [(200,PAYLOAD,"found"),(404,{},"not_found"),
                                                          (429,{},"error"),(500,{},"error"),(302,{},"error"),
                                                          (200,{"unexpected":True},"error")])
async def test_http_response_handling(hass, aioclient_mock, status, body, expected):
    lookup=ProductLookup(hass)
    aioclient_mock.get(f"{BASE_URL}/api/v3/product/{CODE}",json=body,status=status)
    result=await lookup.async_lookup(CODE)
    assert result["status"] == expected
    assert aioclient_mock.call_count == 1


async def test_memory_cache_still_works_when_disk_is_full(hass, monkeypatch):
    lookup=ProductLookup(hass)
    monkeypatch.setattr(lookup,"_fetch",AsyncMock(return_value=product_hint(PAYLOAD,CODE)))
    monkeypatch.setattr(lookup._store,"async_save",AsyncMock(side_effect=OSError("Disk full")))
    assert (await lookup.async_lookup(CODE))["status"] == "found"
    assert lookup.is_fresh(CODE)


@pytest.mark.parametrize("grade", ["a", "b", "c", "d", "e", "A"])
def test_nutriscore_is_validated_without_requiring_a_name(grade):
    result = product_hint({"product": {"code": CODE, "nutriscore_grade": grade, "nutriscore_score": 0, "nutriscore_version": "2023"}}, CODE)
    assert result["nutriscore"] == {"grade": grade.lower(), "score": 0, "version": "2023"}
    assert result["status"] == "not_found"


@pytest.mark.parametrize("grade", [None, "unknown", "not-applicable", "f", "<script>", 1])
def test_missing_or_invalid_nutriscore_stays_absent(grade):
    assert "nutriscore" not in product_hint({"product": {**PAYLOAD["product"], "nutriscore_grade": grade}}, CODE)


async def test_old_name_only_cache_is_refreshed_and_nutriscore_survives_reload(hass, monkeypatch):
    lookup = ProductLookup(hass)
    lookup._cache[CODE.zfill(14)] = {"expires": module.time.time() + 86400, "result": product_hint(PAYLOAD, CODE)}
    fetch = AsyncMock(return_value=product_hint({"product": {**PAYLOAD["product"], "nutriscore_grade": "d"}}, CODE))
    monkeypatch.setattr(lookup, "_fetch", fetch)
    result = await lookup.async_lookup(CODE)
    assert result["nutriscore"]["grade"] == "d" and result["nutriscore"]["checked_at"] > 0
    fetch.assert_awaited_once()
    restored = ProductLookup(hass)
    await restored.async_load()
    monkeypatch.setattr(restored, "_fetch", AsyncMock(side_effect=AssertionError("Must use persisted cache")))
    assert await restored.async_lookup(CODE) == result


async def test_nutriscore_endpoint_reuses_lookup_and_never_sends_qr_or_nfc(hass, hass_ws_client, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    lookup = hass.data[DOMAIN]["readers"].lookup
    common=AsyncMock(return_value={})
    monkeypatch.setattr(lookup.common_index,'async_hint',common)
    fetch = AsyncMock(return_value=product_hint({"product": {**PAYLOAD["product"], "nutriscore_grade": "b"}}, CODE))
    monkeypatch.setattr(lookup, "_fetch", fetch)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/nutriscore", "code": CODE})
    result = (await client.receive_json())["result"]
    assert result["nutriscore"]["grade"] == "b" and result["code"] == CODE
    assert result["brand"] == "Ferrero" and result["content_quantity"] == 400 and result["content_unit"] == "g"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/nutriscore", "code": "https://private.test/qr"})
    assert (await client.receive_json())["result"]["nutriscore"] is None
    fetch.assert_awaited_once_with(CODE)
    common.assert_awaited_once_with(CODE)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/nutriscore", "code": CODE})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"


async def test_nutrition_distribution_uses_stored_catalog_data_only(hass, hass_ws_client, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    lookup = hass.data[DOMAIN]["readers"].lookup
    fetch = AsyncMock(side_effect=AssertionError("Statistics must never fetch products"))
    monkeypatch.setattr(lookup, "_fetch", fetch)
    lookup._cache[CODE.zfill(14)] = {"expires": 0, "result": {"status": "found", "nutriscore": {"grade": "b"}}}
    lookup._cache["8410109115543".zfill(14)] = {"expires": 0, "result": {"status": "found", "nutriscore": {"grade": "e"}}}
    catalog = hass.data[DOMAIN]["catalog"]
    # Aliases and multiple known codes still count a catalog product only once.
    cacao = await catalog.async_save_product({"name": "Cacao", "barcode": CODE, "barcodes": [CODE.zfill(14), "8410109115543"]})
    await catalog.async_save_product({"name": "Sin datos", "barcode": "https://example.test/qr"})
    await catalog.async_save_product({"name": "Sin código"})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/nutrition_distribution"})
    result = await client.receive_json()
    assert result["success"]
    assert result["result"] == {"counts": {"a": 0, "b": 1, "c": 0, "d": 0, "e": 0}, "total": 1, "product_ids": {"a": [], "b": [cacao["id"]], "c": [], "d": [], "e": []}}
    fetch.assert_not_awaited()
    assert lookup.nutrition_distribution([])["total"] == 0
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/nutrition_distribution"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"


def test_nutrition_facts_use_only_normalized_finite_values():
    from custom_components.improved_shopping_list.product_lookup import nutrition_facts
    facts = nutrition_facts({"nutriments":{"energy-kcal_100g":230,"fat_100g":5.2,"salt_100g":float('nan'),"fiber_100g":True,"proteins_100g":-1},"nova_group":4,"ingredients_analysis_tags":["en:vegan"],"categories_tags":["en:vegetables"]})
    assert facts['nutrients'] == {'energy-kcal':230,'fat':5.2}
    assert facts['nova'] == 4 and facts['vegan'] is True
    assert nutrition_facts({}) == {}
    assert nutrition_facts({'nova_group':True,'nutriments':{'fat_100g':101}}) == {}


async def test_nutrition_has_persistent_exact_ean_cache_without_shop_discovery(hass, monkeypatch):
    from copy import deepcopy
    lookup = ProductLookup(hass)
    await lookup.async_load()
    result = {'status':'found','nutrition':{'nutrients':{'energy-kcal':120},'nova':1},'nutriscore':{'grade':'a'}}
    fetch = AsyncMock(return_value=deepcopy(result))
    monkeypatch.setattr(lookup,'_fetch',fetch)
    lookup.catalog_discovery = SimpleNamespace(async_hint=AsyncMock(side_effect=AssertionError('No shop calls for nutrition')))
    first, second = await asyncio.gather(lookup.async_nutrition(CODE),lookup.async_nutrition('0'+CODE))
    assert first == second and fetch.await_count == 1
    first['nutrition']['nova'] = 4
    assert (await lookup.async_nutrition(CODE))['nutrition']['nova'] == 1
    saved = deepcopy(lookup._nutrition_cache)
    restored = ProductLookup(hass)
    monkeypatch.setattr(restored._nutrition_store,'async_load',AsyncMock(return_value=saved))
    await restored.async_load_nutrition()
    monkeypatch.setattr(restored,'_fetch',AsyncMock(side_effect=AssertionError('Cached nutrition needs no requests')))
    assert (await restored.async_nutrition(CODE))['nutrition']['nova'] == 1
    records = restored.nutrition_records([{'id':'p','name':'Producto','barcodes':[CODE,'0'+CODE], 'commercial_references':[]}])['records']
    assert len(records) == 1 and records[0]['grade'] == 'a' and records[0]['fresh']


async def test_nutrition_distribution_uses_exact_alternative_cache_and_keeps_weight_basis(hass):
    lookup = ProductLookup(hass)
    lookup._nutrition_cache[CODE.zfill(14)] = {"expires": module.time.time()+1000, "result": {"status":"found", "nutriscore":{"grade":"b"}, "nutrition":{"nutrients":{"fat":2}}}}
    products = [{"id":"p", "name":"Producto", "commercial_references":[{"ean":CODE, "content_unit":"ml"}]}]
    assert lookup.nutrition_distribution(products)["counts"]["b"] == 1
    assert lookup.nutrition_records(products)["records"][0]["basis"] == "ml"
    hint = product_hint({"product":{**PAYLOAD["product"], "quantity":"400 g", "nutriments":{"fat_100g":2}}},CODE)
    assert hint["basis"] == "g"


async def test_nutrition_prefers_fresh_dictionary_and_stale_data_falls_back_to_off(hass,monkeypatch):
    lookup=ProductLookup(hass);now=int(module.time.time())
    shared={'source':'openfoodfacts','license':'ODbL-1.0','checked_at':now-100,'nutriscore':{'grade':'a','version':'2023'},'nova':2}
    index=SimpleNamespace(nutrition_cached=lambda _code:shared,async_nutrition_hint=AsyncMock(return_value=shared))
    lookup.common_index=index
    fetch=AsyncMock(side_effect=AssertionError('Fresh community data must avoid OFF'))
    monkeypatch.setattr(lookup,'_fetch',fetch)
    result=await lookup.async_nutrition(CODE)
    assert result['nutriscore']=={'grade':'a','version':'2023'} and result['nutrition']['nova']==2
    records=lookup.nutrition_records([{'id':'p','name':'Producto','barcodes':[CODE]}])['records']
    assert records[0]['fresh'] and records[0]['checked_at']==now-100
    assert lookup.nutrition_export([{'id':'p','name':'Producto','barcodes':[CODE]}])[CODE.zfill(14)]['source']=='openfoodfacts'
    shared['checked_at']=now-31*86400
    fetch=AsyncMock(return_value={'status':'found','nutriscore':{'grade':'b'},'nutrition':{'nova':3}})
    monkeypatch.setattr(lookup,'_fetch',fetch)
    result=await lookup.async_nutrition(CODE)
    assert result['nutriscore']['grade']=='b' and result['nutrition']['nova']==3
    fetch.assert_awaited_once_with(CODE)
    # A fresh local observation wins over an older shared one.
    shared['checked_at']=now-200;shared['nova']=1
    assert (await lookup.async_nutrition(CODE))['nutrition']['nova']==3
    assert await lookup.async_nutrition('https://private.test/qr')=={'status':'unsupported'}


async def test_failed_nutrition_refresh_never_rejuvenates_exported_source_date(hass,monkeypatch):
    lookup=ProductLookup(hass);old=int(module.time.time())-31*86400
    lookup._nutrition_cache[CODE.zfill(14)]={'expires':0,'checked_at':old,'result':{'status':'found','nutriscore':{'grade':'c'},'nutrition':{'nova':3}}}
    fetch=AsyncMock(side_effect=ClientError('offline'));monkeypatch.setattr(lookup,'_fetch',fetch)
    result=await lookup.async_nutrition(CODE)
    assert result['status']=='error' and result['nutriscore']['grade']=='c'
    exported=lookup.nutrition_export([{'id':'p','name':'Producto','barcodes':[CODE]}])
    assert exported[CODE.zfill(14)]['checked_at']==old
    lookup.common_index=SimpleNamespace(nutrition_cached=lambda _: {**exported[CODE.zfill(14)],'checked_at':old+1})
    await lookup.async_nutrition(CODE)
    fetch.assert_awaited_once()  # Shared stale data must not bypass the local error backoff.
