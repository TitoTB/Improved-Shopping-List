"""Authenticated commands for the integration's shared local catalog."""

import logging
from typing import Any

import probatio as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .catalog import Catalog, CatalogError
from .const import DOMAIN
from .list_settings import ListSettingsError

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
    websocket_api.async_register_command(hass, ws_category_save)
    websocket_api.async_register_command(hass, ws_category_delete)
    websocket_api.async_register_command(hass, ws_suggestion)
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_subscribe)
    websocket_api.async_register_command(hass, ws_settings_update)


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
