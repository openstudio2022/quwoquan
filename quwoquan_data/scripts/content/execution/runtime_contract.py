"""Execution identity helpers for one immutable content work package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from content.execution.workspace import load_execution_manifest


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def stage_execution_context(execution_id: str) -> dict[str, str]:
    """Return the frozen identity of a current execution work package."""
    normalized = validate_execution_id(execution_id)
    load_execution_manifest(normalized)
    return {
        "executionId": normalized,
        "executionBinding": "frozen",
    }
