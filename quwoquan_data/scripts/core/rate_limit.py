"""Share outbound request pacing between every caller that talks to one host.

Politeness is a property of the host being called, not of the code path calling
it: two callers that pace themselves independently still hit the host at the sum
of their rates. So limiters are keyed and shared here rather than owned by any
one crawl module, and this module stays free of network dependencies so both the
HTTP layer and the crawl layer can reach it without a cycle.
"""

from __future__ import annotations

import threading
import time


_RATE_LIMITERS_LOCK = threading.Lock()
_RATE_LIMITERS: dict[tuple[str, str], "SiteRateLimiter"] = {}


class SiteRateLimiter:
    def __init__(
        self,
        max_requests_per_second: float,
        *,
        crawl_delay: float = 0.0,
    ) -> None:
        declared_interval = (
            1.0 / max_requests_per_second if max_requests_per_second > 0 else 0.0
        )
        self._interval = max(declared_interval, max(0.0, crawl_delay))
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                remaining = self._interval - (now - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
                    now = time.monotonic()
            self._last_request_at = now

    def strengthen(
        self,
        max_requests_per_second: float,
        *,
        crawl_delay: float,
    ) -> None:
        declared_interval = (
            1.0 / max_requests_per_second if max_requests_per_second > 0 else 0.0
        )
        with self._lock:
            self._interval = max(
                self._interval,
                declared_interval,
                max(0.0, crawl_delay),
            )


def shared_rate_limiter(
    site_id: str,
    origin: str,
    *,
    max_requests_per_second: float,
    crawl_delay: float,
) -> SiteRateLimiter:
    key = (site_id, origin)
    with _RATE_LIMITERS_LOCK:
        limiter = _RATE_LIMITERS.get(key)
        if limiter is None:
            limiter = SiteRateLimiter(
                max_requests_per_second,
                crawl_delay=crawl_delay,
            )
            _RATE_LIMITERS[key] = limiter
        else:
            limiter.strengthen(
                max_requests_per_second,
                crawl_delay=crawl_delay,
            )
        return limiter


__all__ = [
    "SiteRateLimiter",
    "shared_rate_limiter",
]
