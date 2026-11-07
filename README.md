# Xiaomi / Mijia Smart Jump Rope (XMSR-P803) for Home Assistant

Reads **jumps, calories and duration** straight from the rope over Bluetooth LE,
without the Mi Fitness app and without any cloud.

> Unofficial. The Xiaomi "eco" protocol is undocumented; this integration was
> reverse-engineered from the rope's own traffic. Tested only with the
> China-region **XMSR-P803** (`yunmai.jmprope.sr803`). Early release: expect rough edges.

## Entities

| Entity | Meaning |
|---|---|
| Jumps | jump count of the current/last session |
| Calories | kcal of the current/last session |
| Duration | seconds of the current/last session |
| Workout active | on while the jump count changed in the last 3 minutes |
| Last read | when Home Assistant last got data from the rope (diagnostic) |

## How it works

The rope only advertises while it is awake (jumping or a button press).
Home Assistant finds it **by its Bluetooth name** (`Mijia Smart Jump Rope ...`), so no
MAC address is needed. When the rope is around, Home Assistant connects,
authenticates with your existing pairing credentials, reads one status message,
and disconnects:

* about **once a minute** when idle (a check runs every 20 s, reads are rate-limited),
* every ~20 s while a workout is running,
* with back-off after failed attempts.

Values stay on screen while the rope sleeps. The **last few seconds of a
workout may be missed** if the rope falls asleep between reads.

## Important limits

* **No button press is needed**, but the rope must be awake and in range of a Home Assistant Bluetooth adapter / proxy.
* Only one device can talk to the rope at a time. Close Mi Fitness on your phone (or turn its Bluetooth off) while you want Home Assistant to read.
* **Do not open the rope in Mi Fitness during a workout you care about**: leaving training in the app resets the data on the rope.
* The integration is read-only: it never changes or resets anything on the rope.
* If you re-pair the rope in Mi Fitness, the token changes: update it here.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/chepa92/ha-xiaomi-jump-rope`, category **Integration**.
2. Install **Xiaomi Smart Jump Rope**, restart Home Assistant.
3. Wake the rope (jump or press its button). It is **auto-discovered** under **Settings → Devices & services**; click *Configure* and enter the two credentials below. (You can also use *Add integration* → *Xiaomi Smart Jump Rope* while the rope is awake.)

## Credentials

The integration needs the credentials of the rope's existing Mi Fitness pairing:

* **app device ID** (32 hex characters),
* **token** (32 hex characters).

They are stored by the Mi Fitness app (the China-region build, package `com.mi.health`) in
`/data/data/com.mi.health/databases/eco_local_device_db`. Reading it needs a **rooted** phone:

```
adb shell su -c "cp /data/data/com.mi.health/databases/eco_local_device_db /sdcard/"
adb pull /sdcard/eco_local_device_db
python tools/extract_credentials.py eco_local_device_db
```

Treat the token like a password: anyone with it can talk to your rope. Never post it publicly.

Creating independent pairing (so no phone is needed at all) is not implemented yet.

## Development

```
pip install bleak cryptography pytest
pytest tests
python tools/read_once.py AA:BB:CC:DD:EE:FF <app_device_id> <token>   # real rope, read-only
```

## Disclaimer

Not affiliated with Xiaomi. Use at your own risk.
