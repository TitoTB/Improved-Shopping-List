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
