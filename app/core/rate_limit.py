"""Simple in-memory sliding-window rate limiter.

State lives in process memory, so limits apply per worker process. That is an
accepted trade-off to avoid an extra dependency (e.g. Redis) for login throttling.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable


class SlidingWindowRateLimiter:
    """Track timestamped events per key and report whether a key is over its limit."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window_seconds: float) -> deque[float]:
        events = self._events[key]
        cutoff = self._clock() - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._events.pop(key, None)
        return events

    def record(self, key: str, window_seconds: float) -> None:
        """Record one event for ``key``."""
        with self._lock:
            self._prune(key, window_seconds)
            self._events[key].append(self._clock())

    def is_limited(self, key: str, max_attempts: int, window_seconds: float) -> bool:
        """Return True if ``key`` has at least ``max_attempts`` events in the window."""
        with self._lock:
            return len(self._prune(key, window_seconds)) >= max_attempts

    def retry_after(self, key: str, window_seconds: float) -> int:
        """Seconds until the oldest event in the window expires (minimum 1)."""
        with self._lock:
            events = self._prune(key, window_seconds)
            if not events:
                return 1
            return max(1, int(events[0] + window_seconds - self._clock()) + 1)

    def clear(self, key: str) -> None:
        """Forget all events for ``key``."""
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        """Forget everything (used by tests)."""
        with self._lock:
            self._events.clear()


login_rate_limiter = SlidingWindowRateLimiter()
