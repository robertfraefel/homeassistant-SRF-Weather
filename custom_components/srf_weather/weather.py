"""Weather entity for SRF Weather."""

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SRF Weather entity from a config entry."""
    coordinator: SRFWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SRFWeatherEntity(coordinator, entry)])


class SRFWeatherEntity(CoordinatorEntity[SRFWeatherCoordinator], WeatherEntity):
    """Representation of SRF Weather data as a HA weather entity."""

    _attr_attribution = "Data provided by SRF Meteo / SRG SSR"
    _attr_has_entity_name = True
    _attr_name = None  # Use device name as entity name

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS

    def __init__(
        self,
        coordinator: SRFWeatherCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
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
        hours = self.coordinator.data.get("hours", [])
        return hours[0] if hours else {}

    @property
    def condition(self) -> str | None:
        symbol = self._current_hour.get("symbol_code")
        if symbol is None:
            return None
        return SYMBOL_TO_CONDITION.get(symbol)

    @property
    def native_temperature(self) -> float | None:
        return self._current_hour.get("TTT_C")

    @property
    def humidity(self) -> float | None:
        return self._current_hour.get("RELHUM_PERCENT")

    @property
    def native_wind_speed(self) -> float | None:
        return self._current_hour.get("FF_KMH")

    @property
    def wind_bearing(self) -> float | None:
        dd = self._current_hour.get("DD_DEG", -1)
        return float(dd) if dd is not None and dd >= 0 else None

    @property
    def native_pressure(self) -> float | None:
        return self._current_hour.get("PRESSURE_HPA")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._current_hour.get("FX_KMH")

    @property
    def native_dew_point(self) -> float | None:
        return self._current_hour.get("DEWPOINT_C")

    @property
    def uv_index(self) -> float | None:
        days = self.coordinator.data.get("days", [])
        return days[0].get("UVI") if days else None

    # ------------------------------------------------------------------
    # Forecasts
    # ------------------------------------------------------------------

    async def async_forecast_daily(self) -> list[Forecast] | None:
        days = self.coordinator.data.get("days", [])
        forecasts: list[Forecast] = []
        for day in days:
            dd = day.get("DD_DEG", -1)
            forecasts.append(
                Forecast(
                    datetime=day["date_time"],
                    condition=SYMBOL_TO_CONDITION.get(day.get("symbol_code")),
                    native_temperature=day.get("TX_C"),
                    native_templow=day.get("TN_C"),
                    native_precipitation=day.get("RRR_MM"),
                    precipitation_probability=day.get("PROBPCP_PERCENT"),
                    native_wind_speed=day.get("FF_KMH"),
                    native_wind_gust_speed=day.get("FX_KMH"),
                    wind_bearing=float(dd) if dd is not None and dd >= 0 else None,
                    uv_index=day.get("UVI"),
                )
            )
        return forecasts or None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
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
