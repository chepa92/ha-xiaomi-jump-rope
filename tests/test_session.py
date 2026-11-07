"""Offline tests for session detection and daily totals."""
import importlib.util
import pathlib
import sys

SPEC = importlib.util.spec_from_file_location(
    "session",
    pathlib.Path(__file__).parent.parent / "custom_components" / "xiaomi_jump_rope" / "session.py",
)
session = importlib.util.module_from_spec(SPEC)
sys.modules["session"] = session
SPEC.loader.exec_module(session)

T0 = 1_800_000_000


def feed(tr, jumps, mono, cal=0, dur=0):
    return tr.update(jumps, cal, dur, mono, T0 + int(mono))


def test_stale_value_does_not_open_a_session():
    tr = session.SessionTracker()
    feed(tr, 88, 0)  # first reading after HA start: leftover from earlier
    feed(tr, 88, 60)
    assert not tr.active


def test_session_opens_on_change_and_ends_on_timeout():
    tr = session.SessionTracker(timeout=180)
    feed(tr, 0, 0)
    feed(tr, 12, 20, cal=2, dur=20)
    assert tr.active
    feed(tr, 40, 40, cal=7, dur=40)
    feed(tr, 40, 100, cal=7, dur=100)
    assert tr.check_timeout(100 + 100, T0 + 200) is None  # only 60 s since last change
    done = tr.check_timeout(40 + 181, T0 + 221)
    assert done is not None
    assert (done.jumps, done.calories) == (40, 7)
    assert done.start_time == T0 + 20 - 20
    assert done.end_time == T0 + 40
    assert not tr.active


def test_reset_to_lower_count_finishes_previous_session():
    tr = session.SessionTracker()
    feed(tr, 0, 0)
    feed(tr, 30, 20, dur=20)
    finished = feed(tr, 3, 60, dur=3)
    assert len(finished) == 1 and finished[0].jumps == 30
    assert tr.active and tr.session.jumps == 3


def test_tiny_sessions_are_ignored():
    tr = session.SessionTracker(min_jumps=5)
    feed(tr, 0, 0)
    feed(tr, 2, 10)
    assert tr.check_timeout(10 + 200, T0 + 210) is None


def test_day_totals_accumulate_and_roll_over():
    day = session.DayTotals()
    f1 = session.FinishedSession(1, 2, 30, 6, 100)
    f2 = session.FinishedSession(3, 4, 50, 9, 200)
    day.add("2026-11-07", f1)
    day.add("2026-11-07", f2)
    assert (day.jumps, day.calories, day.duration, day.sessions) == (80, 15, 300, 2)
    day.roll("2026-11-08")
    assert (day.jumps, day.sessions) == (0, 0)
    assert day.last["jumps"] == 50
    assert session.DayTotals.from_dict(day.to_dict()).last == day.last
