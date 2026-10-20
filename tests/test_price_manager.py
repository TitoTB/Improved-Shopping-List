"""Daily selection, durable pacing, cache retention and direct reference lookups."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import SupportsResponse

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.price_manager import PriceManager, StorePriceView
from custom_components.improved_shopping_list.price_sources import PriceError, PriceSources, structured_offer
from custom_components.improved_shopping_list.store_links import normalize_link, normalize_links
from custom_components.improved_shopping_list import price_manager as module


def product(name="Arroz", identifier="24097", store="alcampo"):
    return {"id":name, "name":name,"barcode":"", "barcodes":[], "store_links":{store:normalize_link(store, identifier)}}


@pytest.fixture
async def env(hass, monkeypatch):
    clock = [datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda:clock[0]))
    monkeypatch.setattr(module, "dt_util", SimpleNamespace(now=lambda:datetime.fromtimestamp(clock[0], timezone.utc)))
    hass.data[DOMAIN] = {"active":True}
    config = {"entities":["todo.one","todo.two"], "price_update_time":"01:00", "stores":{
        "mercadona":{"enabled":True,"warehouse":"mad3"}, "carrefour":{"enabled":True}, "alcampo":{"enabled":True,"region_id":""}}}
    settings = SimpleNamespace(snapshot=config, entry=object(), _generation=1)
    catalog = SimpleNamespace(products=[product(),product("Café","1234"),product("Otro","5678")])
    manager = PriceManager(hass,catalog,settings,SimpleNamespace(record=Mock()))
    await manager.async_load()
    manager._active = True
    state = SimpleNamespace(manager=manager, clock=clock, settings=settings, catalog=catalog,
        items={"todo.one":[{"summary":"ARROZ","status":"needs_action"},{"summary":"Café","status":"completed"}],
               "todo.two":[{"summary":"arroz","status":"needs_action"}]}, requests=[])
    for entity in config["entities"]:
        hass.states.async_set(entity, "1")
    async def get_items(call):
        return {call.data["entity_id"]:{"items":deepcopy(state.items[call.data["entity_id"]])}}
    hass.services.async_register("todo","get_items",get_items,supports_response=SupportsResponse.ONLY)
    async def fetch(store,link,config,before_request):
        await before_request()
        state.requests.append((store,link["id"],clock[0]))
        return {"store":store,"reference_id":link["id"],"url":link["url"],"store_name":"Arroz 500 g", "price":"1.05","currency":"EUR","ean":"3596710387427"}
    manager.sources.fetch = AsyncMock(side_effect=fetch)
    yield state
    await manager.async_stop()


async def test_pending_union_deduplicates_and_reads_do_not_fetch(env):
    view = StorePriceView(env.manager, "alcampo")
    await view.async_refresh(force=True)
    assert env.requests == []
    await env.manager.async_tick()
    assert len(env.requests) == 1
    assert env.manager._data["total"] == 1
    assert env.manager.snapshot("alcampo")["products"][0]["price"] == "1.05"
    assert env.catalog.products[0]["barcode"] == ""  # Store metadata does not reassign scanner codes.
    await env.manager.async_tick()
    assert len(env.requests) == 1


async def test_last_price_remains_when_bought_and_failure_does_not_overwrite(env):
    await env.manager.async_tick()
    old = deepcopy(env.manager._data["offers"])
    env.items["todo.one"] = env.items["todo.two"] = []
    env.clock[0] += 86400
    await env.manager.async_tick()
    assert len(env.requests) == 1
    assert env.manager._data["offers"] == old
    assert env.manager.prices_for(env.catalog.products[0])[0]["price"] == "1.05"
    env.clock[0] += 86400
    env.items["todo.one"] = [{"summary":"Arroz","status":"needs_action"}]
    env.manager.sources.fetch.side_effect = PriceError("Bloqueado HTTP 403",http_status=403)
    await env.manager.async_tick()
    assert env.manager._data["offers"] == old
    assert "403" in env.manager.snapshot("alcampo")["error"]


async def test_five_minutes_persist_after_restart_and_skip_removed_items(env, hass):
    env.items["todo.one"].append({"summary":"Café","status":"needs_action"})
    await env.manager.async_tick()
    assert len(env.requests) == 1 and len(env.manager._data["pending"]) == 1
    restored = PriceManager(hass,env.catalog,env.settings,env.manager.activity)
    await restored.async_load()
    restored._active = True
    restored.sources = env.manager.sources
    env.clock[0] += 299
    await restored.async_tick()
    assert len(env.requests) == 1
    env.items["todo.one"] = env.items["todo.two"] = []
    env.clock[0] += 1
    await restored.async_tick()
    assert len(env.requests) == 1 and restored._data["pending"] == []


async def test_no_daytime_first_run_and_daily_configurable_start(env):
    env.clock[0] += 12*3600
    await env.manager.async_tick()
    assert env.requests == []
    env.settings.snapshot["price_update_time"] = "13:00"
    await env.manager.async_tick()
    assert len(env.requests) == 1
    env.settings.snapshot["price_update_time"] = "13:10"
    env.clock[0] += 600
    await env.manager.async_tick()
    assert len(env.requests) == 1


async def test_blocked_store_stops_but_other_store_continues(env):
    env.catalog.products = [product("Arroz"), product("Segundo","1234"), product("Tomate","69938","mercadona")]
    env.items["todo.one"] = [{"summary":p["name"],"status":"needs_action"} for p in env.catalog.products]
    original = env.manager.sources.fetch.side_effect
    async def fetch(store,link,config,before_request):
        if store == "alcampo":
            await before_request()
            raise PriceError("Alcampo HTTP 403",http_status=403)
        return await original(store,link,config,before_request)
    env.manager.sources.fetch.side_effect = fetch
    await env.manager.async_tick()
    assert env.requests == []
    env.clock[0] += 300
    await env.manager.async_tick()
    assert len(env.requests) == 1 and env.requests[0][0] == "mercadona"
    assert not env.manager._data["pending"]


async def test_late_reply_after_binding_change_is_not_attached(env):
    original = env.manager.sources.fetch.side_effect
    async def fetch(*args):
        result = await original(*args)
        env.catalog.products[0]["store_links"] = {"alcampo":normalize_link("alcampo","1234")}
        return result
    env.manager.sources.fetch.side_effect = fetch
    await env.manager.async_tick()
    assert not env.manager._data["offers"]


@pytest.mark.parametrize("store,value,identifier",[
    ("alcampo","24097","24097"),
    ("alcampo","https://www.compraonline.alcampo.es/products/arroz/24097?tracking=discard","24097"),
    ("mercadona","https://tienda.mercadona.es/product/69938/tomate","69938"),
    ("carrefour","https://www.carrefour.es/supermercado/arroz/R-VC4AECOMM-724474/p","R-VC4AECOMM-724474")])
def test_reference_parsing(store,value,identifier):
    assert normalize_link(store,value)["id"] == identifier
    assert "?" not in normalize_link(store,value)["url"]


@pytest.mark.parametrize("value",["http://www.compraonline.alcampo.es/products/a/1", "https://localhost/products/a/1",
    "https://www.compraonline.alcampo.es.evil.test/products/a/1", "https://user:pass@www.compraonline.alcampo.es/products/a/1",
    "https://www.compraonline.alcampo.es:8443/products/a/1", "https://www.compraonline.alcampo.es/api/private/1", "1\n2"])
def test_unsafe_links_rejected_before_network(value):
    with pytest.raises(ValueError):
        normalize_link("alcampo",value)


async def test_public_alcampo_api_and_403_are_distinct_from_not_found(hass,aioclient_mock):
    source = PriceSources(hass)
    url = "https://www.compraonline.alcampo.es/api/webproductpagews/v5/products/bop?retailerProductId=24097"
    aioclient_mock.get(url,json={"product":{"retailerProductId":"24097","name":"Arroz","price":{"amount":"1.05","currency":"EUR"}},"bopData":{}})
    before = AsyncMock()
    result = await source.fetch("alcampo",normalize_link("alcampo","24097"),{},before)
    assert result["price"] == "1.05" and result["reference_id"] == "24097"
    before.assert_awaited_once()
    aioclient_mock.get(url.replace("24097","9999"),status=403)
    with pytest.raises(PriceError) as error:
        await source.fetch("alcampo",normalize_link("alcampo","9999"),{},before)
    assert error.value.diagnostics["http_status"] == 403


def test_carrefour_structured_price_must_match_reference():
    body = '<script type="application/ld+json">{"@type":"Product","sku":"724474","name":"Arroz","offers":{"price":"2.09","priceCurrency":"EUR"}}</script>'
    link = normalize_link("carrefour","R-VC4AECOMM-724474")
    assert structured_offer(body,link)["price"] == "2.09"
    with pytest.raises(PriceError):
        structured_offer(body.replace('"724474"','"99999"'),link)


async def test_mercadona_reference_does_not_require_ean(hass,aioclient_mock):
    source = PriceSources(hass)
    aioclient_mock.get("https://tienda.mercadona.es/api/products/69938/?lang=es&wh=mad3",json={
        "id":"69938","display_name":"Tomate","price_instructions":{"unit_price":"1.45"}})
    result = await source.fetch("mercadona",normalize_link("mercadona","69938"),{"warehouse":"mad3"},AsyncMock())
    assert result["price"] == "1.45" and result["ean"] == ""


async def test_bindings_persist_and_old_clients_do_not_erase_them(hass):
    from custom_components.improved_shopping_list.catalog import Catalog, FIELDS, CatalogError
    catalog = Catalog(hass)
    await catalog.async_load()
    saved = await catalog.async_save_product({"name":"Arroz", "store_links":{"alcampo":"24097"}})
    assert saved["store_links"]["alcampo"]["id"] == "24097"
    old_payload = {key:value for key,value in saved.items() if key in FIELDS and key != "store_links"}
    saved = await catalog.async_save_product(old_payload)
    assert saved["store_links"]["alcampo"]["id"] == "24097"
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products[0]["store_links"] == saved["store_links"]
    with pytest.raises(CatalogError):
        await catalog.async_save_product({"name":"Error","store_links":{"alcampo":"https://localhost/products/a/1"}})
