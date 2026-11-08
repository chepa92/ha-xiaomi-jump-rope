# Xiaomi / Mijia Smart Jump Rope (XMSR-P803) for Home Assistant

Reads **jumps, calories and duration** straight from the rope over Bluetooth LE, downloads
the **workouts stored on the rope**, and can hand each finished workout to Garmin Connect.
No Mi Fitness app, no phone and no cloud needed.

> Unofficial. The Xiaomi "eco" protocol is undocumented; this integration was
> reverse-engineered from the rope's own traffic. Tested only with the
> China-region **XMSR-P803** (`yunmai.jmprope.sr803`). Early release: expect rough edges.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/chepa92/ha-xiaomi-jump-rope`, category **Integration**.
2. Install **Xiaomi Smart Jump Rope** and restart Home Assistant.
3. Wake the rope (jump or press its button). It is **auto-discovered** under **Settings → Devices & services**, or use **Add integration → Xiaomi Smart Jump Rope** while the rope is awake.
4. Choose **Pair now** and press the rope's **Power button once** when asked (see [Pairing](#pairing)).

There are no GitHub releases yet, so HACS installs the latest commit.

## Entities

| Entity | Meaning |
|---|---|
| Jumps / Calories / Duration | counters of the current (or last) session |
| Jumps today / Calories today / Duration today / Sessions today | totals of finished sessions today plus the running one (reset at midnight, survive restarts) |
| Last session jumps | jumps of the last finished session seen live |
| Workout active | on while a session is in progress |
| Stored workouts *(diagnostic)* | number of records downloaded from the rope and kept in the records file |
| Journal entries *(diagnostic)* | number of workouts in the journal file |
| Last read *(diagnostic)* | when Home Assistant last got data from the rope |

### Buttons

| Button | What it does |
|---|---|
| **Connect now** | Connects immediately, reads the live counters and downloads stored workouts. The rope must be awake. |
| **Resend stored workouts** | Fires the session event again for every stored workout. Garmin Sync skips ones it already uploaded, so it is safe to press. |
| **Clear journal** | Clears the journal and the stored records (a `.bak` copy of each file is kept). Garmin Sync is not affected. |

## How it works

The rope only advertises while it is awake (jumping or a button press). Home Assistant finds it
**by its Bluetooth name** (`Mijia Smart Jump Rope ...`), so no MAC address is needed. When the
rope is around, Home Assistant connects, authenticates, reads the live status and disconnects:

* about **once a minute** when idle (a check runs every 20 s, reads are rate-limited),
* every ~20 s while a workout is running,
* with back-off after failed attempts.

Values stay on screen while the rope sleeps. The **last few seconds of a workout may be missed**
if the rope falls asleep between reads (the finished workout is still picked up from the rope later).

## Stored workouts

The rope keeps up to 90 finished workouts. Home Assistant downloads them when it connects
(at setup, after a workout, every 30 minutes, and on **Connect now**). The rope serves one record at a
time: each record is **saved to disk first and only then confirmed**, which frees it on the rope and makes
it send the next one. A workout that is already stored (same start time) is never saved or announced twice.

Decoded per workout: start, end, elapsed time (pauses included), **jumps**, **calories**, and
average / maximum frequency (jumps per minute). The decoding was checked against the live counters of
three workouts.

### Files (in the Home Assistant config folder)

* `xiaomi_jump_rope_journal_<MAC>.json`: one entry per finished workout (date, time, start/end, jumps, calories, duration), no duplicates.
* `xiaomi_jump_rope_records_<MAC>.json`: every record downloaded from the rope (decoded fields plus the raw bytes).

## The `xiaomi_jump_rope_session_completed` event

The **sensors** follow the live counters; a live session is considered finished when the jump count stops
changing for 3 minutes. The **event** is fired once per workout *stored on the rope*, so it carries exact numbers:

```yaml
event_type: xiaomi_jump_rope_session_completed
data:
  jumps: 120
  calories: 14
  duration: 305            # seconds, start to end
  start_time: 1794085827   # unix time
  end_time: 1794086132
```

### Sending workouts to Garmin Connect

[ha-garmin-sync](https://github.com/chepa92/ha-garmin-sync) (**1.3.0 or newer**) turns each workout into a
Garmin **Jump Rope** activity: one per workout, not one per jump, with start time, duration, calories and the
jump count in the title. Enable *Sync Jump Rope sessions to Garmin* in its options. To upload workouts that
are already stored, press **Resend stored workouts** once; already-uploaded workouts are skipped.

## Pairing

**No phone and no rooting needed.** When you add the integration, choose **Pair now**, then press the
**Power button on the end of the rope's handle once** when Home Assistant asks. The integration pairs with the
rope itself (as its own "app") and stores the credentials in the config entry.

* If the rope reports it is busy (an earlier attempt is still pending), the integration waits about 40 s and retries by itself.
* The rope supports several users (one connected at a time), so pairing as an additional app does not appear to remove existing pairings, but this has not been verified with every phone/app combination.
* Treat the stored credentials like a password: anyone holding them can talk to your rope.

### Reusing an existing Mi Fitness pairing (optional)

Choose **Enter existing credentials** to reuse a pairing made by the Mi Fitness app (China build,
`com.mi.health`). It keeps them in `/data/data/com.mi.health/databases/eco_local_device_db` (rooted phone needed):

```
adb shell su -c "cp /data/data/com.mi.health/databases/eco_local_device_db /sdcard/"
adb pull /sdcard/eco_local_device_db
python tools/extract_credentials.py eco_local_device_db
```

You can also pair from a computer with `python tools/pair.py` (needs `bleak`), which writes
`credentials.json` (keep it private).

## Important limits

* The rope must be **awake and in range** of a Home Assistant Bluetooth adapter or proxy. Pairing needs one button press; normal reading does not.
* Only one device can talk to the rope at a time. Close Mi Fitness on your phone (or turn its Bluetooth off) while you want Home Assistant to read.
* **Workouts are moved, not copied:** once Home Assistant has saved a workout it is confirmed and freed on the rope, so the phone app will no longer see it. Likewise, leaving training in the Mi Fitness app resets the data on the rope.
* Besides reading, the integration does two things on the rope: it **confirms downloaded workouts** (freeing them) and **sets the rope's clock** when it downloads history.
* Elapsed time includes pauses; the rope's separate "active time" figure is not decoded yet.
* If the rope is re-paired in another app with the same app ID, the token changes: remove and re-add the rope here.

## Development

```
pip install bleak cryptography pytest
pytest tests
python tools/read_once.py <app_device_id> <token>   # real rope, wakes it by name, read-only
```

## Disclaimer

Not affiliated with Xiaomi. Use at your own risk.
