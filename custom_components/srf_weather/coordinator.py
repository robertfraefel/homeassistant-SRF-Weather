"""DataUpdateCoordinator for SRF Weather.

The coordinator is the single source of truth for forecast data within a
config entry.  It owns the polling schedule and ensures that all entities
(weather + sensors) share the same fetched payload without making redundant
API calls.

How it fits into HA's architecture
------------------------------------
1. ``__init__.py`` creates one coordinator per config entry.
2. The coordinator calls ``SRFWeatherAPI.get_forecast`` on every poll.
3. All ``CoordinatorEntity`` subclasses (``SRFWeatherEntity``,
   ``SRFWeatherSensor``) subscribe to the coordinator.  HA calls their
   ``_handle_coordinator_update`` callback automatically whenever fresh data
   arrives, which triggers a state write to the HA state machine.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SRFWeatherAPI, SRFWeatherAPIError, SRFWeatherAuthError, SRFWeatherRateLimitError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

# Back-off interval (in seconds) when the API signals quota exhaustion.
RATE_LIMIT_BACKOFF = 3600  # 1 hour

_LOGGER = logging.getLogger(__name__)


class SRFWeatherCoordinator(DataUpdateCoordinator[dict]):
    """Polls the SRF Meteo API and caches the latest forecast data.

    Inherits from ``DataUpdateCoordinator[dict]`` where the generic type
    parameter ``dict`` is the type of ``coordinator.data`` – the parsed JSON
    response from ``/forecastpoint/{geolocationId}``.

    Attributes:
        api:       The ``SRFWeatherAPI`` instance used for HTTP calls.
        latitude:  WGS-84 latitude of the forecast location.
        longitude: WGS-84 longitude of the forecast location.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: SRFWeatherAPI,
        latitude: float,
        longitude: float,
    ) -> None:
        """Initialise the coordinator.

        Args:
            hass:      The Home Assistant instance.
            api:       Configured ``SRFWeatherAPI`` ready to make requests.
            latitude:  Latitude of the location to fetch forecasts for.
            longitude: Longitude of the location to fetch forecasts for.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Poll every 30 minutes.  SRF Meteo updates its model output
            # roughly once per hour, so 30-minute polling gives timely data
            # while staying well within typical API rate limits.
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.latitude = latitude
        self.longitude = longitude

    async def _async_update_data(self) -> dict:
        """Fetch the latest forecast from the SRF API.

        This method is called automatically by ``DataUpdateCoordinator`` on
        every poll interval and also during the first-refresh triggered by
        ``__init__.py``.

        Returns:
            The raw ``ForecastPointWeek`` JSON payload as a Python dict.

        Raises:
            UpdateFailed: Wraps any ``SRFWeatherAuthError`` or
                          ``SRFWeatherAPIError`` so that HA can log the error
                          and mark the integration as unavailable without
                          crashing the event loop.
        """
        try:
            data = await self.api.get_forecast(self.latitude, self.longitude)
        except SRFWeatherRateLimitError as exc:
            # Back off to avoid burning through the daily quota with retries.
            self.update_interval = timedelta(seconds=RATE_LIMIT_BACKOFF)
            _LOGGER.warning(
                "SRF Weather API quota exceeded – backing off to %s s",
                RATE_LIMIT_BACKOFF,
            )
            raise UpdateFailed(f"SRF Weather API quota exceeded: {exc}") from exc
        except SRFWeatherAuthError as exc:
            raise UpdateFailed(f"SRF Weather authentication error: {exc}") from exc
        except SRFWeatherAPIError as exc:
            raise UpdateFailed(f"SRF Weather API error: {exc}") from exc

        # Restore normal polling interval after a successful fetch
        # (in case it was increased due to a previous rate-limit).
        if self.update_interval != timedelta(seconds=DEFAULT_SCAN_INTERVAL):
            self.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
            _LOGGER.info(
                "SRF Weather API recovered – polling interval restored to %s s",
                DEFAULT_SCAN_INTERVAL,
            )
        return data
