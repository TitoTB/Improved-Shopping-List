"""Explicit product retrieval: identity, bounded requests and durable option metadata."""
import json
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.option_lookup import OptionLookup, page_product
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.product_references import normalized_references
from custom_components.improved_shopping_list.store_links import normalize_link

URL = "https://www.carrefour.es/supermercado/pavo/R-prod1/p"
CODE = "3017620422003"


async def test_retired_eci_lookup_never_queries_the_provider(hass,monkeypatch):
    lookup=OptionLookup(hass)
    request=AsyncMock()
    monkeypatch.setattr(lookup,'_page',request)
    try:
        with pytest.raises(PriceError,match='retirada temporalmente'):
            await lookup.retrieve('https://www.elcorteingles.es/supermercado/B001018009401193-patatas/')
        request.assert_not_awaited()
    finally:lookup.close()


def html_product(**changes):
    product = {"@type":"Product", "url":URL, "name":"Pavo 250 g", "brand":{"name":"marca"},
        "gtin13":CODE, "offers":{"price":"2.50","priceCurrency":"EUR"},
        "image":"https://example.test/pavo.png", "additionalProperty":[{"name":"Nutri-Score","value":"A"}]}
    product.update(changes)
    return '<script type="application/ld+json">'+json.dumps(product)+'</script>'


def test_structured_product_fields_require_one_matching_reference():
    result = page_product(html_product(),"carrefour",normalize_link("carrefour",URL))
    assert result["name"] == "Pavo 250 g" and result["brand"] == "Marca"
    assert result["content_quantity"] == 250 and result["content_unit"] == "g"
    assert result["price"] == 2.5 and result["ean"] == CODE and result["nutriscore"]["grade"] == "a"
    assert page_product(html_product(url=URL.replace("prod1","prod2")),"carrefour",normalize_link("carrefour",URL)) is None
    assert page_product(html_product()+html_product(),"carrefour",normalize_link("carrefour",URL)) is None
    pending = page_product(html_product(offers={"price":"NaN","priceCurrency":"EUR"}),"carrefour",normalize_link("carrefour",URL))
    assert "price" not in pending and pending["brand"] == "Marca"


