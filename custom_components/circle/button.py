"""Button entities for Meet Circle - late bedtime reward."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_LATE_BEDTIME_MINUTES, DOMAIN
from .coordinator import CircleCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Circle late bedtime reward buttons."""
    coordinator: CircleCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for pid, profile in coordinator.data["profiles"].items():
        # Only create a button if the profile has at least one bedtime configured
        weekday_id = profile.get("bedtime_weekday_id")
        weekend_id = profile.get("bedtime_weekend_id")
        if weekday_id is not None or weekend_id is not None:
            entities.append(
                CircleLateBedtimeButton(coordinator, pid, entry.entry_id)
            )

    async_add_entities(entities)


class CircleLateBedtimeButton(CoordinatorEntity[CircleCoordinator], ButtonEntity):
    """Button to send a late bedtime reward to a Circle profile."""

    _attr_has_entity_name = True
    _attr_translation_key = "late_bedtime"
    _attr_icon = "mdi:star-circle"

    def __init__(
        self,
        coordinator: CircleCoordinator,
        pid: int,
        entry_id: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._pid = pid
        self._attr_unique_id = f"{entry_id}_{pid}_late_bedtime"
        profile = coordinator.data["profiles"][pid]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{pid}")},
            name=profile["name"],
            manufacturer="Meet Circle",
        )

    async def async_press(self) -> None:
        """Send a late bedtime reward."""
        profile = self.coordinator.data["profiles"].get(self._pid, {})

        # Prefer weekday bedtime ID, fall back to weekend
        offtime_id = profile.get("bedtime_weekday_id") or profile.get(
            "bedtime_weekend_id"
        )

        if offtime_id is None:
            _LOGGER.warning(
                "No bedtime configured for profile %s, cannot send reward",
                self._pid,
            )
            return

        await self.coordinator.api.send_late_bedtime(
            pid=self._pid,
            offtime_id=offtime_id,
            minutes=DEFAULT_LATE_BEDTIME_MINUTES,
        )
        await self.coordinator.async_request_refresh()
