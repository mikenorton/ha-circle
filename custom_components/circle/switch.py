"""Switch entities for Meet Circle - internet pause/unpause."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CircleCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Circle internet access switches."""
    coordinator: CircleCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CircleInternetSwitch(coordinator, pid, entry.entry_id)
        for pid in coordinator.data["profiles"]
    ]

    async_add_entities(entities)


class CircleInternetSwitch(CoordinatorEntity[CircleCoordinator], SwitchEntity):
    """Switch to enable/disable internet access for a Circle profile."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_translation_key = "internet_access"

    def __init__(
        self,
        coordinator: CircleCoordinator,
        pid: int,
        entry_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._pid = pid
        self._attr_unique_id = f"{entry_id}_{pid}_internet_access"
        profile = coordinator.data["profiles"][pid]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{pid}")},
            name=profile["name"],
            manufacturer="Meet Circle",
        )

    @property
    def is_on(self) -> bool:
        """Return True if internet is enabled (not paused)."""
        profile = self.coordinator.data["profiles"].get(self._pid, {})
        return not profile.get("is_paused", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable internet access (set mode to Filter)."""
        await self.coordinator.api.set_mode(self._pid, "Filter")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable internet access (set mode to Pause)."""
        await self.coordinator.api.set_mode(self._pid, "Pause")
        await self.coordinator.async_request_refresh()
