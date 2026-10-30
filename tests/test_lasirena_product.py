"""La Sirena API identity, total package size, price and bounded lookup."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.improved_shopping_list.lasirena_product import product_data
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.price_sources import PriceError
from custom_components.improved_shopping_list.store_links import normalize_link

URL = "https://www.lasirena.es/es/lomos-de-salmon-noruego-premium-655/p"
API = "https://www.lasirena.es/api/catalog_system/pub/products/search?fq=productId:655"


def payload():
    return [{"productId": "655", "productName": "Lomos de salmón noruego Premium", "brand": "la Sirena",
        "Envase": ["Pack 4 x 125 g"], "items": [{"itemId": "655", "ean": "8414532006553",
        "measurementUnit": "un", "unitMultiplier": 1,
        "sellers": [{"sellerDefault": True, "commertialOffer": {"Price": 16.99, "IsAvailable": True}}]}]}]


def test_real_api_format_uses_total_package_not_sku_multiplier():
    result = product_data(payload(), normalize_link("lasirena", URL))
    assert result["ean"] == "8414532006553"
    assert result["brand"] == "La Sirena"
    assert (result["content_quantity"], result["content_unit"], result["pack_count"]) == (500, "g", 4)
    assert result["price"] == 16.99


@pytest.mark.parametrize("change", ["wrong_id", "invalid_ean", "ambiguous_sku"])
def test_rejects_unconfirmed_identity(change):
    data = payload()
    if change == "wrong_id": data[0]["productId"] = "656"
    elif change == "invalid_ean": data[0]["items"][0]["ean"] = "00000655"
    else: data[0]["items"].append(deepcopy(data[0]["items"][0]))
    with pytest.raises(PriceError): product_data(data, normalize_link("lasirena", URL))


def test_unavailable_or_ambiguous_sellers_do_not_invent_a_price():
    data = payload()
    data[0]["items"][0]["sellers"][0]["commertialOffer"]["IsAvailable"] = False
    assert "price" not in product_data(data, normalize_link("lasirena", URL))
    data = payload()
    data[0]["items"][0]["sellers"].append(deepcopy(data[0]["items"][0]["sellers"][0]))
    assert "price" not in product_data(data, normalize_link("lasirena", URL))


async def test_lookup_uses_api_cache_and_rate_callback_without_html_or_checkout(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    before = AsyncMock()
    monkeypatch.setattr(lookup, "_before_request", before)
    fallback = AsyncMock()
    monkeypatch.setattr(lookup.sources, "fetch", fallback)
    aioclient_mock.get(API, json=payload())
    try:
        result = await lookup.retrieve(URL)
        assert result["store"] == "lasirena" and result["reference_id"] == "655"
        assert result["measure_price"]["unit"] == "kg"
        assert result["measure_price"]["quantity"] == 1
        assert result["measure_price"]["price"] == 33.98
        assert await lookup.retrieve(URL) == result
        before.assert_awaited_once()
        fallback.assert_not_awaited()
        assert aioclient_mock.call_count == 1
        with pytest.raises(PriceError, match="EAN"):
            await lookup.retrieve(URL, expected_ean="3017620422003")
    finally: lookup.close()


async def test_blocked_api_does_not_fall_back_to_html_or_retry(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup, "_before_request", AsyncMock())
    aioclient_mock.get(API, status=429, headers={"Retry-After": "1200"})
    try:
        with pytest.raises(PriceError): await lookup.retrieve(URL)
        with pytest.raises(PriceError, match="pausa"): await lookup.retrieve(URL)
        assert aioclient_mock.call_count == 1
    finally: lookup.close()
