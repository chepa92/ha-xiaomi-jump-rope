"""Coordinator: wakes up when the rope advertises, connects, reads, disconnects."""
from __future__ import annotations

import logging
import time
from typing import Any
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from bleak import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ACTIVE_INTERVAL,
    CONF_ADDRESS,
    CONF_APP_DEVICE_ID,
    CONF_TOKEN,
    DOMAIN,
    IDLE_INTERVAL,
    MAX_BACKOFF,
    TICK_INTERVAL,
)
from .protocol import RopeAuthError, RopeError, RopeStatus, read_status
from .session import DayTotals, FinishedSession, SessionTracker

_LOGGER = logging.getLogger(__name__)

EVENT_SESSION_COMPLETED = f"{DOMAIN}_session_completed"
STORE_VERSION = 1


class JumpRopeCoordinator(DataUpdateCoordinator[RopeStatus | None]):
    """Push-style coordinator driven by Bluetooth advertisements.

    The rope only advertises while awake (jumping / button press).  Every
    advertisement is a chance to read the current counters; reads are rate
    limited and back off after failures.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.address: str = entry.data[CONF_ADDRESS].upper()
        self._app_device_id: str = entry.data[CONF_APP_DEVICE_ID]
        self._token = bytes.fromhex(entry.data[CONF_TOKEN])
        self._busy = False
        self._last_attempt = 0.0
        self._failures = 0
        self.last_read: datetime | None = None
        self.last_error: str | None = None
        self.tracker = SessionTracker()
        self.today = DayTotals()
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    async def async_load(self) -> None:
        """Restore today's totals (survives restarts)."""
        self.today = DayTotals.from_dict(await self._store.async_load())
        self.today.roll(dt_util.now().date().isoformat())

    @property
    def today_totals(self) -> DayTotals:
        """Today's totals including the session in progress."""
        self.today.roll(dt_util.now().date().isoformat())
        return self.today

    @callback
    def async_start(self) -> Callable[[], None]:
        """Start watching for the rope; returns one callable that stops everything."""
        cancel_adv = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            BluetoothCallbackMatcher(address=self.address, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )
        cancel_tick = async_track_time_interval(
            self.hass, self._on_tick, timedelta(seconds=TICK_INTERVAL)
        )

        @callback
        def _cancel() -> None:
            cancel_adv()
            cancel_tick()

        return _cancel

    @property
    def is_active(self) -> bool:
        """True while a workout session is in progress."""
        return self.tracker.active

    @callback
    def _on_advertisement(
        self, info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        self._maybe_read()

    @callback
    def _on_tick(self, _now: datetime) -> None:
        """Periodic check: close idle sessions, read if the rope is around."""
        finished = self.tracker.check_timeout(time.monotonic(), int(time.time()))
        if finished is not None:
            self._complete(finished)
        if bluetooth.async_address_present(self.hass, self.address, connectable=True):
            self._maybe_read()

    @callback
    def _maybe_read(self) -> None:
        if self._busy:
            return
        gap = ACTIVE_INTERVAL if self.is_active else IDLE_INTERVAL
        if self._failures:
            gap = max(gap, min(MAX_BACKOFF, 10 * 2**self._failures))
        if time.monotonic() - self._last_attempt < gap:
            return
        self._busy = True
        self._last_attempt = time.monotonic()
        self.config_entry.async_create_background_task(
            self.hass, self._async_read(), f"{DOMAIN}_read_{self.address}"
        )

    async def _async_read(self) -> None:
        try:
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise RopeError("rope not currently visible")
            client = await establish_connection(
                BleakClientWithServiceCache, device, self.address, max_attempts=2
            )
            try:
                status = await read_status(client, self._app_device_id, self._token)
            finally:
                await client.disconnect()
        except RopeAuthError as err:
            self._fail(f"authentication failed: {err}")
        except (RopeError, BleakError, TimeoutError, OSError) as err:
            self._fail(str(err) or type(err).__name__)
        else:
            self._failures = 0
            self.last_error = None
            self.last_read = datetime.now(timezone.utc)
            for finished in self.tracker.update(
                status.jumps,
                status.calories,
                status.duration,
                time.monotonic(),
                int(time.time()),
            ):
                self._complete(finished)
            self.async_set_updated_data(status)
        finally:
            self._busy = False

    def _complete(self, finished: FinishedSession) -> None:
        """A session ended: update totals, persist, fire the event."""
        self.today.add(dt_util.now().date().isoformat(), finished)
        self._store.async_delay_save(self.today.to_dict, 1)
        _LOGGER.info(
            "Jump session finished: %d jumps, %d kcal, %d s",
            finished.jumps, finished.calories, finished.duration,
        )
        self.hass.bus.async_fire(
            EVENT_SESSION_COMPLETED,
            {
                "address": self.address,
                "jumps": finished.jumps,
                "calories": finished.calories,
                "duration": finished.duration,
                "start_time": finished.start_time,
                "end_time": finished.end_time,
            },
        )
        self.async_update_listeners()

    def _fail(self, message: str) -> None:
        self._failures = min(self._failures + 1, 6)
        self.last_error = message
        _LOGGER.debug(
            "Reading %s failed (%d): %s", self.address, self._failures, message
        )
