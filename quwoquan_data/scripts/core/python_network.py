"""Probe external network and Cursor Cloud API readiness without leaking credentials."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Iterable, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

from core.python_environment import (
    CURSOR_CLOUD_API_ME_URL,
    DEFAULT_NETWORK_ENDPOINTS,
    NETWORK_SKIP_ENV,
    _redact_secret_text,
    _redact_secret_value,
)

def _cursor_key_report(value: str | None) -> dict:
    key = str(value or "").strip()
    if not key:
        return {"present": False, "format": "missing", "valid": False}
    valid = key.startswith("crsr_") and len(key) >= 24
    return {
        "present": True,
        "format": "cursor_api_key" if valid else "invalid",
        "valid": valid,
        "redacted": "<present>",
    }


def _parse_json_bytes(payload: bytes) -> dict:
    try:
        decoded = payload.decode("utf-8")
    except Exception:  # noqa: BLE001
        return {}
    try:
        parsed = json.loads(decoded or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cursor_cloud_api_key_type(payload: Mapping[str, object]) -> str:
    if payload.get("userId") or payload.get("userEmail"):
        return "user_api_key"
    if payload.get("apiKeyName"):
        return "service_account_api_key"
    return "unknown"


def _cursor_cloud_api_result(
    *,
    status: int | None,
    payload: Mapping[str, object] | None = None,
    fallback_message: str = "",
) -> dict:
    body = payload if isinstance(payload, Mapping) else {}
    if status == 200:
        return {
            "checked": True,
            "ready": True,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "status": 200,
            "keyType": _cursor_cloud_api_key_type(body),
            "issues": [],
        }
    error_payload = body.get("error") if isinstance(body.get("error"), Mapping) else {}
    error_code = str(error_payload.get("code") or "").strip() or None
    message = _redact_secret_text(
        str(error_payload.get("message") or fallback_message or f"HTTP {status or 'unknown'}")
    )
    issue = (
        "Cursor Cloud Agent unavailable for current API key: "
        f"{error_code or 'forbidden'} ({message})"
        if error_code == "plan_required"
        else (
            f"CURSOR_API_KEY unauthorized for Cursor Cloud Agent API ({message})"
            if int(status or 0) == 401
            else (
                "CURSOR_API_KEY rejected by Cursor Cloud Agent API: "
                f"{error_code or 'http_' + str(status or 'unknown')} ({message})"
            )
        )
    )
    return {
        "checked": True,
        "ready": False,
        "endpoint": CURSOR_CLOUD_API_ME_URL,
        "status": status,
        "keyType": _cursor_cloud_api_key_type(body),
        "errorCode": error_code,
        "message": message,
        "issues": [issue],
    }


def _cursor_cloud_api_probe_with_curl(key: str, *, timeout_seconds: float) -> dict | None:
    curl = shutil.which("curl")
    if not curl:
        return None
    proc = subprocess.run(
        [
            curl,
            "-sS",
            "-L",
            "--max-time",
            str(max(1, int(timeout_seconds))),
            "-H",
            f"Authorization: Bearer {key}",
            "-H",
            "Accept: application/json",
            "-H",
            "User-Agent: quwoquan-data-env-preflight",
            "--output",
            "-",
            "--write-out",
            "\n%{http_code}",
            CURSOR_CLOUD_API_ME_URL,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = (proc.stdout or "").splitlines()
    status_text = lines[-1].strip() if lines else ""
    try:
        status = int(status_text)
    except ValueError:
        status = 0
    body_text = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    payload = {}
    if body_text.strip():
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            parsed = {}
        payload = parsed if isinstance(parsed, dict) else {}
    if status:
        return _cursor_cloud_api_result(
            status=status,
            payload=payload,
            fallback_message=(proc.stderr or "").strip(),
        )
    message = _redact_secret_text((proc.stderr or "").strip() or body_text.strip())
    return {
        "checked": True,
        "ready": False,
        "endpoint": CURSOR_CLOUD_API_ME_URL,
        "status": None,
        "keyType": "unknown",
        "errorCode": None,
        "message": message,
        "issues": [f"Cursor Cloud Agent API probe failed: {message or 'curl unavailable'}"],
    }


def _cursor_cloud_api_probe(*, timeout_seconds: float = 5.0) -> dict:
    key = str(os.environ.get("CURSOR_API_KEY") or "").strip()
    if not key:
        return {
            "checked": False,
            "ready": True,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "issues": [],
            "skipReason": "credential_not_ready",
        }
    request = urlrequest.Request(
        CURSOR_CLOUD_API_ME_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "quwoquan-data-env-preflight",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return _cursor_cloud_api_result(
                status=int(getattr(response, "status", 0) or 0),
                payload=_parse_json_bytes(response.read()),
            )
    except urlerror.HTTPError as exc:
        return _cursor_cloud_api_result(
            status=int(exc.code),
            payload=_parse_json_bytes(exc.read()),
            fallback_message=str(exc.reason or f"HTTP {exc.code}"),
        )
    except Exception as exc:  # noqa: BLE001
        curl_report = _cursor_cloud_api_probe_with_curl(key, timeout_seconds=timeout_seconds)
        if curl_report is not None:
            return curl_report
        message = _redact_secret_text(str(exc))
        return {
            "checked": True,
            "ready": False,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "status": None,
            "keyType": "unknown",
            "errorCode": None,
            "message": message,
            "issues": [f"Cursor Cloud Agent API probe failed: {type(exc).__name__}: {message}"],
        }


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
            "2",
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
    timeout_seconds: float = 5.0,
) -> dict:
    """Probe Cursor and source-network reachability without exposing credentials."""
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


