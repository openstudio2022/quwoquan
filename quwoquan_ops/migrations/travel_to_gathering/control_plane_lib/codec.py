"""canonical digest 与输入校验原语（逐字来自原 ``control_plane.py``）。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import load_json_yaml

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    DIGEST_RE,
    MigrationControlError,
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_digest(object_type: str, object_id: str) -> str:
    return canonical_digest({"objectType": object_type, "objectId": object_id})


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = load_json_yaml(path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise MigrationControlError(
            "INPUT_UNREADABLE",
            f"{label} is unreadable",
        ) from exc
    if not isinstance(value, dict):
        raise MigrationControlError("INPUT_INVALID", f"{label} must be an object")
    return value


def _require_digest(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if DIGEST_RE.fullmatch(text) is None:
        raise MigrationControlError(
            "DIGEST_INVALID",
            f"{label} must be a canonical sha256 digest",
        )
    return text


def _require_nonblank(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MigrationControlError("INPUT_INVALID", f"{label} must be non-empty")
    return text


def _parse_timestamp(value: Any, *, label: str) -> str:
    text = _require_nonblank(value, label=label)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationControlError(
            "INPUT_INVALID",
            f"{label} must be an RFC3339 timestamp",
        ) from exc
    return text
