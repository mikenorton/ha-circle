"""API client for Meet Circle."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import date, datetime, timezone
from typing import Any

import aiohttp

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

# Cognito SRP constants
N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64"
    "ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6B"
    "F12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB31"
    "43DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)
G_HEX = "2"
INFO_BITS = bytearray("Caldera Derived Key", "utf-8")


def _hash_sha256(buf: bytes) -> bytes:
    """SHA256 hash."""
    return hashlib.sha256(buf).digest()


def _hex_hash(hex_str: str) -> str:
    """Hash a hex string."""
    return hashlib.sha256(bytes.fromhex(hex_str)).hexdigest()


def _hex_to_long(hex_str: str) -> int:
    return int(hex_str, 16)


def _long_to_hex(long_num: int) -> str:
    return format(long_num, "x")


def _pad_hex(long_int: int) -> str:
    """Pad a hex value to ensure even length and two's-complement positive."""
    hash_str = _long_to_hex(long_int) if isinstance(long_int, int) else long_int
    if len(hash_str) % 2 == 1:
        hash_str = "0" + hash_str
    elif hash_str[0] in "89ABCDEFabcdef":
        hash_str = "00" + hash_str
    return hash_str


def _compute_hkdf(ikm: bytes, salt: bytes) -> bytes:
    """HKDF for SRP."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    info_bits_update = INFO_BITS + bytearray(chr(1), "utf-8")
    return hmac.new(prk, info_bits_update, hashlib.sha256).digest()[:16]


def _calculate_u(big_a: int, big_b: int) -> int:
    u_hex_hash = _hex_hash(_pad_hex(big_a) + _pad_hex(big_b))
    return _hex_to_long(u_hex_hash)


class CircleAuthError(Exception):
    """Raised when authentication fails."""


class CircleApiError(Exception):
    """Raised when an API call fails."""


class _CognitoSRP:
    """Minimal async Cognito SRP implementation using aiohttp."""

    def __init__(
        self,
        username: str,
        password: str,
        pool_id: str,
        client_id: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._pool_id = pool_id
        self._pool_name = pool_id.split("_", 1)[1]
        self._client_id = client_id
        self._session = session

        self._big_n = _hex_to_long(N_HEX)
        self._g = _hex_to_long(G_HEX)
        self._k = _hex_to_long(_hex_hash("00" + N_HEX + "0" + G_HEX))
        self._small_a = _hex_to_long(os.urandom(128).hex())
        self._big_a = pow(self._g, self._small_a, self._big_n)

    def _get_password_auth_key(
        self, username: str, password: str, big_b: int, salt: int
    ) -> bytes:
        """Calculate the SRP password authentication key."""
        u_value = _calculate_u(self._big_a, big_b)
        if u_value == 0:
            raise CircleAuthError("SRP u value is zero")

        username_password = f"{self._pool_name}{username}:{password}"
        username_password_hash = _hash_sha256(username_password.encode("utf-8"))

        x_value = _hex_to_long(
            _hex_hash(_pad_hex(salt) + username_password_hash.hex())
        )
        s_value = pow(
            big_b - self._k * pow(self._g, x_value, self._big_n),
            self._small_a + u_value * x_value,
            self._big_n,
        )
        return _compute_hkdf(
            bytes.fromhex(_pad_hex(s_value)),
            bytes.fromhex(_pad_hex(u_value)),
        )

    async def authenticate(self) -> dict[str, Any]:
        """Perform SRP authentication, return tokens dict."""
        url = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        }

        # Step 1: InitiateAuth
        init_payload = {
            "AuthFlow": "USER_SRP_AUTH",
            "ClientId": self._client_id,
            "AuthParameters": {
                "USERNAME": self._username,
                "SRP_A": _long_to_hex(self._big_a),
            },
        }

        _LOGGER.debug("Cognito SRP: sending InitiateAuth for %s", self._username)
        async with self._session.post(
            url, json=init_payload, headers=headers
        ) as resp:
            if resp.status != 200:
                error_data = await resp.json(content_type=None)
                error_msg = error_data.get("message", await resp.text())
                raise CircleAuthError(
                    f"Cognito InitiateAuth failed ({resp.status}): {error_msg}"
                )
            init_result = await resp.json(content_type=None)

        challenge = init_result.get("ChallengeName")
        if challenge != "PASSWORD_VERIFIER":
            raise CircleAuthError(f"Unexpected challenge: {challenge}")

        params = init_result["ChallengeParameters"]
        user_id = params["USER_ID_FOR_SRP"]
        salt_hex = params["SALT"]
        srp_b_hex = params["SRP_B"]
        secret_block = params["SECRET_BLOCK"]

        big_b = _hex_to_long(srp_b_hex)
        salt = _hex_to_long(salt_hex)

        hkdf = self._get_password_auth_key(user_id, self._password, big_b, salt)

        # Build timestamp
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%a %b %-d %H:%M:%S UTC %Y")

        # Build claim signature
        msg = bytearray(self._pool_name, "utf-8")
        msg.extend(bytearray(user_id, "utf-8"))
        msg.extend(base64.standard_b64decode(secret_block))
        msg.extend(bytearray(timestamp, "utf-8"))
        signature = base64.standard_b64encode(
            hmac.new(hkdf, msg, hashlib.sha256).digest()
        ).decode("utf-8")

        # Step 2: RespondToAuthChallenge
        headers["X-Amz-Target"] = (
            "AWSCognitoIdentityProviderService.RespondToAuthChallenge"
        )
        challenge_payload = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ClientId": self._client_id,
            "ChallengeResponses": {
                "USERNAME": user_id,
                "PASSWORD_CLAIM_SECRET_BLOCK": secret_block,
                "PASSWORD_CLAIM_SIGNATURE": signature,
                "TIMESTAMP": timestamp,
            },
        }

        _LOGGER.debug("Cognito SRP: responding to PASSWORD_VERIFIER challenge")
        async with self._session.post(
            url, json=challenge_payload, headers=headers
        ) as resp:
            if resp.status != 200:
                error_data = await resp.json(content_type=None)
                error_msg = error_data.get("message", str(error_data))
                raise CircleAuthError(
                    f"Cognito authentication failed ({resp.status}): {error_msg}"
                )
            auth_result = await resp.json(content_type=None)

        tokens = auth_result.get("AuthenticationResult", {})
        if not tokens.get("IdToken"):
            raise CircleAuthError(
                f"Cognito auth succeeded but no IdToken in response: "
                f"{list(auth_result.keys())}"
            )

        _LOGGER.debug("Cognito SRP: authentication successful")
        return {
            "id_token": tokens["IdToken"],
            "access_token": tokens["AccessToken"],
            "refresh_token": tokens["RefreshToken"],
        }


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
            srp = _CognitoSRP(
                username=self._email,
                password=self._password,
                pool_id=COGNITO_USER_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                session=self._session,
            )
            cognito_tokens = await srp.authenticate()
            cognito_id_token = cognito_tokens["id_token"]
        except CircleAuthError:
            raise
        except Exception as err:
            raise CircleAuthError(f"Cognito authentication failed: {err}") from err

        try:
            circle_tokens = await self._exchange_for_circle_token(cognito_id_token)
        except CircleAuthError:
            raise
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

    async def _exchange_for_circle_token(
        self, cognito_id_token: str
    ) -> dict[str, str]:
        """Exchange Cognito ID token for Circle access + refresh tokens."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        payload = {
            "jwt": cognito_id_token,
            "deviceid": self._device_id,
        }

        _LOGGER.debug("Exchanging Cognito token for Circle access token")
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

        _LOGGER.debug("Circle token exchange successful")
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
        self,
        url: str,
        params: dict[str, str] | None = None,
        retry_auth: bool = True,
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
        _LOGGER.warning("send_late_bedtime params: %s", params)
        return await self._request(ADD_EXTENSION_URL, params=params)
