"""Config flow for the Xiaomi Smart Jump Rope.

The rope is found by its Bluetooth name.  It can be paired directly from Home
Assistant (press the rope's Power button once) or an existing Mi Fitness pairing
can be reused by entering its credentials.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol
from bleak import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_ADDRESS,
    CONF_APP_DEVICE_ID,
    CONF_TOKEN,
    DEVICE_NAME_PREFIX,
    DOMAIN,
)
from .protocol import BindResult, RopeBusyError, RopeError, bind

_LOGGER = logging.getLogger(__name__)
_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
BUSY_RETRIES = 2
BUSY_WAIT = 40  # seconds the rope needs to forget an earlier pairing attempt


class JumpRopeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the jump rope."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None
        self._pair_task: asyncio.Task[BindResult] | None = None
        self._pair_error: str | None = None
        self._result: BindResult | None = None

    # -- discovery -----------------------------------------------------------

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """The rope was seen advertising."""
        self._address = discovery_info.address.upper()
        self._name = discovery_info.name
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": self._name or "Jump Rope"}
        return await self.async_step_method()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a rope that is currently visible to Home Assistant."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._discovered.get(self._address)
            await self.async_set_unique_id(self._address)
            self._abort_if_unique_id_configured()
            return await self.async_step_method()

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

    # -- how to get credentials ----------------------------------------------

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="method", menu_options=["pair", "credentials"]
        )

    # -- pairing from Home Assistant -----------------------------------------

    async def _async_pair(self) -> BindResult:
        """Connect and pair; retries once the rope has forgotten an old attempt."""
        for attempt in range(BUSY_RETRIES + 1):
            device = bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if device is None:
                raise RopeError("rope not visible: wake it with a button press")
            client = await establish_connection(
                BleakClientWithServiceCache, device, self._address, max_attempts=2
            )
            try:
                return await bind(client, self._address)
            except RopeBusyError:
                if attempt == BUSY_RETRIES:
                    raise
            finally:
                await client.disconnect()
            await asyncio.sleep(BUSY_WAIT)
        raise RopeError("pairing failed")  # pragma: no cover

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show progress while the user presses the rope's Power button."""
        if self._pair_task is None:
            self._pair_error = None
            self._pair_task = self.hass.async_create_task(self._async_pair())
        if not self._pair_task.done():
            return self.async_show_progress(
                step_id="pair",
                progress_action="pair",
                progress_task=self._pair_task,
            )
        task, self._pair_task = self._pair_task, None
        try:
            self._result = task.result()
        except (RopeError, BleakError, TimeoutError, OSError) as err:
            _LOGGER.debug("Pairing failed: %s", err)
            self._pair_error = str(err) or type(err).__name__
            return self.async_show_progress_done(next_step_id="pair_failed")
        return self.async_show_progress_done(next_step_id="pair_done")

    async def async_step_pair_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="pair_failed",
            menu_options=["pair", "credentials"],
            description_placeholders={"error": self._pair_error or "unknown error"},
        )

    async def async_step_pair_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._result is not None
        return self.async_create_entry(
            title=self._name or "Mijia Smart Jump Rope",
            data={
                CONF_ADDRESS: self._address,
                CONF_APP_DEVICE_ID: self._result.app_device_id,
                CONF_TOKEN: self._result.token.hex(),
            },
        )

    # -- reuse an existing pairing -------------------------------------------

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the credentials of an existing pairing."""
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
