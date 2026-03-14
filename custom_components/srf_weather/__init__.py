"""SRF Weather – Home Assistant custom integration.

This module is the integration entry point.  Home Assistant calls
``async_setup_entry`` once for every config entry that was created via the
UI (see ``config_flow.py``).  It wires together the three main objects:

1. ``SRFWeatherAPI``        – the low-level HTTP client (OAuth2 + REST)
2. ``SRFWeatherCoordinator``– polls the API on a schedule and caches data
3. Platform entities        – ``weather`` and ``sensor`` entities that read
                              from the coordinator

The coordinator is stored in ``hass.data[DOMAIN][entry.entry_id]`` so that
both platform modules can retrieve it in their own ``async_setup_entry``
functions without needing a direct reference.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SRFWeatherAPI
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN
from .coordinator import SRFWeatherCoordinator

# Platforms that this integration provides entities for.
# HA will call ``async_setup_entry`` in each platform module automatically.
PLATFORMS: list[Platform] = [Platform.WEATHER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SRF Weather from a config entry.

    Called by Home Assistant after the user completes the config flow or on
    restart when an existing entry is loaded.  Performs the initial data fetch
    (``async_config_entry_first_refresh``) so that entities are available with
    real data from the very first render.

    Args:
        hass:  The Home Assistant instance.
        entry: The config entry containing credentials and location data.

    Returns:
        ``True`` on success.  Raising ``ConfigEntryNotReady`` inside the
        coordinator's first refresh will signal HA to retry later.
    """
    # Re-use the HA-managed aiohttp session (handles SSL, timeouts, etc.)
    session = async_get_clientsession(hass)

    api = SRFWeatherAPI(
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        session,
    )
    api.set_storage_dir(hass.config.config_dir)

    coordinator = SRFWeatherCoordinator(
        hass,
        api,
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
    )

    # Block until the first successful fetch.  If this raises, HA marks the
    # entry as "not ready" and retries with exponential back-off.
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator so platform modules can retrieve it by entry_id.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Delegate entity creation to weather.py and sensor.py.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and clean up associated resources.

    Called by HA when the user removes the integration or during shutdown.
    Unloading the platforms removes all entities that were created by this
    entry.

    Args:
        hass:  The Home Assistant instance.
        entry: The config entry being removed.

    Returns:
        ``True`` if all platforms unloaded successfully, ``False`` otherwise.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Remove the coordinator from the shared data store.
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
