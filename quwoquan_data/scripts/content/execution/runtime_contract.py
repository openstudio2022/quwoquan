"""Execution identity helpers for one immutable content work package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from content.execution.workspace import execution_manifest_path


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def stage_execution_context(execution_id: str, duplicate_id: str = "") -> dict[str, str]:
    """Return the only stage identity allowed by the execution contract.

    Internal callers still have a two-argument signature during source cleanup, but
    both arguments must be the same readable executionId.  No task, batch, plan or
    worker identity is projected into stage artifacts.
    """
    normalized = validate_execution_id(execution_id)
    if duplicate_id and validate_execution_id(duplicate_id) != normalized:
        raise ValueError("content execution must use one executionId")
    return {
        "executionId": normalized,
        "executionBinding": "frozen" if execution_manifest_path(normalized).is_file() else "standalone",
    }
