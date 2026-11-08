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

# 129-byte summary: start 1794167885, end 1794168743 (858 s)
SUMMARY = bytes.fromhex(
    "010001004dd4f06a2004b900f0007000f04dd4f06aa7d7f06a5a03000005000000000000000000000000"
    "000000000000000000000000000000000000000000000000002500000002000000b8000000000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000e00000000d9ba523c"
)


def test_summary_times():
    d = records.decode_record(SUMMARY)
    assert d["kind"] == "summary"
    assert d["start_time"] == 1794167885
    assert d["end_time"] == 1794168743
    assert d["elapsed_seconds"] == 858 == d["end_time"] - d["start_time"]


def test_garbage_never_raises():
    assert records.decode_record(b"")["kind"] == "other"
    assert records.decode_record(bytes(5))["kind"] == "other"
