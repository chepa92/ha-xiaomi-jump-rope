# Xiaomi / Mijia Smart Jump Rope (XMSR-P803) for Home Assistant

Reads **jumps, calories and duration** straight from the rope over Bluetooth LE,
without the Mi Fitness app and without any cloud.

> Unofficial. The Xiaomi "eco" protocol is undocumented; this integration was
> reverse-engineered from the rope's own traffic. Tested only with the
> China-region **XMSR-P803** (`yunmai.jmprope.sr803`). Early release: expect rough edges.

## Entities

| Entity | Meaning |
|---|---|
| Jumps / Calories / Duration | counters of the current (or last) session |
| Jumps today / Calories today / Duration today / Sessions today | totals of finished sessions today plus the running one (reset at midnight, survive restarts) |
| Last session jumps | jumps of the last finished session (attributes via the event below) |
| Workout active | on while a session is in progress |
| Last read | when Home Assistant last got data from the rope (diagnostic) |

## Sessions and the `xiaomi_jump_rope_session_completed` event

The rope has no "workout finished" signal, so a session is considered **finished** when
the jump count stops changing for **3 minutes** (or the rope restarts its counters).
Sessions shorter than 5 jumps are ignored. A stale value left on the rope from before
Home Assistant started is not treated as a session: a session starts when the count is
seen **changing**.

When a session finishes, one event is fired:

```yaml
event_type: xiaomi_jump_rope_session_completed
data:
  jumps: 120
  calories: 14
  duration: 305        # seconds
  start_time: 1794085827   # unix time
  end_time: 1794086132
```

### Sending sessions to Garmin Connect

[ha-garmin-sync](https://github.com/chepa92/ha-garmin-sync) can turn each finished session into a
Garmin **Jump Rope** activity (one per session, not one per jump): enable
*Sync Jump Rope sessions to Garmin* in its options (needs a version with jump rope support).

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
* If the rope is re-paired in another app with the same app ID, the token changes: remove and re-add the rope here.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/chepa92/ha-xiaomi-jump-rope`, category **Integration**.
2. Install **Xiaomi Smart Jump Rope**, restart Home Assistant.
3. Wake the rope (jump or press its button). It is **auto-discovered** under **Settings → Devices & services**; click *Configure* and enter the two credentials below. (You can also use *Add integration* → *Xiaomi Smart Jump Rope* while the rope is awake.)

## Pairing

**No phone and no rooting needed.** When you add the integration, choose **Pair now**,
then press the **Power button on the end of the rope's handle once** when Home Assistant
asks. The integration pairs with the rope itself (as its own "app") and stores the
credentials in the config entry.

* If the rope reports it is busy (an earlier attempt is still pending), the integration waits about 40 s and retries by itself.
* Pairing as an additional app does **not** remove existing pairings in principle (the rope supports several users, one connected at a time), but this has not been verified with every phone/app combination.
* Treat the stored credentials like a password: anyone holding them can talk to your rope.

### Reusing an existing Mi Fitness pairing (optional)

Choose **Enter existing credentials** to reuse a pairing made by the Mi Fitness app
(China build, `com.mi.health`). It keeps them in
`/data/data/com.mi.health/databases/eco_local_device_db` (rooted phone needed):

```
adb shell su -c "cp /data/data/com.mi.health/databases/eco_local_device_db /sdcard/"
adb pull /sdcard/eco_local_device_db
python tools/extract_credentials.py eco_local_device_db
```

You can also pair from a computer with `python tools/pair.py` (needs `bleak`), which writes
`credentials.json` (keep it private).

## Development

```
pip install bleak cryptography pytest
pytest tests
python tools/read_once.py AA:BB:CC:DD:EE:FF <app_device_id> <token>   # real rope, read-only
```

## Disclaimer

Not affiliated with Xiaomi. Use at your own risk.
