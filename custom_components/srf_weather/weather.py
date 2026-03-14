"""Weather entity for SRF Weather.

Provides a single ``WeatherEntity`` per config entry that surfaces:

Current conditions (from ``hours[0]``)
  - Condition string (mapped from ``symbol_code`` via ``SYMBOL_TO_CONDITION``)
  - Temperature (°C)
  - Humidity (%)
  - Wind speed (km/h)
  - Wind gust speed (km/h)
  - Wind bearing (°, -1 in the API means "turning winds" → exposed as None)
  - Atmospheric pressure (hPa)
  - Dew point (°C)
  - UV index (taken from today's ``days[0]`` entry)

Forecasts
  - Daily forecast (``async_forecast_daily``) – up to 7 days from ``days``
  - Hourly forecast (``async_forecast_hourly``) – up to 24 h from ``hours``

HA Weather entity feature flags
  ``FORECAST_DAILY``  – enables the daily forecast tab in the UI.
  ``FORECAST_HOURLY`` – enables the hourly forecast tab in the UI.

All native units are declared as class attributes so HA can perform unit
conversion automatically when the user's unit system differs (e.g. °F).

API field reference
-------------------
Days:
  ``date_time``      ISO-8601 datetime string for the start of the day
  ``symbol_code``    Daytime weather symbol (1–40)
  ``TX_C``           Maximum temperature for the day (°C)
  ``TN_C``           Minimum temperature for the day (°C)
  ``RRR_MM``         Total precipitation (mm)
  ``PROBPCP_PERCENT``Probability of precipitation (%)
  ``FF_KMH``         Average wind speed (km/h)
  ``FX_KMH``         Maximum wind gust speed (km/h)
  ``DD_DEG``         Wind direction (°), -1 = turning winds
  ``UVI``            UV index (0–20)

Hours:
  ``date_time``      ISO-8601 datetime string for the start of the hour
  ``symbol_code``    Weather symbol for this hour
  ``TTT_C``          Temperature (°C)
  ``RELHUM_PERCENT`` Relative humidity (%)
  ``FF_KMH``         Average wind speed (km/h)
  ``FX_KMH``         Wind gust speed (km/h)
  ``DD_DEG``         Wind direction (°), -1 = turning winds
  ``PRESSURE_HPA``   Atmospheric pressure (hPa)
  ``DEWPOINT_C``     Dew point (°C)
  ``RRR_MM``         Precipitation (mm)
  ``PROBPCP_PERCENT``Probability of precipitation (%)
"""

from __future__ import annotations

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SYMBOL_TO_CONDITION
from .coordinator import SRFWeatherCoordinator

