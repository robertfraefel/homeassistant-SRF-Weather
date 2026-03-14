"""Sensor entities for SRF Weather.

This module exposes weather data fields that are not part of the standard HA
``WeatherEntity`` interface as individual ``SensorEntity`` instances.  All
sensors share the coordinator and therefore update in sync.

Design pattern
--------------
Rather than writing one class per sensor, a single ``SRFWeatherSensor`` class
is driven by an ``SRFSensorEntityDescription`` dataclass.  Each description
specifies:

  - All standard ``SensorEntityDescription`` metadata (key, unit, device class,
    state class, icon, translation key).
  - A ``value_fn`` lambda that extracts the relevant field from the raw API
    data dict.
  - A ``source`` string (``"hourly"`` or ``"daily"``) that tells the sensor
    which array inside the coordinator payload to read from.

Adding a new sensor requires only a new entry in ``SENSOR_DESCRIPTIONS`` –
no new class is needed.

Sensor inventory
----------------
Source: ``hours[0]`` (current hour from the hourly forecast)
  - Felt temperature   (TTTFEEL_C, °C)
  - Dew point          (DEWPOINT_C, °C)
  - Sunshine duration  (SUN_MIN, minutes of sunshine in the current hour)
  - Solar irradiance   (IRRADIANCE_WM2, W/m²)
  - Fresh snow         (FRESHSNOW_MM, mm of new snow in the current hour)
  - Precipitation prob (PROBPCP_PERCENT, %)

Source: ``days[0]`` (today from the daily forecast)
  - UV index           (UVI, dimensionless, 0–20)
  - Sunshine hours     (SUN_H, hours of sunshine today)

API field reference (hourly)
-----------------------------
``TTTFEEL_C``    Felt/apparent temperature accounting for wind and humidity
``DEWPOINT_C``   Temperature at which air becomes saturated (dew point)
``SUN_MIN``      Minutes of sunshine in the hour preceding the timestamp
``IRRADIANCE_WM2`` Global solar irradiance (direct + diffuse) in W/m²
``FRESHSNOW_MM`` Fresh snow depth in the hour preceding the timestamp

API field reference (daily)
----------------------------
``UVI``   UV index at solar noon (0 = minimal, 11+ = extreme)
``SUN_H`` Total expected sunshine hours for the day (0–25)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SYMBOL_TO_CONDITION
from .coordinator import SRFWeatherCoordinator


@dataclass(frozen=True, kw_only=True)
class SRFSensorEntityDescription(SensorEntityDescription):
    """Extends ``SensorEntityDescription`` with SRF-specific metadata.

    Attributes:
        value_fn: A callable that accepts one row dict from the coordinator
                  data (either a ``days`` or ``hours`` element) and returns
                  the sensor's native value.  Typically a one-liner lambda
                  such as ``lambda d: d.get("TTTFEEL_C")``.
        source:   Which array inside the coordinator payload to read from.
                  ``"hourly"`` → ``coordinator.data["hours"][0]``
                  ``"daily"``  → ``coordinator.data["days"][0]``
    """

    value_fn: Callable[[dict], Any]
    # Determines whether to read from the hourly or daily forecast array.
    source: str = "hourly"
    # Index into the source array (0 = current, 1 = next, etc.)
    index: int = 0


# ---------------------------------------------------------------------------
# Sensor descriptors – one entry per exposed sensor.
# All translation_key values must be defined in strings.json / translations/.
# ---------------------------------------------------------------------------

SENSOR_DESCRIPTIONS: tuple[SRFSensorEntityDescription, ...] = (
    # =====================================================================
    # Hourly sensors (from hours[0])
    # =====================================================================
    SRFSensorEntityDescription(
        key="felt_temperature",
        translation_key="felt_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        value_fn=lambda d: d.get("TTTFEEL_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda d: d.get("TTT_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="temperature_range_low",
        translation_key="temperature_range_low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-chevron-down",
        value_fn=lambda d: d.get("TTL_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="temperature_range_high",
        translation_key="temperature_range_high",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-chevron-up",
        value_fn=lambda d: d.get("TTH_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-thermometer",
        value_fn=lambda d: d.get("DEWPOINT_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda d: d.get("RELHUM_PERCENT"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="pressure",
        translation_key="pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda d: d.get("PRESSURE_HPA"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="precipitation",
        translation_key="precipitation",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda d: d.get("RRR_MM"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="precipitation_probability",
        translation_key="precipitation_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda d: d.get("PROBPCP_PERCENT"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="wind_speed",
        translation_key="wind_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=lambda d: d.get("FF_KMH"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="wind_gust_speed",
        translation_key="wind_gust_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
        value_fn=lambda d: d.get("FX_KMH"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="wind_direction",
        translation_key="wind_direction",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-outline",
        value_fn=lambda d: d.get("DD_DEG") if d.get("DD_DEG", -1) >= 0 else None,
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="sunshine_duration",
        translation_key="sunshine_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda d: d.get("SUN_MIN"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="irradiance",
        translation_key="irradiance",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: d.get("IRRADIANCE_WM2"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="fresh_snow",
        translation_key="fresh_snow",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake",
        # API field is FRESHSNOW_CM (centimeters)
        value_fn=lambda d: d.get("FRESHSNOW_CM"),
        source="hourly",
    ),
    # =====================================================================
    # Daily sensors (from days[0])
    # =====================================================================
    SRFSensorEntityDescription(
        key="temperature_max",
        translation_key="temperature_max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-high",
        value_fn=lambda d: d.get("TX_C"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="temperature_min",
        translation_key="temperature_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-low",
        value_fn=lambda d: d.get("TN_C"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="precipitation_daily",
        translation_key="precipitation_daily",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda d: d.get("RRR_MM"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="precipitation_probability_daily",
        translation_key="precipitation_probability_daily",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda d: d.get("PROBPCP_PERCENT"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="wind_speed_daily",
        translation_key="wind_speed_daily",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=lambda d: d.get("FF_KMH"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="wind_gust_speed_daily",
        translation_key="wind_gust_speed_daily",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
        value_fn=lambda d: d.get("FX_KMH"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="wind_direction_daily",
        translation_key="wind_direction_daily",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-outline",
        value_fn=lambda d: d.get("DD_DEG") if d.get("DD_DEG", -1) >= 0 else None,
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="uv_index",
        translation_key="uv_index",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-wireless",
        value_fn=lambda d: d.get("UVI"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="sunshine_hours",
        translation_key="sunshine_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny",
        value_fn=lambda d: d.get("SUN_H"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="sunrise",
        translation_key="sunrise",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-up",
        value_fn=lambda d: d.get("SUNRISE"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="sunset",
        translation_key="sunset",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-down",
        value_fn=lambda d: d.get("SUNSET"),
        source="daily",
    ),
)


def _build_forecast_descriptions() -> tuple[SRFSensorEntityDescription, ...]:
    """Generate forecast sensor descriptions for days 1–6."""
    descriptions: list[SRFSensorEntityDescription] = []
    for day in range(1, 7):
        label = f"d{day}"
        descriptions.extend([
            SRFSensorEntityDescription(
                key=f"forecast_{label}_condition",
                translation_key=f"forecast_{label}_condition",
                native_unit_of_measurement=None,
                icon="mdi:weather-partly-cloudy",
                value_fn=lambda d: SYMBOL_TO_CONDITION.get(d.get("symbol_code")),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_temp_max",
                translation_key=f"forecast_{label}_temp_max",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:thermometer-high",
                value_fn=lambda d: d.get("TX_C"),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_temp_min",
                translation_key=f"forecast_{label}_temp_min",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:thermometer-low",
                value_fn=lambda d: d.get("TN_C"),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_precipitation",
                translation_key=f"forecast_{label}_precipitation",
                native_unit_of_measurement=UnitOfLength.MILLIMETERS,
                device_class=SensorDeviceClass.PRECIPITATION,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:water",
                value_fn=lambda d: d.get("RRR_MM"),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_precip_prob",
                translation_key=f"forecast_{label}_precip_prob",
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:weather-rainy",
                value_fn=lambda d: d.get("PROBPCP_PERCENT"),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_wind_speed",
                translation_key=f"forecast_{label}_wind_speed",
                native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
                device_class=SensorDeviceClass.WIND_SPEED,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:weather-windy",
                value_fn=lambda d: d.get("FF_KMH"),
                source="daily",
                index=day,
            ),
            SRFSensorEntityDescription(
                key=f"forecast_{label}_sunshine_hours",
                translation_key=f"forecast_{label}_sunshine_hours",
                native_unit_of_measurement=UnitOfTime.HOURS,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:weather-sunny",
                value_fn=lambda d: d.get("SUN_H"),
                source="daily",
                index=day,
            ),
        ])
    return tuple(descriptions)


FORECAST_DESCRIPTIONS = _build_forecast_descriptions()

ALL_SENSOR_DESCRIPTIONS = SENSOR_DESCRIPTIONS + FORECAST_DESCRIPTIONS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one ``SRFWeatherSensor`` for every entry in ``SENSOR_DESCRIPTIONS``.

    Called by HA after ``__init__.async_setup_entry`` forwards setup to the
    ``sensor`` platform.

    Args:
        hass:              The Home Assistant instance.
        entry:             The config entry being set up.
        async_add_entities: Callback to register new entities with HA.
    """
    coordinator: SRFWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SRFWeatherSensor(coordinator, entry, description)
        for description in ALL_SENSOR_DESCRIPTIONS
    )


