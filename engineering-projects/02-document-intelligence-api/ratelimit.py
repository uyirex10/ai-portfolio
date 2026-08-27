"""Per-client rate limiting.

The point here is cost control before it is abuse control. Every accepted request makes
at least two model calls, so an unbounded caller is a billing incident, not just a load
problem. A sliding window is used rather than a fixed one because a fixed window lets a
caller fire the full quota at 11:59:59 and again at 12:00:00 - double the intended rate
at exactly the moment the limit is supposed to bind.

In-process and in-memory, which is a real limitation and stated as one: the counters
live in this worker, so they reset on restart and are not shared between replicas.
Deployed as a single Render web service that is accurate. Scale past one instance and
this needs to move to Redis - until then, more instances silently multiply the limit.
"""

import collections
import os
import threading
import time


def _limit() -> int:
    try:
        return int(os.environ.get("DOCINTEL_RATE_LIMIT_PER_MINUTE", "10"))
    except ValueError:
        return 10


WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding-window request counter, keyed by client name."""

    def __init__(self, limit: int | None = None, window: int = WINDOW_SECONDS):
        self._limit = limit
        self._window = window
        self._hits: dict[str, collections.deque[float]] = collections.defaultdict(
            collections.deque
        )
        # FastAPI runs sync endpoints in a threadpool, so two requests for the same
        # client genuinely race here.
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit if self._limit is not None else _limit()

    def check(self, client: str, now: float | None = None) -> tuple[bool, int]:
        """Record an attempt. Returns (allowed, retry_after_seconds).

        A rejected request is not recorded. Counting rejections would extend the
        lockout every time a client retried, which turns a rate limit into a ban.
        """
        now = time.monotonic() if now is None else now
        limit = self.limit
        with self._lock:
            hits = self._hits[client]
            cutoff = now - self._window
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                retry_after = max(1, int(hits[0] + self._window - now) + 1)
                return False, retry_after

            hits.append(now)
            return True, 0

    def remaining(self, client: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[client]
            cutoff = now - self._window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            return max(0, self.limit - len(hits))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# One limiter for the process, shared by every request.
limiter = RateLimiter()
