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
    return data["eci_catalog"] if msg.get("source")=="elcorteingles" else data["catalog_sources"]


@callback
def register(hass):
    for command in (status, subscribe, set_enabled):
        websocket_api.async_register_command(hass,command)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/status",vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles"))})
@callback
def status(hass,connection,msg):
    if source := manager(hass,connection,msg):
        connection.send_result(msg["id"],source.snapshot)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/subscribe",vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles"))})
@callback
def subscribe(hass,connection,msg):
    if source := manager(hass,connection,msg):
        update = lambda:connection.send_event(msg["id"],source.snapshot)
        connection.subscriptions[msg["id"]] = source.subscribe(update)
        connection.send_result(msg["id"])
        update()


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/catalog_sources/set",vol.Required("enabled"):bool,vol.Optional("source",default="alcampo"):vol.In(("alcampo","elcorteingles"))})
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
