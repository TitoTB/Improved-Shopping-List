"""Authenticated commands for the integration's shared local catalog."""

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .carrefour_account import CarrefourAccountError
from .catalog import Catalog, CatalogError
from .const import DOMAIN
from .list_settings import ListSettingsError
from .stores import StoreError
from .store_location import reference_location
from .icons import IconError
from .community import build_export
from .community_sync import CommunityError
from .product_translation import async_translate_name
from .product_lookup import is_product_barcode
from .store_links import normalize_links, STORES
from . import store_availability

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
    from .dia_websocket import register as register_dia
    register_dia(hass)
    from .lidl_websocket import register as register_lidl
    register_lidl(hass)
    websocket_api.async_register_command(hass, ws_alcampo_status)
    websocket_api.async_register_command(hass, ws_alcampo_options)
    websocket_api.async_register_command(hass, ws_dia_prices_status)
    websocket_api.async_register_command(hass, ws_dia_prices_options)
    websocket_api.async_register_command(hass, ws_alcampo_test_search)
    websocket_api.async_register_command(hass, ws_comparison_data)
    for command in (ws_carrefour_account_status, ws_carrefour_account_login, ws_carrefour_account_send_code,
                    ws_carrefour_account_verify, ws_carrefour_account_disconnect, ws_carrefour_account_purchases, ws_carrefour_account_sync_history, ws_carrefour_account_options, ws_carrefour_account_preview, ws_carrefour_account_preview_saved):
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_catalog_get)
    websocket_api.async_register_command(hass, ws_stock_get)
    for command in (ws_quantities_get, ws_quantities_subscribe, ws_quantities_adjust):
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_stock_subscribe)
    websocket_api.async_register_command(hass, ws_stock_add)
    websocket_api.async_register_command(hass, ws_stock_adjust)
    websocket_api.async_register_command(hass, ws_stock_save)
    websocket_api.async_register_command(hass, ws_stock_remove)
    websocket_api.async_register_command(hass, ws_purchase_detection_settings)
    websocket_api.async_register_command(hass, ws_detected_purchase_complete)
    websocket_api.async_register_command(hass, ws_detected_purchase_discard)
    websocket_api.async_register_command(hass, ws_detected_purchase_search_ticket)
    websocket_api.async_register_command(hass, ws_detected_purchase_preview_ticket)
    for command in (ws_receipts_get, ws_receipts_subscribe, ws_receipts_preview, ws_receipts_confirm, ws_receipts_discard, ws_receipts_options, ws_receipts_link, ws_receipts_review_saved):
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_catalog_subscribe)
    websocket_api.async_register_command(hass, ws_catalog_save)
    for command in (ws_recipe_save, ws_recipe_delete, ws_recipe_add, ws_recipe_season):
        websocket_api.async_register_command(hass, command)
    websocket_api.async_register_command(hass, ws_season_months)
    websocket_api.async_register_command(hass, ws_recommendation_category_save)
    websocket_api.async_register_command(hass, ws_recommendation_category_delete)
    websocket_api.async_register_command(hass, ws_catalog_delete)
    websocket_api.async_register_command(hass, ws_category_save)
    websocket_api.async_register_command(hass, ws_category_delete)
    websocket_api.async_register_command(hass, ws_suggestion)
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_subscribe)
    websocket_api.async_register_command(hass, ws_settings_update)
    websocket_api.async_register_command(hass, ws_name_mode)
    websocket_api.async_register_command(hass, ws_gateway_save)
    websocket_api.async_register_command(hass, ws_gateway_remove)
    websocket_api.async_register_command(hass, ws_personalization)
    websocket_api.async_register_command(hass, ws_notifications)
    websocket_api.async_register_command(hass, ws_store_update)
    websocket_api.async_register_command(hass, ws_resolve_store)
    websocket_api.async_register_command(hass, ws_store_products)
    websocket_api.async_register_command(hass, ws_store_progress)
    websocket_api.async_register_command(hass, ws_carrefour_products)
    websocket_api.async_register_command(hass, ws_favorite_store)
    websocket_api.async_register_command(hass, ws_price_schedule)
    websocket_api.async_register_command(hass, ws_store_enabled)
    websocket_api.async_register_command(hass, ws_cached_prices)
    websocket_api.async_register_command(hass, ws_refresh_prices)
    websocket_api.async_register_command(hass, ws_refresh_all_prices)
    websocket_api.async_register_command(hass, ws_readers_get)
    websocket_api.async_register_command(hass, ws_readers_subscribe)
    websocket_api.async_register_command(hass, ws_reader_capture)
    websocket_api.async_register_command(hass, ws_readers_save)
    websocket_api.async_register_command(hass, ws_readers_delete)
    websocket_api.async_register_command(hass, ws_readers_dismiss)
    websocket_api.async_register_command(hass, ws_icons_search)
    websocket_api.async_register_command(hass, ws_icons_import)
    websocket_api.async_register_command(hass, ws_icons_info)
    websocket_api.async_register_command(hass, ws_community_export)
    websocket_api.async_register_command(hass, ws_community_status)
    websocket_api.async_register_command(hass, ws_community_sharing)
    websocket_api.async_register_command(hass, ws_nutriscore)
    websocket_api.async_register_command(hass, ws_nutrition_distribution)
    websocket_api.async_register_command(hass, ws_logs_get)
    websocket_api.async_register_command(hass, ws_logs_subscribe)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/quantities/get"})