class SRFWeatherSensor(CoordinatorEntity[SRFWeatherCoordinator], SensorEntity):
    """A sensor entity that exposes a single field from the SRF forecast data.

    One instance of this class is created per ``SRFSensorEntityDescription``.
    All instances share the same ``coordinator`` and therefore refresh together
    when the coordinator polls the API.

    The ``native_value`` property delegates to the description's ``value_fn``
    so the class itself contains no field-specific logic.
    """

    entity_description: SRFSensorEntityDescription
    _attr_has_entity_name = True
    _attr_attribution = "Data provided by SRF Meteo / SRG SSR"

    def __init__(
        self,
        coordinator: SRFWeatherCoordinator,
        entry: ConfigEntry,
        description: SRFSensorEntityDescription,
    ) -> None:
        """Initialise the sensor.

        Args:
            coordinator:  The shared data coordinator for this config entry.
            entry:        The config entry (provides name and ID).
            description:  The descriptor that defines this sensor's metadata
                          and value extraction logic.
        """
        super().__init__(coordinator)
        self.entity_description = description

        # Unique ID = entry_id + sensor key, guaranteeing uniqueness across
        # multiple configured locations and within a single location.
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Attach to the same logical device as the weather entity so that all
        # sensors are grouped together in the HA device page.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="SRG SSR",
            model="SRF Meteo",
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor value extracted from the coordinator data.

        Reads the first element of either the ``hours`` or ``days`` array
        (determined by ``entity_description.source``) and passes it to the
        description's ``value_fn`` to extract the relevant field.

        Returns ``None`` when the coordinator data is empty or the field is
        absent, which causes HA to show the sensor state as "unavailable".
        """
        data = self.coordinator.data
        # Select the correct forecast array based on the descriptor's source.
        if self.entity_description.source == "daily":
            rows = data.get("days", [])
        else:
            rows = data.get("hours", [])

        idx = self.entity_description.index
        if idx >= len(rows):
            return None

        return self.entity_description.value_fn(rows[idx])
