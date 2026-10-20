"""Iconify search, safe downloads, persistence and authenticated commands."""

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.icons import (
    BASE_URL, ICONS_URL, IconError, IconLibrary, split_icon, validated_svg,
)

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M1 1h4v4z"/></svg>'
INFO = {"name": "Tabler Icons", "author": {"name": "Pawe\u0142 Kuna", "url": "https://github.com/tabler/tabler-icons"},
        "license": {"title": "MIT", "url": "https://github.com/tabler/tabler-icons/blob/master/LICENSE"}}
SEARCH = {"icons": ["tabler:milk", "tabler:milk-filled"], "collections": {"tabler": INFO}}


@pytest.mark.parametrize("identifier", ["../secret", "evil:milk", "tabler:../milk", "tabler:milk?x=1", "tabler:milk#x", "TABLER:milk", "tabler:milk:other"])
def test_rejects_arbitrary_hosts_paths_and_sets(identifier):
    with pytest.raises(IconError):
        split_icon(identifier)


@pytest.mark.parametrize("raw", [b"<html></html>",
    SVG.replace(b"<path", b'<script>alert(1)</script><path'),
    SVG.replace(b"<path", b'<path onclick="alert(1)"'),
    SVG.replace(b"<path", b'<path style="fill:red"'),
    SVG.replace(b"<path", b'<path fill="url(https://example.test/a.svg)"'),
    SVG.replace(b"<path", b'<use href="https://example.test/a.svg"/><path'),
    b'<!DOCTYPE svg [<!ENTITY x "bad">]>' + SVG,
    SVG.replace(b"0 0 24 24", b"0 0 NaN 24"), b"x" * 262145,
])
def test_rejects_active_external_or_invalid_svg(raw):
    with pytest.raises(IconError):
        validated_svg(raw)


def test_accepts_static_shapes_and_local_gradients():
    assert b"#20352d" in validated_svg(SVG)
    gradient = SVG.replace(b'<path fill="currentColor"', b'<defs><linearGradient id="a"><stop offset="0" stop-color="#fff"/></linearGradient></defs><path fill="url(#a)"')
    assert b"linearGradient" in validated_svg(gradient)


async def test_search_cache_and_downloaded_icon_survive_restart(hass, aioclient_mock, monkeypatch):
    library = IconLibrary(hass)
    await library.async_load()
    aioclient_mock.get(f"{BASE_URL}/search", json=SEARCH)
    result = await library.async_search("milk")
    assert [item["id"] for item in result["icons"]] == SEARCH["icons"]
    assert result["icons"][0]["license"] == "MIT"
    assert (await library.async_search("MILK")) == result
    assert aioclient_mock.call_count == 1
    assert not list(library.directory.iterdir())  # Previews are not imported.
    aioclient_mock.get(f"{BASE_URL}/tabler/milk.svg", content=SVG)
    asset = await library.async_import("tabler:milk")
    assert asset["url"].startswith(ICONS_URL + "/")
    assert asset["author"] == INFO["author"]["name"]
    assert b"path" in (library.directory / asset["url"].rsplit("/", 1)[-1]).read_bytes()
    restored = IconLibrary(hass)
    await restored.async_load()
    monkeypatch.setattr(restored, "_request", AsyncMock(side_effect=AssertionError("The saved icon must work offline")))
    assert restored.info(asset["url"]) == asset
    assert await restored.async_import("tabler:milk") == asset
    assert aioclient_mock.call_count == 2
    # Returned metadata cannot mutate the library.
    restored.info(asset["url"])["author"] = "Changed"
    assert restored.info(asset["url"])["author"] == asset["author"]


async def test_pagination_and_invalid_attribution(hass, monkeypatch):
    library = IconLibrary(hass)
    request = AsyncMock(return_value={"icons": [f"tabler:milk-{index}" for index in range(32)], "collections": {"tabler": INFO}})
    monkeypatch.setattr(library, "_request", request)
    result = await library.async_search("milk", 32)
    assert result["has_more"] and result["next_start"] == 64
    assert request.call_args.args[1]["start"] == 32
    request.return_value = {"icons": ["tabler:milk", "evil:icon", "tabler:../x"], "collections": {"tabler": {}}}
    assert (await library.async_search("other"))["icons"] == []
    for query, start in [("x", 0), ("a\nb", 0), ("a" * 101, 0), ("milk", -1), ("milk", True)]:
        with pytest.raises(IconError):
            await library.async_search(query, start)


@pytest.mark.parametrize("status", [302, 429, 500])
async def test_network_errors_allow_retry_and_rate_limits_back_off(hass, aioclient_mock, status):
    library = IconLibrary(hass)
    aioclient_mock.get(f"{BASE_URL}/search", status=status)
    with pytest.raises(IconError):
        await library.async_search("milk")
    if status == 429:
        with pytest.raises(IconError):
            await library.async_search("bread")
        assert aioclient_mock.call_count == 1


async def test_no_asset_is_published_if_storage_fails(hass, monkeypatch):
    library = IconLibrary(hass)
    await library.async_load()
    library._collections["tabler"] = {"collection": "Tabler", "author": "Author", "license": "MIT", "license_url": "https://example.test/license"}
    monkeypatch.setattr(library, "_request", AsyncMock(return_value=SVG))
    monkeypatch.setattr(library._store, "async_save", AsyncMock(side_effect=OSError("Full disk")))
    with pytest.raises(IconError, match="guardar"):
        await library.async_import("tabler:milk")
    assert library._assets == {}


async def test_authenticated_search_import_static_image_and_unloaded_guard(hass, hass_ws_client, hass_client, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    aioclient_mock.get(f"{BASE_URL}/search", json=SEARCH)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/icons/search", "query": "milk"})
    assert (await client.receive_json())["result"]["icons"][0]["id"] == "tabler:milk"
    aioclient_mock.get(f"{BASE_URL}/tabler/milk.svg", content=SVG)
    await client.send_json({"id": 2, "type": f"{DOMAIN}/icons/import", "icon_id": "tabler:milk"})
    result = await client.receive_json()
    assert result["success"]
    asset = result["result"]
    http = await hass_client()
    response = await http.get(asset["url"])
    assert response.status == 200 and "image/svg+xml" in response.content_type
    assert "path" in await response.text()
    await client.send_json({"id": 3, "type": f"{DOMAIN}/icons/info", "image_url": asset["url"]})
    assert (await client.receive_json())["result"]["license"] == "MIT"
    await client.send_json({"id": 4, "type": f"{DOMAIN}/icons/import", "icon_id": "evil:milk"})
    assert (await client.receive_json())["error"]["code"] == "icon_import_error"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 5, "type": f"{DOMAIN}/icons/search", "query": "milk"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"
