import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, maximum: int | None, period_seconds: float = 60.0) -> None:
        self.maximum = maximum
        self.period_seconds = period_seconds
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                if self.maximum is None:
                    return
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.period_seconds:
                    self._calls.popleft()
                if len(self._calls) < self.maximum:
                    self._calls.append(now)
                    return
                wait = self.period_seconds - (now - self._calls[0])
            time.sleep(max(wait, 0.01))

    def update_maximum(self, maximum: int | None) -> None:
        if maximum is None or maximum < 1:
            return
        with self._lock:
            self.maximum = maximum
