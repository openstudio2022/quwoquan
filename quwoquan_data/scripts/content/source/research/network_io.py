"""Network IO for public-source research providers."""
from __future__ import annotations

import json
import subprocess
import urllib.parse
from typing import Any

from core.runtime_policy import active_runtime_policy
from content.source.research import network_breaker


_USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
_RUNTIME_POLICY = active_runtime_policy()
_CURL_RETRIES = _RUNTIME_POLICY.curl_retries
_CURL_RETRY_DELAY_SECONDS = _RUNTIME_POLICY.curl_retry_delay_seconds


def curl_raw(url: str, *, timeout: int) -> tuple[int, bytes]:
    if network_breaker.BREAKER.is_open(url) or network_breaker.wave_budget_exceeded():
        return -1, b""
    effective_timeout = max(1, int(timeout))
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-L",
            "-A",
            _USER_AGENT,
            "--retry",
            str(max(1, int(_CURL_RETRIES))),
            "--retry-delay",
            str(_CURL_RETRY_DELAY_SECONDS),
            "--retry-all-errors",
            "--max-time",
            str(effective_timeout),
            url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        network_breaker.BREAKER.record_success(url)
    elif proc.returncode in network_breaker.NETWORK_CURL_EXIT_CODES:
        network_breaker.BREAKER.record_network_failure(url)
    stdout = (
        proc.stdout
        if isinstance(proc.stdout, bytes)
        else bytes(str(proc.stdout or ""), "utf-8")
    )
    return proc.returncode, stdout


def curl_json(url: str, *, timeout: int) -> dict[str, Any]:
    returncode, stdout = curl_raw(url, timeout=timeout)
    if returncode != 0:
        return {}
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def curl_text(url: str, *, timeout: int) -> str:
    returncode, stdout = curl_raw(url, timeout=timeout)
    if returncode != 0:
        return ""
    return stdout.decode("utf-8", errors="replace")


def wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return curl_json(
        f"https://{host}/w/api.php?{query}",
        timeout=_RUNTIME_POLICY.provider_timeouts.mediawiki_seconds,
    )
