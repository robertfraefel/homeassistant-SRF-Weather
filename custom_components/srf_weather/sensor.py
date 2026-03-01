"""Sensor entities for SRF Weather – exposes extra fields not in the weather entity."""

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
    """Extends SensorEntityDescription with a value extractor."""

    value_fn: Callable[[dict], Any]
    # "hourly" → read from coordinator.data["hours"][0]
    # "daily"  → read from coordinator.data["days"][0]
    source: str = "hourly"


SENSOR_DESCRIPTIONS: tuple[SRFSensorEntityDescription, ...] = (
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
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake",
        value_fn=lambda d: d.get("FRESHSNOW_MM"),
        source="hourly",
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
        key="precipitation_probability",
        translation_key="precipitation_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda d: d.get("PROBPCP_PERCENT"),
        source="hourly",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SRF Weather sensors from a config entry."""
    coordinator: SRFWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SRFWeatherSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class SRFWeatherSensor(CoordinatorEntity[SRFWeatherCoordinator], SensorEntity):
    """A sensor that exposes a single field from the SRF Weather API."""

    entity_description: SRFSensorEntityDescription
    _attr_has_entity_name = True
    _attr_attribution = "Data provided by SRF Meteo / SRG SSR"

    def __init__(
        self,
        coordinator: SRFWeatherCoordinator,
        entry: ConfigEntry,
        description: SRFSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="SRG SSR",
            model="SRF Meteo",
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if self.entity_description.source == "daily":
            rows = data.get("days", [])
        else:
            rows = data.get("hours", [])
        if not rows:
            return None
        return self.entity_description.value_fn(rows[0])
