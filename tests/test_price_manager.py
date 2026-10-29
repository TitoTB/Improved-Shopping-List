"""Receipt-only prices and retained source-format/link validation."""
from copy import deepcopy


import asyncio


from datetime import datetime, timezone


from types import SimpleNamespace


from unittest.mock import AsyncMock, Mock


import pytest


from homeassistant.core import SupportsResponse


from pytest_homeassistant_custom_component.common import MockConfigEntry


from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY, CONF_TODO_ENTITIES


from custom_components.improved_shopping_list.list_settings import ListSettings


from custom_components.improved_shopping_list.store_location import reference_location


from custom_components.improved_shopping_list.price_manager import PriceManager, StorePriceView


from custom_components.improved_shopping_list.price_sources import PriceError, PriceSources, carrefour_offer


from custom_components.improved_shopping_list.store_links import normalize_link, normalize_links


from custom_components.improved_shopping_list import price_manager as module


def product(name="Arroz", identifier="24097", store="alcampo"):
    return {"id":name, "name":name,"barcode":"", "barcodes":[], "store_links":{store:normalize_link(store, identifier)}}


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


def test_carrefour_numeric_internal_reference_can_differ_from_analytics_id():
    link=normalize_link("carrefour","R-521002958")
    data=carrefour_response(item_internal_id="521002958",item_id="150306",item_ean=["8410100024264"],price=5.99)
    offer=carrefour_offer(data,link)
    assert offer["price"]=="5.99" and offer["ean"]=="8410100024264"
    for internal in ("521002959","VC4AECOMM-150306"):
        with pytest.raises(PriceError):
            carrefour_offer(carrefour_response(item_internal_id=internal,item_id="150306"),link)
    with pytest.raises(PriceError):
        carrefour_offer({"impressions":data["impressions"]*2},link)


def test_carrefour_legacy_prod_reference_has_a_different_numeric_analytics_id():
    link = normalize_link("carrefour","R-prod310215")
    data = carrefour_response(item_internal_id="prod310215",item_id="371977",
        item_name="cafe-molido-natural-cultivo-sostenible-nestle-bonka-500-g",
        item_ean=["7613036039468"],price=7.59)
    offer = carrefour_offer(data,link)
    assert offer["price"] == "7.59" and offer["ean"] == "7613036039468"
    # Other suggestions may occur, but only the explicitly linked product matches.
    data["impressions"].append(carrefour_response()["impressions"][0])
    assert carrefour_offer(data,link) == offer
    for replacement in ("prod999999", "", "R-prod310215"):
        wrong = carrefour_response(item_internal_id=replacement,item_id="371977")
        with pytest.raises(PriceError) as error:
            carrefour_offer(wrong,link)
        assert error.value.diagnostics["match_count"] == 0
        assert error.value.diagnostics["returned_references"][0]["item_id"] == "371977"
    with pytest.raises(PriceError):
        carrefour_offer({"impressions":data["impressions"]*2},link)


async def test_carrefour_legacy_prod_reference_fetches_using_original_reference(hass,aioclient_mock):
    url = "https://www.carrefour.es/cloud-api/pdp-food-analytics/v1/impressions?product_id=R-prod310215"
    aioclient_mock.get(url,json=carrefour_response(item_internal_id="prod310215",item_id="371977",price=7.59))
    gate = AsyncMock()
    sources = PriceSources(hass)
    try:
        result = await sources.fetch("carrefour",normalize_link("carrefour","R-prod310215"),{"sale_point":"005290"},gate)
        assert result["reference_id"] == "R-prod310215" and result["price"] == "7.59"
        gate.assert_awaited_once()
    finally:
        sources.close()


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



async def test_only_confirmed_receipt_prices_are_exposed_and_no_providers_are_contacted(hass,aioclient_mock):
    catalog=SimpleNamespace(products=[product()])
    settings=SimpleNamespace(snapshot={"stores":{},"price_updates_enabled":True,"price_update_time":"01:00"})
    manager=PriceManager(hass,catalog,settings,None)
    manager._data["offers"]={"retired":{"price":"999.00","source":"community"}}
    manager._data["legacy_ean"]={"retired":{"price":"99.00","source":"legacy_feed"}}
    assert manager.prices_for(catalog.products[0])==[]
    receipt={"store":"carrefour","price":2.65,"source":"receipt","checked_at":123}
    manager.receipts=SimpleNamespace(offers_for=lambda _product:[receipt,{"price":99,"source":"community"}])
    assert [offer["price"] for offer in manager.prices_for(catalog.products[0])]==[2.65]
    manager.start()
    await manager.async_tick();await manager.async_refresh_all();await manager.async_refresh_store("carrefour")
    assert aioclient_mock.call_count==0 and not manager.progress["running"]
    await manager.async_stop()
    settings.snapshot["price_updates_enabled"]=False
    assert manager.prices_for(catalog.products[0])==[]


async def test_migration_cancels_stored_public_price_queue(hass,aioclient_mock):
    catalog=SimpleNamespace(products=[product()]);settings=SimpleNamespace(snapshot={"stores":{}})
    manager=PriceManager(hass,catalog,settings,None)
    await manager._store.async_save({"offers":{"external":{"source":"community","price":1}},"legacy_ean":{},"pending":[{"store":"carrefour"}]})
    await manager.async_load()
    assert (await manager._store.async_load())["pending"]==[]
    assert (await manager._store.async_load())["offers"]=={}
    assert manager.prices_for(catalog.products[0])==[]
    assert aioclient_mock.call_count==0
