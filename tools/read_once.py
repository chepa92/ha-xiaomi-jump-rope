"""Standalone check against a real rope (no Home Assistant needed).

    pip install bleak cryptography
    python read_once.py <app_device_id> <token>

Wake the rope first.  Read-only: it never changes the workout.
"""
import asyncio
import importlib.util
import pathlib
import sys

from bleak import BleakClient, BleakScanner

SPEC = importlib.util.spec_from_file_location(
    "protocol",
    pathlib.Path(__file__).parent.parent / "custom_components" / "xiaomi_jump_rope" / "protocol.py",
)
protocol = importlib.util.module_from_spec(SPEC)
sys.modules["protocol"] = protocol
SPEC.loader.exec_module(protocol)


async def main(app_device_id: str, token_hex: str) -> None:
    print("looking for 'Mijia Smart Jump Rope' (wake it: jump or press the button)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (ad.local_name or d.name or "").startswith("Mijia Smart Jump Rope"),
        timeout=30,
    )
    if device is None:
        sys.exit("rope not found")
    print("found", device.name)
    async with BleakClient(device, timeout=20) as client:
        status = await protocol.read_status(client, app_device_id, bytes.fromhex(token_hex))
        print(status)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(*sys.argv[1:]))
