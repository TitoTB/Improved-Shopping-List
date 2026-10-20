"""A native Home Assistant panel for existing to-do lists."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .catalog import Catalog
from .const import (
    CONF_TODO_ENTITY,
    DOMAIN,
    NAME,
    PANEL_ELEMENT,
    PANEL_PATH,
    STATIC_URL,
    VERSION,
)
from .websocket import async_register_commands


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register public frontend assets once, including after entry reloads."""
    if DOMAIN not in hass.data:
        catalog = Catalog(hass)
        await catalog.async_load()
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        hass.data[DOMAIN] = {"catalog": catalog, "active": False}
        async_register_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add the sidebar panel. List data stays in the selected to-do provider."""
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=NAME,
        sidebar_icon="mdi:shopping",
        module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
        config={
            "default_entity": entry.options.get(
                CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY]
            ),
            "version": VERSION,
        },
        require_admin=False,
    )
    hass.data[DOMAIN]["active"] = True
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel without changing any shopping-list items."""
    frontend.async_remove_panel(hass, PANEL_PATH)
    hass.data[DOMAIN]["active"] = False
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Refresh the default list after changing integration options."""
    await hass.config_entries.async_reload(entry.entry_id)
