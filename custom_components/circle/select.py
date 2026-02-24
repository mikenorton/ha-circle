"""Select entities for Meet Circle - late bedtime reward time picker."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CircleCoordinator

_LOGGER = logging.getLogger(__name__)

LATE_BEDTIME_STEP = 15  # minutes between each option
LATE_BEDTIME_MAX = 120  # maximum extension in minutes


def _parse_bedtime_start(start_str: str) -> time | None:
    """Parse a bedtime start time string into a time object."""
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
        try:
            return datetime.strptime(start_str.strip(), fmt).time()
        except ValueError:
            continue
    # Try as minutes from midnight
    try:
        total = int(start_str)
        return time(total // 60, total % 60)
    except (ValueError, TypeError):
        return None


def _format_time(t: time) -> str:
    """Format a time as '8:15 PM' style string."""
    hour = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {ampm}"


def _get_active_bedtime(
    profile: dict[str, Any],
) -> tuple[dict[str, Any] | None, int | None]:
    """Get the active bedtime dict and offtime ID for today's day type."""
    day = datetime.now().weekday()
    # Friday (4) and Saturday (5) nights use weekend bedtime
    if day in (4, 5):
        bt = profile.get("bedtime_weekend") or profile.get("bedtime_weekday")
        bt_id = profile.get("bedtime_weekend_id") or profile.get(
            "bedtime_weekday_id"
        )
    else:
        bt = profile.get("bedtime_weekday") or profile.get("bedtime_weekend")
        bt_id = profile.get("bedtime_weekday_id") or profile.get(
            "bedtime_weekend_id"
        )
    return bt, bt_id


def _generate_options(bedtime_start: time) -> list[str]:
    """Generate time options in 15-min increments after bedtime."""
    base = datetime.combine(datetime.today(), bedtime_start)
    return [
        _format_time((base + timedelta(minutes=offset)).time())
        for offset in range(LATE_BEDTIME_STEP, LATE_BEDTIME_MAX + 1, LATE_BEDTIME_STEP)
    ]


def _minutes_offset(bedtime_start: time, selected: str) -> int | None:
    """Calculate minutes between bedtime and a selected time string."""
    selected_time = _parse_bedtime_start(selected)
    if selected_time is None:
        return None
    base = datetime.combine(datetime.today(), bedtime_start)
    sel = datetime.combine(datetime.today(), selected_time)
    if sel <= base:
        sel += timedelta(days=1)  # handle midnight crossing
    return int((sel - base).total_seconds() // 60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Circle late bedtime reward select entities."""
    coordinator: CircleCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Remove orphaned button entities from before the select migration
    ent_reg = er.async_get(hass)
    for ent_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if (
            ent_entry.domain == "button"
            and ent_entry.unique_id.endswith("_late_bedtime")
        ):
            _LOGGER.debug("Removing orphaned button entity %s", ent_entry.entity_id)
            ent_reg.async_remove(ent_entry.entity_id)

    entities = []
    for pid, profile in coordinator.data["profiles"].items():
        if (
            profile.get("bedtime_weekday_id") is not None
            or profile.get("bedtime_weekend_id") is not None
        ):
            entities.append(
                CircleLateBedtimeSelect(coordinator, pid, entry.entry_id)
            )

    async_add_entities(entities)


class CircleLateBedtimeSelect(CoordinatorEntity[CircleCoordinator], SelectEntity):
    """Select entity to pick a late bedtime reward time for a Circle profile."""

    _attr_has_entity_name = True
    _attr_translation_key = "late_bedtime"
    _attr_icon = "mdi:star-circle"
    _attr_current_option = None

    def __init__(
        self,
        coordinator: CircleCoordinator,
        pid: int,
        entry_id: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._pid = pid
        self._attr_unique_id = f"{entry_id}_{pid}_late_bedtime"
        profile = coordinator.data["profiles"][pid]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{pid}")},
            name=profile["name"],
            manufacturer="Meet Circle",
        )

    def _get_bedtime_info(self) -> tuple[time | None, int | None]:
        """Get the parsed bedtime start time and offtime ID for today."""
        profile = self.coordinator.data["profiles"].get(self._pid, {})
        bt, bt_id = _get_active_bedtime(profile)
        if bt is None or bt.get("state") == "disabled":
            _LOGGER.debug(
                "Profile %s: bedtime is None or disabled (bt=%s)", self._pid, bt
            )
            return None, bt_id
        start_val = bt.get("start")
        if start_val is None:
            _LOGGER.debug("Profile %s: bedtime has no 'start' field", self._pid)
            return None, bt_id
        parsed = _parse_bedtime_start(str(start_val))
        if parsed is None:
            _LOGGER.warning(
                "Profile %s: could not parse bedtime start %r", self._pid, start_val
            )
        return parsed, bt_id

    @property
    def options(self) -> list[str]:
        """Return available time options based on the current bedtime."""
        bedtime_start, _ = self._get_bedtime_info()
        if bedtime_start is None:
            return ["No bedtime set"]
        return _generate_options(bedtime_start)

    @property
    def available(self) -> bool:
        """Return True if a bedtime is active for today."""
        bedtime_start, offtime_id = self._get_bedtime_info()
        return bedtime_start is not None and offtime_id is not None

    async def async_select_option(self, option: str) -> None:
        """Handle a time selection - send the late bedtime reward."""
        _LOGGER.debug("Profile %s: selected option %r", self._pid, option)
        bedtime_start, offtime_id = self._get_bedtime_info()

        if bedtime_start is None or offtime_id is None:
            _LOGGER.warning(
                "No active bedtime for profile %s (start=%s, offtime_id=%s)",
                self._pid,
                bedtime_start,
                offtime_id,
            )
            return

        minutes = _minutes_offset(bedtime_start, option)
        _LOGGER.debug(
            "Profile %s: bedtime_start=%s, selected=%s, offset=%s min, offtime_id=%s",
            self._pid,
            bedtime_start,
            option,
            minutes,
            offtime_id,
        )
        if minutes is None or minutes <= 0:
            _LOGGER.error(
                "Could not calculate offset for selected time: %s", option
            )
            return

        await self.coordinator.api.send_late_bedtime(
            pid=self._pid,
            offtime_id=offtime_id,
            minutes=minutes,
        )
        _LOGGER.debug("Profile %s: late bedtime reward sent (%s min)", self._pid, minutes)

        # Keep current_option as None so the user can pick the same time again
        self._attr_current_option = None
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
