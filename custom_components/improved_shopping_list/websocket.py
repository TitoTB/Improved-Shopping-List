"""Authenticated commands for the integration's shared local catalog."""

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .catalog import Catalog, CatalogError
from .const import DOMAIN
from .list_settings import ListSettingsError
from .stores import StoreError
from .icons import IconError
from .community import build_export
from .product_translation import async_translate_name
from .product_lookup import is_product_barcode
from .store_links import normalize_links, STORES
from .lidl import LIDL_REGIONS

_LOGGER = logging.getLogger(__name__)


def _catalog(hass: HomeAssistant, connection, msg) -> Catalog | None:
    data = hass.data.get(DOMAIN, {})
    if not data.get("active"):
        connection.send_error(msg["id"], "not_loaded", "Improved Shopping List no está activa.")
        return None
    return data["catalog"]


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register once; commands check that the config entry is still loaded."""
    websocket_api.async_register_command(hass, ws_catalog_get)
    websocket_api.async_register_command(hass, ws_catalog_subscribe)
    websocket_api.async_register_command(hass, ws_catalog_save)
    websocket_api.async_register_command(hass, ws_catalog_delete)
    websocket_api.async_register_command(hass, ws_category_save)
    websocket_api.async_register_command(hass, ws_category_delete)
    websocket_api.async_register_command(hass, ws_suggestion)
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_subscribe)
    websocket_api.async_register_command(hass, ws_settings_update)
    websocket_api.async_register_command(hass, ws_personalization)
    websocket_api.async_register_command(hass, ws_store_update)
    websocket_api.async_register_command(hass, ws_store_products)
    websocket_api.async_register_command(hass, ws_store_progress)
    websocket_api.async_register_command(hass, ws_carrefour_products)
    websocket_api.async_register_command(hass, ws_favorite_store)
    websocket_api.async_register_command(hass, ws_price_schedule)
    websocket_api.async_register_command(hass, ws_cached_prices)
    websocket_api.async_register_command(hass, ws_refresh_prices)
    websocket_api.async_register_command(hass, ws_lidl_regions)
    websocket_api.async_register_command(hass, ws_readers_get)
    websocket_api.async_register_command(hass, ws_readers_subscribe)
    websocket_api.async_register_command(hass, ws_readers_save)
    websocket_api.async_register_command(hass, ws_readers_delete)
    websocket_api.async_register_command(hass, ws_readers_dismiss)
    websocket_api.async_register_command(hass, ws_icons_search)
    websocket_api.async_register_command(hass, ws_icons_import)
    websocket_api.async_register_command(hass, ws_icons_info)
    websocket_api.async_register_command(hass, ws_community_export)
    websocket_api.async_register_command(hass, ws_nutriscore)
    websocket_api.async_register_command(hass, ws_logs_get)
    websocket_api.async_register_command(hass, ws_logs_subscribe)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/logs/get"})
@callback
def ws_logs_get(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["activity"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/logs/subscribe"})
@callback
def ws_logs_subscribe(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    activity = hass.data[DOMAIN]["activity"]

    @callback
    def on_update():
        connection.send_event(msg["id"], activity.snapshot)

    connection.subscriptions[msg["id"]] = activity.subscribe(on_update)
    connection.send_result(msg["id"])
    on_update()


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/icons/search", vol.Required("query"): str,
    vol.Optional("start", default=0): vol.All(int, vol.Range(min=0, max=320)),
    vol.Optional("translate", default=False): bool,
    vol.Optional("product_id"): str,
})
@websocket_api.async_response
async def ws_icons_search(hass, connection, msg):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        query = msg["query"].strip()
        if msg["translate"] and 2 <= len(query) <= 100:
            query = (await catalog.async_icon_query(msg["product_id"], query) if msg.get("product_id")
                     else await async_translate_name(hass, query)) or query
        community = await hass.data[DOMAIN]["community"].async_search(query[:100]) if msg["start"] == 0 else []
        try:
            result = await hass.data[DOMAIN]["icons"].async_search(query[:100], msg["start"])
        except IconError:
            if not community:
                raise
            result = {"icons": [], "next_start": 32, "has_more": False}
        result = {**result, "icons": [*community, *result["icons"]], "query": query[:100]}
    except (IconError, CatalogError, OSError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "icon_search_error", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/icons/import", vol.Required("icon_id"): str})
@websocket_api.async_response
async def ws_icons_import(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        library = hass.data[DOMAIN]["community"] if msg["icon_id"].startswith("community:") else hass.data[DOMAIN]["icons"]
        result = await library.async_import(msg["icon_id"])
    except IconError as err:
        connection.send_error(msg["id"], "icon_import_error", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/icons/info", vol.Required("image_url"): str})
@callback
def ws_icons_info(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["icons"].info(msg["image_url"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/community/export"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_community_export(hass, connection, msg):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    icons = hass.data[DOMAIN]["icons"]
    try:
        result = await hass.async_add_executor_job(build_export, catalog.products, deepcopy(icons._assets),
                                                   Path(hass.config.path()), icons.directory)
    except (IconError, OSError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "community_export_error", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/nutriscore", vol.Required("code"): str})
@websocket_api.async_response
async def ws_nutriscore(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    code = msg["code"].strip()
    result = await hass.data[DOMAIN]["readers"].lookup.async_lookup(code)
    connection.send_result(msg["id"], {"code": code, "nutriscore": result.get("nutriscore"),
                                      "product_name": result.get("product_name", result.get("name", "")),
                                      "source_url": f"https://world.openfoodfacts.org/product/{code}" if is_product_barcode(code) else ""})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/get"})
@callback
def ws_readers_get(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["readers"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/subscribe"})
@callback
def ws_readers_subscribe(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    readers = hass.data[DOMAIN]["readers"]

    @callback
    def on_update():
        connection.send_event(msg["id"], readers.snapshot)

    connection.subscriptions[msg["id"]] = readers.subscribe(on_update)
    connection.send_result(msg["id"])
    on_update()


async def _reader_write(hass, connection, msg, operation):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await operation(hass.data[DOMAIN]["readers"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist reader changes")
        connection.send_error(msg["id"], "storage_error", "No se han podido guardar los cambios de lectores.")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/save", vol.Required("reader"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_readers_save(hass, connection, msg):
    await _reader_write(hass, connection, msg, lambda manager: manager.async_save_reader(msg["reader"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/delete", vol.Required("reader_id"): str, vol.Required("revision"): int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_readers_delete(hass, connection, msg):
    await _reader_write(hass, connection, msg, lambda manager: manager.async_delete_reader(msg["reader_id"], msg["revision"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/dismiss", vol.Required("pending_id"): str})
@websocket_api.async_response
async def ws_readers_dismiss(hass, connection, msg):
    await _reader_write(hass, connection, msg, lambda manager: manager.async_dismiss(msg["pending_id"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/get"})
@callback
def ws_settings_get(hass: HomeAssistant, connection, msg) -> None:
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["settings"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/subscribe"})
@callback
def ws_settings_subscribe(hass: HomeAssistant, connection, msg) -> None:
    if not _catalog(hass, connection, msg):
        return
    settings = hass.data[DOMAIN]["settings"]

    @callback
    def on_update():
        connection.send_event(msg["id"], settings.snapshot)

    connection.subscriptions[msg["id"]] = settings.subscribe(on_update)
    connection.send_result(msg["id"])
    on_update()


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/settings/update",
    vol.Required("action"): vol.In(("add", "remove", "primary")),
    vol.Required("entity_id"): str,
})
@websocket_api.require_admin
@callback
def ws_settings_update(hass: HomeAssistant, connection, msg) -> None:
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update(msg["action"], msg["entity_id"])
    except ListSettingsError as err:
        connection.send_error(msg["id"], "invalid_list", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/settings/personalization",
    vol.Required("appearance"): dict,
})
@websocket_api.require_admin
@callback
def ws_personalization(hass: HomeAssistant, connection, msg) -> None:
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_appearance(msg["appearance"])
    except ListSettingsError as err:
        connection.send_error(msg["id"], "invalid_appearance", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/settings/store",
    vol.Required("store"): vol.In(tuple(STORES)),
    vol.Required("enabled"): bool,
    vol.Optional("postal_code", default=""): str,
    vol.Optional("verify", default=False): bool,
    vol.Optional("region_id", default=""): str,
    vol.Optional("sale_point"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_store_update(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        settings = hass.data[DOMAIN]["settings"]
        result = (await settings.async_update_lidl(msg["enabled"], msg["region_id"]) if msg["store"] == "lidl"
                  else await settings.async_update_alcampo(msg["enabled"], msg["region_id"]) if msg["store"] == "alcampo"
                  else await settings.async_update_carrefour(msg["enabled"], msg.get("sale_point")) if msg["store"] == "carrefour"
            else await settings.async_update_store(msg["enabled"], msg["postal_code"], msg["verify"]))
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_store", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/favorite_store", vol.Required("store"): vol.In(tuple(STORES))})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_favorite_store(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["settings"].async_favorite_store(msg["store"])
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_store", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/carrefour_products", vol.Optional("force", default=False): bool})
@websocket_api.async_response
async def ws_carrefour_products(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    if msg["force"] and not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Solo los administradores pueden forzar la actualización.")
        return
    result = hass.data[DOMAIN]["price_manager"].snapshot("carrefour")
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/store_progress"})
@callback
def ws_store_progress(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    products = hass.data[DOMAIN]["store_products"]

    @callback
    def on_update():
        connection.send_event(msg["id"], deepcopy(products.progress))

    connection.subscriptions[msg["id"]] = products.subscribe(on_update)
    connection.send_result(msg["id"])
    on_update()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/price_schedule", vol.Required("time"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_price_schedule(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_price_schedule(msg["time"])
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_schedule", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/refresh_prices",
    vol.Required("store"):vol.In(tuple(STORES))})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_refresh_prices(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["price_manager"].async_refresh_store(msg["store"])
    except (ValueError, OSError) as err:
        connection.send_error(msg["id"], "price_refresh_error", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/store_prices",
    vol.Optional("links", default={}):dict, vol.Optional("codes", default=[]):[str],
    vol.Optional("store", default=""):vol.In(("", *STORES))})
@websocket_api.async_response
async def ws_cached_prices(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    manager = hass.data[DOMAIN]["price_manager"]
    try:
        links = normalize_links(msg["links"])
        if len(msg["codes"]) > 51 or any(len(code) > 1024 for code in msg["codes"]):
            raise ValueError("Demasiados códigos de producto.")
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_store_link", str(err))
        return
    if msg["store"]:
        result = manager.snapshot(msg["store"])
    else:
        result = {"products":manager.prices_for({"store_links":links,"barcodes":msg["codes"]}), "nightly":True}
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/lidl_regions"})
@callback
def ws_lidl_regions(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], {"regions":[{"id":key,"name":name} for key,name in LIDL_REGIONS.items()]})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/settings/store_products",
    vol.Optional("force", default=False): bool,
})
@websocket_api.async_response
async def ws_store_products(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    if msg["force"] and not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Solo los administradores pueden forzar la actualización.")
        return
    try:
        result = await hass.data[DOMAIN]["store_products"].async_refresh(msg["force"])
    except (StoreError, OSError) as err:
        connection.send_error(msg["id"], "store_products_error", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/get"})
@callback
def ws_catalog_get(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if catalog := _catalog(hass, connection, msg):
        connection.send_result(msg["id"], catalog.snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/subscribe"})
@callback
def ws_catalog_subscribe(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return

    @callback
    def on_update() -> None:
        connection.send_event(msg["id"], catalog.snapshot)

    connection.subscriptions[msg["id"]] = catalog.subscribe(on_update)
    connection.send_result(msg["id"])
    on_update()


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/save",
    vol.Required("product"): dict,
})
@websocket_api.async_response
async def ws_catalog_save(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        product = await catalog.async_save_product(msg["product"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist catalog product")
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar el catálogo. Inténtalo de nuevo.")
    else:
        connection.send_result(msg["id"], {"product": product})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/delete",
    vol.Required("product_id"): str,
    vol.Required("revision"): int,
})
@websocket_api.async_response
async def ws_catalog_delete(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        await catalog.async_delete_product(msg["product_id"], msg["revision"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not delete catalog product")
        connection.send_error(msg["id"], "storage_error", "No se ha podido eliminar el producto. Inténtalo de nuevo.")
    else:
        connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/category/save",
    vol.Required("category"): dict,
})
@websocket_api.async_response
async def ws_category_save(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        category = await catalog.async_save_category(msg["category"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist category")
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar la categoría.")
    else:
        connection.send_result(msg["id"], {"category": category})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/category/delete",
    vol.Required("category_id"): str,
    vol.Required("revision"): int,
})
@websocket_api.async_response
async def ws_category_delete(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        await catalog.async_delete_category(msg["category_id"], msg["revision"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not delete category")
        connection.send_error(msg["id"], "storage_error", "No se ha podido eliminar la categoría.")
    else:
        connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/suggestion",
    vol.Required("action"): vol.In(("add", "dismiss")),
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_suggestion(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        if msg["action"] == "add":
            product = await catalog.async_save_product({"name": msg["name"]}, from_suggestion=True)
            result = {"product": product}
        else:
            await catalog.async_dismiss_suggestion(msg["name"])
            result = {}
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist catalog suggestion")
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar el cambio. Inténtalo de nuevo.")
    else:
        connection.send_result(msg["id"], result)
