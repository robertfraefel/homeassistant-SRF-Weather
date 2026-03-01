"""DataUpdateCoordinator for SRF Weather."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SRFWeatherAPI, SRFWeatherAPIError, SRFWeatherAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SRFWeatherCoordinator(DataUpdateCoordinator[dict]):
    """Fetches and caches SRF Weather forecast data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SRFWeatherAPI,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.latitude = latitude
        self.longitude = longitude

    async def _async_update_data(self) -> dict:
        """Fetch latest forecast data from the SRF API."""
        try:
            return await self.api.get_forecast(self.latitude, self.longitude)
        except SRFWeatherAuthError as exc:
            raise UpdateFailed(f"SRF Weather authentication error: {exc}") from exc
        except SRFWeatherAPIError as exc:
            raise UpdateFailed(f"SRF Weather API error: {exc}") from exc
