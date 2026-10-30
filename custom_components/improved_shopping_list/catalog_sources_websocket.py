"""Catalog source consent and live completion progress."""
import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from .const import DOMAIN


def manager(hass,connection,msg):
    data = hass.data.get(DOMAIN,{})
    if not data.get("active"):
        connection.send_error(msg["id"],"not_loaded","La integración no está cargada.")
        return None
    if msg.get("source")=="elcorteingles":
        connection.send_error(msg["id"],"source_unavailable","El catálogo de El Corte Inglés está retirado temporalmente.")
        return None
    if msg.get("source") in ("masymas","bm","consum"):return data["public_catalogs"][msg["source"]]
    return data["mercadona_catalog"] if msg.get("source")=="mercadona" else data["catalog_sources"]


@callback
def register(hass):
    for command in (status, subscribe, set_enabled, set_visibility):
        websocket_api.async_register_command(hass,command)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/status",vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles","mercadona","masymas","bm","consum"))})
@callback
def status(hass,connection,msg):
    if source := manager(hass,connection,msg):
        connection.send_result(msg["id"],source.snapshot)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/subscribe",vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles","mercadona","masymas","bm","consum"))})
@callback
def subscribe(hass,connection,msg):
    if source := manager(hass,connection,msg):
        update = lambda:connection.send_event(msg["id"],source.snapshot)
        connection.subscriptions[msg["id"]] = source.subscribe(update)
        connection.send_result(msg["id"])
        update()


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/set",vol.Required("enabled"):bool,vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles","mercadona","masymas","bm","consum"))})
@websocket_api.require_admin
@websocket_api.async_response
async def set_enabled(hass,connection,msg):
    if source := manager(hass,connection,msg):
        try:
            result = await source.async_set_enabled(msg["enabled"])
        except (ValueError,OSError) as err:
            connection.send_error(msg["id"],"catalog_source_error",str(err))
        else:
            connection.send_result(msg["id"],result)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/visibility",vol.Required("show_store"):bool,vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles","mercadona","masymas","bm","consum"))})
@websocket_api.require_admin
@websocket_api.async_response
async def set_visibility(hass,connection,msg):
    if source := manager(hass,connection,msg):
        try:
            result=await source.async_set_show_store(msg["show_store"])
        except (ValueError,OSError) as err:
            connection.send_error(msg["id"],"catalog_source_error",str(err))
        else:
            connection.send_result(msg["id"],result)