ICONS_URL = f"/{DOMAIN}/icons"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the weather entity for a config entry.

    Called by HA after ``__init__.async_setup_entry`` forwards setup to the
    ``weather`` platform.  Retrieves the already-initialised coordinator from
    ``hass.data`` and registers a single ``SRFWeatherEntity``.

    Args:
        hass:              The Home Assistant instance.
        entry:             The config entry being set up.
        async_add_entities: Callback to register new entities with HA.
    """
    coordinator: SRFWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SRFWeatherEntity(coordinator, entry)])


class SRFWeatherEntity(CoordinatorEntity[SRFWeatherCoordinator], WeatherEntity):
    """A HA weather entity backed by SRF Meteo forecast data.

    Inherits from both ``CoordinatorEntity`` (to receive push updates from the
    coordinator) and ``WeatherEntity`` (the HA base class for weather).

    Class-level ``_attr_*`` attributes are the preferred way to declare static
    metadata in modern HA integrations – they avoid redundant property boiler-
    plate and are picked up automatically by the base class.
    """

    # Shown in the HA entity registry as the data source.
    _attr_attribution = "Data provided by SRF Meteo / SRG SSR"

    # ``has_entity_name = True`` combined with ``name = None`` tells HA to use
    # the device name (the user-supplied "Name" field) as the entity's display
    # name, following the modern HA entity naming convention.
    _attr_has_entity_name = True
    _attr_name = None

    # Advertise which forecast types this entity can serve.
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    # Native measurement units – HA converts to the user's preferred system.
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS

    def __init__(
        self,
        coordinator: SRFWeatherCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the weather entity.

        Args:
            coordinator: The shared data coordinator for this config entry.
            entry:       The config entry (provides name, unique id, etc.).
        """
        super().__init__(coordinator)

        # Use the config entry ID as the entity unique ID.  This is stable
        # across restarts and guaranteed unique within HA.
        self._attr_unique_id = entry.entry_id

        # Group this entity (and all sensor entities) under one logical device
        # in the HA device registry.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="SRG SSR",
            model="SRF Meteo",
            entry_type=None,
        )

    # ------------------------------------------------------------------
    # Current conditions (taken from the first available hourly slot)
    # ------------------------------------------------------------------

    @property
    def _current_hour(self) -> dict:
        """Return the first hourly forecast slot as a convenience accessor.

        The first element of ``hours`` represents the current (or most recent)
        hour.  An empty dict is returned as a safe fallback so that all
        property callers can use ``.get()`` without raising ``IndexError``.
        """
        hours = self.coordinator.data.get("hours", [])
        return hours[0] if hours else {}

    @property
    def condition(self) -> str | None:
        """Current weather condition string, mapped from ``symbol_code``."""
        symbol = self._current_hour.get("symbol_code")
        if symbol is None:
            return None
        return SYMBOL_TO_CONDITION.get(symbol)

    @property
    def entity_picture(self) -> str | None:
        """Return path to the SRF weather icon for the current symbol code."""
        symbol = self._current_hour.get("symbol_code")
        if symbol is None:
            return None
        if symbol < 0:
            return f"{ICONS_URL}/night/{symbol}.svg"
        return f"{ICONS_URL}/day/{symbol}.svg"

    @property
    def native_temperature(self) -> float | None:
        """Current temperature in °C (``TTT_C`` from the hourly data)."""
        return self._current_hour.get("TTT_C")

    @property
    def humidity(self) -> float | None:
        """Current relative humidity in % (``RELHUM_PERCENT``)."""
        return self._current_hour.get("RELHUM_PERCENT")

    @property
    def native_wind_speed(self) -> float | None:
        """Current average wind speed in km/h (``FF_KMH``)."""
        return self._current_hour.get("FF_KMH")

    @property
    def wind_bearing(self) -> float | None:
        """Current wind direction in degrees (``DD_DEG``).

        The SRF API uses ``-1`` to indicate turning/variable winds, which
        cannot be represented as a bearing.  In that case ``None`` is returned
        so HA omits the wind direction arrow rather than showing a bogus value.
        """
        dd = self._current_hour.get("DD_DEG", -1)
        return float(dd) if dd is not None and dd >= 0 else None

    @property
    def native_pressure(self) -> float | None:
        """Current atmospheric pressure in hPa (``PRESSURE_HPA``)."""
        return self._current_hour.get("PRESSURE_HPA")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Current wind gust speed in km/h (``FX_KMH``)."""
        return self._current_hour.get("FX_KMH")

    @property
    def native_dew_point(self) -> float | None:
        """Current dew point in °C (``DEWPOINT_C``)."""
        return self._current_hour.get("DEWPOINT_C")

    @property
    def uv_index(self) -> float | None:
        """UV index for today (``UVI`` from the daily data, scale 0–20).

        UV index is only available per day (not per hour), so the value is
        taken from the first element of ``days`` which represents today.
        """
        days = self.coordinator.data.get("days", [])
        return days[0].get("UVI") if days else None

    # ------------------------------------------------------------------
    # Forecasts
    # ------------------------------------------------------------------

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Build the daily forecast list from the ``days`` API data.

        Each ``DayForecastInterval`` from the API is converted to a HA
        ``Forecast`` TypedDict.  The daytime symbol code (``symbol_code``) is
        used for the condition; night codes (``symbol24_code``) are ignored
        here because HA's forecast UI is daytime-centric.

        Returns:
            List of ``Forecast`` dicts (one per day), or ``None`` if no data
            is available (which will mark the forecast as unavailable in HA).
        """
        days = self.coordinator.data.get("days", [])
        forecasts: list[Forecast] = []
        for day in days:
            dd = day.get("DD_DEG", -1)
            forecasts.append(
                Forecast(
                    datetime=day["date_time"],
                    condition=SYMBOL_TO_CONDITION.get(day.get("symbol_code")),
                    native_temperature=day.get("TX_C"),       # Daily maximum
                    native_templow=day.get("TN_C"),            # Daily minimum
                    native_precipitation=day.get("RRR_MM"),
                    precipitation_probability=day.get("PROBPCP_PERCENT"),
                    native_wind_speed=day.get("FF_KMH"),
                    native_wind_gust_speed=day.get("FX_KMH"),
                    # -1 means turning winds → omit bearing
                    wind_bearing=float(dd) if dd is not None and dd >= 0 else None,
                    uv_index=day.get("UVI"),
                )
            )
        # Return None (not empty list) so HA marks forecast as unavailable
        # rather than showing an empty card when there is no data.
        return forecasts or None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Build the hourly forecast list from the ``hours`` API data.

        Each ``OneHourForecastInterval`` from the API is converted to a HA
        ``Forecast`` TypedDict.  Additional fields (humidity, dew point) that
        are not present in daily forecasts are included here.

        Returns:
            List of ``Forecast`` dicts (one per hour), or ``None`` if no data.
        """
        hours = self.coordinator.data.get("hours", [])
        forecasts: list[Forecast] = []
        for hour in hours:
            dd = hour.get("DD_DEG", -1)
            forecasts.append(
                Forecast(
                    datetime=hour["date_time"],
                    condition=SYMBOL_TO_CONDITION.get(hour.get("symbol_code")),
                    native_temperature=hour.get("TTT_C"),
                    native_precipitation=hour.get("RRR_MM"),
                    precipitation_probability=hour.get("PROBPCP_PERCENT"),
                    native_wind_speed=hour.get("FF_KMH"),
                    native_wind_gust_speed=hour.get("FX_KMH"),
                    wind_bearing=float(dd) if dd is not None and dd >= 0 else None,
                    humidity=hour.get("RELHUM_PERCENT"),
                    native_dew_point=hour.get("DEWPOINT_C"),
                )
            )
        return forecasts or None
