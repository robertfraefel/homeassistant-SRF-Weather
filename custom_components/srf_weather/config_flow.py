"""Config flow for SRF Weather integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import SRFWeatherAPI
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SRFWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for SRF Weather."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]

            # Use lat/lon as unique ID to prevent duplicate entries.
            await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = SRFWeatherAPI(
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                session,
            )

            try:
                valid = await api.validate_credentials()
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            else:
                if not valid:
                    errors["base"] = "invalid_auth"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        # Pre-fill lat/lon from HA home location.
        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="SRF Weather"): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_LATITUDE, default=default_lat): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=default_lon): cv.longitude,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
