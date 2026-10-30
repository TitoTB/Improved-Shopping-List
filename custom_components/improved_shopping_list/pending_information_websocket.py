"""Shared pending-information batch status and explicit administrator action."""
import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from .const import DOMAIN

PREFIX=f"{DOMAIN}/catalog/refresh_pending/"


def manager(hass,connection,msg):
    data=hass.data.get(DOMAIN,{})
    if not data.get("active") or not data.get("pending_information_refresh"):
        connection.send_error(msg["id"],"not_loaded","La integración no está cargada.");return None
    return data["pending_information_refresh"]


@callback
def register(hass):
    for command in (status,subscribe,start):websocket_api.async_register_command(hass,command)


@websocket_api.websocket_command({vol.Required("type"):PREFIX+"status"})
@callback
def status(hass,connection,msg):
    if service:=manager(hass,connection,msg):connection.send_result(msg["id"],service.snapshot)


@websocket_api.websocket_command({vol.Required("type"):PREFIX+"subscribe"})
@callback
def subscribe(hass,connection,msg):
    if service:=manager(hass,connection,msg):
        update=lambda:connection.send_event(msg["id"],service.snapshot)
        connection.subscriptions[msg["id"]]=service.subscribe(update)
        connection.send_result(msg["id"]);update()


@websocket_api.websocket_command({vol.Required("type"):PREFIX+"start"})
@websocket_api.require_admin
@websocket_api.async_response
async def start(hass,connection,msg):
    if service:=manager(hass,connection,msg):
        try:result=await service.async_start()
        except (ValueError,OSError) as err:connection.send_error(msg["id"],"catalog_refresh_error",str(err))
        else:connection.send_result(msg["id"],result)
