"""Credential redaction for persisted source snapshots."""

from __future__ import annotations

import json
import re

_RAW_SNAPSHOT_BEARER = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    flags=re.IGNORECASE,
)
_RAW_SNAPSHOT_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:access[_-]?token|api[_-]?key|authcode|authorization|credential|"
    r"password|private[_-]?key|secret|signature|token|x-amz-credential|"
    r"x-amz-signature)s?\b\s*=\s*)([^&#\s\"'<>\\]+)"
)
_RAW_SNAPSHOT_EMPTY_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:access[_-]?token|api[_-]?key|authcode|authorization|credential|"
    r"password|private[_-]?key|secret|signature|token|x-amz-credential|"
    r"x-amz-signature)s?\b\s*=\s*)(?=[&#\s\"'<>\\]|$)"
)
_RAW_SNAPSHOT_SECRET_KEY_SUFFIXES = (
    "apikey",
    "credential",
    "password",
    "privatekey",
    "secret",
    "signature",
    "token",
)


def _redact_embedded_snapshot_secrets(value: str) -> str:
    redacted = _RAW_SNAPSHOT_BEARER.sub("Bearer <redacted>", value)
    redacted = _RAW_SNAPSHOT_SECRET_ASSIGNMENT.sub(
        r"\1<redacted>",
        redacted,
    )
    return _RAW_SNAPSHOT_EMPTY_SECRET_ASSIGNMENT.sub(
        r"\1<redacted>",
        redacted,
    )


def _snapshot_key_is_secret(value: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    return normalized.endswith(_RAW_SNAPSHOT_SECRET_KEY_SUFFIXES)


def _redact_snapshot_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _snapshot_key_is_secret(key)
                else _redact_snapshot_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_snapshot_json(item) for item in value]
    if isinstance(value, str):
        return _redact_embedded_snapshot_secrets(value)
    return value


def redact_raw_source_snapshot(raw: bytes, *, raw_format: str = "") -> bytes:
    """Remove credential-like values before an untrusted snapshot persists."""
    text = raw.decode("utf-8", errors="replace")
    if str(raw_format or "").strip() == "mediawiki_api_json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(
                _redact_snapshot_json(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
    return _redact_embedded_snapshot_secrets(text).encode("utf-8")
