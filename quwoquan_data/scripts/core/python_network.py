"""Probe external network and Cursor Cloud API readiness without leaking credentials."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Iterable
from urllib import error as urlerror
from urllib import request as urlrequest

from core.python_environment import (
    DEFAULT_NETWORK_ENDPOINTS,
    NETWORK_SKIP_ENV,
)


def _probe_endpoint(url: str, *, timeout_seconds: float) -> dict:
    row = {"url": url, "reachable": False, "status": None, "error": "", "method": ""}
    last_error = ""
    for method in ("HEAD", "GET"):
        request = urlrequest.Request(
            url,
            method=method,
            headers={"User-Agent": "quwoquan-data-env-preflight"},
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                row["status"] = int(getattr(response, "status", 0) or 0)
                row["reachable"] = True
                row["method"] = method
                row["error"] = ""
                return row
        except urlerror.HTTPError as exc:
            row["status"] = int(exc.code)
            row["method"] = method
            # 401/403/404/405 still prove DNS/TLS/routing reached the service.
            row["reachable"] = exc.code < 500
            row["error"] = "" if row["reachable"] else str(exc)
            if row["reachable"]:
                return row
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            # Some endpoints close TLS/HTTP2 HEAD probes but accept GET. Retry
            # with GET before declaring the network unavailable.
            if method == "HEAD":
                continue
            row["method"] = method
            row["error"] = last_error
    curl_row = _probe_endpoint_with_curl(url, timeout_seconds=timeout_seconds)
    if curl_row["reachable"]:
        return curl_row
    if not row["error"]:
        row["error"] = curl_row.get("error") or last_error
    return row


def _probe_endpoint_with_curl(url: str, *, timeout_seconds: float) -> dict:
    row = {"url": url, "reachable": False, "status": None, "error": "", "method": "curl"}
    curl = shutil.which("curl")
    if not curl:
        row["error"] = "curl not found"
        return row
    proc = subprocess.run(
        [
            curl,
            "-I",
            "-L",
            "--retry",
            "1",
            "--retry-delay",
            "1",
            "--retry-all-errors",
            "--max-time",
            str(max(1, int(timeout_seconds))),
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    code_text = (proc.stdout or "").strip()
    try:
        status = int(code_text)
    except ValueError:
        status = 0
    row["status"] = status or None
    if proc.returncode == 0 and status and status < 500:
        row["reachable"] = True
        return row
    row["error"] = (proc.stderr or "").strip() or f"curl status={status or 'unknown'}"
    return row


def check_network_endpoints(
    endpoints: Iterable[str] | None = None,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    """Probe Cursor and source-network reachability without exposing credentials."""
    if timeout_seconds is None:
        timeout_seconds = 5.0
    configured = os.environ.get("QWQ_ENV_NETWORK_ENDPOINTS")
    if endpoints is None and configured:
        endpoints = [part.strip() for part in configured.split(",") if part.strip()]
    urls = list(endpoints or DEFAULT_NETWORK_ENDPOINTS)
    if os.environ.get(NETWORK_SKIP_ENV) == "1":
        return {
            "checked": False,
            "skipped": True,
            "skipReason": f"{NETWORK_SKIP_ENV}=1",
            "ready": True,
            "endpoints": [{"url": url, "reachable": None, "status": None, "error": ""} for url in urls],
            "issues": [],
        }
    rows = [_probe_endpoint(url, timeout_seconds=timeout_seconds) for url in urls]
    issues = [
        f"network endpoint unreachable: {row['url']}: {row.get('error') or row.get('status') or 'unknown'}"
        for row in rows
        if not row.get("reachable")
    ]
    return {
        "checked": True,
        "skipped": False,
        "ready": not issues,
        "endpoints": rows,
        "issues": issues,
    }
