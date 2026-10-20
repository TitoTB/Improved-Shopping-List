"""Translation failures must never block a catalog save."""

import pytest

from custom_components.improved_shopping_list.product_translation import URL, async_translate_name


async def test_translates_spanish_name_and_decodes_entities(hass, aioclient_mock):
    aioclient_mock.get(URL, json={"responseStatus": 200, "responseData": {"translatedText": "Bread &amp; butter"}})
    assert await async_translate_name(hass, "Pan y mantequilla") == "Bread & butter"
    request = aioclient_mock.mock_calls[0]
    assert request[1].query["q"] == "Pan y mantequilla"
    assert request[1].query["langpair"] == "es|en"


@pytest.mark.parametrize("response", [
    {}, [], {"responseStatus": 403, "responseData": {"translatedText": "QUOTA EXCEEDED"}},
    {"responseStatus": 200, "quotaFinished": True, "responseData": {"translatedText": "QUOTA EXCEEDED"}},
    {"responseStatus": 200, "responseData": None},
    {"responseStatus": 200, "responseData": {"translatedText": 42}},
    {"responseStatus": 200, "responseData": {"translatedText": "Bad\ntext"}},
    {"responseStatus": 200, "responseData": {"translatedText": "x" * 301}},
])
async def test_ignores_invalid_or_quota_responses(hass, aioclient_mock, response):
    aioclient_mock.get(URL, json=response)
    assert await async_translate_name(hass, "Leche") == ""


@pytest.mark.parametrize("status", [429, 500])
async def test_http_failure(hass, aioclient_mock, status):
    aioclient_mock.get(URL, status=status)
    assert await async_translate_name(hass, "Leche") == ""


async def test_timeout_and_size_limits(hass, aioclient_mock):
    aioclient_mock.get(URL, exc=TimeoutError())
    assert await async_translate_name(hass, "Leche") == ""
    assert await async_translate_name(hass, "é" * 251) == ""
    assert len(aioclient_mock.mock_calls) == 1


async def test_rejects_oversized_response(hass, aioclient_mock):
    aioclient_mock.get(URL, content=b"x" * 32769)
    assert await async_translate_name(hass, "Leche") == ""
