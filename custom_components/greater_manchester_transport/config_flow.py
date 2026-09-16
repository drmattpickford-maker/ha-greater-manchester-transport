"""Configuration flow for Greater Manchester Transport."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_BODS_API_KEY, DOMAIN


class GreaterManchesterTransportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure schedule-only use or optional BODS live bus data."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Greater Manchester Transport", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_BODS_API_KEY, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "note": "Optional. Leave blank for TfGM schedule-only monitoring."
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Allow a BODS key to be changed or deliberately removed later."""
        return GreaterManchesterTransportOptionsFlow(config_entry)


class GreaterManchesterTransportOptionsFlow(config_entries.OptionsFlow):
    """Settings which do not require deleting the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current_key = self._entry.options.get(
            CONF_BODS_API_KEY, self._entry.data.get(CONF_BODS_API_KEY, "")
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BODS_API_KEY, default=current_key): str,
                }
            ),
            description_placeholders={
                "note": "Leave the BODS key empty and save to remove it."
            },
        )
