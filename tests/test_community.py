"""Voluntary export privacy, reviewed dictionary ranking and offline assets."""

import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
import zipfile

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.community import CommunityLibrary, build_export, validate_index
from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.icons import IconLibrary, IconError, ICONS_URL

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#ff0000" d="M0 0h20v20z"/></svg>'


def reviewed(identifier="rice", contributions=1):
    digest = hashlib.sha256(SVG).hexdigest()
    return {"id": identifier, "name_en": "Rice", "terms": ["rice", "arroz"], "file": f"images/{digest}.svg", "sha256": digest,
            "author": "An author", "license": "CC0-1.0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "contributions": contributions}


def test_export_allowlist_dedup_missing_translation_and_paths(tmp_path):
    directory = tmp_path / "icons"
    directory.mkdir()
    (directory / "rice.svg").write_bytes(SVG)
    (tmp_path / "secret.svg").write_bytes(SVG)
    url = ICONS_URL + "/rice.svg"
    products = [{"name": "Arroz", "name_en": "Rice", "image_url": url, "notes": "PRIVATE", "barcode": "123", "id": "private-id"},
                {"name": "ARROZ", "name_en": "Rice", "image_url": url},
                {"name": "Pan", "icon": "mdi:bread-slice"},
                {"name": "Secret", "image_url": ICONS_URL + "/../secret.svg"},
                {"name": "External", "image_url": "https://example.test/icon.png?token=PRIVATE"},
                {"name": "Public", "image_url": "https://example.test/public.png"}]
    result = build_export(products, {url: {"author": "Author", "license": "MIT"}}, tmp_path, directory)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["data"]))) as archive:
        text = archive.read("dictionary.json").decode()
        manifest = json.loads(text)
        assert "PRIVATE" not in text and "private-id" not in text and "barcode" not in text
        assert result["images"] == 1 and len(manifest["entries"]) == 3
        assert manifest["entries"][0]["catalog_uses"] == 2
        assert manifest["entries"][1]["name_en"] == ""
        assert all(entry["requires_review"] for entry in manifest["entries"])
        assert not any(".." in name for name in archive.namelist())


@pytest.mark.parametrize("field,value", [("file", "../private.svg"), ("sha256", "0" * 64), ("contributions", True),
                                         ("license_url", "javascript:alert(1)"), ("terms", []), ("id", "../rice")])
def test_invalid_reviewed_index_rejected(field, value):
    item = reviewed()
    item[field] = value
    with pytest.raises((IconError, TypeError)):
        validate_index({"schema_version": 1, "icons": [item]})


async def test_rank_cache_import_hash_and_offline(hass, monkeypatch):
    icons = IconLibrary(hass)
    await icons.async_load()
    library = CommunityLibrary(hass, icons)
    fetch = AsyncMock(return_value=json.dumps({"schema_version": 1, "icons": [reviewed("a", 1), reviewed("b", 4)]}).encode())
    monkeypatch.setattr(library, "_fetch", fetch)
    assert [icon["id"] for icon in await library.async_search("ARROZ")] == ["community:b", "community:a"]
    assert len(await library.async_search("rice")) == 2
    assert fetch.await_count == 1
    fetch.return_value = SVG
    asset = await library.async_import("community:b")
    assert asset["collection"] == "Comunidad" and asset["author"] == "An author"
    assert Path(icons.directory / asset["url"].rsplit("/", 1)[1]).is_file()
    fetch.side_effect = IconError("Offline")
    assert await library.async_import("community:b") == asset
    restored = CommunityLibrary(hass, icons)
    await restored.async_load()
    monkeypatch.setattr(restored, "_fetch", fetch)
    assert len(await restored.async_search("rice")) == 2
    bad = deepcopy(library._items[0])
    bad["sha256"] = "0" * 64
    library._items = [bad]
    fetch.side_effect = None
    fetch.return_value = SVG
    with pytest.raises(IconError, match="coincide"):
        await library.async_import("community:a")


async def test_export_websocket_admin_and_unloaded(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.data[DOMAIN]["catalog"].async_save_product({"name": "Pan", "icon": "mdi:bread-slice"})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/community/export"})
    response = await client.receive_json()
    assert response["success"] and response["result"]["entries"] == 1
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(response["result"]["data"]))) as archive:
        assert json.loads(archive.read("dictionary.json"))["entries"][0]["name"] == "Pan"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 2, "type": f"{DOMAIN}/community/export"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"


async def test_export_denied_for_non_admin(hass, hass_ws_client, hass_read_only_user):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(token))
    await client.send_json({"id": 1, "type": f"{DOMAIN}/community/export"})
    assert not (await client.receive_json())["success"]


async def test_suggestions_precede_iconify_and_survive_provider_error(hass, hass_ws_client, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    community = hass.data[DOMAIN]["community"]
    community._items = [reviewed()]
    community._next_refresh = float("inf")
    search = AsyncMock(return_value={"icons": [{"id": "noto:rice"}], "next_start": 32, "has_more": True})
    monkeypatch.setattr(hass.data[DOMAIN]["icons"], "async_search", search)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/icons/search", "query": "rice"})
    result = (await client.receive_json())["result"]
    assert [icon["id"] for icon in result["icons"]] == ["community:rice", "noto:rice"]
    search.side_effect = IconError("Offline")
    await client.send_json({"id": 2, "type": f"{DOMAIN}/icons/search", "query": "rice"})
    result = (await client.receive_json())["result"]
    assert result["icons"][0]["id"] == "community:rice" and not result["has_more"]
