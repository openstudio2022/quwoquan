"""Bounded read-only GitHub Actions API access."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any


ApiStats = dict[str, int | None]


class GithubActionsApiError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        request_count: int,
        retry_count: int,
        last_http_status: int | None = None,
        rate_limit_remaining: int | None = None,
        rate_limit_reset_epoch: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.request_count = request_count
        self.retry_count = retry_count
        self.last_http_status = last_http_status
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_reset_epoch = rate_limit_reset_epoch

    def diagnostic(self) -> ApiStats:
        return {
            "requestCount": self.request_count,
            "retryCount": self.retry_count,
            "lastHttpStatus": self.last_http_status,
            "rateLimitRemaining": self.rate_limit_remaining,
            "rateLimitResetEpoch": self.rate_limit_reset_epoch,
        }


def parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"authoritative timestamp is missing: {label}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _remaining_seconds(deadline: datetime | None, now: Callable[[], datetime]) -> float:
    if deadline is None:
        return 30.0
    return max(0.0, (deadline - now()).total_seconds())


def _retry_delay(error: urllib.error.HTTPError, now: Callable[[], datetime]) -> float:
    retry_after = error.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return float(retry_after)
    reset = error.headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        return max(0.0, float(reset) - now().timestamp())
    return 2.0


def request_json(
    url: str,
    token: str,
    *,
    deadline: datetime | None = None,
    max_attempts: int = 5,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, dict[str, int | None]]:
    request_count = 0
    retry_count = 0
    last_http_status: int | None = None
    while True:
        remaining = _remaining_seconds(deadline, now)
        if remaining <= 0:
            raise GithubActionsApiError(
                "AUTHORITY_DEADLINE_EXCEEDED",
                request_count=request_count,
                retry_count=retry_count,
                last_http_status=last_http_status,
            )
        if request_count >= max_attempts:
            raise GithubActionsApiError(
                "AUTHORITY_RETRY_EXHAUSTED",
                request_count=request_count,
                retry_count=retry_count,
                last_http_status=last_http_status,
            )
        request_count += 1
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=min(30.0, remaining)) as response:
                last_http_status = int(response.status)
                remaining_header = response.headers.get("X-RateLimit-Remaining")
                reset_header = response.headers.get("X-RateLimit-Reset")
                return json.load(response), {
                    "requestCount": request_count,
                    "retryCount": retry_count,
                    "lastHttpStatus": last_http_status,
                    "rateLimitRemaining": (
                        int(remaining_header)
                        if remaining_header and remaining_header.isdigit()
                        else None
                    ),
                    "rateLimitResetEpoch": (
                        int(reset_header)
                        if reset_header and reset_header.isdigit()
                        else None
                    ),
                }
        except urllib.error.HTTPError as error:
            last_http_status = error.code
            rate_limited = error.code == 429 or (
                error.code == 403
                and error.headers.get("X-RateLimit-Remaining") == "0"
            )
            retryable = rate_limited or error.code >= 500
            if not retryable:
                raise GithubActionsApiError(
                    "AUTHORITY_HTTP_REJECTED",
                    request_count=request_count,
                    retry_count=retry_count,
                    last_http_status=last_http_status,
                ) from error
            delay = min(_retry_delay(error, now), _remaining_seconds(deadline, now))
        except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as error:
            delay = min(2.0, _remaining_seconds(deadline, now))
            if delay <= 0:
                raise GithubActionsApiError(
                    "AUTHORITY_UNAVAILABLE",
                    request_count=request_count,
                    retry_count=retry_count,
                    last_http_status=last_http_status,
                ) from error
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise GithubActionsApiError(
                "AUTHORITY_RESPONSE_INVALID",
                request_count=request_count,
                retry_count=retry_count,
                last_http_status=last_http_status,
            ) from error
        retry_count += 1
        if delay > 0:
            sleep(delay)


def load_paginated_items(
    base_url: str,
    token: str,
    *,
    key: str,
    query: dict[str, str] | None = None,
    deadline: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    items: list[dict[str, Any]] = []
    request_count = 0
    retry_count = 0
    last_http_status: int | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset_epoch: int | None = None
    page = 1
    while True:
        encoded = urllib.parse.urlencode({**(query or {}), "per_page": "100", "page": str(page)})
        payload, stats = request_json(
            f"{base_url}?{encoded}",
            token,
            deadline=deadline,
        )
        request_count += int(stats["requestCount"] or 0)
        retry_count += int(stats["retryCount"] or 0)
        last_http_status = stats["lastHttpStatus"]
        rate_limit_remaining = stats.get("rateLimitRemaining")
        rate_limit_reset_epoch = stats.get("rateLimitResetEpoch")
        batch = payload.get(key) if isinstance(payload, dict) else None
        if not isinstance(batch, list):
            raise GithubActionsApiError(
                "AUTHORITY_RESPONSE_INVALID",
                request_count=request_count,
                retry_count=retry_count,
                last_http_status=last_http_status,
            )
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return items, {
                "requestCount": request_count,
                "retryCount": retry_count,
                "lastHttpStatus": last_http_status,
                "rateLimitRemaining": rate_limit_remaining,
                "rateLimitResetEpoch": rate_limit_reset_epoch,
            }
        page += 1


def load_run_and_jobs(
    repository: str,
    run_id: str,
    token: str,
    *,
    deadline: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], ApiStats]:
    run_url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    run, run_stats = request_json(run_url, token, deadline=deadline)
    if not isinstance(run, dict):
        raise GithubActionsApiError(
            "AUTHORITY_RESPONSE_INVALID",
            request_count=1,
            retry_count=0,
        )
    jobs, job_stats = load_paginated_items(
        f"{run_url}/jobs",
        token,
        key="jobs",
        query={"filter": "latest"},
        deadline=deadline,
    )
    return run, jobs, {
        "requestCount": int(run_stats["requestCount"] or 0)
        + int(job_stats["requestCount"] or 0),
        "retryCount": int(run_stats["retryCount"] or 0)
        + int(job_stats["retryCount"] or 0),
        "lastHttpStatus": job_stats["lastHttpStatus"],
        "rateLimitRemaining": job_stats.get("rateLimitRemaining"),
        "rateLimitResetEpoch": job_stats.get("rateLimitResetEpoch"),
    }
