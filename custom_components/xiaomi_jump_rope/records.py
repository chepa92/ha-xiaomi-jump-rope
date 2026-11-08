"""Decoding of stored workout records (pure Python, no Home Assistant).

Every record starts with ``01 00 01 00`` followed by its 7-byte id::

    id = start time (u32 LE) | flags (u8) | kind (u8) | check (u8)

``kind`` 0x04 is the workout *summary* (129 bytes); ``kind`` 0x02 is the *detail*
record (per-second data).  In the summary (all u32 little endian): start time @17, end
time @21, elapsed seconds @25 (start to end, pauses included), jumps @64, average
and maximum frequency in jumps/min @68 / @72, calories @120.  (Checked against the
live counters of three workouts.)
"""
from __future__ import annotations

import struct

HEADER = bytes.fromhex("01000100")
KIND_SUMMARY = 0x04
KIND_DETAIL = 0x02


def decode_record(data: bytes) -> dict:
    """Best-effort decode; never raises."""
    out: dict = {"length": len(data)}
    try:
        if len(data) < 11 or data[:4] != HEADER:
            out["kind"] = "other"
            return out
        rid = data[4:11]
        out["id_start_time"] = struct.unpack_from("<I", rid, 0)[0]
        kind = rid[5]
        out["kind"] = {KIND_SUMMARY: "summary", KIND_DETAIL: "detail"}.get(kind, f"0x{kind:02x}")
        if kind == KIND_SUMMARY and len(data) >= 29:
            start, end, elapsed = struct.unpack_from("<III", data, 17)
            out.update(start_time=start, end_time=end, elapsed_seconds=elapsed)
            if len(data) >= 124:
                out.update(
                    jumps=struct.unpack_from("<I", data, 64)[0],
                    avg_frequency=struct.unpack_from("<I", data, 68)[0],
                    max_frequency=struct.unpack_from("<I", data, 72)[0],
                    calories=struct.unpack_from("<I", data, 120)[0],
                )
    except (struct.error, IndexError):
        pass
    return out
