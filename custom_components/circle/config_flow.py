"""Config flow for Meet Circle integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CircleApiClient, CircleAuthError
from .const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CircleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Meet Circle."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step: collect credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            device_id = user_input[CONF_DEVICE_ID]

            session = async_get_clientsession(self.hass)
            client = CircleApiClient(
                email=email,
                password=password,
                device_id=device_id,
                session=session,
            )

            try:
                tokens = await client.authenticate()
            except CircleAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=email,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_DEVICE_ID: device_id,
                        "access_token": tokens["access_token"],
                        "refresh_token": tokens["refresh_token"],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_DEVICE_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when tokens expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle re-auth confirmation step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            password = user_input[CONF_PASSWORD]
            email = reauth_entry.data[CONF_EMAIL]
            device_id = reauth_entry.data[CONF_DEVICE_ID]

            session = async_get_clientsession(self.hass)
            client = CircleApiClient(
                email=email,
                password=password,
                device_id=device_id,
                session=session,
            )

            try:
                tokens = await client.authenticate()
            except CircleAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during re-authentication")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_PASSWORD: password,
                        "access_token": tokens["access_token"],
                        "refresh_token": tokens["refresh_token"],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
