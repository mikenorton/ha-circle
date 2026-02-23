"""Sensor entities for Meet Circle - bedtime and profile info."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CircleCoordinator


def _bedtime_value(profile: dict[str, Any], key: str) -> str | None:
    """Extract a bedtime start time string or 'Disabled'."""
    bt = profile.get(key)
    if bt is None:
        return None
    if bt.get("state") == "disabled":
        return "Disabled"
    return bt.get("start")


@dataclass(frozen=True, kw_only=True)
class CircleSensorDescription(SensorEntityDescription):
    """Describes a Circle sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


SENSOR_DESCRIPTIONS: tuple[CircleSensorDescription, ...] = (
    CircleSensorDescription(
        key="bedtime_weekday",
        translation_key="bedtime_weekday",
        icon="mdi:bed-clock",
        value_fn=lambda p: _bedtime_value(p, "bedtime_weekday"),
    ),
    CircleSensorDescription(
        key="bedtime_weekend",
        translation_key="bedtime_weekend",
        icon="mdi:bed-clock",
        value_fn=lambda p: _bedtime_value(p, "bedtime_weekend"),
    ),
    CircleSensorDescription(
        key="profile_mode",
        translation_key="profile_mode",
        icon="mdi:shield-account",
        value_fn=lambda p: p.get("mode"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Circle sensor entities."""
    coordinator: CircleCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CircleProfileSensor(coordinator, pid, description, entry.entry_id)
        for pid in coordinator.data["profiles"]
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class CircleProfileSensor(CoordinatorEntity[CircleCoordinator], SensorEntity):
    """Sensor showing Circle profile information."""

    _attr_has_entity_name = True
    entity_description: CircleSensorDescription

    def __init__(
        self,
        coordinator: CircleCoordinator,
        pid: int,
        description: CircleSensorDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._pid = pid
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{pid}_{description.key}"
        profile = coordinator.data["profiles"][pid]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{pid}")},
            name=profile["name"],
            manufacturer="Meet Circle",
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        profile = self.coordinator.data["profiles"].get(self._pid, {})
        return self.entity_description.value_fn(profile)
