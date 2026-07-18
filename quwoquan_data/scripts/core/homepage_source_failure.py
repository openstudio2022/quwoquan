"""Typed failure contract for entity homepage source authoring."""
from __future__ import annotations
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from core.io import read_json
from core.homepage_source_judge import normalize_page_title

ENTITY_PAGE_FAILURE_FILE = "failure.json"
ENTITY_PAGE_FAILURE_SCHEMA = "quwoquan_data.entity_page_failure"

class EntityPageFailureKind(StrEnum):
    SOURCE_ENTITY_MISMATCH = "source_entity_mismatch"
    SOURCE_INSUFFICIENT = "source_insufficient"
    SOURCE_PAGE_TYPE_INVALID = "source_page_type_invalid"
    OTHER = "other"

ENTITY_PAGE_FAILURE_KINDS = frozenset(kind.value for kind in EntityPageFailureKind)

SOURCE_RECOVERY_FAILURE_KINDS = frozenset(
    {
        EntityPageFailureKind.SOURCE_ENTITY_MISMATCH,
        EntityPageFailureKind.SOURCE_INSUFFICIENT,
        EntityPageFailureKind.SOURCE_PAGE_TYPE_INVALID,
    }
)

def entity_page_failure_kind(
    failure: Mapping[str, Any] | None,
) -> EntityPageFailureKind | None:
    if not isinstance(failure, Mapping):
        return None
    try:
        return EntityPageFailureKind(str(failure.get("failureKind") or ""))
    except ValueError:
        return None

def read_entity_page_failure(draft_dir: Path) -> dict[str, Any] | None:
    path = Path(draft_dir) / ENTITY_PAGE_FAILURE_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": "", "_unreadable": True}
    return payload if isinstance(payload, dict) else {"schema": "", "_unreadable": True}

def entity_page_failure_issues(
    failure: Mapping[str, Any] | None,
    *,
    entity_name: str,
) -> list[str]:
    """failure.json schema 校验：返回问题列表（空 = 合法失败报告）。"""
    issues: list[str] = []
    if not isinstance(failure, Mapping) or failure.get("_unreadable"):
        return ["failure.json unreadable or not a JSON object"]
    if str(failure.get("schema") or "") != ENTITY_PAGE_FAILURE_SCHEMA:
        issues.append(
            f"schema must be {ENTITY_PAGE_FAILURE_SCHEMA}, got {failure.get('schema')!r}"
        )
    if normalize_page_title(str(failure.get("targetEntity") or "")) != normalize_page_title(entity_name):
        issues.append(
            f"targetEntity mismatch: failure={failure.get('targetEntity')!r} expected={entity_name!r}"
        )
    kind = entity_page_failure_kind(failure)
    if kind is None:
        issues.append(f"failureKind invalid: {failure.get('failureKind')!r}")
    reasons = failure.get("reasons")
    if not isinstance(reasons, list) or not any(str(r).strip() for r in reasons):
        issues.append("reasons must be a non-empty list")
    return issues
