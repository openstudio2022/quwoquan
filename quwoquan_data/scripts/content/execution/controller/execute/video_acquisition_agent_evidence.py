"""Small create-once and exact-JSON helpers for video agent inputs."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn

AUTHOR_FIELDS = frozenset(
    {
        "schema", "candidateId", "contentSha256", "entityId", "status",
        "entityMatch", "attributionMatch", "qualityStatus", "caption", "findings",
    }
)
JUDGMENT_FIELDS = frozenset(
    {
        "rightsStatus", "authorizationRequired", "distributionDecision",
        "safetyStatus", "entityMatch", "qualityStatus", "privacyRisk",
        "minorRisk", "maliciousMediaRisk", "watermarkStatus", "findings",
    }
)


def write_agent_evidence_once(
    path: Path,
    payload: Mapping[str, Any],
    *,
    fail: Callable[[str, str], NoReturn],
) -> Path:
    body = json.dumps(dict(payload), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            fail(
                "DATA.SOURCE.AGENT_CREATE_ONCE_CONFLICT",
                f"agent evidence already contains different bytes: {path}",
            )
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def exact_json_object(text: str, *, fields: frozenset[str]) -> dict[str, Any] | None:
    values = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        values.insert(0, fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        values.append(text[first : last + 1])
    for value in values:
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and set(payload) == fields:
            return payload
    return None


__all__ = [
    "AUTHOR_FIELDS",
    "JUDGMENT_FIELDS",
    "exact_json_object",
    "write_agent_evidence_once",
]
