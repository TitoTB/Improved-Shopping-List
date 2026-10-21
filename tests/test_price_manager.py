"""Daily selection, durable pacing, cache retention and direct reference lookups."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import SupportsResponse

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.price_manager import PriceManager, StorePriceView
from custom_components.improved_shopping_list.price_sources import PriceError, PriceSources, carrefour_offer
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


async def test_retired_provider_cache_and_queue_migrate_without_touching_other_prices(env,hass):
    await env.manager.async_tick()
    kept = deepcopy(env.manager._data["offers"])
    data = env.manager._data
    data["offers"]["lidl:28:11107037"] = {"store":"lidl","price":"2.89"}
    data["attempts"]["lidl:28:11107037"] = "2026-10-20"
    data["legacy_ean"]["lidl:0012345"] = {"store":"lidl","price":"2.89"}
    data["errors"].update(lidl="Old failure",carrefour="Preserved failure")
    data["blocked_until"]["lidl"] = env.clock[0]+3600
    data["blocked_day"]["lidl"] = "2026-10-20"
    other_job = {"store":"alcampo","link":normalize_link("alcampo","1234"),"scope":""}
    data.update(pending=[{"store":"lidl","link":{"id":"11107037"},"scope":"28"},other_job],total=3,processed=1)
    await env.manager._save()
    restored = PriceManager(hass,env.catalog,env.settings,env.manager.activity)
    await restored.async_load()
    assert restored._data["offers"] == kept
    assert restored._data["pending"] == [other_job]
    assert restored._data["processed"] == 2 and restored._data["total"] == 3
    assert restored._data["errors"] == {"carrefour":"Preserved failure"}
    for name in ("offers","attempts","legacy_ean","errors","blocked_day","blocked_until"):
        assert not any(key.startswith("lidl") for key in restored._data[name])
    assert len(env.requests) == 1  # Loading/migrating does not make requests.
    stored = await restored._store.async_load()
    assert stored["pending"] == [other_job]


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


async def test_daily_run_with_no_enabled_stores_does_not_read_lists_or_log_a_queue(env):
    for configuration in env.settings.snapshot["stores"].values():
        configuration["enabled"] = False
    env.manager.pending_names = AsyncMock(side_effect=AssertionError("No list read expected"))
    await env.manager.async_tick()
    assert env.requests == [] and env.manager._data["pending"] == []
    env.manager.activity.record.assert_not_called()


async def test_last_price_remains_when_bought_and_failure_does_not_overwrite(env):
    assert env.manager.progress["last_updated"] == 0
    await env.manager.async_tick()
    updated = env.manager.progress["last_updated"]
    assert updated == env.clock[0]
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
    assert "403" in env.manager.progress["errors"]["alcampo"]
    assert env.manager.progress["last_updated"] == updated


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


async def test_manual_daytime_run_only_pending_selected_store_and_shared_pacing(env):
    env.manager._queue = Mock()
    env.clock[0] += 12*3600
    env.items["todo.one"].append({"summary":"Café","status":"needs_action"})
    env.catalog.products.append(product("Arroz","69938","mercadona"))
    result = await env.manager.async_refresh_store("alcampo")
    assert result["queued"] == 2 and not env.requests
    await env.manager.async_tick()
    assert len(env.requests) == 1
    # Clicking again while the remaining references wait does not requeue the first.
    await env.manager.async_refresh_store("alcampo")
    assert len(env.manager._data["pending"]) == 1
    env.clock[0] += 299
    await env.manager.async_tick()
    assert len(env.requests) == 1
    env.clock[0] += 1
    await env.manager.async_tick()
    assert len(env.requests) == 2 and all(request[0] == "alcampo" for request in env.requests)
    assert env.manager.activity.record.call_args.kwargs["source"] == "manual"


async def test_manual_can_repeat_today_but_preserves_five_minute_wait(env):
    env.manager._queue = Mock()
    await env.manager.async_tick()
    assert len(env.requests) == 1
    await env.manager.async_refresh_store("alcampo")
    await env.manager.async_tick()
    assert len(env.requests) == 1
    env.clock[0] += 300
    await env.manager.async_tick()
    assert len(env.requests) == 2


async def test_manual_skips_bought_during_wait_and_keeps_last_price(env):
    env.manager._queue = Mock()
    await env.manager.async_tick()
    old = deepcopy(env.manager._data["offers"])
    await env.manager.async_refresh_store("alcampo")
    env.items["todo.one"] = env.items["todo.two"] = []
    env.clock[0] += 300
    await env.manager.async_tick()
    assert len(env.requests) == 1 and env.manager._data["offers"] == old
    assert not env.manager._data["pending"]


async def test_manual_rejects_disabled_unavailable_lists_and_server_wait(env,hass):
    env.manager._queue = Mock()
    env.settings.snapshot["stores"]["alcampo"]["enabled"] = False
    with pytest.raises(ValueError,match="Habilita"):
        await env.manager.async_refresh_store("alcampo")
    env.settings.snapshot["stores"]["alcampo"]["enabled"] = True
    hass.states.async_set("todo.one","unavailable")
    with pytest.raises(ValueError,match="listas"):
        await env.manager.async_refresh_store("alcampo")
    env.manager._data["blocked_until"]["alcampo"] = env.clock[0]+600
    with pytest.raises(ValueError,match="pausa"):
        await env.manager.async_refresh_store("alcampo")
    assert not env.requests


async def test_manual_reserved_request_not_replayed_after_restart(env,hass):
    env.manager._queue = Mock()
    env.clock[0] += 12*3600
    await env.manager.async_refresh_store("alcampo")
    job = env.manager._data["pending"][0]
    job["reserved"] = True  # Crash after durable reservation, before reply.
    await env.manager._save()
    restored = PriceManager(hass,env.catalog,env.settings,env.manager.activity)
    await restored.async_load()
    restored._active = True
    restored.sources = env.manager.sources
    await restored.async_tick()
    assert not env.requests and not restored._data["pending"]


async def test_unavailable_list_does_not_block_known_pending_from_other_list(env,hass):
    hass.states.async_set("todo.one", "unavailable")
    await env.manager.async_tick()
    assert len(env.requests) == 1


async def test_lists_can_finish_starting_during_the_nightly_window(env,hass):
    for entity in env.settings.snapshot["entities"]:
        hass.states.async_set(entity,"unavailable")
    await env.manager.async_tick()
    assert not env.requests
    env.clock[0] += 300
    for entity in env.settings.snapshot["entities"]:
        hass.states.async_set(entity,"1")
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
    assert error.value.diagnostics["endpoint"] == "/api/webproductpagews/v5/products/bop"
    assert error.value.diagnostics["region_id"] == ""


@pytest.mark.parametrize("region",["", "ac90d761-9d58-4918-a37d-dd14e1ce384a"])
async def test_alcampo_anonymous_headers_region_and_product_metadata(hass,aioclient_mock,monkeypatch,region):
    import aiohttp
    from custom_components.improved_shopping_list import price_sources
    create_session = price_sources.async_create_clientsession
    def anonymous_session(hass,**kwargs):
        # The HA test fixture replaces the returned session and its cookie jar.
        assert isinstance(kwargs["cookie_jar"],aiohttp.DummyCookieJar)
        return create_session(hass,**kwargs)
    monkeypatch.setattr(price_sources,"async_create_clientsession",anonymous_session)
    captured = []
    original_get = aiohttp.ClientSession.get
    def get(session,url,**kwargs):
        captured.append(kwargs)
        return original_get(session,url,**kwargs)
    monkeypatch.setattr(aiohttp.ClientSession,"get",get)
    url = "https://www.compraonline.alcampo.es/api/webproductpagews/v5/products/bop?retailerProductId=10739"
    if region:
        url += "&regionId=" + region
    aioclient_mock.get(url,json={"product":{"retailerProductId":"10739","name":"Patatas",
        "price":{"amount":"2.65","currency":"EUR"},"available":True,
        "unitPrice":{"price":{"amount":"15.59","currency":"EUR"},"unitName":"PER_1KG"}},
        "bopData":{"fields":[{"title":"features","content":"<table><tr><td>EAN</td><td>8410199023094</td></tr></table>"}]}})
    link = normalize_link("alcampo","https://www.compraonline.alcampo.es/products/patatas/10739")
    before = AsyncMock()
    result = await PriceSources(hass).fetch("alcampo",link,{"region_id":region},before)
    assert result["price"] == "2.65" and result["ean"] == "8410199023094"
    assert result["reference_price"] == "15.59" and result["reference_unit"] == "PER_1KG"
    assert result["available"] is True and result["reference_id"] == "10739"
    assert captured[0]["headers"] == {"Accept":"application/json",
        "User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)",
        "Referer":link["url"],"ecom-request-source":"web"}
    assert captured[0]["allow_redirects"] is False
    before.assert_awaited_once()


def carrefour_response(**changes):
    return {"impressions":[{"item_id":"491998", "item_internal_id":"VC4AECOMM-491998",
        "item_name":"anacardo-crudo-original-carrefour-200-g", "price":2.69, "currency":"EUR",
        "item_ean":["3560071237950"], **changes}]}


@pytest.mark.parametrize("changes",[
    {"item_id":"9999"}, {"item_internal_id":"VC4AECOMM-9999"},
    {"currency":"USD"}, {"price":None}, {"price":"NaN"}, {"price":-1}])
def test_carrefour_json_rejects_wrong_reference_or_price(changes):
    with pytest.raises(PriceError):
        carrefour_offer(carrefour_response(**changes),normalize_link("carrefour","R-VC4AECOMM-491998"))


def test_carrefour_empty_and_ambiguous_responses():
    link = normalize_link("carrefour","R-VC4AECOMM-491998")
    assert carrefour_offer({"impressions":[]},link) is None
    for data in ({}, {"impressions":{}}, {"impressions":carrefour_response()["impressions"]*2}):
        with pytest.raises(PriceError):
            carrefour_offer(data,link)


async def test_carrefour_api_uses_center_without_session_and_validates_result(hass,aioclient_mock,monkeypatch):
    import aiohttp
    captured = []
    original_get = aiohttp.ClientSession.get
    def get(session,url,**kwargs):
        captured.append(kwargs["headers"])
        return original_get(session,url,**kwargs)
    monkeypatch.setattr(aiohttp.ClientSession,"get",get)
    url = "https://www.carrefour.es/cloud-api/pdp-food-analytics/v1/impressions?product_id=R-VC4AECOMM-491998"
    aioclient_mock.get(url,json=carrefour_response())
    link = normalize_link("carrefour","https://www.carrefour.es/supermercado/anacardo-crudo-original-carrefour-200-g/R-VC4AECOMM-491998/p")
    before = AsyncMock()
    result = await PriceSources(hass).fetch("carrefour",link,{"sale_point":"005290"},before)
    assert result["price"] == "2.69" and result["ean"] == "3560071237950" and result["sale_point"] == "005290"
    assert result["available"] is None
    assert captured[0]["sale_point"] == "005290" and captured[0]["Referer"] == link["url"]
    assert not any(key.lower() in ("cookie","authorization","jsessionid","profile_id","session_id") for key in captured[0])
    before.assert_awaited_once()


async def test_carrefour_centers_keep_independent_cached_prices(env):
    env.manager._queue = Mock()
    env.catalog.products = [product("Arroz","R-VC4AECOMM-491998","carrefour")]
    env.settings.snapshot["stores"]["carrefour"]["sale_point"] = "005290"
    await env.manager.async_tick()
    assert env.manager.prices_for(env.catalog.products[0])
    env.settings.snapshot["stores"]["carrefour"]["sale_point"] = "123456"
    assert not env.manager.prices_for(env.catalog.products[0])
    assert env.manager._data["offers"]  # The former center's prices remain stored.
    await env.manager.async_refresh_store("carrefour")
    env.clock[0] += 300
    await env.manager.async_tick()
    assert env.manager.prices_for(env.catalog.products[0])[0]["scope"] == "123456"
    assert len(env.manager._data["offers"]) == 2


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
