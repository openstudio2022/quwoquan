"""Canonical final reviewer-input assembly and hard byte-budget validation."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ReviewerContextBudgetExceeded(ValueError):
    def __init__(self, *, role: str, byte_count: int, limit: int, metadata: Mapping[str, Any]):
        super().__init__(f"role={role} assembled reviewer input={byte_count} bytes 超过 {limit}")
        self.role = role
        self.byte_count = byte_count
        self.limit = limit
        self.metadata = dict(metadata)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text_digest(value: str) -> str:
    return sha256_digest(value.encode("utf-8"))


def _marked_text(value: str, *, label: str, max_bytes: int) -> tuple[str, dict[str, Any] | None]:
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value, None
    marker = f"[REVIEW_TRUNCATED {label} original_bytes={len(raw)} digest={sha256_digest(raw)}]"
    marker_bytes = marker.encode("utf-8")
    keep = max(0, max_bytes - len(marker_bytes) - 1)
    prefix = raw[:keep].decode("utf-8", errors="ignore")
    result = prefix + "\n" + marker
    return result, {
        "component": label,
        "operation": "marked_truncation",
        "original_byte_count": len(raw),
        "assembled_byte_count": len(result.encode("utf-8")),
        "original_digest": sha256_digest(raw),
        "marker": marker,
    }


def _compact_findings(findings: Sequence[object], *, max_summary_bytes: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = [dict(item) for item in findings if isinstance(item, Mapping)]
    summaries: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for index, finding in enumerate(normalized):
        summary, change = _marked_text(
            str(finding.get("summary") or ""),
            label=f"evidence.findings[{index}].summary",
            max_bytes=max_summary_bytes,
        )
        summaries.append(
            {
                "id": str(finding.get("id") or ""),
                "owner": str(finding.get("owner") or ""),
                "severity": str(finding.get("severity") or ""),
                "path": str(finding.get("path") or ""),
                "summary": summary,
            }
        )
        if change:
            changes.append(change)
    return {"count": len(normalized), "findings": summaries}, changes


def _context_projection(
    contexts: Sequence[Mapping[str, Any]], *, repo_root: Path, include_content: bool,
    per_context_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projected: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for index, raw in enumerate(contexts):
        identity = {
            "path": str(raw.get("path") or ""),
            "anchor": raw.get("anchor"),
            "kind": str(raw.get("kind") or ""),
            "exists": bool(raw.get("exists")),
            "content_digest": raw.get("content_digest"),
        }
        item = {"identity": identity, "content": None}
        path = repo_root / identity["path"]
        if include_content and identity["exists"] and path.is_file() and not path.is_symlink():
            text = path.read_text(encoding="utf-8")
            item["content"], change = _marked_text(
                text,
                label=f"relevant_contexts[{index}].content",
                max_bytes=per_context_bytes,
            )
            if change:
                changes.append(change)
        elif identity["exists"]:
            item["content"] = (
                "[REVIEW_REF_ONLY content omitted; identity and content_digest retained]"
            )
            changes.append(
                {
                    "component": f"relevant_contexts[{index}].content",
                    "operation": "digest_ref_only",
                    "original_byte_count": path.stat().st_size if path.is_file() else 0,
                    "assembled_byte_count": len(item["content"].encode("utf-8")),
                    "original_digest": identity["content_digest"],
                    "marker": item["content"],
                }
            )
        projected.append(item)
    return projected, changes


def _diff_summary(changed_paths: Sequence[str], *, repo_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for relative in changed_paths:
        path = repo_root / relative
        exists = path.is_file() and not path.is_symlink()
        raw = path.read_bytes() if exists else b""
        rows.append(
            {
                "path": relative,
                "exists": exists,
                "byte_count": len(raw),
                "content_digest": sha256_digest(raw) if exists else None,
            }
        )
    return {
        "changed_path_count": len(changed_paths),
        "changed_paths_digest": sha256_digest(canonical_json_bytes(list(changed_paths))),
        "paths": rows,
    }


def _assemble_candidate(
    *, plan: Mapping[str, Any], reviewer: Mapping[str, Any], evidence_identity: Mapping[str, Any],
    evidence_summary: Mapping[str, Any], system_prompt: str, role_prompt: str,
    checklist_prompt: str, grading_prompt: str, repo_root: Path,
    include_context_content: bool, per_context_bytes: int, finding_summary_bytes: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contexts, context_changes = _context_projection(
        [item for item in plan.get("contexts", []) if isinstance(item, Mapping)],
        repo_root=repo_root,
        include_content=include_context_content,
        per_context_bytes=per_context_bytes,
    )
    findings, finding_changes = _compact_findings(
        evidence_summary.get("findings") or [], max_summary_bytes=finding_summary_bytes
    )
    owner = dict(plan.get("owner_identity") or {})
    candidate = {
        "schema_version": 1,
        "system_prompt": system_prompt,
        "role_prompt": role_prompt,
        "checklist_prompt": checklist_prompt,
        "grading_prompt": grading_prompt,
        "identity": {
            "workflow": plan.get("workflow"),
            "deliverable": plan.get("deliverable"),
            "scope": plan.get("scope"),
            "round": plan.get("round"),
            "reviewer": {
                "role": reviewer.get("role"),
                "kind": reviewer.get("kind"),
                "required": reviewer.get("required"),
                "profile": reviewer.get("profile"),
            },
            "owner_identity": owner,
            "candidate_evidence_identity": dict(plan.get("candidate_evidence_identity") or {}),
            "candidate_identity": {
                "plan_fingerprint_ref": plan.get("fingerprint_receipt", {}).get("ref"),
                "plan_fingerprint_digest": plan.get("fingerprint_receipt", {}).get("digest"),
                "head_sha": plan.get("head_sha"),
            },
        },
        "changed_paths_and_diff_summary": _diff_summary(
            [str(item) for item in plan.get("changed_paths") or []], repo_root=repo_root
        ),
        "evidence_summary": {
            "identity": dict(evidence_identity),
            "terminal": evidence_summary.get("terminal"),
            "results": evidence_summary.get("results") or evidence_summary.get("evidence") or [],
            **findings,
        },
        "relevant_contexts": contexts,
    }
    return candidate, [*context_changes, *finding_changes]


def assemble_reviewer_context(
    *, plan: Mapping[str, Any], reviewer: Mapping[str, Any], evidence_identity: Mapping[str, Any],
    evidence_summary: Mapping[str, Any], system_prompt: str, role_prompt: str,
    checklist_prompt: str, grading_prompt: str, repo_root: Path, limit: int,
) -> dict[str, Any]:
    """Assemble the exact final reviewer payload, structurally compressing before refusal."""
    passes = (
        ("full", True, 8192, 4096),
        ("structured_compression", True, 2048, 1024),
        ("refs_and_marked_truncation", False, 0, 256),
    )
    attempts: list[dict[str, Any]] = []
    for mode, include_content, context_bytes, finding_bytes in passes:
        candidate, changes = _assemble_candidate(
            plan=plan,
            reviewer=reviewer,
            evidence_identity=evidence_identity,
            evidence_summary=evidence_summary,
            system_prompt=system_prompt,
            role_prompt=role_prompt,
            checklist_prompt=checklist_prompt,
            grading_prompt=grading_prompt,
            repo_root=repo_root,
            include_context_content=include_content,
            per_context_bytes=context_bytes,
            finding_summary_bytes=finding_bytes,
        )
        raw = canonical_json_bytes(candidate)
        attempts.append({"mode": mode, "byte_count": len(raw), "digest": sha256_digest(raw)})
        if len(raw) <= limit:
            return {
                "assembled_input": candidate,
                "assembled_input_byte_count": len(raw),
                "assembled_input_digest": sha256_digest(raw),
                "compression": {
                    "mode": mode,
                    "applied": mode != "full" or bool(changes),
                    "changes": changes,
                    "attempts": attempts,
                    "identity_fields_preserved": [
                        "identity.reviewer",
                        "identity.owner_identity",
                        "identity.candidate_evidence_identity",
                        "identity.candidate_identity",
                    ],
                },
                "limit": limit,
            }
    raise ReviewerContextBudgetExceeded(
        role=str(reviewer.get("role") or ""),
        byte_count=attempts[-1]["byte_count"],
        limit=limit,
        metadata={"attempts": attempts, "identity_fields_preserved": True},
    )


__all__ = [
    "ReviewerContextBudgetExceeded",
    "assemble_reviewer_context",
    "canonical_json_bytes",
    "sha256_digest",
]
