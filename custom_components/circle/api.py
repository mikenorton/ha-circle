"""API client for Meet Circle."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import aiohttp
from pycognito import Cognito

from .const import (
    ADD_EXTENSION_URL,
    BADGES_URL,
    BEDTIMES_URL,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
    GRANT_ADMIN_URL,
    QUERY_ALL_URL,
    UPDATE_MODE_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class CircleAuthError(Exception):
    """Raised when authentication fails."""


class CircleApiError(Exception):
    """Raised when an API call fails."""


class CircleApiClient:
    """Client for the Meet Circle cloud API."""

    def __init__(
        self,
        email: str,
        password: str,
        device_id: str,
        session: aiohttp.ClientSession,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._device_id = device_id
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token

    @property
    def access_token(self) -> str | None:
        """Return the current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    async def authenticate(self) -> dict[str, str]:
        """Authenticate with Cognito and exchange for Circle tokens.

        Returns dict with access_token and refresh_token.
        Raises CircleAuthError on failure.
        """
        try:
            cognito_id_token = await self._get_cognito_token()
        except Exception as err:
            raise CircleAuthError(f"Cognito authentication failed: {err}") from err

        try:
            circle_tokens = await self._exchange_for_circle_token(cognito_id_token)
        except Exception as err:
            raise CircleAuthError(
                f"Circle token exchange failed: {err}"
            ) from err

        self._access_token = circle_tokens["access_token"]
        self._refresh_token = circle_tokens["refresh_token"]

        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
        }

    async def _get_cognito_token(self) -> str:
        """Get a Cognito ID token using email and password."""
        # pycognito uses boto3 which is synchronous, run in executor
        import asyncio

        loop = asyncio.get_running_loop()

        def _auth() -> str:
            cognito = Cognito(
                COGNITO_USER_POOL_ID,
                COGNITO_CLIENT_ID,
                username=self._email,
            )
            cognito.authenticate(password=self._password)
            return cognito.id_token

        return await loop.run_in_executor(None, _auth)

    async def _exchange_for_circle_token(self, cognito_id_token: str) -> dict[str, str]:
        """Exchange Cognito ID token for Circle access + refresh tokens."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        payload = {
            "jwt": cognito_id_token,
            "deviceid": self._device_id,
        }

        async with self._session.post(
            GRANT_ADMIN_URL, json=payload, headers=headers
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise CircleAuthError(
                    f"Grant admin failed with status {resp.status}: {text}"
                )
            data = await resp.json()

        if not data.get("ok"):
            raise CircleAuthError(f"Grant admin returned error: {data}")

        return {
            "access_token": data["access-token"],
            "refresh_token": data["refresh-token"],
        }

    def _headers(self) -> dict[str, str]:
        """Return common request headers with auth."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        }

    async def _request(
        self, url: str, params: dict[str, str] | None = None, retry_auth: bool = True
    ) -> Any:
        """Make an authenticated GET request. Retry once on 401."""
        async with self._session.get(
            url, params=params, headers=self._headers()
        ) as resp:
            if resp.status == 401 and retry_auth:
                _LOGGER.debug("Got 401, attempting to re-authenticate")
                await self.authenticate()
                return await self._request(url, params=params, retry_auth=False)
            if resp.status != 200:
                text = await resp.text()
                raise CircleApiError(
                    f"API request to {url} failed with status {resp.status}: {text}"
                )
            return await resp.json()

    async def get_all_profiles(self) -> dict[str, Any]:
        """Fetch all profiles and Circle settings."""
        params = {
            "appid": self._device_id,
            "check_ethernet": "true",
            "check_subscription": "true",
        }
        return await self._request(QUERY_ALL_URL, params=params)

    async def get_badges(self) -> list[dict[str, Any]]:
        """Fetch badges (pause status) for all profiles."""
        return await self._request(BADGES_URL)

    async def get_bedtimes(self, pid: int) -> list[dict[str, Any]]:
        """Fetch bedtime schedules for a profile."""
        url = BEDTIMES_URL.format(pid=pid)
        return await self._request(url)

    async def set_mode(self, pid: int, mode: str) -> dict[str, Any]:
        """Set the mode for a profile (Pause or Filter)."""
        params = {
            "appid": self._device_id,
            "user.pid": str(pid),
            "value": mode,
        }
        return await self._request(UPDATE_MODE_URL, params=params)

    async def send_late_bedtime(
        self,
        pid: int,
        offtime_id: int,
        minutes: int = 15,
        target_date: date | None = None,
    ) -> dict[str, Any]:
        """Send a late bedtime reward extension."""
        if target_date is None:
            target_date = date.today()

        params = {
            "appid": self._device_id,
            "clear": "true",
            "date": target_date.strftime("%Y%m%d"),
            "id": "N",
            "offTimeId": str(offtime_id),
            "startMinutes": str(minutes),
            "user.pid": str(pid),
        }
        return await self._request(ADD_EXTENSION_URL, params=params)
