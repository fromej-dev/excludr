"""In-process registry of articles currently queued for, or being screened by, the AI.

Keys are ``(project_id, article_id, stage)``. ``POST .../screening/run-ai`` claims the
keys of the articles it schedules and releases them when the batch flow finishes or
fails, so overlapping requests (the screening view's lookahead and manual batches)
never screen the same article twice at the same time.

The registry lives in process memory, guarded by a ``threading.Lock``. That is
enough for the current single-process deployment (one uvicorn worker running the
flows in-process). With several API workers or remote flow runners each process
would have its own set, and duplicates across processes would no longer be caught;
a shared store (e.g. a database row or Redis set) would then be needed.
"""

import threading
import time
from collections.abc import Iterable

InFlightKey = tuple[int, int, str]

# Safety net: a claim whose release was somehow lost (e.g. the background task never
# ran because the response could not be sent) expires instead of blocking forever.
CLAIM_TTL_SECONDS = 6 * 60 * 60

_lock = threading.Lock()
_in_flight: dict[InFlightKey, float] = {}


def _alive(key: InFlightKey, now: float) -> bool:
    claimed_at = _in_flight.get(key)
    return claimed_at is not None and now - claimed_at < CLAIM_TTL_SECONDS


def claim(keys: Iterable[InFlightKey]) -> list[InFlightKey]:
    """Atomically mark keys as in flight; return only those that were not already."""
    claimed: list[InFlightKey] = []
    now = time.monotonic()
    with _lock:
        for key in keys:
            if not _alive(key, now):
                _in_flight[key] = now
                claimed.append(key)
    return claimed


def release(keys: Iterable[InFlightKey]) -> None:
    """Forget keys (missing keys are ignored)."""
    with _lock:
        for key in keys:
            _in_flight.pop(key, None)


def is_in_flight(key: InFlightKey) -> bool:
    with _lock:
        return _alive(key, time.monotonic())


def clear() -> None:
    """Drop every entry (tests)."""
    with _lock:
        _in_flight.clear()
