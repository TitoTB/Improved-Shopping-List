"""Select the default to-do entity through the Home Assistant UI."""

from typing import Any

import probatio as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import CONF_TODO_ENTITY, CONF_TODO_ENTITIES, DOMAIN, NAME
from .list_settings import list_options


def _schema(selected: str | None = None) -> vol.Schema:
    field = (
        vol.Required(CONF_TODO_ENTITY, default=selected)
        if selected
        else vol.Required(CONF_TODO_ENTITY)
    )
    return vol.Schema(
        {
            field: selector.EntitySelector(selector.EntitySelectorConfig(domain="todo"))
        }
    )


def _valid_entity(hass: HomeAssistant, entity_id: str) -> bool:
    return entity_id.startswith("todo.") and hass.states.get(entity_id) is not None


class ImprovedShoppingListConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One integration instance with a selectable default list."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            if _valid_entity(self.hass, user_input[CONF_TODO_ENTITY]):
                return self.async_create_entry(title=NAME, data=user_input)
            errors[CONF_TODO_ENTITY] = "invalid_entity"
        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "ImprovedShoppingListOptionsFlow":
        return ImprovedShoppingListOptionsFlow()


class ImprovedShoppingListOptionsFlow(config_entries.OptionsFlow):
    """Change the default list without reinstalling the integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if _valid_entity(self.hass, user_input[CONF_TODO_ENTITY]):
                entities = list_options(self.config_entry)["entities"]
                if user_input[CONF_TODO_ENTITY] not in entities:
                    entities.append(user_input[CONF_TODO_ENTITY])
                return self.async_create_entry(title="", data={
                    **self.config_entry.options, **user_input, CONF_TODO_ENTITIES: entities,
                })
            errors[CONF_TODO_ENTITY] = "invalid_entity"
        selected = self.config_entry.options.get(
            CONF_TODO_ENTITY, self.config_entry.data[CONF_TODO_ENTITY]
        )
        return self.async_show_form(
            step_id="init", data_schema=_schema(selected), errors=errors
        )