@callback
def ws_quantities_get(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["quantities"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/quantities/subscribe"})
@callback
def ws_quantities_subscribe(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    manager = hass.data[DOMAIN]["quantities"]
    @callback
    def update():
        connection.send_event(msg["id"], manager.snapshot)
    connection.subscriptions[msg["id"]] = manager.subscribe(update)
    connection.send_result(msg["id"])
    update()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/quantities/adjust",
    vol.Required("entity_id"): str, vol.Required("uid"): str, vol.Required("direction"): vol.In((-1, 1))})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_quantities_adjust(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["quantities"].async_adjust(msg["entity_id"], msg["uid"], msg["direction"])
    except (CatalogError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid_quantity", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/get"})
@callback
def ws_stock_get(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["stock"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/get"})
@websocket_api.require_admin
@callback
def ws_receipts_get(hass, connection, msg):
    if _catalog(hass,connection,msg):
        connection.send_result(msg["id"],hass.data[DOMAIN]["receipts"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/subscribe"})
@websocket_api.require_admin
@callback
def ws_receipts_subscribe(hass, connection, msg):
    if not _catalog(hass,connection,msg):
        return
    data = hass.data[DOMAIN]
    connection.subscriptions[msg["id"]] = data["stock"].subscribe(lambda:connection.send_event(msg["id"],data["receipts"].snapshot))
    connection.send_result(msg["id"])
    connection.send_event(msg["id"],data["receipts"].snapshot)


async def _receipt_operation(hass,connection,msg,operation):
    if not _catalog(hass,connection,msg):
        return
    try:
        result = await operation(hass.data[DOMAIN]["receipts"],connection.user.id)
    except CatalogError as err:
        connection.send_error(msg["id"],err.code,str(err))
    except OSError:
        connection.send_error(msg["id"],"storage_error","No se ha podido guardar el ticket. No se ha modificado el stock.")
    else:
        connection.send_result(msg["id"],result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/preview",
    vol.Required("pdf"):vol.All(str,vol.Length(max=2796204))})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_receipts_preview(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_preview(msg["pdf"],owner))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/confirm",vol.Required("token"):str,
    vol.Required("lines"):list,vol.Required("update_prices"):bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_receipts_confirm(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_confirm(msg["token"],owner,msg["lines"],msg["update_prices"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/options",vol.Required("token"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_receipts_options(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_options(msg["token"],owner))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/link",vol.Required("token"):str,vol.Required("lines"):list})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_receipts_link(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_link(msg["token"],owner,msg["lines"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/discard",vol.Required("token"):str})
@websocket_api.require_admin
@callback
def ws_receipts_discard(hass,connection,msg):
    if _catalog(hass,connection,msg):
        hass.data[DOMAIN]["receipts"].discard(msg["token"],connection.user.id)
        connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/subscribe"})
@callback
def ws_stock_subscribe(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    stock = hass.data[DOMAIN]["stock"]
    connection.subscriptions[msg["id"]] = stock.subscribe(lambda: connection.send_event(msg["id"], stock.snapshot))
    connection.send_result(msg["id"])
    connection.send_event(msg["id"], stock.snapshot)


async def _stock_write(hass, connection, msg, operation):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await operation(hass.data[DOMAIN]["stock"])
        await hass.data[DOMAIN]["recurrence"].async_sync_stock()
        if isinstance(result,dict) and result.get("id"):
            result = next((item for item in hass.data[DOMAIN]["stock"].snapshot["items"] if item["id"] == result["id"]),result)
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except OSError:
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar el stock.")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/add", vol.Required("name"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_stock_add(hass, connection, msg):
    await _stock_write(hass, connection, msg, lambda stock: stock.async_add(msg["name"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/adjust", vol.Required("item_id"):str, vol.Required("delta"):int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_stock_adjust(hass, connection, msg):
    await _stock_write(hass, connection, msg, lambda stock: stock.async_adjust(msg["item_id"], msg["delta"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/save", vol.Required("item_id"):str,
    vol.Required("revision"):int, vol.Required("config"):dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_stock_save(hass, connection, msg):
    await _stock_write(hass, connection, msg, lambda stock: stock.async_save(msg["item_id"],msg["revision"],msg["config"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stock/remove", vol.Required("item_id"):str, vol.Required("revision"):int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_stock_remove(hass, connection, msg):
    await _stock_write(hass, connection, msg, lambda stock: stock.async_remove(msg["item_id"], msg["revision"]))


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
        shared = hass.data[DOMAIN]["community_sync"].suggestions(query[:100])
        community = shared + (await hass.data[DOMAIN]["community"].async_search(query[:100]) if msg["start"] == 0 and len(shared) < 6 else []) if msg["start"] == 0 else []
        try:
            offset = 32 if len(shared) >= 6 else 0
            result = ({"icons": [], "next_start": 32, "has_more": True} if offset and msg["start"] == 0 else
                await hass.data[DOMAIN]["icons"].async_search(query[:100], max(0, msg["start"]-offset)))
            if offset and msg["start"]:
                result["next_start"] += offset
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
        library = (hass.data[DOMAIN]["community_sync"] if msg["icon_id"].startswith("shared:") else
            hass.data[DOMAIN]["community"] if msg["icon_id"].startswith("community:") else hass.data[DOMAIN]["icons"])
        result = await library.async_import(msg["icon_id"])
    except (IconError, CommunityError) as err:
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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/nutrition_distribution"})
@callback
def ws_nutrition_distribution(hass, connection, msg):
    if catalog := _catalog(hass, connection, msg):
        lookup = hass.data[DOMAIN]["readers"].lookup
        connection.send_result(msg["id"], lookup.nutrition_distribution(catalog.products))


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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readers/capture", vol.Required("reader_id"):str})
@websocket_api.require_admin
@callback
def ws_reader_capture(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        stop = hass.data[DOMAIN]["readers"].capture(msg["reader_id"], lambda reading: connection.send_event(msg["id"], reading))
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    else:
        connection.subscriptions[msg["id"]] = stop
        connection.send_result(msg["id"])


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
        connection.send_result(msg["id"], {**hass.data[DOMAIN]["settings"].snapshot,
            "available_stores": sorted(store_availability.AVAILABLE_STORES)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/subscribe"})
@callback
def ws_settings_subscribe(hass: HomeAssistant, connection, msg) -> None:
    if not _catalog(hass, connection, msg):
        return
    settings = hass.data[DOMAIN]["settings"]

    @callback
    def on_update():
        connection.send_event(msg["id"], {**settings.snapshot,
            "available_stores": sorted(store_availability.AVAILABLE_STORES)})

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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/name_mode",
    vol.Required("entity_id"): str, vol.Required("enabled"): bool})
@websocket_api.require_admin
@callback
def ws_name_mode(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_name_mode(msg["entity_id"], msg["enabled"])
    except ListSettingsError as err:
        connection.send_error(msg["id"], "invalid_list", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/gateway_save",
    vol.Required("entity_id"): str, vol.Required("target_entity"): str,
    vol.Required("remove_after_transfer"): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_gateway_save(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["gateway_lists"].async_configure(
            msg["entity_id"], msg["target_entity"], msg["remove_after_transfer"])
    except (ListSettingsError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid_gateway", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/gateway_remove",
    vol.Required("entity_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_gateway_remove(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    result = await hass.data[DOMAIN]["gateway_lists"].async_remove(msg["entity_id"])
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/notifications", vol.Required("notifications"): dict})
@websocket_api.require_admin
@callback
def ws_notifications(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_notifications(msg["notifications"])
    except ListSettingsError as err:
        connection.send_error(msg["id"], "invalid_notifications", str(err))
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
    vol.Optional("area_id", default=""): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_store_update(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        settings = hass.data[DOMAIN]["settings"]
        result = (await settings.async_update_regional(msg["store"], msg["enabled"], msg["postal_code"], msg["area_id"], msg["verify"]) if msg["store"] in ("consum", "lasirena", "eroski", "dia")
                  else await settings.async_update_alcampo(msg["enabled"], msg["region_id"]) if msg["store"] == "alcampo"
                  else await settings.async_update_carrefour(msg["enabled"], msg.get("sale_point")) if msg["store"] == "carrefour"
            else await settings.async_update_store(msg["enabled"], msg["postal_code"], msg["verify"]))
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_store", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/resolve_store",
    vol.Required("store"):vol.In(("consum", "lasirena", "eroski", "dia")), vol.Required("postal_code"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_resolve_store(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    settings = hass.data[DOMAIN]["settings"]
    generation = settings._generation
    try:
        location = reference_location(msg["store"])
        result = {"postal_code": location["postal_code"], "areas": [{"id": location["area_id"], "name": location["area_name"], "zone": location["zone"]}]}
        if generation != settings._generation or not hass.data.get(DOMAIN, {}).get("active"):
            raise StoreError("La integración se ha detenido.")
        connection.send_result(msg["id"], result)
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_store", str(err))


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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/store_enabled",
    vol.Required("store"):vol.In(tuple(STORES)), vol.Required("enabled"):bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_store_enabled(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["settings"].async_toggle_located_store(msg["store"], msg["enabled"])
    except StoreError as err:
        connection.send_error(msg["id"], "invalid_location", str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/price_schedule", vol.Required("time"):str,
    vol.Optional("enabled"):bool,vol.Optional("days"):int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_price_schedule(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_price_schedule(msg["time"],msg.get("enabled"),msg.get("days"))
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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/refresh_all_prices"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_refresh_all_prices(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["price_manager"].async_refresh_all()
    except (ValueError,OSError) as err:
        connection.send_error(msg["id"],"price_refresh_error",str(err))
    else:
        connection.send_result(msg["id"],result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/store_prices",
    vol.Optional("links", default={}):dict, vol.Optional("codes", default=[]):[str],
    vol.Optional("product_id",default=""):str,
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
        product=next((product for product in hass.data[DOMAIN]["catalog"].products if product["id"]==msg["product_id"]),None)
        result = {"products":manager.prices_for(product or {"store_links":links,"barcodes":msg["codes"]}), "nightly":True}
    connection.send_result(msg["id"], result)


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
        await hass.data[DOMAIN]["recurrence"].async_sync_stock()
        product = next(item for item in catalog.products if item["id"] == product["id"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist catalog product")
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar el catálogo. Inténtalo de nuevo.")
    else:
        connection.send_result(msg["id"], {"product": product})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recipe/save", vol.Required("recipe"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recipe_save(hass, connection, msg):
    await _recipe_write(hass, connection, msg, "save")


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recipe/delete", vol.Required("recipe_id"): str, vol.Required("revision"): int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recipe_delete(hass, connection, msg):
    await _recipe_write(hass, connection, msg, "delete")


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recipe/season_months", vol.Required("recipe_id"): str,
    vol.Required("months"): list, vol.Required("enabled"): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recipe_season(hass, connection, msg):
    await _recipe_write(hass, connection, msg, "season")


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recipe/add", vol.Required("recipe_id"): str,
    vol.Required("revision"): int, vol.Required("entity_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recipe_add(hass, connection, msg):
    await _recipe_write(hass, connection, msg, "add")


async def _recipe_write(hass, connection, msg, action):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        if action == "save":
            result = {"recipe": await catalog.async_save_recipe(msg["recipe"])}
        elif action == "delete":
            await catalog.async_delete_recipe(msg["recipe_id"], msg["revision"])
            result = {}
        elif action == "season":
            result = {"recipe": await catalog.async_set_recipe_season_months(msg["recipe_id"], msg["months"], msg["enabled"])}
        else:
            result = await hass.data[DOMAIN]["quantities"].async_add_recipe(msg["recipe_id"], msg["revision"], msg["entity_id"], hass.data[DOMAIN]["readers"]._operation_lock)
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not process recipe")
        connection.send_error(msg["id"], "storage_error", "No se ha podido completar la operación con la receta.")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recommendation_category/save",
    vol.Required("category"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recommendation_category_save(hass, connection, msg):
    await _recommendation_category_write(hass, connection, msg, False)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/catalog/recommendation_category/delete",
    vol.Required("category_id"): str, vol.Required("revision"): int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_recommendation_category_delete(hass, connection, msg):
    await _recommendation_category_write(hass, connection, msg, True)


async def _recommendation_category_write(hass, connection, msg, delete):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        if delete:
            await catalog.async_delete_recommendation_category(msg["category_id"], msg["revision"])
            result = {}
        else:
            result = {"category": await catalog.async_save_recommendation_category(msg["category"])}
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist suggestion category")
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar la categoría de sugerencias.")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/catalog/season_months",
    vol.Required("product_id"): str, vol.Required("months"): list,
    vol.Required("enabled"): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_season_months(hass, connection, msg):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    try:
        product = await catalog.async_set_season_months(msg["product_id"], msg["months"], msg["enabled"])
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        _LOGGER.exception("Could not persist seasonal products")
        connection.send_error(msg["id"], "storage_error", "No se han podido guardar los productos de temporada.")
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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/community/status"})
@websocket_api.require_admin
@callback
def ws_community_status(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["community_sync"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/community/sharing", vol.Required("enabled"): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_community_sharing(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["community_sync"].async_sharing(msg["enabled"])
    except (CommunityError, OSError, ValueError, TimeoutError):
        connection.send_error(msg["id"], "community_error", "No se ha podido guardar o iniciar la autorización comunitaria.")
    else:
        connection.send_result(msg["id"], result)


async def _carrefour_account_operation(hass, connection, msg, action, operation):
    if not _catalog(hass, connection, msg):
        return
    data = hass.data[DOMAIN]
    try:
        result = await operation(data["carrefour_account"], connection.user.id)
    except CarrefourAccountError as err:
        data["activity"].record("stores.account", "Carrefour: " + str(err), source="manual", diagnostics={"action": action, **err.diagnostics})
        connection.send_error(msg["id"], err.code, str(err))
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except (OSError, HomeAssistantError):
        connection.send_error(msg["id"], "storage_error", "No se ha podido guardar la sesión o preparar el ticket de Carrefour.")
    else:
        data["activity"].record("stores.account", "Carrefour: " + action, source="manual",
            diagnostics={"action": action, **({"purchases": len(result["purchases"])} if isinstance(result, dict) and "purchases" in result else {})})
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/status"})
@websocket_api.require_admin
@callback
def ws_carrefour_account_status(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["carrefour_account"].status(connection.user.id))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/login",
    vol.Required("username"): vol.All(str, vol.Length(min=1, max=255)),
    vol.Required("password"): vol.All(str, vol.Length(max=255)),
    vol.Optional("remember_credentials", default=False): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_login(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "conexión de cuenta solicitada",
        lambda manager, owner: manager.async_login(owner, msg["username"], msg["password"], msg["remember_credentials"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/send_code", vol.Required("destination"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_send_code(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "código de verificación solicitado",
        lambda manager, owner: manager.async_send_code(owner, msg["destination"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/verify", vol.Required("code"): vol.All(str, vol.Length(max=10))})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_verify(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "verificación de cuenta",
        lambda manager, owner: manager.async_verify(owner, msg["code"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/disconnect"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_disconnect(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "cuenta desconectada",
        lambda manager, owner: manager.async_disconnect(owner))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/purchases", vol.Optional("cursor"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_purchases(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "consulta manual de compras",
        lambda manager, owner: manager.async_purchases(owner, msg.get("cursor")))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/preview", vol.Required("purchase_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_preview(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "ticket descargado para revisión",
        lambda manager, owner: manager.async_preview(owner, msg["purchase_id"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/sync_history"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_sync_history(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "historial de compras incorporado",
        lambda manager, owner: manager.async_sync_history(owner))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/options",vol.Required("options"):dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_options(hass, connection, msg):
    await _carrefour_account_operation(hass,connection,msg,"opciones guardadas",lambda manager,owner:manager.async_options(owner,msg["options"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/review_saved",vol.Required("receipt_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_receipts_review_saved(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_review_saved(msg["receipt_id"],owner))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/carrefour_account/preview_saved", vol.Required("receipt_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_carrefour_account_preview_saved(hass, connection, msg):
    await _carrefour_account_operation(hass, connection, msg, "ticket de compra guardada recuperado",
        lambda manager, owner: manager.async_preview_saved(owner, msg["receipt_id"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/dia/prices/status"})
@websocket_api.require_admin
def ws_dia_prices_status(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["dia_prices"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/dia/prices/options", vol.Required("options"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_prices_options(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["dia_prices"].async_options(msg["options"])
        connection.send_result(msg["id"], result)
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/alcampo/status"})
@websocket_api.require_admin
def ws_alcampo_status(hass, connection, msg):
    if _catalog(hass, connection, msg):
        connection.send_result(msg["id"], hass.data[DOMAIN]["alcampo"].snapshot)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/alcampo/options", vol.Required("options"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_alcampo_options(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["alcampo"].async_options(msg["options"])
        connection.send_result(msg["id"], result)
    except CatalogError as err:
        connection.send_error(msg["id"], err.code, str(err))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/purchase_detection", vol.Required("config"):dict})
@websocket_api.require_admin
@callback
def ws_purchase_detection_settings(hass, connection, msg):
    if not _catalog(hass,connection,msg):
        return
    try:
        result = hass.data[DOMAIN]["settings"].update_purchase_detection(msg["config"])
    except ListSettingsError as err:
        connection.send_error(msg["id"],"invalid_purchase_detection",str(err))
    else:
        connection.send_result(msg["id"],result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/complete_detection",
    vol.Required("receipt_id"):str, vol.Required("store"):str, vol.Required("total"):vol.Any(int,float),
    vol.Optional("store_name",default=""):str, vol.Optional('product_keys'): [str], vol.Optional('shoppers'): [str]})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_detected_purchase_complete(hass, connection, msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_complete_detected_purchase(
        msg["receipt_id"],msg["store"],msg["total"],msg["store_name"],msg.get('product_keys'),msg.get('shoppers')))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/discard_detection",vol.Required("receipt_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_detected_purchase_discard(hass, connection, msg):
    await _receipt_operation(hass,connection,msg,lambda manager,owner:manager.async_discard_detected_purchase(msg["receipt_id"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/alcampo/test_search", vol.Required("product_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_alcampo_test_search(hass, connection, msg):
    if not _catalog(hass, connection, msg):
        return
    try:
        result = await hass.data[DOMAIN]["alcampo"].async_test_search(msg["product_id"])
        connection.send_result(msg["id"], result)
    except (CatalogError, OSError) as err:
        connection.send_error(msg["id"], getattr(err, "code", "alcampo_error"), str(err))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/analytics/comparison"})
@callback
def ws_comparison_data(hass, connection, msg):
    if not (catalog := _catalog(hass, connection, msg)):
        return
    data = hass.data[DOMAIN]
    if not data["settings"].snapshot.get("price_updates_enabled", True):
        connection.send_result(msg["id"], {"observations":[], "purchases":[], "stores":[], "enabled":False})
        return
    connection.send_result(msg["id"], data["price_history"].comparison_data(catalog, data["settings"], data["receipts"], [{**offer,"catalog_product_id":product["id"]} for product in catalog.products for key in ("alcampo", "dia_prices") if (manager := data.get(key)) and (offer := manager.offer_for(product))]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/search_detection_ticket",vol.Required("receipt_id"):str,vol.Required("store"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_detected_purchase_search_ticket(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda receipts,owner:hass.data[DOMAIN]["ticket_accounts"].async_search_manual(receipts,owner,msg["receipt_id"],msg["store"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/receipts/preview_detection_ticket",vol.Required("recovery_token"):str,vol.Required("purchase_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_detected_purchase_preview_ticket(hass,connection,msg):
    await _receipt_operation(hass,connection,msg,lambda receipts,owner:hass.data[DOMAIN]["ticket_accounts"].async_preview_manual(receipts,owner,msg["recovery_token"],msg["purchase_id"]))
