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

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SRFWeatherAPI, SRFWeatherAPIError, SRFWeatherAuthError, SRFWeatherRateLimitError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

# Back-off interval (in seconds) when the API signals quota exhaustion.
RATE_LIMIT_BACKOFF = 3600  # 1 hour

# Maximum age (in seconds) of cached data to still be considered usable
# on startup without making an API call.
CACHE_MAX_AGE = 7200  # 2 hours

_LOGGER = logging.getLogger(__name__)


def _compute_interval(max_requests: int) -> int:
    """Compute the polling interval in seconds from a daily request budget."""
    if max_requests <= 0:
        return DEFAULT_SCAN_INTERVAL
    interval = 86400 // max_requests
    # Clamp to at least 10 minutes
    return max(interval, 600)


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
        max_requests: int = 40,
        config_dir: str | None = None,
    ) -> None:
        """Initialise the coordinator.

        Args:
            hass:         The Home Assistant instance.
            api:          Configured ``SRFWeatherAPI`` ready to make requests.
            latitude:     Latitude of the location to fetch forecasts for.
            longitude:    Longitude of the location to fetch forecasts for.
            max_requests: Maximum daily API requests (determines poll interval).
            config_dir:   HA config directory for persistent cache files.
        """
        interval = _compute_interval(max_requests)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.latitude = latitude
        self.longitude = longitude
        self._default_interval = interval
        self._cache_file: str | None = None
        if config_dir:
            safe_id = f"{latitude:.4f}_{longitude:.4f}"
            self._cache_file = os.path.join(
                config_dir, f".srf_weather_cache_{safe_id}.json"
            )

    # ------------------------------------------------------------------
    # Persistent forecast cache
    # ------------------------------------------------------------------

    async def async_load_cached_data(self) -> bool:
        """Try to load forecast data from disk cache.

        Returns True if valid cached data was loaded, False otherwise.
        """
        if not self._cache_file:
            return False
        try:
            cache = await asyncio.to_thread(self._read_cache)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return False

        if cache is None:
            return False

        saved_at = datetime.fromisoformat(cache["_saved_at"])
        age = (datetime.now() - saved_at).total_seconds()
        if age > CACHE_MAX_AGE:
            _LOGGER.debug(
                "SRF Weather: cache too old (%.0f s), will fetch fresh data", age
            )
            return False

        # Remove our metadata key before using as coordinator data
        data = {k: v for k, v in cache.items() if k != "_saved_at"}
        self.async_set_updated_data(data)
        _LOGGER.info(
            "SRF Weather: loaded cached forecast (age %.0f min)", age / 60
        )
        return True

    def _read_cache(self) -> dict | None:
        """Read cached forecast from disk (blocking)."""
        if self._cache_file and os.path.exists(self._cache_file):
            with open(self._cache_file, "r") as fh:
                return json.load(fh)
        return None

    def _write_cache(self, data: dict) -> None:
        """Write forecast data to disk cache (blocking)."""
        if not self._cache_file:
            return
        cache = dict(data)
        cache["_saved_at"] = datetime.now().isoformat()
        with open(self._cache_file, "w") as fh:
            json.dump(cache, fh)

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

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
        if self.update_interval != timedelta(seconds=self._default_interval):
            self.update_interval = timedelta(seconds=self._default_interval)
            _LOGGER.info(
                "SRF Weather API recovered – polling interval restored to %s s",
                self._default_interval,
            )

        # Persist to disk so we can avoid an API call on next HA restart
        try:
            await asyncio.to_thread(self._write_cache, data)
        except OSError:
            pass  # non-critical

        return data

    def current_hour_index(self) -> int:
        """Return the index of the hourly slot closest to *now*.

        The SRF API returns hours starting from midnight, so index 0 is
        often in the past.  This finds the last slot whose ``date_time``
        is at or before the current time.
        """
        hours = (self.data or {}).get("hours", [])
        if not hours:
            return 0
        now = datetime.now(timezone.utc)
        best = 0
        for i, hour in enumerate(hours):
            dt_str = hour.get("date_time")
            if dt_str is None:
                continue
            if datetime.fromisoformat(dt_str) <= now:
                best = i
            else:
                break
        return best
