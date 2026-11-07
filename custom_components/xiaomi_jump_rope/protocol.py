"""BLE protocol for the Mijia Smart Jump Rope (yunmai.jmprope.sr803, "XMSR-P803").

The rope talks the Xiaomi "eco" protocol over GATT service 0xFE95:

* ``0x52``  write-without-response (host -> rope)
* ``0x51``  notify                 (rope -> host)

Frames (little endian, one per GATT write/notification)::

    seq(u16)=0  control frame, kind(u8):
                  0 CMD        dtype(u8) frame_count(u16)
                  1 ACK        status(u8) [seq(u16)...]
                  2 SINGLE_CMD dtype(u8) payload
                  3 SINGLE_ACK status(u8)
    seq(u16)>=1 data frame (payload chunk)

``dtype`` 2 = plaintext protobuf (handshake), 1 = AES-CCM encrypted protobuf.

Authentication re-uses the credentials (``app_device_id`` + ``token``) of an
existing Mi Fitness pairing ("reconnect" flow: cmd 26 -> 27).  After the
handshake the rope pushes a status message (type 8, id 66) containing the
current workout counters.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import struct
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_LOGGER = logging.getLogger(__name__)

CHAR_VERSION = "00000050-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00000051-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "00000052-0000-1000-8000-00805f9b34fb"
CHAR_EXTRA = (
    "00000053-0000-1000-8000-00805f9b34fb",
    "00000055-0000-1000-8000-00805f9b34fb",
)

DTYPE_ENCRYPTED = 1
DTYPE_PLAIN = 2
CMD_RECONNECT_HELLO = 26
CMD_RECONNECT_CONFIRM = 27
MSG_TYPE_FITNESS = 8
MSG_ID_STATUS_PUSH = 66


class RopeError(Exception):
    """Base error."""


class RopeAuthError(RopeError):
    """The rope rejected / failed the authentication handshake."""


class RopeTimeout(RopeError):
    """The rope did not answer in time (usually: asleep, busy or out of range)."""


# --------------------------------------------------------------------------- protobuf


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def f_varint(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def f_bytes(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def f_str(field: int, value: str) -> bytes:
    return f_bytes(field, value.encode())


def f_float(field: int, value: float) -> bytes:
    return _varint((field << 3) | 5) + struct.pack("<f", value)


def _read_varint(data: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def parse_pb(data: bytes) -> list[tuple[int, int, int | bytes]]:
    """Return a list of ``(field, wire_type, value)``."""
    out: list[tuple[int, int, int | bytes]] = []
    i = 0
    while i < len(data):
        key, i = _read_varint(data, i)
        field, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(data, i)
        elif wt == 2:
            ln, i = _read_varint(data, i)
            v, i = data[i : i + ln], i + ln
        elif wt == 5:
            v, i = data[i : i + 4], i + 4
        elif wt == 1:
            v, i = data[i : i + 8], i + 8
        else:
            raise ValueError(f"bad wire type {wt}")
        out.append((field, wt, v))
    return out


def pb_get(fields, number: int):
    for f, _, v in fields:
        if f == number:
            return v
    return None


def make_packet(ptype: int, pid: int, account: bytes | None = None) -> bytes:
    out = f_varint(1, ptype) + f_varint(2, pid)
    if account is not None:
        out += f_bytes(3, account)
    return out


def parse_packet(data: bytes):
    f = parse_pb(data)
    acct = pb_get(f, 3)
    return pb_get(f, 1), pb_get(f, 2), (parse_pb(acct) if acct is not None else None)


# --------------------------------------------------------------------------- crypto


def hkdf(info: str, ikm: bytes, salt: bytes, length: int = 64) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=length, salt=salt, info=info.encode()
    ).derive(ikm)


def hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def ccm_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    return AESCCM(key, tag_length=4).encrypt(nonce, data, None)


def ccm_decrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    return AESCCM(key, tag_length=4).decrypt(nonce, data, None)


@dataclass
class SessionKeys:
    device_key: bytes
    app_key: bytes
    device_iv: bytes
    app_iv: bytes

    def decrypt(self, wire: bytes) -> bytes:
        """Decrypt a message pushed by the rope."""
        return ccm_decrypt(self.device_key, self.device_iv + b"\x00" * 8, wire)


# --------------------------------------------------------------------------- status


@dataclass
class RopeStatus:
    """Workout counters reported by the rope."""

    jumps: int
    calories: int
    duration: int  # seconds
    state: int | None = None
    timestamp: int | None = None


def parse_status_push(plain: bytes) -> RopeStatus | None:
    """Parse a decrypted push; returns None if it is not the status push."""
    try:
        top = parse_pb(plain)
        if pb_get(top, 2) != MSG_ID_STATUS_PUSH:
            return None
        body = pb_get(top, 10)
        sub = pb_get(parse_pb(body), 53) if body is not None else None
        if sub is None:
            return None
        f = {a: v for a, wt, v in parse_pb(sub) if wt == 0}
    except (ValueError, IndexError):
        return None
    if 17 not in f or 20 not in f:
        return None
    return RopeStatus(
        jumps=int(f[17]),
        calories=int(f[20]),
        duration=int(f.get(16, 0)),
        state=int(f[2]) if 2 in f else None,
        timestamp=int(f[15]) if 15 in f else None,
    )


# --------------------------------------------------------------------------- channel


class Channel:
    """Framing / ACK state machine on top of a connected bleak client."""

    def __init__(self, client) -> None:
        self.client = client
        self.acks: asyncio.Queue = asyncio.Queue()
        self.msgs: asyncio.Queue = asyncio.Queue()
        self._incoming: list | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def mtu(self) -> int:
        try:
            return max(int(self.client.mtu_size), 23)
        except Exception:  # noqa: BLE001
            return 23

    async def read_version(self) -> None:
        """The official app reads char 0x50 first; the rope ignores the
        handshake unless this happened."""
        try:
            await self.client.read_gatt_char(CHAR_VERSION)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("version read failed: %s", err)

    async def start(self) -> None:
        for char in (CHAR_NOTIFY, CHAR_WRITE, *CHAR_EXTRA):
            try:
                await self.client.start_notify(char, self._on_notify)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("no notify on %s: %s", char[:8], err)

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for char in (CHAR_NOTIFY, CHAR_WRITE, *CHAR_EXTRA):
            try:
                await self.client.stop_notify(char)
            except Exception:  # noqa: BLE001
                pass

    async def _write(self, frame: bytes) -> None:
        await self.client.write_gatt_char(CHAR_WRITE, frame, response=False)

    def _on_notify(self, _sender, data: bytearray) -> None:
        task = asyncio.get_running_loop().create_task(self._handle(bytes(data)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, d: bytes) -> None:
        if len(d) < 3:
            return
        seq = struct.unpack_from("<H", d, 0)[0]
        if seq != 0:
            inc = self._incoming
            if inc is None:
                return
            inc[2][seq] = d[2:]
            if len(inc[2]) >= inc[1]:
                payload = b"".join(inc[2][i] for i in range(1, inc[1] + 1))
                self._incoming = None
                await self._write(struct.pack("<HBB", 0, 1, 0))
                await self.msgs.put((inc[0], payload))
            return
        kind = d[2]
        if kind == 0:
            dtype, count = d[3], struct.unpack_from("<H", d, 4)[0]
            self._incoming = [dtype, count, {}]
            await self._write(struct.pack("<HBB", 0, 1, 1))
        elif kind == 2:
            await self._write(struct.pack("<HBB", 0, 3, 0))
            await self.msgs.put((d[3], d[4:]))
        elif kind in (1, 3):
            await self.acks.put((kind, d[3]))

    async def send(self, dtype: int, payload: bytes, timeout: float = 12.0) -> None:
        """Send one message (single-frame only; all handshake messages fit)."""
        if len(payload) > self.mtu - 7:
            raise RopeError(f"payload of {len(payload)} bytes does not fit MTU {self.mtu}")
        await self._write(struct.pack("<HBB", 0, 2, dtype) + payload)
        try:
            _kind, status = await asyncio.wait_for(self.acks.get(), timeout)
        except asyncio.TimeoutError as err:
            raise RopeTimeout("no ACK from rope") from err
        if status != 0:
            raise RopeError(f"unexpected ACK status {status}")

    async def recv(self, timeout: float = 10.0) -> tuple[int, bytes]:
        try:
            return await asyncio.wait_for(self.msgs.get(), timeout)
        except asyncio.TimeoutError as err:
            raise RopeTimeout("no message from rope") from err


# --------------------------------------------------------------------------- session


async def authenticate(
    ch: Channel, app_device_id: str, token: bytes
) -> tuple[SessionKeys, bytes | None]:
    """Run the reconnect handshake.

    Returns the session keys and, if the rope's confirm answer was already an
    encrypted push, that (still encrypted) message.
    """
    app_random = os.urandom(16)
    hello = make_packet(
        1,
        CMD_RECONNECT_HELLO,
        f_bytes(30, f_bytes(1, app_random) + f_str(2, app_device_id)),
    )
    await ch.send(DTYPE_PLAIN, hello, 15)
    dtype, payload = await ch.recv(15)
    _t, _i, acct = parse_packet(payload)
    if acct is None:
        raise RopeAuthError("empty reply to hello")
    err = pb_get(acct, 3)
    if err is not None:
        raise RopeAuthError(f"rope returned error {err} (wrong credentials?)")
    f40 = pb_get(acct, 31)
    if f40 is None:
        raise RopeAuthError("unexpected reply to hello")
    f = parse_pb(f40)
    dev_random, dev_sign = pb_get(f, 1), pb_get(f, 2)

    okm = hkdf("miwear-auth", token, app_random + dev_random, 64)
    keys = SessionKeys(okm[0:16], okm[16:32], okm[32:36], okm[36:40])
    if not hmac.compare_digest(hmac_sha256(keys.device_key, dev_random + app_random), dev_sign):
        raise RopeAuthError("device signature mismatch (wrong token?)")

    app_sign = hmac_sha256(keys.app_key, app_random + dev_random)
    info = f_varint(1, 0) + f_float(2, 33.0) + f_str(3, "HomeAssistant")
    enc = ccm_encrypt(keys.app_key, keys.app_iv + b"\x00" * 8, info)
    confirm = make_packet(1, CMD_RECONNECT_CONFIRM, f_bytes(32, f_bytes(1, app_sign) + f_bytes(2, enc)))
    await ch.send(DTYPE_PLAIN, confirm, 30)
    dtype, payload = await ch.recv(30)
    if dtype == DTYPE_ENCRYPTED:
        return keys, payload
    _t, _i, acct = parse_packet(payload)
    err = pb_get(acct, 3) if acct else None
    if err:
        raise RopeAuthError(f"confirm rejected with error {err}")
    return keys, None


async def read_status(client, app_device_id: str, token: bytes, timeout: float = 15.0) -> RopeStatus:
    """Authenticate on an already connected client and return the first status push.

    Read-only: nothing is written that could alter or reset the workout.
    """
    ch = Channel(client)
    await ch.read_version()
    await ch.start()
    try:
        keys, pending = await authenticate(ch, app_device_id, token)
        deadline = time.monotonic() + timeout
        while True:
            if pending is not None:
                dtype, wire = DTYPE_ENCRYPTED, pending
                pending = None
            else:
                dtype, wire = await ch.recv(max(0.1, deadline - time.monotonic()))
            if dtype != DTYPE_ENCRYPTED:
                continue
            try:
                status = parse_status_push(keys.decrypt(wire))
            except Exception:  # noqa: BLE001
                continue
            if status is not None:
                return status
            if time.monotonic() > deadline:
                raise RopeTimeout("no status push received")
    finally:
        await ch.stop()
