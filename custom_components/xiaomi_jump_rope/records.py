"""Decoding of stored workout records (pure Python, no Home Assistant).

Every record starts with ``01 00 01 00`` followed by its 7-byte id::

    id = start time (u32 LE) | flags (u8) | kind (u8) | check (u8)

``kind`` 0x04 is the workout *summary* (129 bytes); ``kind`` 0x02 is the *detail*
record (per-second data).  In the summary, from offset 17: start time (u32),
end time (u32), elapsed seconds (u32), then counters whose exact meaning is still
being confirmed (they are returned raw under ``"words"``).
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
            out["words"] = {
                str(off): struct.unpack_from("<I", data, off)[0]
                for off in range(29, len(data) - 4, 4)
                if struct.unpack_from("<I", data, off)[0]
            }
    except (struct.error, IndexError):
        pass
    return out
