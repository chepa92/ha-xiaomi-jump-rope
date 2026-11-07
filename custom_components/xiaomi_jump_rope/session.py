"""Workout session detection and daily totals (pure Python, no Home Assistant).

The rope only reports counters of its *current* session; it has no notion of
"finished".  We infer the end of a session when

* the jump count has not changed for ``timeout`` seconds, or
* the count went *down* (the rope started a new session / was reset).

A session only opens once the count is seen **changing**, so a stale value left
on the rope from an earlier workout is never mistaken for a new session.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SESSION_TIMEOUT = 180  # seconds without a change that end a session
MIN_SESSION_JUMPS = 5  # shorter sessions are ignored (noise / accidental swing)


@dataclass
class Session:
    """A workout in progress."""

    start_time: int  # unix seconds
    jumps: int
    calories: int
    duration: int
    last_change: float  # monotonic
    last_change_wall: int  # unix seconds


@dataclass
class FinishedSession:
    """A completed workout."""

    start_time: int
    end_time: int
    jumps: int
    calories: int
    duration: int


class SessionTracker:
    """Turn a stream of counter readings into finished sessions."""

    def __init__(
        self, timeout: float = SESSION_TIMEOUT, min_jumps: int = MIN_SESSION_JUMPS
    ) -> None:
        self.timeout = timeout
        self.min_jumps = min_jumps
        self.session: Session | None = None
        self._prev_jumps: int | None = None

    @property
    def active(self) -> bool:
        return self.session is not None

    def update(
        self, jumps: int, calories: int, duration: int, mono: float, wall: int
    ) -> list[FinishedSession]:
        """Feed one reading; returns sessions that finished because of it."""
        finished: list[FinishedSession] = []
        s = self.session

        if s is not None and jumps < s.jumps:
            # The rope restarted its counters: the previous session is over.
            done = self._finish(s)
            if done:
                finished.append(done)
            s = self.session = None

        if s is None:
            changed = self._prev_jumps is not None and jumps != self._prev_jumps
            if changed and jumps > 0:
                self.session = Session(
                    start_time=wall - max(duration, 0),
                    jumps=jumps,
                    calories=calories,
                    duration=duration,
                    last_change=mono,
                    last_change_wall=wall,
                )
        else:
            if jumps != s.jumps:
                s.last_change = mono
                s.last_change_wall = wall
            s.jumps, s.calories, s.duration = jumps, calories, duration

        self._prev_jumps = jumps
        return finished

    def check_timeout(self, mono: float, wall: int) -> FinishedSession | None:
        """Finish the open session if nothing changed for ``timeout`` seconds."""
        s = self.session
        if s is None or mono - s.last_change < self.timeout:
            return None
        self.session = None
        return self._finish(s)

    def _finish(self, s: Session) -> FinishedSession | None:
        if s.jumps < self.min_jumps:
            return None
        return FinishedSession(
            start_time=s.start_time,
            end_time=s.last_change_wall,
            jumps=s.jumps,
            calories=s.calories,
            duration=s.duration,
        )


@dataclass
class DayTotals:
    """Sum of finished sessions for one local calendar day."""

    date: str = ""
    jumps: int = 0
    calories: int = 0
    duration: int = 0
    sessions: int = 0
    last: dict = field(default_factory=dict)  # most recent finished session

    def roll(self, today: str) -> None:
        """Reset the counters when the day changed (keeps ``last``)."""
        if self.date != today:
            self.date, self.jumps, self.calories, self.duration, self.sessions = today, 0, 0, 0, 0

    def add(self, today: str, f: FinishedSession) -> None:
        self.roll(today)
        self.jumps += f.jumps
        self.calories += f.calories
        self.duration += f.duration
        self.sessions += 1
        self.last = {
            "jumps": f.jumps,
            "calories": f.calories,
            "duration": f.duration,
            "start_time": f.start_time,
            "end_time": f.end_time,
        }

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "jumps": self.jumps,
            "calories": self.calories,
            "duration": self.duration,
            "sessions": self.sessions,
            "last": self.last,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "DayTotals":
        d = d or {}
        return cls(
            date=str(d.get("date", "")),
            jumps=int(d.get("jumps", 0)),
            calories=int(d.get("calories", 0)),
            duration=int(d.get("duration", 0)),
            sessions=int(d.get("sessions", 0)),
            last=dict(d.get("last", {})),
        )
