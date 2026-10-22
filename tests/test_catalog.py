"""Catalog persistence, validation, concurrent edits and real WebSocket commands."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, normalize_category, normalize_product, normalized_name
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN


@pytest.mark.parametrize(("first","second"), [("Seitan","Seitán"),("SEITA\u0301N", " seitan "),("ＣＡＦÉ   molido","cafe molido")])
def test_product_name_keys_ignore_accents_case_and_extra_spaces(first,second):
    assert normalized_name(first) == normalized_name(second)


async def test_accent_insensitive_suggestion_matching_keeps_catalog_spelling(hass):
    catalog=Catalog(hass)
    await catalog.async_load()
    first=await catalog.async_save_product({"name":"Seitán"})
    match=await catalog.async_save_product({"name":"SEITAN"},from_suggestion=True)
    assert match["id"] == first["id"] and match["name"] == "Seitán"
    await catalog.async_dismiss_suggestion("CAFÉ molido")
    restored=Catalog(hass)
    await restored.async_load()
    assert restored.snapshot["dismissed_suggestions"] == ["cafe molido"]


def editable(product, **changes):
    """Build the same public edit payload a client sends, without server metadata."""
    return {
        **{key: product[key] for key in (
            "id", "revision", "name", "category", "tags", "barcode",
            "price", "currency", "image_url", "icon", "notes",
        )},
        **changes,
    }


async def test_translation_is_persisted_reused_and_updated_with_name(hass, product_translation):
    product_translation.return_value = "Milk"
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Leche"})
    assert product["name_en"] == "Milk"
    product_translation.assert_awaited_once_with(hass, "Leche")
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products[0]["name_en"] == "Milk"
    product = await restored.async_save_product(editable(product, notes="Una nota"))
    assert product["name_en"] == "Milk"
    assert product_translation.await_count == 1
    product_translation.return_value = "Bread"
    product = await restored.async_save_product(editable(product, name="Pan"))
    assert product["name_en"] == "Bread"
    assert product_translation.await_count == 2


async def test_translation_failure_keeps_product_and_retries_on_save(hass, product_translation):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Leche"})
    assert product["name"] == "Leche" and product["name_en"] == ""
    product_translation.return_value = "Milk"
    product = await catalog.async_save_product(editable(product))
    assert product["name_en"] == "Milk"
    product_translation.return_value = ""
    product = await catalog.async_save_product(editable(product, name="Pan"))
    assert product["name_en"] == ""  # Never search a renamed product with the old translation.


async def test_old_product_gets_translation_on_save(hass, product_translation):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Leche"})
    catalog._products[product["id"]].pop("name_en")
    product_translation.return_value = "Milk"
    product = await catalog.async_save_product(editable(product))
    assert product["name_en"] == "Milk"


async def test_icon_query_backfills_old_rice_without_conflicting_with_open_form(hass, product_translation):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz"})
    product_translation.return_value = "Rice"
    assert await catalog.async_icon_query(product["id"], "Arroz") == "Rice"
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products[0]["name_en"] == "Rice"
    assert restored.products[0]["revision"] == product["revision"]
    product_translation.reset_mock()
    assert await catalog.async_icon_query(product["id"], "Arroz") == "Rice"
    product_translation.assert_not_awaited()
    edited = await catalog.async_save_product(editable(product, notes="Guardar ficha abierta"))
    assert edited["name_en"] == "Rice"


async def test_late_icon_translation_does_not_overwrite_renamed_product(hass, product_translation):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz"})
    started, release = asyncio.Event(), asyncio.Event()
    async def translate(*_):
        started.set()
        await release.wait()
        return "Rice"
    product_translation.side_effect = translate
    pending = asyncio.create_task(catalog.async_icon_query(product["id"], "Arroz"))
    await started.wait()
    # Simulate an intervening committed edit without a second slow translation.
    catalog._products[product["id"]] = {**catalog._products[product["id"]], "name": "Pan", "name_en": "Bread"}
    release.set()
    assert await pending == "Rice"
    assert catalog.products[0]["name_en"] == "Bread"


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


async def test_product_delete_is_durable_releases_codes_and_checks_revision(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    category = await catalog.async_save_category({"name": "Despensa"})
    product = await catalog.async_save_product({"name": "Cacao", "category": category["name"], "barcode": "00123", "nfc_tags": ["AA:BB"]})
    with pytest.raises(CatalogError, match="Otra sesión"):
        await catalog.async_delete_product(product["id"], product["revision"] + 1)
    assert catalog.products == [product]
    notifications = []
    unsubscribe = catalog.subscribe(lambda: notifications.append(catalog.snapshot))
    await catalog.async_delete_product(product["id"], product["revision"])
    assert catalog.products == [] and notifications[-1]["products"] == []
    assert catalog.snapshot["categories"][0]["product_count"] == 0
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products == []
    await restored.async_save_product({"name": "Otro", "barcode": "00123", "nfc_tags": ["AA:BB"]})
    with pytest.raises(CatalogError) as error:
        await catalog.async_delete_product(product["id"], product["revision"])
    assert error.value.code == "not_found"
    unsubscribe()


async def test_product_delete_storage_failure_preserves_entry(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Cacao"})
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_delete_product(product["id"], product["revision"])
    assert catalog.products == [product]


async def test_delete_product_websocket_updates_other_sessions_without_changing_todo(hass, hass_ws_client):
    hass.states.async_set("todo.bring", "1", {"friendly_name": "Compra"})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    catalog = hass.data[DOMAIN]["catalog"]
    product = await catalog.async_save_product({"name": "Cacao"})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/subscribe"})
    await client.receive_json()
    await client.receive_json()
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/delete", "product_id": product["id"], "revision": 99})
    assert (await client.receive_json())["error"]["code"] == "conflict"
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/delete", "product_id": product["id"], "revision": product["revision"]})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 3)["success"]
    assert next(message for message in messages if message["id"] == 1)["event"]["products"] == []
    assert hass.states.get("todo.bring").state == "1"
    await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 4, "type": f"{DOMAIN}/catalog/delete", "product_id": product["id"], "revision": product["revision"]})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"


async def test_removed_brand_and_format_migrate_without_losing_products(hass):
    catalog=Catalog(hass)
    await catalog.async_load()
    product=await catalog.async_save_product({"name":"Cacao","brand":"Marca antigua","format":"500 g","barcode":"0012345","tags":["Desayuno"]})
    assert "brand" not in product and "format" not in product
    await catalog._store.async_save({"products":{product["id"]:{**product,"brand":"Marca antigua","format":"500 g"}},"categories":{},"dismissed_suggestions":[]})
    restored=Catalog(hass)
    await restored.async_load()
    assert restored.products == [product]
    stored=await restored._store.async_load()
    assert "brand" not in stored["products"][product["id"]] and "format" not in stored["products"][product["id"]]
    updated=await restored.async_save_product(editable(product,brand="Desde una sesión antigua",format="250 g"))
    assert "brand" not in updated and "format" not in updated
    assert updated["barcode"] == "0012345" and updated["tags"] == ["Desayuno"]


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
    assert (await client.receive_json())["event"] == {"products": [], "categories": [], "recommendation_categories": [], "recipes": [], "dismissed_suggestions": []}
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/save", "product": {"name": "Cacao"}})
    messages = [await client.receive_json(), await client.receive_json()]
    saved = next(message for message in messages if message["id"] == 2)
    assert saved["success"]
    product = saved["result"]["product"]
    assert next(message for message in messages if message["id"] == 1)["event"]["products"] == [product]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product], "categories": [], "recommendation_categories": [], "recipes": [], "dismissed_suggestions": []}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json({"id": 4, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["error"]["code"] == "not_loaded"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await client.send_json({"id": 5, "type": f"{DOMAIN}/catalog/get"})
    assert (await client.receive_json())["result"] == {"products": [product], "categories": [], "recommendation_categories": [], "recipes": [], "dismissed_suggestions": []}
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
    await client.send_json({"id": 10, "type": f"{DOMAIN}/catalog/suggestion", "action": "dismiss", "name": "Leche"})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 10)["success"]
    assert next(message for message in messages if message["id"] == 1)["event"]["dismissed_suggestions"] == ["leche"]
    await client.send_json({"id": 11, "type": f"{DOMAIN}/catalog/suggestion", "action": "add", "name": "Arroz"})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 11)["result"]["product"]["name"] == "Arroz"
    await client.send_json({"id": 12, "type": f"{DOMAIN}/catalog/suggestion", "action": "add", "name": " ARROZ "})
    assert (await client.receive_json())["success"]
    assert len(hass.data[DOMAIN]["catalog"].products) == 2


async def test_suggestions_durable_dismissals_and_concurrent_acceptance(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    results = await asyncio.gather(
        catalog.async_save_product({"name": "Leche entera"}, from_suggestion=True),
        catalog.async_save_product({"name": "  LECHE   entera "}, from_suggestion=True),
    )
    assert results[0]["id"] == results[1]["id"]
    assert len(catalog.products) == 1
    await catalog.async_dismiss_suggestion(" ＣＡＣＡＯ   puro ")
    await catalog.async_dismiss_suggestion("cacao puro")
    # Subsequent product/category writes must keep dismissals.
    await catalog.async_save_category({"name": "Despensa"})
    await catalog.async_save_product({"name": "Arroz"})
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.snapshot["dismissed_suggestions"] == ["cacao puro"]
    assert len(restored.products) == 2
    restored.snapshot["dismissed_suggestions"].clear()
    assert restored.snapshot["dismissed_suggestions"] == ["cacao puro"]


async def test_suggestion_write_failure_keeps_state_and_can_retry(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    save = catalog._store.async_save
    notifications = []
    catalog.subscribe(lambda: notifications.append(True))
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_dismiss_suggestion("Cacao")
    assert catalog.snapshot["dismissed_suggestions"] == []
    assert notifications == []
    monkeypatch.setattr(catalog._store, "async_save", save)
    await catalog.async_dismiss_suggestion("Cacao")
    assert catalog.snapshot["dismissed_suggestions"] == ["cacao"]
    assert notifications == [True]
    with pytest.raises(CatalogError):
        await catalog.async_dismiss_suggestion(" ")


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


async def test_seasonal_months_are_atomic_durable_and_preserved_by_product_edits(hass, product_translation):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Fresas"})
    product_translation.reset_mock()
    await asyncio.gather(
        catalog.async_set_season_months(product["id"], [1, 3], True),
        catalog.async_set_season_months(product["id"], [3, 12], True),
    )
    current = catalog.products[0]
    assert current["season_months"] == [1, 3, 12]
    revision = current["revision"]
    same = await catalog.async_set_season_months(product["id"], [3, 3], True)
    assert same["revision"] == revision
    removed = await catalog.async_set_season_months(product["id"], [1], False)
    assert removed["season_months"] == [3, 12]
    product_translation.assert_not_awaited()
    edited = await catalog.async_save_product(editable(removed, name="Fresa"))
    assert edited["season_months"] == [3, 12]
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.products[0]["season_months"] == [3, 12]
    await restored.async_delete_product(edited["id"], edited["revision"])
    with pytest.raises(CatalogError, match="ya no existe"):
        await restored.async_set_season_months(edited["id"], [3], True)


@pytest.mark.parametrize("months", [[], [0], [13], [True], [1.0], ["1"], None, list(range(13))])
async def test_seasonal_month_validation(hass, months):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Fresas"})
    with pytest.raises(CatalogError, match="meses válidos"):
        await catalog.async_set_season_months(product["id"], months, True)
    assert catalog.products[0]["season_months"] == []


async def test_seasonal_storage_failure_does_not_publish_partial_changes(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Fresas"})
    notifications = []
    catalog.subscribe(lambda: notifications.append(True))
    before = catalog.snapshot
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_set_season_months(product["id"], [1, 2], True)
    assert catalog.snapshot == before
    assert notifications == []


async def test_seasonal_websocket_updates_subscribers_and_validates_months(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    catalog = hass.data[DOMAIN]["catalog"]
    product = await catalog.async_save_product({"name": "Fresas"})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/subscribe"})
    assert (await client.receive_json())["success"]
    await client.receive_json()
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/season_months",
                            "product_id": product["id"], "months": [3, 4], "enabled": True})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 2)["result"]["product"]["season_months"] == [3, 4]
    assert next(message for message in messages if message["id"] == 1)["event"]["products"][0]["season_months"] == [3, 4]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/season_months",
                            "product_id": product["id"], "months": [False], "enabled": True})
    assert (await client.receive_json())["error"]["code"] == "invalid_product"


async def test_recommendation_categories_are_independent_durable_and_allow_multiple_membership(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    normal = await catalog.async_save_category({"name": "Fruta"})
    apple = await catalog.async_save_product({"name": "Manzana", "category": normal["name"]})
    pear = await catalog.async_save_product({"name": "Pera", "category": normal["name"]})
    first = await catalog.async_save_recommendation_category({"name": "Postres", "icon": "mdi:chef-hat", "color": "#8e44ad", "product_ids": [apple["id"], pear["id"], apple["id"]]})
    second = await catalog.async_save_recommendation_category({"name": "Merienda", "product_ids": [apple["id"]]})
    assert len(first["product_ids"]) == 2
    assert catalog.products[0]["category"] == "Fruta"
    # Unrelated writes and migrations must retain suggestion groups.
    await catalog.async_dismiss_suggestion("Pan")
    renamed = await catalog.async_save_product(editable(apple, name="Manzana roja"))
    restored = Catalog(hass)
    await restored.async_load()
    assert len(restored.snapshot["recommendation_categories"]) == 2
    current = next(group for group in restored.recommendation_categories if group["id"] == first["id"])
    assert renamed["id"] in current["product_ids"]
    updated = await restored.async_save_recommendation_category({"id": current["id"], "revision": current["revision"], "name": "Dulces", "product_ids": [apple["id"]]})
    with pytest.raises(CatalogError, match="Otra sesión"):
        await restored.async_delete_recommendation_category(first["id"], first["revision"])
    await restored.async_delete_recommendation_category(updated["id"], updated["revision"])
    assert len(restored.products) == 2 and restored.categories[0]["name"] == "Fruta"
    await restored.async_delete_product(renamed["id"], renamed["revision"])
    remaining = restored.recommendation_categories[0]
    assert remaining["id"] == second["id"] and remaining["product_ids"] == []
    assert remaining["revision"] == second["revision"] + 1


@pytest.mark.parametrize("data", [
    {"name": " "}, {"name": "Productos de temporada"}, {"name": "Grupo", "icon": "javascript:bad"},
    {"name": "Grupo", "color": "red"}, {"name": "Grupo", "product_ids": ["missing"]},
    {"name": "Grupo", "product_ids": [True]}, {"name": "Grupo", "unexpected": True},
])
async def test_recommendation_category_validation(hass, data):
    catalog = Catalog(hass)
    await catalog.async_load()
    with pytest.raises(CatalogError):
        await catalog.async_save_recommendation_category(data)
    assert catalog.recommendation_categories == []


async def test_recommendation_category_name_duplicates_and_storage_failures(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    first = await catalog.async_save_recommendation_category({"name": "Café"})
    with pytest.raises(CatalogError, match="Ya existe"):
        await catalog.async_save_recommendation_category({"name": " CAFE "})
    before = catalog.snapshot
    notifications = []
    catalog.subscribe(lambda: notifications.append(True))
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_save_recommendation_category({"id": first["id"], "revision": first["revision"], "name": "Desayuno"})
    with pytest.raises(OSError):
        await catalog.async_delete_recommendation_category(first["id"], first["revision"])
    assert catalog.snapshot == before and notifications == []


async def test_recommendation_category_websocket_push_and_delete(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/subscribe"})
    assert (await client.receive_json())["success"]
    await client.receive_json()
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/recommendation_category/save", "category": {"name": "Postres"}})
    messages = [await client.receive_json(), await client.receive_json()]
    group = next(message for message in messages if message["id"] == 2)["result"]["category"]
    assert next(message for message in messages if message["id"] == 1)["event"]["recommendation_categories"] == [group]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/recommendation_category/delete", "category_id": group["id"], "revision": group["revision"]})
    messages = [await client.receive_json(), await client.receive_json()]
    assert next(message for message in messages if message["id"] == 3)["success"]
    assert next(message for message in messages if message["id"] == 1)["event"]["recommendation_categories"] == []


async def test_recipes_persist_units_months_membership_and_cleanup_without_deleting_products(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz", "purchase_unit": "g", "unit_quantity": 100})
    recipe = await catalog.async_save_recipe({"name": "Arroz cocido", "image_url": "/local/arroz.png", "ingredients": [{"product_id": product["id"], "quantity": 250}]})
    assert recipe["ingredients"] == [{"product_id": product["id"], "quantity": 250, "unit": "g"}]
    recipe = await catalog.async_set_recipe_season_months(recipe["id"], [1, 12], True)
    group = await catalog.async_save_recommendation_category({"name": "Comidas", "recipe_ids": [recipe["id"]]})
    edited = await catalog.async_save_recipe({"id": recipe["id"], "revision": recipe["revision"], "name": "Arroz blanco", "ingredients": [{"product_id": product["id"], "quantity": 300, "unit": "g"}]})
    assert edited["season_months"] == [1, 12]
    assert edited["image_url"] == "/local/arroz.png"
    restored = Catalog(hass)
    await restored.async_load()
    assert restored.recipes == [edited]
    assert restored.recommendation_categories[0]["recipe_ids"] == [edited["id"]]
    # Older category editors cannot erase recipe associations.
    group = await restored.async_save_recommendation_category({"id": group["id"], "revision": group["revision"], "name": "Almuerzos"})
    assert group["recipe_ids"] == [edited["id"]]
    with pytest.raises(CatalogError, match="Otra sesión"):
        await restored.async_delete_recipe(recipe["id"], recipe["revision"])
    await restored.async_delete_recipe(edited["id"], edited["revision"])
    assert restored.recommendation_categories[0]["recipe_ids"] == []
    assert restored.products == [product]


@pytest.mark.parametrize("ingredients", [[], [{"product_id": "missing", "quantity": 1}], [{"product_id": "product", "quantity": 0}],
    [{"product_id": "product", "quantity": True}], [{"product_id": "product", "quantity": 1, "unit": "kg"}],
    [{"product_id": "product", "quantity": 1}, {"product_id": "product", "quantity": 2}]])
async def test_recipe_validation(hass, ingredients):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz", "purchase_unit": "g"})
    ingredients = [{**item, "product_id": product["id"] if item["product_id"] == "product" else item["product_id"]} for item in ingredients]
    with pytest.raises(CatalogError):
        await catalog.async_save_recipe({"name": "Receta", "ingredients": ingredients})
    assert catalog.recipes == []


async def test_recipe_storage_failure_keeps_existing_data_and_conflicts(hass, monkeypatch):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Pan"})
    recipe = await catalog.async_save_recipe({"name": "Tostada", "ingredients": [{"product_id": product["id"], "quantity": 1}]})
    before = catalog.snapshot
    monkeypatch.setattr(catalog._store, "async_save", AsyncMock(side_effect=OSError("Disk full")))
    with pytest.raises(OSError):
        await catalog.async_delete_recipe(recipe["id"], recipe["revision"])
    assert catalog.snapshot == before


async def test_recipe_websocket_save_push_delete(hass, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    product = await hass.data[DOMAIN]["catalog"].async_save_product({"name": "Pan"})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/catalog/recipe/save", "recipe": {"name": "Tostadas", "ingredients": [{"product_id": product["id"], "quantity": 2}]}})
    result = await client.receive_json()
    assert result["success"]
    recipe = result["result"]["recipe"]
    await client.send_json({"id": 2, "type": f"{DOMAIN}/catalog/recipe/season_months", "recipe_id": recipe["id"], "months": [6], "enabled": True})
    recipe = (await client.receive_json())["result"]["recipe"]
    assert recipe["season_months"] == [6]
    await client.send_json({"id": 3, "type": f"{DOMAIN}/catalog/recipe/delete", "recipe_id": recipe["id"], "revision": recipe["revision"]})
    assert (await client.receive_json())["success"]


@pytest.mark.parametrize("image_url", ["javascript:alert(1)", "data:image/svg+xml,test", "//example.com/recipe.png", "https://", "https://example.com/" + "x" * 2048, 12])
async def test_recipe_image_validation(hass, image_url):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz"})
    with pytest.raises(CatalogError):
        await catalog.async_save_recipe({"name": "Receta", "image_url": image_url, "ingredients": [{"product_id": product["id"], "quantity": 1}]})
    assert catalog.recipes == []


async def test_recipe_image_can_change_and_clear(hass):
    catalog = Catalog(hass)
    await catalog.async_load()
    product = await catalog.async_save_product({"name": "Arroz"})
    recipe = await catalog.async_save_recipe({"name": "Receta", "image_url": "https://example.com/arroz.png", "ingredients": [{"product_id": product["id"], "quantity": 1}]})
    assert recipe["image_url"] == "https://example.com/arroz.png"
    edited = await catalog.async_save_recipe({"id": recipe["id"], "revision": recipe["revision"], "name": recipe["name"], "image_url": "", "ingredients": recipe["ingredients"]})
    assert edited["image_url"] == ""
