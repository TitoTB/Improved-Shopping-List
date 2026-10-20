"""Exercise configuration, actual panel registration and reloads in HA Core."""

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import (
    CONF_TODO_ENTITY,
    DOMAIN,
    PANEL_PATH,
)


async def test_config_flow_rejects_missing_and_non_todo_entities(hass):
    """The default list must exist and belong to the todo domain."""
    hass.states.async_set("sensor.example", "1")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    for entity_id in ("todo.missing", "sensor.example"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TODO_ENTITY: entity_id}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {CONF_TODO_ENTITY: "invalid_entity"}


async def test_config_flow_creates_entry_and_prevents_duplicate(hass):
    """An arbitrary existing todo provider can be selected."""
    hass.states.async_set("todo.bring", "0")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TODO_ENTITY: "todo.bring"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_TODO_ENTITY: "todo.bring"}
    await hass.async_block_till_done()
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert duplicate["type"] == FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


async def test_setup_options_reload_unload_and_reinstall(hass):
    """Changing options must not duplicate static routes or remove provider data."""
    hass.states.async_set("todo.bring", "2", {"friendly_name": "Bring!"})
    hass.states.async_set("todo.local", "1", {"friendly_name": "Casa"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, title="Improved Shopping List",
        data={CONF_TODO_ENTITY: "todo.bring"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    panel = hass.data[DATA_PANELS][PANEL_PATH]
    assert panel.config["default_entity"] == "todo.bring"
    assert panel.config["_panel_custom"]["module_url"].endswith("panel.js?v=0.1.0")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TODO_ENTITY: "todo.local"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.data[DATA_PANELS][PANEL_PATH].config["default_entity"] == "todo.local"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_PATH not in hass.data[DATA_PANELS]
    assert hass.states.get("todo.bring").state == "2"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_PATH in hass.data[DATA_PANELS]


async def test_frontend_module_is_served(hass, hass_client):
    """The registered URL serves the actual module, without a www copy step."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_client()
    response = await client.get("/improved_shopping_list_static/panel.js?v=0.1.0")
    assert response.status == 200
    assert "improved-shopping-list-panel" in await response.text()
