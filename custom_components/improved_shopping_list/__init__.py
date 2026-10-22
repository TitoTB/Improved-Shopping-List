"""A native Home Assistant panel for existing to-do lists."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .catalog import Catalog
from .activity import ActivityLog
from .community import CommunityLibrary
from .community_sync import CommunitySync
from .icons import ICONS_URL, IconLibrary
from .list_settings import ListSettings
from .gateway_lists import GatewayLists
from .entity_data import EntityData
from .quantities import ListQuantities
from .notifications import NotificationManager
from .readers import ReaderManager
from .stock import StockManager
from .stock_automation import StockAutomation
from .receipts import ReceiptManager
from .carrefour_account import CarrefourAccount
from .alcampo import AlcampoManager
from .price_manager import PriceManager, StorePriceView
from .recurrence import RecurrenceManager
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

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TIME]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register public frontend assets once, including after entry reloads."""
    if DOMAIN not in hass.data:
        catalog = Catalog(hass)
        await catalog.async_load()
        settings = ListSettings(hass)
        stock = StockManager(hass, catalog)
        await stock.async_load()
        readers = ReaderManager(hass, catalog, settings)
        readers.stock = stock
        await readers.async_load()
        activity = ActivityLog(hass, catalog, settings, readers)
        await activity.async_load()
        readers.activity = activity
        stock.activity = activity
        quantities = ListQuantities(hass, catalog, settings, activity)
        await quantities.async_load()
        notifications = NotificationManager(hass, settings, stock, activity, catalog, readers)
        await notifications.async_load()
        gateways = GatewayLists(hass, settings, activity, readers._operation_lock)
        await gateways.async_load()
        stock_automation = StockAutomation(hass,stock,settings,activity,readers._operation_lock)
        stock_automation.quantities = quantities
        prices = PriceManager(hass, catalog, settings, activity)
        await prices.async_load()
        receipts = ReceiptManager(hass, stock, stock_automation, prices)
        carrefour_account = CarrefourAccount(hass, receipts, activity)
        await carrefour_account.async_load()
        carrefour_account.settings=settings
        stock_automation.carrefour_account=carrefour_account
        prices.receipts = receipts
        alcampo = AlcampoManager(hass, catalog, settings, prices, receipts, activity)
        await alcampo.async_load()
        prices.alcampo = alcampo
        store_products = StorePriceView(prices, "mercadona")
        recurrence = RecurrenceManager(hass, catalog, settings, activity, readers._operation_lock, stock)
        await recurrence.async_load()
        await recurrence.async_sync_stock()
        icons = IconLibrary(hass)
        await icons.async_load()
        community = CommunityLibrary(hass, icons)
        await community.async_load()
        community_sync = CommunitySync(hass, catalog, icons, prices, readers.lookup)
        await community_sync.async_load()
        prices.community = community_sync
        readers.lookup.community = community_sync
        catalog.community = community_sync
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False),
             StaticPathConfig(ICONS_URL, str(icons.directory), True)]
        )
        hass.data[DOMAIN] = {"catalog": catalog, "stock":stock, "receipts":receipts, "stock_automation":stock_automation, "settings": settings, "price_manager":prices, "store_products": store_products, "recurrence": recurrence, "readers": readers, "icons": icons, "community": community, "community_sync": community_sync, "activity": activity, "active": False}
        hass.data[DOMAIN]["carrefour_account"] = carrefour_account
        hass.data[DOMAIN]["alcampo"] = alcampo
        hass.data[DOMAIN]["gateway_lists"] = gateways
        hass.data[DOMAIN]["quantities"] = quantities
        hass.data[DOMAIN]["entity_data"] = EntityData(hass, hass.data[DOMAIN])
        hass.data[DOMAIN]["notifications"] = notifications
        async_register_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add the sidebar panel. List data stays in the selected to-do provider."""
    hass.data[DOMAIN]["settings"].attach(entry)
    await _async_register_panel(hass, entry)
    hass.data[DOMAIN]["active"] = True
    hass.data[DOMAIN]["carrefour_account"].start()
    hass.data[DOMAIN]["activity"].start()
    hass.data[DOMAIN]["quantities"].start()
    hass.data[DOMAIN]["gateway_lists"].start()
    hass.data[DOMAIN]["stock"].start()
    hass.data[DOMAIN]["stock_automation"].start()
    hass.data[DOMAIN]["readers"].start()
    hass.data[DOMAIN]["recurrence"].start()
    hass.data[DOMAIN]["community_sync"].start()
    hass.data[DOMAIN]["price_manager"].start()
    hass.data[DOMAIN]["alcampo"].start()
    hass.data[DOMAIN]["entity_data"].start()
    hass.data[DOMAIN]["notifications"].start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.data[DOMAIN]["settings"].notify()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel without changing any shopping-list items."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await hass.data[DOMAIN]["notifications"].async_stop()
    hass.data[DOMAIN]["entity_data"].stop()
    frontend.async_remove_panel(hass, PANEL_PATH)
    hass.data[DOMAIN]["active"] = False
    await hass.data[DOMAIN]["carrefour_account"].async_stop()
    await hass.data[DOMAIN]["quantities"].async_stop()
    await hass.data[DOMAIN]["gateway_lists"].async_stop()
    await hass.data[DOMAIN]["community_sync"].async_stop()
    hass.data[DOMAIN]["stock"].stop()
    await hass.data[DOMAIN]["stock_automation"].async_stop()
    await hass.data[DOMAIN]["alcampo"].async_stop()
    await hass.data[DOMAIN]["price_manager"].async_stop()
    await hass.data[DOMAIN]["recurrence"].async_stop()
    hass.data[DOMAIN]["settings"].detach()
    await hass.data[DOMAIN]["readers"].async_stop()
    await hass.data[DOMAIN]["activity"].async_stop()
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Notify open panels while keeping provider subscriptions alive."""
    if not hass.data[DOMAIN]["active"]:
        return
    hass.data[DOMAIN]["settings"].notify()
    panel = hass.data.get(frontend.DATA_PANELS, {}).get(PANEL_PATH)
    if panel:
        frontend.async_register_built_in_panel(
            hass, component_name="custom", sidebar_title=NAME, sidebar_icon="mdi:shopping",
            frontend_url_path=PANEL_PATH, require_admin=False, update=True,
            config={**panel.config, "default_entity": entry.options.get(CONF_TODO_ENTITY, entry.data[CONF_TODO_ENTITY])},
        )
