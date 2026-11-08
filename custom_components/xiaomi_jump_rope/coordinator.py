"""Coordinator: wakes up when the rope advertises, connects, reads, disconnects."""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_INTERVAL,
    CONF_ADDRESS,
    CONF_APP_DEVICE_ID,
    CONF_TOKEN,
    DOMAIN,
    HISTORY_INTERVAL,
    IDLE_INTERVAL,
    MAX_BACKOFF,
    TICK_INTERVAL,
)
from .protocol import RawRecord, RopeAuthError, RopeError, RopeStatus, read_session
from .records import decode_record
from .session import DayTotals, FinishedSession, SessionTracker

_LOGGER = logging.getLogger(__name__)

EVENT_SESSION_COMPLETED = f"{DOMAIN}_session_completed"
STORE_VERSION = 1


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


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
        mac = self.address.replace(":", "")
        # Journal of finished sessions (like xiaomi_abwheel_journal_<MAC>.json)
        self.journal_path = hass.config.path(f"{DOMAIN}_journal_{mac}.json")
        # Every record downloaded from the rope (raw + decoded), keyed by record id
        self.records_path = hass.config.path(f"{DOMAIN}_records_{mac}.json")
        self.journal_entries = 0
        self.stored_records = 0
        self._records: dict[str, Any] = {}
        self._want_history = True
        self._last_history = 0.0

    async def async_load(self) -> None:
        """Restore today's totals, the journal count and the downloaded records."""
        self.today = DayTotals.from_dict(await self._store.async_load())
        self.today.roll(dt_util.now().date().isoformat())
        journal = await self.hass.async_add_executor_job(_read_json, self.journal_path, [])
        self.journal_entries = len(journal) if isinstance(journal, list) else 0
        records = await self.hass.async_add_executor_job(_read_json, self.records_path, {})
        self._records = records if isinstance(records, dict) else {}
        self.stored_records = len(self._records)

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

        self._maybe_read()  # do not wait for the first tick / advertisement
        return _cancel

    @property
    def is_active(self) -> bool:
        """True while a workout session is in progress."""
        return self.tracker.active

    # ------------------------------------------------------------------ triggers

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

    async def async_force_read(self) -> None:
        """"Connect now": read the counters and download stored workouts right away."""
        if self._busy:
            raise HomeAssistantError("A read is already in progress, try again in a moment")
        self._busy = True
        self._last_attempt = time.monotonic()
        self._failures = 0
        await self._async_read(force=True)
        if self.last_error:
            raise HomeAssistantError(f"Could not read the rope: {self.last_error}")

    # ------------------------------------------------------------------ reading

    async def _async_read(self, force: bool = False) -> None:
        want_history = (
            force
            or self._want_history
            or time.monotonic() - self._last_history > HISTORY_INTERVAL
        )
        try:
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise RopeError("rope not currently visible (press its button)")
            client = await establish_connection(
                BleakClientWithServiceCache, device, self.address, max_attempts=2
            )
            try:
                status, records = await read_session(
                    client,
                    self._app_device_id,
                    self._token,
                    want_history=want_history,
                    known_ids=set(self._records),
                    on_record=self._on_record,
                )
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
            if want_history:
                self._want_history = False
                self._last_history = time.monotonic()
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

    async def _on_record(self, record: RawRecord) -> bool:
        """Save a downloaded record to disk; True = safe to free it on the rope."""
        key = record.record_id.hex()
        entry = {
            "record_id": key,
            "received_at": dt_util.now().isoformat(timespec="seconds"),
            "decoded": decode_record(record.data),
            "raw_hex": record.data.hex(),
        }
        self._records[key] = entry
        try:
            await self.hass.async_add_executor_job(_write_json, self.records_path, self._records)
        except OSError as err:
            _LOGGER.error("Could not save record %s: %s (not confirming it)", key, err)
            self._records.pop(key, None)
            return False
        self.stored_records = len(self._records)
        self.async_update_listeners()
        return True

    # ------------------------------------------------------------------ sessions

    def _complete(self, finished: FinishedSession) -> None:
        """A session ended: update totals, persist, journal, fire the event."""
        self.today.add(dt_util.now().date().isoformat(), finished)
        self._store.async_delay_save(self.today.to_dict, 1)
        self._want_history = True  # the rope now holds a record of it
        _LOGGER.info(
            "Jump session finished: %d jumps, %d kcal, %d s",
            finished.jumps, finished.calories, finished.duration,
        )
        self.hass.async_create_task(self._async_journal(finished))
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

    async def _async_journal(self, finished: FinishedSession) -> None:
        start = datetime.fromtimestamp(finished.start_time)
        record = {
            "training_date": start.strftime("%Y-%m-%d"),
            "training_time": start.strftime("%H:%M:%S"),
            "start_time": finished.start_time,
            "end_time": finished.end_time,
            "jumps": finished.jumps,
            "calories": finished.calories,
            "duration_sec": finished.duration,
            "recorded_at": dt_util.now().isoformat(timespec="seconds"),
        }

        def _append() -> int:
            journal = _read_json(self.journal_path, [])
            if not isinstance(journal, list):
                journal = []
            if str(finished.start_time) not in {str(r.get("start_time")) for r in journal}:
                journal.append(record)
                _write_json(self.journal_path, journal)
            return len(journal)

        try:
            self.journal_entries = await self.hass.async_add_executor_job(_append)
        except OSError as err:
            _LOGGER.error("Could not write the journal: %s", err)
        else:
            self.async_update_listeners()

    def _fail(self, message: str) -> None:
        self._failures = min(self._failures + 1, 6)
        self.last_error = message
        _LOGGER.debug(
            "Reading %s failed (%d): %s", self.address, self._failures, message
        )
