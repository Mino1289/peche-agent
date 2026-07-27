"""Rate-limiter Gemini / Gemma (req/min et req/jour)."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock


def _rpm_limit(model: str) -> int:
    if "gemma" in model.lower():
        return int(os.environ.get("GEMMA_RPM_LIMIT", "14"))
    return int(os.environ.get("GEMINI_RPM_LIMIT", "14"))


@dataclass
class RateLimiter:
    """Compteurs glissants par modèle."""

    _minute: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: Lock = field(default_factory=Lock)

    def acquire(self, model: str, *, timeout: float = 30.0) -> bool:
        limit = _rpm_limit(model)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                now = time.monotonic()
                q = self._minute[model]
                while q and now - q[0] > 60.0:
                    q.popleft()
                if len(q) < limit:
                    q.append(now)
                    return True
            time.sleep(0.5)
        return False


_limiter = RateLimiter()


def wait_for_model(model: str) -> bool:
    return _limiter.acquire(model)