async def test_lookup_uses_public_metadata_cache_and_checks_the_ean(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    fetch = AsyncMock(side_effect=AssertionError("Complete page must not call a second source"))
    monkeypatch.setattr(lookup.sources,"fetch",fetch)
    aioclient_mock.get(URL,text=html_product())
    try:
        result = await lookup.retrieve(URL, expected_ean=CODE)
        assert result["store"] == "carrefour" and result["price"] == 2.5
        assert await lookup.retrieve(URL) == result
        assert aioclient_mock.call_count == 1
        with pytest.raises(PriceError, match="EAN"):
            await lookup.retrieve(URL, expected_ean="4006381333931")
        assert aioclient_mock.call_count == 1
    finally:
        lookup.close()


async def test_blocked_page_can_use_the_existing_official_endpoint(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    fetch = AsyncMock(return_value={"store_name":"Pavo 250 g","brand":{"name":"marca API"},"price":"2.75","currency":"EUR","ean":CODE})
    monkeypatch.setattr(lookup.sources,"fetch",fetch)
    aioclient_mock.get(URL,status=403)
    try:
        result = await lookup.retrieve(URL,"carrefour")
        assert result["price"] == 2.75 and result["content_quantity"] == 250 and result["brand"] == "Marca API"
        assert fetch.await_count == 1
        assert not lookup._blocked_until.get("carrefour")
    finally:
        lookup.close()


async def test_missing_product_and_rejected_api_keep_both_diagnostics(hass, aioclient_mock, monkeypatch):
    lookup=OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    url="https://www.compraonline.alcampo.es/products/allioli/722018"
    body="<html><body>Contenido sin producto</body></html>"
    aioclient_mock.get(url,text=body,headers={"Content-Type":"text/html","Server":"test-edge"})
    fetch=AsyncMock(side_effect=PriceError("Consulta rechazada",http_status=403,response_class="access_denied",
        endpoint="/api/webproductpagews/v5/products/bop",server="CloudFront"))
    monkeypatch.setattr(lookup.sources,"fetch",fetch)
    try:
        with pytest.raises(PriceError,match="HTTP 403") as raised:
            await lookup.retrieve(url)
        info=raised.value.diagnostics
        assert info["http_status"]==403 and info["retry_seconds"]>0
        page,api=info["attempts"]
        assert page["stage"]=="product_page" and page["http_status"]==200
        assert page["response_class"]=="structured_product_missing" and page["response_bytes"]==len(body)
        assert api["stage"]=="product_api" and api["http_status"]==403 and api["server"]=="CloudFront"
        assert lookup._blocked_until["alcampo"]>0 and aioclient_mock.call_count==1
    finally:
        lookup.close()


async def test_rate_limit_keeps_http_details_and_does_not_try_the_api(hass, aioclient_mock, monkeypatch):
    lookup=OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    fetch=AsyncMock()
    monkeypatch.setattr(lookup.sources,"fetch",fetch)
    aioclient_mock.get(URL,status=429,headers={"Retry-After":"1800","Server":"test-edge"})
    try:
        with pytest.raises(PriceError) as raised:
            await lookup.retrieve(URL)
        info=raised.value.diagnostics
        assert info["response_class"]=="rate_limited" and info["retry_seconds"]>=1790
        assert info["attempts"][0]["http_status"]==429
        fetch.assert_not_awaited()
    finally:
        lookup.close()


async def test_official_url_corrects_the_store_and_keeps_ean_validation(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    fetch = AsyncMock(side_effect=AssertionError("Complete page must not call a second source"))
    monkeypatch.setattr(lookup.sources,"fetch",fetch)
    url="https://www.compraonline.alcampo.es/products/delta-caf%C3%A9-220-g/540978"
    aioclient_mock.get(url,text=html_product(url=url,gtin13="5601082041728"))
    try:
        result=await lookup.retrieve(url+"?srsltid=tracking","carrefour",expected_ean="5601082041728")
        assert result["store"]=="alcampo" and result["reference_id"]=="540978" and result["url"]==url
        assert aioclient_mock.call_count==1
        with pytest.raises(PriceError,match="EAN"):
            await lookup.retrieve(url,"carrefour",expected_ean=CODE)
        assert aioclient_mock.call_count==1
    finally:
        lookup.close()


async def test_numeric_carrefour_option_recovers_when_html_is_blocked(hass, aioclient_mock, monkeypatch):
    lookup=OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    url="https://www.carrefour.es/supermercado/cafe-molido-natural-puro-colombia-cultivo-sostenible-bonka-nestle-250-g/R-521002958/p"
    aioclient_mock.get(url,status=403)
    aioclient_mock.get("https://www.carrefour.es/cloud-api/pdp-food-analytics/v1/impressions?product_id=R-521002958",json={"impressions":[{
        "item_internal_id":"521002958","item_id":"150306","item_name":"cafe-molido-natural-puro-colombia-cultivo-sostenible-bonka-nestle-250-g",
        "item_brand":"bonka","item_ean":["8410100024264"],"price":5.99,"currency":"EUR"}]})
    try:
        result=await lookup.retrieve(url,"carrefour")
        assert result["reference_id"]=="R-521002958" and result["ean"]=="8410100024264"
        assert result["price"]==5.99 and result["brand"]=="Bonka" and result["content_quantity"]==250 and result["content_unit"]=="g"
        assert aioclient_mock.call_count==2
    finally:
        lookup.close()


async def test_unknown_hosts_and_external_redirects_are_never_requested(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup,"_before_request",AsyncMock())
    monkeypatch.setattr(lookup.sources,"fetch",AsyncMock(return_value=None))
    try:
        for url in ("http://127.0.0.1/test","https://example.test/product","https://www.carrefour.es@127.0.0.1/test"):
            with pytest.raises(ValueError):
                await lookup.retrieve(url)
        assert aioclient_mock.call_count == 0
        aioclient_mock.get(URL,status=302,headers={"Location":"http://127.0.0.1/internal"})
        with pytest.raises(PriceError):
            await lookup.retrieve(URL)
        assert aioclient_mock.call_count == 1
    finally:
        lookup.close()


async def test_retrieved_option_is_only_saved_with_the_product_and_feeds_prices(hass, hass_ws_client, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.main"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    data = hass.data[DOMAIN]
    monkeypatch.setattr(data["option_lookup"],"retrieve",AsyncMock(return_value={"store":"carrefour","reference_id":"R-prod1", "url":URL,
        "name":"Pavo 250 g","ean":CODE,"brand":"Marca","image_url":"https://example.com/pavo.png","content_quantity":250,"content_unit":"g","price":2.5,"currency":"EUR","checked_at":1800000000}))
    monkeypatch.setattr(data["readers"].lookup,"async_lookup",AsyncMock(return_value={"nutriscore":{"grade":"b","checked_at":1800000000}}))
    client = await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/catalog/retrieve_option","url":URL})
    result = (await client.receive_json())["result"]
    assert result["nutriscore"]["grade"] == "b" and data["catalog"].products == []
    ref = {key:result[key] for key in ("store","reference_id","url","name","ean","brand","image_url","content_quantity","content_unit","nutriscore")}
    ref.update(content_confirmed=True,last_price={key:result[key] for key in ("price","currency","checked_at")})
    await client.send_json({"id":2,"type":f"{DOMAIN}/catalog/save","product":{"name":"Pavo","commercial_references":[ref]}})
    product = (await client.receive_json())["result"]["product"]
    assert product["name"] == "Pavo" and product["commercial_references"][0]["last_price"]["price"] == 2.5
    assert product["commercial_references"][0]["image_url"] == result["image_url"]
    offers = data["price_manager"].prices_for(product)
    assert offers[0]["price"] == 2.5 and offers[0]["pack_quantity"] == 250
    assert data["price_history"]._entries[-1]["price"] == 2.5
    assert data["stock"].snapshot["items"] == []
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_option_prices_and_nutriscore_are_validated():
    ref = {"store":"carrefour","reference_id":"R-prod1","last_price":{"price":float("nan"),"currency":"EUR","checked_at":1800000000}}
    with pytest.raises(ValueError):
        normalized_references([ref])
    ref.pop("last_price")
    ref["nutriscore"] = {"grade":"z","checked_at":1800000000}
    with pytest.raises(ValueError):
        normalized_references([ref])
