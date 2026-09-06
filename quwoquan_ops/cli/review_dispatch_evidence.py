"""Review registry evidence validation and projection helpers."""
from __future__ import annotations

import hashlib
from typing import Any, Callable


def _refuse(refuse: Callable[[str, str], None], code: str, message: str) -> None:
    refuse(code, message)


def validate_result_artifact_kind(
    evidence_id: str, config: dict[str, Any], *, refuse: Callable[[str, str], None]
) -> None:
    if config.get("result_artifact") not in (None, "code-health-report-v1"):
        _refuse(
            refuse,
            "REVIEW.INVALID_EVIDENCE",
            f"evidence={evidence_id} result_artifact 非 canonical kind",
        )


def resolve_evidence(
    registry: dict[str, Any],
    reviewers: list[dict[str, Any]],
    *,
    segment: str,
    baseline_evidence: str,
    checklist_evidence: Callable[[str], list[str]],
    refuse: Callable[[str, str], None],
) -> list[dict[str, Any]]:
    catalog = registry.get("evidence") or {}
    resolved: dict[str, dict[str, Any]] = {}
    consumers_by_id: dict[str, list[str]] = {}
    for reviewer in reviewers:
        evidence_ids = list(dict.fromkeys(
            ([baseline_evidence] if baseline_evidence else [])
            + checklist_evidence(reviewer["checklist"])
        ))
        reviewer["evidence"] = evidence_ids
        for evidence_id in evidence_ids:
            consumers_by_id.setdefault(evidence_id, []).append(reviewer["role"])
    for evidence_id, consumers in consumers_by_id.items():
        config = catalog.get(evidence_id)
        if config is None:
            _refuse(refuse, "REVIEW.UNKNOWN_EVIDENCE", f"checklist 引用了未注册 evidence={evidence_id}")
        if config.get("segment") != segment:
            continue
        command = str(config["command"])
        resolved[evidence_id] = {
            "id": evidence_id,
            "command": command,
            "segment": segment,
            "required": bool(config.get("required", True)),
            "covers": list(config.get("covers") or []),
            "timeout_seconds": int(config["timeout_seconds"]),
            "command_digest": "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest(),
            "consumers": list(dict.fromkeys(consumers)),
            "result_artifact": config.get("result_artifact"),
        }
    return list(resolved.values())
