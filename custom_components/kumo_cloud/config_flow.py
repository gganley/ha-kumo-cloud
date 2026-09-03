"""Config flow for Kumo Cloud."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KumoCloudApi, KumoCloudAuthError, KumoCloudError
from .const import DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class KumoCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Kumo Cloud config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for cloud credentials and verify them."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = KumoCloudApi(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
                account = await api.async_get_account()
            except KumoCloudAuthError:
                errors["base"] = "invalid_auth"
            except KumoCloudError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(account.get("id")))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=account.get("username") or user_input[CONF_USERNAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
