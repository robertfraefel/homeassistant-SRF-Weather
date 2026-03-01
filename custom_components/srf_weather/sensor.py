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
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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


# ---------------------------------------------------------------------------
# Sensor descriptors – one entry per exposed sensor.
# All translation_key values must be defined in strings.json / translations/.
# ---------------------------------------------------------------------------

SENSOR_DESCRIPTIONS: tuple[SRFSensorEntityDescription, ...] = (
    # -- Hourly sensors ------------------------------------------------------
    SRFSensorEntityDescription(
        key="felt_temperature",
        translation_key="felt_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
        # TTTFEEL_C = apparent/felt temperature (considers wind chill & humidity)
        value_fn=lambda d: d.get("TTTFEEL_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-thermometer",
        # DEWPOINT_C = temperature at which air reaches 100% relative humidity
        value_fn=lambda d: d.get("DEWPOINT_C"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="sunshine_duration",
        translation_key="sunshine_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        # SUN_MIN = minutes of sunshine recorded in the previous hour
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
        # IRRADIANCE_WM2 = global horizontal irradiance (direct + diffuse)
        value_fn=lambda d: d.get("IRRADIANCE_WM2"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="fresh_snow",
        translation_key="fresh_snow",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake",
        # FRESHSNOW_MM = new snow depth accumulated in the previous hour
        value_fn=lambda d: d.get("FRESHSNOW_MM"),
        source="hourly",
    ),
    SRFSensorEntityDescription(
        key="precipitation_probability",
        translation_key="precipitation_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        # PROBPCP_PERCENT = model probability that precipitation will occur
        value_fn=lambda d: d.get("PROBPCP_PERCENT"),
        source="hourly",
    ),
    # -- Daily sensors -------------------------------------------------------
    SRFSensorEntityDescription(
        key="uv_index",
        translation_key="uv_index",
        native_unit_of_measurement=None,  # Dimensionless index
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-wireless",
        # UVI = UV index at solar noon for today (scale 0–20)
        value_fn=lambda d: d.get("UVI"),
        source="daily",
    ),
    SRFSensorEntityDescription(
        key="sunshine_hours",
        translation_key="sunshine_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny",
        # SUN_H = total expected sunshine hours for the day (0–25 cap in API)
        value_fn=lambda d: d.get("SUN_H"),
        source="daily",
    ),
)


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
        for description in SENSOR_DESCRIPTIONS
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

        if not rows:
            return None

        # Apply the field extractor to the first (current) row.
        return self.entity_description.value_fn(rows[0])
