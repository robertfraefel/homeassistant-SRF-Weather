"""Config flow for the SRF Weather integration.

This module implements the UI setup wizard that runs when a user adds SRF
Weather via *Settings → Devices & Services → Add Integration*.

Flow overview
-------------
Step ``user`` (the only step):
  1. Display a form asking for name, API credentials, and location.
  2. On submission, derive a unique ID from the rounded lat/lon pair to
     prevent duplicate entries for the same location.
  3. Validate the credentials against the live API.
  4. Create the config entry on success, or re-display the form with an
     inline error message on failure.

Error keys (defined in ``strings.json`` / ``translations/``):
  - ``cannot_connect`` – network-level failure reaching the token endpoint.
  - ``invalid_auth``   – the API rejected the client_id / client_secret.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode
import homeassistant.helpers.config_validation as cv

from .api import SRFWeatherAPI
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_MAX_REQUESTS, DEFAULT_MAX_REQUESTS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SRFWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the multi-step UI config flow for SRF Weather.

    Currently only one step (``user``) is needed, but the class can be
    extended with an ``async_step_reauth`` method in the future to handle
    credential re-entry after an auth failure without removing the entry.

    Class attributes:
        VERSION: Schema version stored in the config entry.  Increment when
                 the ``data`` dict structure changes and a migration is needed.
    """

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step shown to the user.

        On the first call ``user_input`` is ``None`` (HA just wants the form).
        On subsequent calls it contains the submitted values.

        Args:
            user_input: Dict of field values from the submitted form, or
                        ``None`` when the form is being rendered for the first
                        time.

        Returns:
            A ``ConfigFlowResult`` – either ``async_show_form`` (render or
            re-render the form) or ``async_create_entry`` (success).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]

            # Build a stable unique ID from the location so HA can detect and
            # abort duplicate config entries for the same coordinates.
            await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
            self._abort_if_unique_id_configured()

            # Re-use the HA-managed session; do NOT create a bare ClientSession
            # here as it would never be properly closed.
            session = async_get_clientsession(self.hass)
            api = SRFWeatherAPI(
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                session,
            )

            try:
                valid = await api.validate_credentials()
            except aiohttp.ClientError:
                # Network-level failure (DNS, timeout, TLS, …)
                errors["base"] = "cannot_connect"
            else:
                if not valid:
                    # Connected fine but credentials were rejected by the API.
                    errors["base"] = "invalid_auth"

            if not errors:
                # All good – persist the entry.  ``title`` is shown in the
                # integrations list; ``data`` is stored encrypted on disk.
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        # Pre-populate lat/lon from the HA home location so most users only
        # need to paste their API credentials and hit submit.
        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="SRF Weather"): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_LATITUDE, default=default_lat): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=default_lon): cv.longitude,
                vol.Optional(CONF_MAX_REQUESTS, default=DEFAULT_MAX_REQUESTS): NumberSelector(
                    NumberSelectorConfig(min=1, max=200, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="/Tag")
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,  # Empty dict = no errors shown; keys map to strings.json
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        entry: ConfigEntry = self._get_reconfigure_entry()

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            new_unique_id = f"{lat:.4f}_{lon:.4f}"

            # If coordinates changed, check for duplicates.
            if new_unique_id != entry.unique_id:
                await self.async_set_unique_id(new_unique_id)
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
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_unique_id,
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=entry.data.get(CONF_NAME, "SRF Weather")): str,
                vol.Required(CONF_CLIENT_ID, default=entry.data.get(CONF_CLIENT_ID, "")): str,
                vol.Required(CONF_CLIENT_SECRET, default=entry.data.get(CONF_CLIENT_SECRET, "")): str,
                vol.Required(CONF_LATITUDE, default=entry.data.get(CONF_LATITUDE)): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=entry.data.get(CONF_LONGITUDE)): cv.longitude,
                vol.Optional(CONF_MAX_REQUESTS, default=entry.data.get(CONF_MAX_REQUESTS, DEFAULT_MAX_REQUESTS)): NumberSelector(
                    NumberSelectorConfig(min=1, max=200, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="/Tag")
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )
