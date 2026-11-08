"""Decoding tests with real records captured from a rope."""
import importlib.util
import pathlib
import sys

SPEC = importlib.util.spec_from_file_location(
    "records",
    pathlib.Path(__file__).parent.parent / "custom_components" / "xiaomi_jump_rope" / "records.py",
)
records = importlib.util.module_from_spec(SPEC)
sys.modules["records"] = records
SPEC.loader.exec_module(records)

# Real 129-byte summaries captured from a rope.
# 1: start 1794167885, end 1794168743 (858 s), 37 jumps, 14 kcal
SUMMARY = bytes.fromhex(
    "010001004dd4f06a2004b900f0007000f04dd4f06aa7d7f06a5a0300000500000000000000000000"
    "0000000000000000000000000000000000000000000000002500000002000000b800000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0e00000000d9ba523c"
)
# 2: watched live: 33 jumps, 5 kcal, 536 s elapsed
LIVE = bytes.fromhex(
    "01000100b5d9f06a2004b900f0007000f0b5d9f06acddbf06a180200000300000000000000000000"
    "0000000000000000000000000000000000000000000000002100000003000000a100000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0500000000d2cee068"
)


def test_summary_times():
    d = records.decode_record(SUMMARY)
    assert d["kind"] == "summary"
    assert d["start_time"] == 1794167885
    assert d["end_time"] == 1794168743
    assert d["elapsed_seconds"] == 858 == d["end_time"] - d["start_time"]


def test_summary_counters_match_live_values():
    d = records.decode_record(LIVE)
    assert (d["jumps"], d["calories"], d["elapsed_seconds"]) == (33, 5, 536)
    assert (d["avg_frequency"], d["max_frequency"]) == (3, 161)


def test_first_summary_counters():
    d = records.decode_record(SUMMARY)
    assert (d["jumps"], d["calories"]) == (37, 14)


def test_garbage_never_raises():
    assert records.decode_record(b"")["kind"] == "other"
    assert records.decode_record(bytes(5))["kind"] == "other"
