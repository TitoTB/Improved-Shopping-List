"""Lidl reference validation and region-specific, general, currently valid prices."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.lidl import LIDL_REGIONS
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.price_sources import PriceError, PriceSources, lidl_offer
from custom_components.improved_shopping_list.store_links import normalize_link
from custom_components.improved_shopping_list.stores import StoreError

LINK = normalize_link("lidl", "11107037")
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc).timestamp()
URL = "https://www.lidl.es/p/api/gridboxes/ES/es?erpNumbers=11107037"


def response():
    return [{"erpNumber":"11107037", "itemId":11107037,"productId":11107037,
        "fullTitle":"Cuña de queso", "canonicalPath":"/p/cuna-de-queso/p11107037",
        "ians":["5720495"], "price":{"price":99},
        "regionsV2":{"28":{"status":"ONLINE","regionPriceId":"1"},
                     "26":{"status":"ONLINE","regionPriceId":"2"}},
        "regionsPrices":{"1":{"currentPrice":{"price":2.89,"currencyCode":"EUR",
            "startDate":"2026-10-18T22:00Z","endDateExclusive":"2026-10-25T22:00Z",
            "packaging":{"text":"250 g"},"discount":{"fromNormalPriceForLidlPlus":False}},
            "futureLidlPlusPrices":[{"price":1.99}]},
            "2":{"currentPrice":{"price":3.49,"currencyCode":"EUR"}}}}]


def test_regional_price_and_internal_ian_not_used_as_barcode():
    data = response()
    result = lidl_offer(data,LINK,"28",now=NOW)
    assert result["price"] == "2.89" and result["region_name"] == "Madrid"
    assert result["ean"] == "" and result["available"] is None
    assert result["url"] == "https://www.lidl.es/p/cuna-de-queso/p11107037"
    assert result["packaging"] == "250 g" and result["valid_until"] > NOW
    assert lidl_offer(data,LINK,"26",now=NOW)["price"] == "3.49"
    assert lidl_offer(data,LINK,"1",now=NOW) is None
    assert lidl_offer([],LINK,"28",now=NOW) is None
    data[0]["regionsV2"]["28"]["status"] = "OFFLINE"
    assert lidl_offer(data,LINK,"28",now=NOW) is None


@pytest.mark.parametrize("change", [
    {"startDate":"2099-01-01T00:00Z"}, {"endDateExclusive":"2020-01-01T00:00Z"},
    {"discount":{"fromNormalPriceForLidlPlus":True}}])
def test_future_expired_and_member_only_prices_are_not_current_prices(change):
    data = response()
    data[0]["regionsPrices"]["1"]["currentPrice"].update(change)
    assert lidl_offer(data,LINK,"28",now=NOW) is None


@pytest.mark.parametrize("change", [{"price":"NaN"},{"price":-1},{"currencyCode":"USD"},
    {"variantsHaveDifferentPrices":True},{"startDate":"2026-10-21"},{"discount":[1]}])
def test_bad_or_ambiguous_prices_rejected(change):
    data = response()
    data[0]["regionsPrices"]["1"]["currentPrice"].update(change)
    with pytest.raises(PriceError):
        lidl_offer(data,LINK,"28",now=NOW)


def test_identity_and_shape_must_match():
    for data in ({},response()*2,[{**response()[0],"itemId":99}],
                 [{**response()[0],"erpNumber":"999"}]):
        with pytest.raises(PriceError):
            lidl_offer(data,LINK,"28",now=NOW)
    with pytest.raises(PriceError):
        lidl_offer(response(),LINK,"999",now=NOW)


def test_online_zone_does_not_fall_back_to_other_zone():
    data = response()
    price = deepcopy(data[0]["regionsPrices"]["2"])
    del data[0]["regionsV2"]
    data[0]["zones"] = {"BAL":{**price,"statusOnlineActual":"ONLINE"}}
    assert lidl_offer(data,LINK,"48",now=NOW)["price"] == "3.49"
    assert lidl_offer(data,LINK,"28",now=NOW) is None
    assert lidl_offer(data,LINK,"51",now=NOW) is None


@pytest.mark.parametrize("value",["https://example.org/p/foo/p11107037",
    "http://www.lidl.es/p/foo/p11107037", "https://www.lidl.es@localhost/p/foo/p11107037",
    "https://www.lidl.es:123/p/foo/p11107037", "../11107037"])
def test_untrusted_links_rejected(value):
    with pytest.raises(ValueError):
        normalize_link("lidl",value)


def test_link_normalizes_id_and_discards_tracking():
    assert LINK["id"] == "11107037"
    assert normalize_link("lidl","https://www.lidl.es/p/queso/p11107037?utm_source=test#x") == {
        "id":"11107037","url":"https://www.lidl.es/p/queso/p11107037"}


async def test_anonymous_api_uses_reference_and_pacing(hass,aioclient_mock,monkeypatch):
    import aiohttp
    captured = []
    original = aiohttp.ClientSession.get
    def get(session,url,**kwargs):
        captured.append(kwargs)
        return original(session,url,**kwargs)
    monkeypatch.setattr(aiohttp.ClientSession,"get",get)
    data = response()
    price = data[0]["regionsPrices"]["1"]["currentPrice"]
    price.update(startDate="2020-01-01T00:00Z",endDateExclusive="2099-01-01T00:00Z")
    aioclient_mock.get(URL,json=data)
    before = AsyncMock()
    result = await PriceSources(hass).fetch("lidl",LINK,{"region_id":"28"},before)
    assert result["price"] == "2.89" and result["reference_id"] == "11107037"
    before.assert_awaited_once()
    headers = captured[0]["headers"]
    assert headers["Referer"] == LINK["url"] and headers["Accept"] == "application/json"
    assert not any(key.lower() in ("cookie","authorization","x-apikey") for key in headers)
    assert captured[0]["allow_redirects"] is False


@pytest.mark.parametrize("status",[403,429])
async def test_http_failure_has_actionable_diagnostics(hass,aioclient_mock,status):
    aioclient_mock.get(URL,status=status,headers={"Retry-After":"300"})
    with pytest.raises(PriceError) as caught:
        await PriceSources(hass).fetch("lidl",LINK,{"region_id":"28"},AsyncMock())
    assert caught.value.diagnostics["region_id"] == "28"
    assert caught.value.diagnostics["http_status"] == status
    assert caught.value.diagnostics["retry_seconds"] == 300


async def test_invalid_region_makes_no_request(hass,aioclient_mock):
    before = AsyncMock()
    with pytest.raises(PriceError):
        await PriceSources(hass).fetch("lidl",LINK,{"region_id":""},before)
    before.assert_not_awaited()
    assert aioclient_mock.call_count == 0


async def test_settings_require_region_and_preserve_favorite_and_options(hass):
    entry = MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"},options={
        "stores":{"carrefour":{"enabled":True}},"favorite_store":"carrefour","other":True})
    entry.add_to_hass(hass)
    settings = ListSettings(hass); settings.attach(entry)
    hass.data[DOMAIN] = {"active":True}
    assert settings.snapshot["stores"]["lidl"] == {"enabled":False,"region_id":""}
    with pytest.raises(StoreError):
        await settings.async_update_lidl(True,"")
    await settings.async_update_lidl(True,"28")
    assert settings.snapshot["favorite_store"] == "carrefour"
    await settings.async_favorite_store("lidl")
    assert settings.snapshot["favorite_store"] == "lidl"
    await settings.async_update_lidl(False,"")
    assert settings.snapshot["stores"]["lidl"] == {"enabled":False,"region_id":"28"}
    assert settings.snapshot["favorite_store"] == "carrefour" and entry.options["other"]
    settings.detach()
    with pytest.raises(StoreError):
        await settings.async_update_lidl(True,"28")


async def test_websocket_configuration_and_region_list(hass,hass_ws_client,aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/settings/lidl_regions"})
    assert len((await client.receive_json())["result"]["regions"]) == len(LIDL_REGIONS)
    await client.send_json({"id":2,"type":f"{DOMAIN}/settings/store","store":"lidl","enabled":True,"region_id":"28"})
    assert (await client.receive_json())["result"]["stores"]["lidl"]["region_id"] == "28"
    await client.send_json({"id":3,"type":f"{DOMAIN}/catalog/store_prices","store":"lidl"})
    assert (await client.receive_json())["result"]["products"] == []
    assert aioclient_mock.call_count == 0
