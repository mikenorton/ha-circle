"""DataUpdateCoordinator for the Meet Circle integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CircleApiClient, CircleApiError, CircleAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CircleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the Circle API for profile data."""

    def __init__(self, hass: HomeAssistant, api: CircleApiClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Circle API."""
        try:
            all_data = await self.api.get_all_profiles()
            badges_data = await self.api.get_badges()
        except CircleAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except CircleApiError as err:
            raise UpdateFailed(f"Error communicating with Circle API: {err}") from err

        # Build badge lookup: pid -> list of badges
        badges_by_pid: dict[int, list[str]] = {}
        for badge_entry in badges_data:
            badges_by_pid[badge_entry["pid"]] = badge_entry.get("badges", [])

        # Build profiles dict
        profiles: dict[int, dict[str, Any]] = {}
        users = all_data.get("users", [])

        for user in users:
            pid = int(user["pid"])
            name = user.get("name", f"Profile {pid}")
            mode = user.get("mode", "Unknown")
            age_category = user.get("ageCategory", "Unknown")

            # Skip the "Unmanaged Devices" profile
            if mode == "Unmanaged":
                continue

            badges = badges_by_pid.get(pid, [])
            is_paused = "pause" in badges

            profile: dict[str, Any] = {
                "pid": pid,
                "name": name,
                "mode": mode,
                "age_category": age_category,
                "is_paused": is_paused,
                "badges": badges,
                "bedtime_weekday": None,
                "bedtime_weekend": None,
                "bedtime_weekday_id": None,
                "bedtime_weekend_id": None,
            }

            # Fetch bedtimes for this profile
            try:
                bedtimes = await self.api.get_bedtimes(pid)
                for bt in bedtimes:
                    if bt.get("name") == "bedtime_weekday":
                        profile["bedtime_weekday"] = bt
                        profile["bedtime_weekday_id"] = bt.get("id")
                    elif bt.get("name") == "bedtime_weekend":
                        profile["bedtime_weekend"] = bt
                        profile["bedtime_weekend_id"] = bt.get("id")
            except (CircleApiError, CircleAuthError):
                _LOGGER.debug("Could not fetch bedtimes for profile %s", pid)

            profiles[pid] = profile

        return {
            "profiles": profiles,
            "overall": all_data.get("overall", {}),
        }
