"""Credential-free downloads, exact EAN matching, deltas and last-good cache."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.improved_shopping_list.const import DOMAIN
from custom_components.improved_shopping_list.feed_protocol import descriptor, digest, encode, gtin, snapshot
from custom_components.improved_shopping_list.retail_feed import ROOT, RetailFeed


def product(price="1.35"):
    return {"ean": "8431876279146", "name": "Alcaparras", "price": price, "currency": "EUR",
            "affiliate_url": "https://www.awin1.com/pclick.php?p=123&a=1535625&m=25399"}


def publication(price="1.35"):
    raw = snapshot([product(price)])
    version = digest(raw)
    return {"schema": 1, "store": "carrefour", "version": version, "products_count": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": descriptor(f"snapshots/{version}.json", raw), "delta": None}, raw


@pytest.fixture
def feed(hass):
    hass.data[DOMAIN] = {"active": True}
    settings = SimpleNamespace(entry=object(), _generation=1,
        snapshot={"stores": {"carrefour": {"enabled": True}}})
    catalog = SimpleNamespace(products=[{"name": "Mi producto", "barcodes": ["8431876279146"]}])
    instance = RetailFeed(hass, catalog, settings, SimpleNamespace(record=Mock()))
    instance._store = SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value=None))
    return instance


async def test_full_download_exact_matching_and_304(feed):
    manifest, raw = publication()
    feed._get = AsyncMock(side_effect=[(encode(manifest), '"one"'), (raw, "")])
    result = await feed.async_refresh()
    assert result["products"] == [product()]
    assert result["error"] == ""
    assert result["version"] == manifest["version"]
    await feed.async_refresh()
    assert feed._get.await_count == 2  # Daily checks, not one request per product.
    feed._get = AsyncMock(return_value=(None, '"one"'))
    await feed.async_refresh(force=True)
    assert feed._get.call_args.args[1] == {"If-None-Match": '"one"'}
    feed.catalog.products = [{"barcodes": ["8721201901058"]}]
    assert feed.snapshot()["products"] == []


async def test_delta_and_full_fallback_when_versions_were_skipped(feed):
    first, raw = publication()
    feed._get = AsyncMock(side_effect=[(encode(first), ""), (raw, "")])
    await feed.async_refresh()
    second, raw2 = publication("1.55")
    delta = encode({"schema": 1, "base_version": first["version"], "version": second["version"],
        "upsert": [product("1.55")], "deleted": []})
    second["delta"] = {**descriptor(f"deltas/{digest(delta)}.json", delta), "base_version": first["version"]}
    feed._get = AsyncMock(side_effect=[(encode(second), ""), (delta, "")])
    assert (await feed.async_refresh(force=True))["products"][0]["price"] == "1.55"
    assert feed._get.call_args.args[0].startswith("deltas/")
    third, raw3 = publication("1.75")
    third["delta"] = second["delta"]  # Its base is not our local version.
    feed._get = AsyncMock(side_effect=[(encode(third), ""), (raw3, "")])
    assert (await feed.async_refresh(force=True))["products"][0]["price"] == "1.75"
    assert feed._get.call_args.args[0].startswith("snapshots/")


async def test_bad_checksum_and_network_failures_keep_previous_prices(feed):
    first, raw = publication()
    feed._get = AsyncMock(side_effect=[(encode(first), ""), (raw, "")])
    await feed.async_refresh()
    previous = dict(feed._data)
    second, _ = publication("1.55")
    feed._get = AsyncMock(side_effect=[(encode(second), ""), (b"corrupted", "")])
    result = await feed.async_refresh(force=True)
    assert result["error"]
    assert feed._data == previous
    feed._get = AsyncMock(side_effect=FileNotFoundError("El catálogo todavía no se ha publicado."))
    result = await feed.async_refresh(force=True)
    assert result["products"] == [product()]
    assert "publicado" in result["error"]


async def test_late_reply_after_settings_change_is_discarded(feed):
    manifest, raw = publication()
    async def get(path, *args, **kwargs):
        if path == "manifest.json":
            return encode(manifest), ""
        feed.settings._generation += 1
        return raw, ""
    feed._get = AsyncMock(side_effect=get)
    assert not (await feed.async_refresh())["version"]
    feed._store.async_save.assert_not_awaited()
    feed.settings.snapshot["stores"]["carrefour"]["enabled"] = False
    await feed.async_refresh(force=True)
    assert feed._get.await_count == 2


async def test_persisted_cache_can_be_loaded_without_network(feed):
    manifest, raw = publication()
    data = {"version": manifest["version"], "products": {gtin(product()["ean"]): product()},
        "checked_at": 1, "generated_at": manifest["generated_at"], "etag": '"cache"'}
    feed._store.async_load.return_value = data
    await feed.async_load()
    assert feed.snapshot()["products"] == [product()]
    assert feed.snapshot()["stale"]
    feed._store.async_load.return_value = {**data, "version": "wrong"}
    await feed.async_load()
    assert "no es válida" in feed.error


async def test_real_http_uses_public_fixed_paths_and_integrity_checks(feed, aioclient_mock):
    manifest, raw = publication()
    aioclient_mock.get(ROOT + "manifest.json", content=encode(manifest), headers={"ETag": '"initial"'})
    aioclient_mock.get(ROOT + manifest["snapshot"]["path"], content=raw)
    assert (await feed.async_refresh())["products"] == [product()]
    assert aioclient_mock.call_count == 2
    for method, url, body, headers in aioclient_mock.mock_calls:
        assert method == "GET"
        assert str(url).startswith(ROOT)
        assert "Authorization" not in (headers or {})
    with pytest.raises(ValueError):
        await feed._get("../../private")
