"""Config flow for the Xiaomi Smart Jump Rope (auto-discovery by Bluetooth name)."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_ADDRESS, CONF_APP_DEVICE_ID, CONF_TOKEN, DEVICE_NAME_PREFIX, DOMAIN

_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")


class JumpRopeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the jump rope."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """The rope was seen advertising: only credentials are needed."""
        self._address = discovery_info.address.upper()
        self._name = discovery_info.name
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": self._name or "Jump Rope"}
        return await self.async_step_credentials()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a rope that is currently visible to Home Assistant."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._discovered.get(self._address)
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            return await self.async_step_credentials()

        configured = self._async_current_ids()
        self._discovered = {
            info.address.upper(): f"{info.name} ({info.address.upper()})"
            for info in async_discovered_service_info(self.hass, False)
            if (info.name or "").startswith(DEVICE_NAME_PREFIX)
            and info.address.upper() not in configured
        }
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the pairing credentials of the Mi Fitness app."""
        errors: dict[str, str] = {}
        if user_input is not None:
            app_device_id = user_input[CONF_APP_DEVICE_ID].strip().lower()
            token = user_input[CONF_TOKEN].strip().lower()
            if not _HEX32.match(app_device_id):
                errors[CONF_APP_DEVICE_ID] = "invalid_app_device_id"
            if not _HEX32.match(token):
                errors[CONF_TOKEN] = "invalid_token"
            if not errors:
                return self.async_create_entry(
                    title=self._name or "Mijia Smart Jump Rope",
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_APP_DEVICE_ID: app_device_id,
                        CONF_TOKEN: token,
                    },
                )
        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_DEVICE_ID): str,
                    vol.Required(CONF_TOKEN): str,
                }
            ),
            errors=errors,
            description_placeholders={"name": self._name or "Jump Rope"},
        )
