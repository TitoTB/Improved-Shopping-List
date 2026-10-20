"""Catalog persistence, validation, concurrent edits and real WebSocket commands."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, normalize_category, normalize_product
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN


def editable(product, **changes):
    """Build the same public edit payload a client sends, without server metadata."""
    return {
        **{key: product[key] for key in (
            "id", "revision", "name", "category", "tags", "brand", "barcode",
            "format", "price", "currency", "image_url", "icon", "notes",
        )},
        **changes,
    }


async def test_catalog_persists_normalizes_and_returns_snapshots(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    await catalog.async_save_category({"name": "Despensa"})
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
    await catalog.async_save_category({"name": "Despensa"})
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
    {"icon": "shopping"},
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
    assert (await client.receive_json())["event"] == {"products": [], "categories": []}
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/save", "product": {"name": "Cacao"}})
    messages = [await client.receive_json(), await client.receive_json()]
    saved = next(message for message in messages if message["id"] == 2)
    assert saved["success"]
    product = saved["result"]["product"]
    assert next(message for message in messages if message["id"] == 1)["event"]["products"] == [product]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product], "categories": []}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 4, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await client.send_json({"id": 5, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product], "categories": []}
    await client.send_json({"id": 6, "type": f"{DOMAIN}/catalog/save", "product": {"name": "Cacao", "price": -1}})
    assert (await client.receive_json())["error"]["code"] == "invalid_product"
    await client.send_json({"id": 7, "type": f"{DOMAIN}/catalog/category/save", "category": {"name": "Despensa", "icon": "mdi:shopping", "color": "#267052"}})
    messages = [await client.receive_json(), await client.receive_json()]
    category = next(message for message in messages if message["id"] == 7)["result"]["category"]
    await client.send_json({"id": 8, "type": f"{DOMAIN}/catalog/save", "product": editable(product, category="Despensa")})
    messages = [await client.receive_json(), await client.receive_json()]
    updated = next(message for message in messages if message["id"] == 8)["result"]["product"]
    assert next(message for message in messages if message["id"] == 1)["event"]["categories"][0]["product_count"] == 1
    await client.send_json({"id": 9, "type": f"{DOMAIN}/catalog/category/delete", "category_id": category["id"], "revision": category["revision"]})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 9)["success"]
    retained = next(message for message in messages if message["id"] == 1)["event"]["products"][0]
    assert retained["id"] == updated["id"] and retained["category"] == ""


async def test_category_rename_delete_and_stale_product_edit(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    category = await catalog.async_save_category({"name": "Lácteos", "icon": "mdi:shopping", "color": "#ABCDEF"})
    product = await catalog.async_save_product({"name": "Yogur", "category": "lácteos", "price": "2.50", "icon": "mdi:view-grid"})
    assert product["category"] == "Lácteos"
    assert catalog.categories[0]["product_count"] == 1
    renamed = await catalog.async_save_category({"id": category["id"], "revision": 1, "name": "Frescos", "icon": "mdi:shopping", "color": "#267052"})
    assert catalog.products[0]["category"] == "Frescos"
    with pytest.raises(CatalogError, match="Otra sesión"):
        await catalog.async_save_product(editable(product, name="Yogur nuevo"))
    with pytest.raises(CatalogError, match="Otra sesión"):
        await catalog.async_delete_category(category["id"], 1)
    await catalog.async_delete_category(renamed["id"], renamed["revision"])
    assert catalog.categories == []
    retained = catalog.products[0]
    assert retained["id"] == product["id"]
    assert retained["category"] == ""
    assert retained["price"] == "2.50"
    assert retained["icon"] == "mdi:view-grid"
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products == [retained] and restored.categories == []


async def test_legacy_category_migration_is_durable_and_preserves_products(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    legacy = await catalog.async_save_product({"name": "Cacao", "price": "1.50"})
    legacy["category"] = "Despensa"
    legacy.pop("icon")
    await catalog._store.async_save({"products": {legacy["id"]: legacy}})
    migrated = Catalog(hass)
    await migrated.async_load()
    assert migrated.products == [legacy]
    assert migrated.categories[0]["name"] == "Despensa"
    assert migrated.categories[0]["icon"] == "mdi:tag"
    again = Catalog(hass)
    await again.async_load()
    assert again.categories == migrated.categories
    assert again.products == [legacy]


async def test_category_delete_write_failure_is_atomic(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    category = await catalog.async_save_category({"name": "Despensa"})
    product = await catalog.async_save_product({"name": "Cacao", "category": "Despensa"})
    before = catalog.snapshot
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_delete_category(category["id"], category["revision"])
    assert catalog.snapshot == before
    assert catalog.products == [product]


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"icon": "javascript:alert(1)"},
    {"color": "red;display:none"}, {"color": "#123"},
])
def test_category_validation(changes):
    with pytest.raises(CatalogError):
        normalize_category({"name": "Despensa", **changes})


async def test_category_names_are_unique_and_dangling_assignments_rejected(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    await catalog.async_save_category({"name": "Despensa"})
    with pytest.raises(CatalogError, match="Ya existe"):
        await catalog.async_save_category({"name": "despensa"})
    with pytest.raises(CatalogError, match="categoría ya no existe"):
        await catalog.async_save_product({"name": "Cacao", "category": "Eliminada"})
