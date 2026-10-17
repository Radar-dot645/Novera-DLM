"""Global bandwidth limiter shared by all download threads."""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, bytes_per_second: int = 0):
        self.rate = max(0, int(bytes_per_second))
        self._lock = threading.Lock()
        self._next = time.monotonic()

    def set_rate(self, bytes_per_second: int) -> None:
        with self._lock:
            self.rate = max(0, int(bytes_per_second))

    def throttle(self, nbytes: int) -> None:
        if self.rate <= 0:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + nbytes / self.rate
            delay = start - now
        if delay > 0:
            time.sleep(min(delay, 5.0))


GLOBAL = RateLimiter(0)
