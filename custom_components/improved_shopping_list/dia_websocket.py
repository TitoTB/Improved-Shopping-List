"""Administrator-only DIA account commands; no credentials in responses or logs."""
import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError
from .catalog import CatalogError
from .const import DOMAIN
from .dia_account import DiaAccountError


async def _operation(hass,connection,msg,action):
    data=hass.data.get(DOMAIN,{})
    if not data.get("active"):
        connection.send_error(msg["id"],"not_loaded","Improved Shopping List no está activa.")
        return
    manager=data["dia_account"];owner=connection.user.id
    try:
        if action=="status":result=manager.status(owner)
        elif action=="login":result=await manager.async_login(owner,msg["username"],msg["password"],msg["remember_credentials"])
        elif action=="disconnect":result=await manager.async_disconnect(owner)
        elif action=="options":result=await manager.async_options(owner,msg["options"])
        elif action=="purchases":result=await manager.async_purchases(owner,msg.get("cursor"))
        elif action=="sync_history":result=await manager.async_sync_history(owner)
        elif action=="preview":result=await manager.async_preview(owner,msg["purchase_id"])
        else:result=await manager.async_preview_saved(owner,msg["receipt_id"])
    except DiaAccountError as err:
        data["activity"].record("stores.account","DIA: "+str(err),source="manual",diagnostics={"action":action,**err.diagnostics})
        connection.send_error(msg["id"],err.code,str(err))
    except CatalogError as err:
        connection.send_error(msg["id"],err.code,str(err))
    except (OSError,HomeAssistantError):
        connection.send_error(msg["id"],"storage_error","No se ha podido guardar la sesión o preparar el ticket de DIA.")
    else:
        if action!="status":data["activity"].record("stores.account","DIA: "+{"login":"cuenta conectada","disconnect":"cuenta desconectada","options":"opciones guardadas","purchases":"historial consultado","sync_history":"historial incorporado","preview":"ticket preparado para revisar","preview_saved":"ticket preparado para revisar"}[action],source="manual")
        connection.send_result(msg["id"],result)


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/status"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_status(hass,connection,msg):
    await _operation(hass,connection,msg,"status")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/login",vol.Required("username"):vol.All(str,vol.Length(min=1,max=255)),vol.Required("password"):vol.All(str,vol.Length(max=255)),vol.Optional("remember_credentials",default=False):bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_login(hass,connection,msg):
    await _operation(hass,connection,msg,"login")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/disconnect"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_disconnect(hass,connection,msg):
    await _operation(hass,connection,msg,"disconnect")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/options",vol.Required("options"):dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_options(hass,connection,msg):
    await _operation(hass,connection,msg,"options")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/purchases",vol.Optional("cursor"):dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_purchases(hass,connection,msg):
    await _operation(hass,connection,msg,"purchases")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/sync_history"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_sync_history(hass,connection,msg):
    await _operation(hass,connection,msg,"sync_history")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/preview",vol.Required("purchase_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_preview(hass,connection,msg):
    await _operation(hass,connection,msg,"preview")


@websocket_api.websocket_command({vol.Required("type"):f"{DOMAIN}/dia_account/preview_saved",vol.Required("receipt_id"):str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_dia_preview_saved(hass,connection,msg):
    await _operation(hass,connection,msg,"preview_saved")


def register(hass):
    for command in (ws_dia_status,ws_dia_login,ws_dia_disconnect,ws_dia_options,ws_dia_purchases,ws_dia_sync_history,ws_dia_preview,ws_dia_preview_saved):
        websocket_api.async_register_command(hass,command)
