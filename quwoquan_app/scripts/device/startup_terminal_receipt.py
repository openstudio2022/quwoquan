"""Canonical safe-terminal evidence shared by launch supervisor and iOS UAT."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "quwoquan_app.startup_safe_terminal.v1"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_FIELDS = {
    "schema",
    "launchAttemptId",
    "startupAttemptId",
    "platform",
    "deviceId",
    "applicationId",
    "launchProvenance",
    "runtimeConfigSupplyMode",
    "effectiveLaunchManifestDigest",
    "artifactDigest",
    "configurationState",
    "surface",
    "canonicalTerminal",
    "hotRestart",
    "observedMarkerDigest",
}


def canonical_document_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def marker_digest(raw_marker: str) -> str:
    return "sha256:" + hashlib.sha256(raw_marker.encode("utf-8")).hexdigest()


def canonical_terminal_for_surface(surface: str) -> str:
    normalized = str(surface).strip()
    if normalized != "router_shell":
        raise ValueError(
            "startup safe-terminal surface must be router_shell"
        )
    return "routerShell"


def build_startup_terminal_receipt(
    *,
    launch_attempt: Mapping[str, Any],
    startup_attempt_id: str,
    configuration_state: str,
    surface: str,
    canonical_terminal: str,
    hot_restart: bool,
    observed_marker_digest: str,
) -> dict[str, Any]:
    value = {
        "schema": SCHEMA,
        "launchAttemptId": str(launch_attempt.get("attemptId") or ""),
        "startupAttemptId": str(startup_attempt_id).strip(),
        "platform": str(launch_attempt.get("platform") or ""),
        "deviceId": str(launch_attempt.get("deviceId") or ""),
        "applicationId": str(launch_attempt.get("applicationId") or ""),
        "launchProvenance": str(
            launch_attempt.get("launchProvenance") or ""
        ),
        "runtimeConfigSupplyMode": str(
            launch_attempt.get("runtimeConfigSupplyMode") or ""
        ),
        "effectiveLaunchManifestDigest": str(
            launch_attempt.get("launchDigest") or ""
        ),
        "artifactDigest": str(launch_attempt.get("artifactDigest") or ""),
        "configurationState": str(configuration_state).strip(),
        "surface": str(surface).strip(),
        "canonicalTerminal": str(canonical_terminal).strip(),
        "hotRestart": bool(hot_restart),
        "observedMarkerDigest": str(observed_marker_digest).strip(),
    }
    return validate_startup_terminal_receipt(value, launch_attempt=launch_attempt)


def validate_startup_terminal_receipt(
    value: object,
    *,
    launch_attempt: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("startup safe-terminal receipt fields mismatch")
    expected = {
        "schema": SCHEMA,
        "launchAttemptId": launch_attempt.get("attemptId"),
        "platform": launch_attempt.get("platform"),
        "deviceId": launch_attempt.get("deviceId"),
        "applicationId": launch_attempt.get("applicationId"),
        "launchProvenance": launch_attempt.get("launchProvenance"),
        "runtimeConfigSupplyMode": launch_attempt.get(
            "runtimeConfigSupplyMode"
        ),
        "effectiveLaunchManifestDigest": launch_attempt.get("launchDigest"),
        "artifactDigest": launch_attempt.get("artifactDigest"),
        "configurationState": "complete",
        "surface": "router_shell",
        "canonicalTerminal": "routerShell",
        "hotRestart": False,
    }
    if any(
        value.get(field) != expected_value
        for field, expected_value in expected.items()
    ):
        raise ValueError("startup safe-terminal receipt identity mismatch")
    if value["canonicalTerminal"] != canonical_terminal_for_surface(
        str(value["surface"])
    ):
        raise ValueError("startup safe-terminal surface mapping mismatch")
    startup_attempt_id = str(value.get("startupAttemptId") or "")
    if re.fullmatch(r"[A-Za-z0-9_-]+", startup_attempt_id) is None:
        raise ValueError("startup safe-terminal attemptId is invalid")
    for field in (
        "effectiveLaunchManifestDigest",
        "artifactDigest",
        "observedMarkerDigest",
    ):
        if _DIGEST_RE.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"startup safe-terminal {field} is invalid")
    return dict(value)


def read_startup_terminal_receipt(
    path: Path,
    *,
    launch_attempt: Mapping[str, Any],
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("startup safe-terminal receipt is missing or unsafe")
    decoded = json.loads(path.read_text(encoding="utf-8"))
    return validate_startup_terminal_receipt(
        decoded,
        launch_attempt=launch_attempt,
    )


def write_startup_terminal_receipt(path: Path, value: Mapping[str, Any]) -> str:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("startup safe-terminal receipt path must be fresh and absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        encoded = (
            json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("startup safe-terminal receipt write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    return canonical_document_digest(value)
