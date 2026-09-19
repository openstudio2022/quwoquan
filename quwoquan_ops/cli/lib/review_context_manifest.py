"""Review context and candidate validation without feature-tree write authority authority."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from .agent_governance_contract import declared_object
from .candidate_evidence import CandidateEvidenceError, candidate_identity, validate_candidate_ref
from .evidence_fingerprint import snapshot_path

class ReviewDispatchError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message); self.code, self.message = code, message

def _refuse(code: str, message: str) -> None: raise ReviewDispatchError(code, message)

def empty_candidate_identity() -> dict[str, Any]:
    return declared_object({"ref": None, "canonical_bytes_sha256": None, "schema_version": None, "delivery_writer": None, "lead_lane": None, "delivery_policy_digests": None, "changed_paths_digest": None, "workspace_digests": None, "fingerprint_ref": None, "fingerprint_digest": None, "impact_plan_ref": None, "impact_plan_digest": None}, "review_plan", "candidate_evidence_identity_fields")

def normalize_contexts(manifest: dict[str, Any], *, candidate_evidence_ref: str | None, changed_paths: list[str], required: bool, repo_root: Path) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    candidate = empty_candidate_identity(); contexts: list[dict[str, Any]] = []
    if required and not candidate_evidence_ref: _refuse("IDENTITY.MIGRATION_REQUIRED", "POST Review 必须携带 --candidate-evidence")
    if candidate_evidence_ref:
        try: ref, raw, payload, fingerprint = validate_candidate_ref(candidate_evidence_ref, repo_root=repo_root, expected_changed_paths=changed_paths)
        except CandidateEvidenceError as exc: _refuse(exc.code, exc.message)
        candidate = candidate_identity(ref, raw, payload, fingerprint)
        contexts = list(payload["context_snapshots"])
    if manifest:
        raw_contexts = manifest.get("canonical_contexts") or []
        for item in raw_contexts:
            snap = snapshot_path(str(item["path"]), repo_root=repo_root)
            contexts.append(declared_object({"path": item["path"], "anchor": item.get("anchor"), "kind": item.get("kind"), "exists": snap["exists"], "content_digest": snap["content_digest"]}, "review_plan", "context_fields"))
    contexts = sorted({(c["path"], c.get("anchor"), c["kind"]): c for c in contexts}.values(), key=lambda c: (c["path"], c.get("anchor") or "", c["kind"]))
    return contexts, len(str(manifest).encode()), candidate

def validate_current_candidate(plan: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    identity = plan.get("candidate_evidence_identity") or {}; ref = identity.get("ref")
    if not ref: _refuse("IDENTITY.MIGRATION_REQUIRED", "Review plan 缺 candidate evidence ref")
    try: candidate_ref, raw, payload, fingerprint = validate_candidate_ref(ref, repo_root=repo_root, expected_changed_paths=list(plan.get("changed_paths") or []))
    except CandidateEvidenceError as exc: _refuse(exc.code, exc.message)
    if candidate_identity(candidate_ref, raw, payload, fingerprint) != identity: _refuse("CANDIDATE.STALE", "Review plan candidate identity 已漂移")
    return payload
