"""Progress math and Rich reporter. Never invents a percentage."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


def percent(done: int, total: int | None) -> float | None:
    """percentage = done_bytes / total_bytes * 100 (None if total unknown/zero)."""
    if not total or total <= 0:
        return None
    return max(0.0, min(100.0, done / total * 100))


def speed(delta_bytes: int, delta_seconds: float) -> float | None:
    """speed = delta_bytes / delta_time (None if no measurable interval)."""
    if delta_seconds <= 0 or delta_bytes < 0:
        return None
    return delta_bytes / delta_seconds


def eta(done: int, total: int | None, rate: float | None) -> float | None:
    """ETA = remaining_bytes / speed (None unless total known and rate > 0)."""
    if not total or not rate or rate <= 0:
        return None
    return max(0.0, (total - done) / rate)


def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return "?"


def fmt_eta(seconds: float | None) -> str:
    if seconds is None:
        return "ETA --"
    s = int(seconds)
    return f"ETA {s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"ETA {s // 60:02d}:{s % 60:02d}"


@dataclass
class RateMeter:
    """Smoothed speed from sampled (bytes, time) deltas."""
    window: float = 1.0
    _t: float = field(default_factory=time.monotonic)
    _b: int = 0
    rate: float | None = None

    def update(self, done: int, now: float | None = None) -> float | None:
        now = time.monotonic() if now is None else now
        dt = now - self._t
        if dt >= self.window:
            r = speed(done - self._b, dt)
            if r is not None:
                self.rate = r if self.rate is None else 0.5 * self.rate + 0.5 * r
            self._t, self._b = now, done
        return self.rate


class Reporter:
    """Callable (done,total) -> updates one Rich task with measured percent/speed/ETA."""

    def __init__(self, progress, description: str):
        self.progress = progress
        self.meter = RateMeter()
        self.task = progress.add_task(description, total=None, speed="", eta="")

    def __call__(self, done: int, total: int | None) -> None:
        rate = self.meter.update(done)
        self.progress.update(self.task, completed=done, total=total,
                             speed=f"{fmt_bytes(rate)}/s" if rate else "",
                             eta=fmt_eta(eta(done, total, rate)) if total else "")
