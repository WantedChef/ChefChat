from __future__ import annotations

from collections import deque
import time


class RateLimiter:
    """Simple per-user rolling window rate limiter."""

    def __init__(self, window_s: float, max_events: int) -> None:
        self.window_s = window_s
        self.max_events = max_events
        self._events: dict[str, deque[float]] = {}

    def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        q = self._events.setdefault(user_id, deque())

        while q and (now - q[0]) > self.window_s:
            q.popleft()

        if len(q) >= self.max_events:
            return False

        q.append(now)
        return True
