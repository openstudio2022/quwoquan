#!/usr/bin/env python3
"""Capture and validate candidate-bound startup health failure evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO


SCHEMA = "qwq.startup-health-failure-evidence.v1"
MAX_BODY_BYTES = 65_536
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
TARGET_PATTERN = re.compile(r"(?:alpha|beta|gamma)-local")


class StartupHealthFailureEvidenceError(ValueError):
    """The captured response cannot prove one exact startup health failure."""


def _read_bounded(stream: BinaryIO) -> bytes:
    body = stream.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise StartupHealthFailureEvidenceError(
            "startup health response exceeds the managed evidence limit"
        )
    return body


def _failure_details(body: bytes) -> tuple[list[str], dict[str, str]]:
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StartupHealthFailureEvidenceError(
            "startup health response is not canonical JSON"
        ) from exc
    if not isinstance(document, dict) or document.get("status") != "degraded":
        raise StartupHealthFailureEvidenceError(
            "startup health response does not declare degraded status"
        )
    failed = document.get("failedChecks")
    checks = document.get("checks")
    if not isinstance(failed, list) or not isinstance(checks, dict):
        raise StartupHealthFailureEvidenceError(
            "startup health response has no typed failed-check closure"
        )
    names = sorted(
        {
            str(name).strip()
            for name in failed
            if isinstance(name, str) and str(name).strip()
        }
    )
    details = {
        name: str(checks.get(name) or "").strip()
        for name in names
    }
    if not names or any(not detail for detail in details.values()):
        raise StartupHealthFailureEvidenceError(
            "startup health response lost a failed-check detail"
        )
    return names, details


def _validate_identity(
    *,
    target: str,
    candidate_digest: str,
    service: str,
    url: str,
) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        TARGET_PATTERN.fullmatch(target) is None
        or SHA256_PATTERN.fullmatch(candidate_digest) is None
        or service != "content-service"
        or parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.path != "/healthz"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise StartupHealthFailureEvidenceError(
            "startup health capture identity is invalid"
        )


def _write_create_once(path: Path, payload: Mapping[str, Any]) -> None:
    output = path.expanduser().resolve()
    if output.name != "startup-health-failure.json" or not output.parent.is_dir():
        raise StartupHealthFailureEvidenceError(
            "startup health evidence output is not a prepared run root"
        )
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            output,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except OSError as exc:
        raise StartupHealthFailureEvidenceError(
            "startup health evidence must be create-once"
        ) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)


def capture(
    *,
    target: str,
    candidate_digest: str,
    service: str,
    url: str,
    output: Path,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Capture one non-2xx health response without changing runtime state."""

    _validate_identity(
        target=target,
        candidate_digest=candidate_digest,
        service=service,
        url=url,
    )
    request = urllib.request.Request(url, method="GET")
    try:
        response = opener(request, timeout=5.0)
        status_code = int(response.status)
        with response:
            body = _read_bounded(response)
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        with exc:
            body = _read_bounded(exc)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise StartupHealthFailureEvidenceError(
            "startup health endpoint was unavailable during teardown"
        ) from exc
    if status_code < 400:
        raise StartupHealthFailureEvidenceError(
            "startup health endpoint did not return a failure"
        )
    failed_checks, failure_details = _failure_details(body)
    payload = {
        "schema": SCHEMA,
        "target": target,
        "candidateDigest": candidate_digest,
        "service": service,
        "statusCode": status_code,
        "bodyByteLength": len(body),
        "bodySha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "failedChecks": failed_checks,
        "failureDetails": failure_details,
    }
    _write_create_once(output, payload)
    return payload


def load(
    path: Path,
    *,
    target: str,
    candidate_digest: str,
    service: str,
) -> dict[str, Any]:
    """Load one exact managed artifact for the enclosing startup report."""

    resolved = path.expanduser().resolve()
    try:
        metadata = resolved.lstat()
        raw = resolved.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise StartupHealthFailureEvidenceError(
            "startup health failure evidence is unreadable"
        ) from exc
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise StartupHealthFailureEvidenceError(
            "startup health failure evidence must be a regular file"
        )
    expected = {
        "schema": SCHEMA,
        "target": target,
        "candidateDigest": candidate_digest,
        "service": service,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise StartupHealthFailureEvidenceError(
            "startup health failure evidence identity mismatch"
        )
    failed = payload.get("failedChecks")
    details = payload.get("failureDetails")
    if (
        isinstance(payload.get("statusCode"), bool)
        or not isinstance(payload.get("statusCode"), int)
        or int(payload["statusCode"]) < 400
        or not isinstance(failed, list)
        or not isinstance(details, dict)
        or not failed
        or sorted(details) != sorted(failed)
        or any(not isinstance(details.get(name), str) or not details[name] for name in failed)
        or SHA256_PATTERN.fullmatch(str(payload.get("bodySha256") or "")) is None
        or isinstance(payload.get("bodyByteLength"), bool)
        or not isinstance(payload.get("bodyByteLength"), int)
        or not 0 < int(payload["bodyByteLength"]) <= MAX_BODY_BYTES
    ):
        raise StartupHealthFailureEvidenceError(
            "startup health failure evidence closure is invalid"
        )
    return {
        **payload,
        "artifactPath": str(resolved),
        "artifactSha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        capture(
            target=args.target,
            candidate_digest=args.candidate_digest,
            service=args.service,
            url=args.url,
            output=args.output,
        )
    except StartupHealthFailureEvidenceError as exc:
        parser.exit(2, f"GATE_BLOCK: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
