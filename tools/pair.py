"""Pair a rope from the command line (no phone, no Home Assistant needed).

    pip install bleak cryptography
    python pair.py

Wake the rope (press its button).  When the script says so, press the Power button
on the end of the handle ONCE.  The new credentials are written to
``credentials.json`` (never commit it: it is the key to your rope).
"""
import asyncio
import importlib.util
import json
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


def _beep() -> None:
    try:
        import winsound

        winsound.Beep(2200, 400)
        winsound.Beep(2200, 400)
    except Exception:  # noqa: BLE001
        print("\a", end="")


async def main() -> None:
    print("looking for 'Mijia Smart Jump Rope' (wake it: press the button)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (ad.local_name or d.name or "").startswith("Mijia Smart Jump Rope"),
        timeout=40,
    )
    if device is None:
        sys.exit("rope not found")
    print("found", device.name, device.address)
    async with BleakClient(device, timeout=20) as client:

        def press() -> None:
            print(">>> PRESS THE POWER BUTTON ON THE ROPE NOW <<<", flush=True)
            _beep()

        result = await protocol.bind(client, device.address, on_press_needed=press)
    out = pathlib.Path("credentials.json")
    out.write_text(
        json.dumps(
            {
                "address": device.address,
                "app_device_id": result.app_device_id,
                "token": result.token.hex(),
            },
            indent=2,
        )
    )
    print(f"paired. credentials saved to {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
