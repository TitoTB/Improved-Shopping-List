"""Admin-only configuration for local meal routines."""
import logging
import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError
from .catalog import CatalogError
from .const import DOMAIN

_LOGGER=logging.getLogger(__name__)


async def _run(hass,connection,msg,action):
    data=hass.data.get(DOMAIN,{})
    if not data.get('active') or not data.get('meal_routines'):
        connection.send_error(msg['id'],'not_loaded','La integración no está activa.');return
    manager=data['meal_routines']
    try:
        if action=='save':await manager.async_save(msg['routine'])
        elif action=='delete':await manager.async_delete(msg['routine_id'],msg['revision'])
        connection.send_result(msg['id'],manager.snapshot)
    except CatalogError as error:connection.send_error(msg['id'],error.code,str(error))
    except (OSError,HomeAssistantError):
        _LOGGER.exception('Could not persist meal routine')
        connection.send_error(msg['id'],'storage_error','No se ha podido guardar la rutina. Inténtalo de nuevo.')


@websocket_api.websocket_command({vol.Required('type'):f'{DOMAIN}/routines/get'})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_get(hass,connection,msg):await _run(hass,connection,msg,'get')


@websocket_api.websocket_command({vol.Required('type'):f'{DOMAIN}/routines/save',vol.Required('routine'):dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass,connection,msg):await _run(hass,connection,msg,'save')


@websocket_api.websocket_command({vol.Required('type'):f'{DOMAIN}/routines/delete',vol.Required('routine_id'):str,vol.Required('revision'):int})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete(hass,connection,msg):await _run(hass,connection,msg,'delete')


def register(hass):
    for command in (ws_get,ws_save,ws_delete):websocket_api.async_register_command(hass,command)
