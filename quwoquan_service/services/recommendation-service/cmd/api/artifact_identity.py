"""Fail-closed verification of the environment identity embedded by package."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

_SCHEMA = "qwq.environment-artifact-identity"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})


def verify_embedded_artifact_identity() -> None:
    path = Path(
        os.environ.get(
            "QWQ_ARTIFACT_IDENTITY_FILE",
            "/etc/quwoquan/artifact-identity.json",
        )
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("environment artifact identity is unreadable") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "environment",
        "configDigest",
    }:
        raise RuntimeError("environment artifact identity fields mismatch")
    environment = str(payload.get("environment") or "")
    if payload.get("schema") != _SCHEMA or environment not in _ENVIRONMENTS:
        raise RuntimeError("environment artifact identity is invalid")
    if _DIGEST.fullmatch(str(payload.get("configDigest") or "")) is None:
        raise RuntimeError("environment artifact config digest is invalid")
    asserted = str(os.environ.get("APP_ENV") or "").strip()
    if not asserted or asserted != environment:
        raise RuntimeError("APP_ENV assertion does not match embedded environment")
