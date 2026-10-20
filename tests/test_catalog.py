"""Catalog persistence, validation, concurrent edits and real WebSocket commands."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, normalize_product
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN


def editable(product, **changes):
    """Build the same public edit payload a client sends, without server metadata."""
    return {
        **{key: product[key] for key in (
            "id", "revision", "name", "category", "tags", "brand", "barcode",
            "format", "price", "currency", "image_url", "notes",
        )},
        **changes,
    }


async def test_catalog_persists_normalizes_and_returns_snapshots(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({
        "name": "  Cacao  ", "category": " Despensa ",
        "tags": ["Desayuno", "desayuno", "  Sin gluten  "],
        "price": "2,50", "barcode": "0012345678905",
        "image_url": "/local/cacao.png",
    })
    assert product["name"] == "Cacao"
    assert product["category"] == "Despensa"
    assert product["tags"] == ["Desayuno", "Sin gluten"]
    assert product["price"] == "2.50"
    assert product["currency"] == "EUR"
    assert product["barcode"] == "0012345678905"
    assert product["revision"] == 1
    assert product["price_updated_at"]
    snapshot = catalog.products
    snapshot[0]["name"] = "Must not change storage"
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products == [product]
    assert catalog.products == [product]


async def test_catalog_edit_keeps_id_and_price_date_when_price_unchanged(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Cacao", "price": "0"})
    updated = await catalog.async_save_product(editable(product, category="Despensa"))
    assert updated["id"] == product["id"]
    assert updated["revision"] == 2
    assert updated["created_at"] == product["created_at"]
    assert updated["price_updated_at"] == product["price_updated_at"]
    assert updated["price"] == "0.00"
    assert len(catalog.products) == 1


async def test_catalog_duplicate_barcode_and_concurrent_edits(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Cacao", "barcode": "12345678"})
    with pytest.raises(CatalogError, match="Ya existe"):
        await catalog.async_save_product({"name": "Otro cacao", "barcode": "12345678"})
    results = await asyncio.gather(
        catalog.async_save_product(editable(product, price="1.50")),
        catalog.async_save_product(editable(product, price="2.00")),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    errors = [result for result in results if isinstance(result, CatalogError)]
    assert len(errors) == 1 and errors[0].code == "conflict"
    assert catalog.products[0]["revision"] == 2


async def test_catalog_failed_disk_write_does_not_change_or_broadcast(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    notifications = []
    unsubscribe = catalog.subscribe(lambda: notifications.append(True))
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_save_product({"name": "Cacao"})
    assert catalog.products == []
    assert notifications == []
    unsubscribe()


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"price": "NaN"}, {"price": "1.005"},
    {"price": -1}, {"price": True}, {"tags": "Desayuno"},
    {"tags": ["x" * 41]}, {"currency": "euro"},
    {"image_url": "javascript:alert(1)"}, {"image_url": "//example.com/image.png"},
    {"unexpected": "value"},
])
def test_catalog_rejects_invalid_product_fields(changes):
    with pytest.raises(CatalogError):
        normalize_product({"name": "Cacao", **changes})


async def test_catalog_websocket_save_push_get_and_unload(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"] == {"products": []}
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/save", "product": {"name": "Cacao"}})
    messages = [await client.receive_json(), await client.receive_json()]
    saved = next(message for message in messages if message["id"] == 2)
    assert saved["success"]
    product = saved["result"]["product"]
    assert next(message for message in messages if message["id"] == 1)["event"]["products"] == [product]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product]}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 4, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await client.send_json({"id": 5, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product]}
    await client.send_json({"id": 6, "type": f"{DOMAIN}/catalog/save", "product": {"name": "Cacao", "price": -1}})
    assert (await client.receive_json())["error"]["code"] == "invalid_product"
