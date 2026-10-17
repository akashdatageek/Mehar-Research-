"""Minimum-interval rate limiter with injectable clock (tests use a fake clock)."""

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Blocks so consecutive `wait()` returns are at least `min_interval` seconds apart."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            if self._last is not None:
                remaining = self._last + self.min_interval - now
                if remaining > 0:
                    self.sleep(remaining)
                    now = self.clock()
            self._last = now
