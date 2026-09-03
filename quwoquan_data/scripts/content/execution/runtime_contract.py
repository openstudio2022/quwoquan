"""Pure hash and stage-context helpers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage_execution_context(execution_id: str) -> dict[str, str]:
    return {"executionId": validate_execution_id(execution_id), "executionBinding": "frozen"}


__all__ = ["canonical_sha256", "file_sha256", "stage_execution_context"]
