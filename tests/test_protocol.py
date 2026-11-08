"""Offline tests for the protocol helpers (no hardware, no Home Assistant)."""
import importlib.util
import pathlib
import sys

SPEC = importlib.util.spec_from_file_location(
    "protocol",
    pathlib.Path(__file__).parent.parent / "custom_components" / "xiaomi_jump_rope" / "protocol.py",
)
protocol = importlib.util.module_from_spec(SPEC)
sys.modules["protocol"] = protocol
SPEC.loader.exec_module(protocol)


def test_parse_status_push():
    # decrypted push captured from a real rope: 33 jumps, 6 kcal
    plain = bytes.fromhex(
        "08081042521daa031a0800100378e4eddea00680019e01880121900100980100a00106"
    )
    status = protocol.parse_status_push(plain)
    assert status is not None
    assert status.jumps == 33
    assert status.calories == 6
    assert status.duration == 158
    assert status.state == 3


def test_other_push_is_ignored():
    # type 8 id 64 sport-state push is not a status push
    plain = bytes.fromhex("0808104052") + b"\x00"
    assert protocol.parse_status_push(plain) is None


def test_ccm_roundtrip():
    key, nonce = bytes(range(16)), bytes(range(12))
    assert protocol.ccm_decrypt(key, nonce, protocol.ccm_encrypt(key, nonce, b"hello")) == b"hello"


def test_protobuf_roundtrip():
    msg = protocol.f_varint(1, 8) + protocol.f_bytes(2, b"abc") + protocol.f_str(3, "x")
    fields = protocol.parse_pb(msg)
    assert protocol.pb_get(fields, 1) == 8
    assert protocol.pb_get(fields, 2) == b"abc"
    assert protocol.pb_get(fields, 3) == b"x"


def test_hkdf_is_deterministic_64_bytes():
    out = protocol.hkdf("miwear-auth", b"k" * 16, b"s" * 32, 64)
    assert len(out) == 64 and out == protocol.hkdf("miwear-auth", b"k" * 16, b"s" * 32, 64)


def test_ecdh_agreement_and_app_id():
    a_priv, a_pub = protocol.new_keypair()
    b_priv, b_pub = protocol.new_keypair()
    assert len(a_pub) == 64
    assert protocol.ecdh(a_priv, b_pub) == protocol.ecdh(b_priv, a_pub)
    ident = protocol.make_app_device_id("aa:bb:cc:dd:ee:ff", "homeassistant")
    assert len(ident) == 32 and ident == protocol.make_app_device_id("AA:BB:CC:DD:EE:FF", "homeassistant")


def test_ccm_with_aad():
    key, nonce = bytes(range(16)), bytes(range(12))
    ct = protocol.ccm_encrypt(key, nonce, b"payload", b"bind-data")
    import pytest
    with pytest.raises(Exception):
        protocol.ccm_decrypt(key, nonce, ct)  # wrong (missing) aad must fail
