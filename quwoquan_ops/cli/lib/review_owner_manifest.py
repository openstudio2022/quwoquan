"""Owner manifest exact-ref loading and current-identity validation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lib.agent_governance_contract import (
    contract_schema_version,
    contract_section,
    declared_object,
    validate_declared_fields,
    validate_feature_context_manifest,
)
from lib.evidence_fingerprint import (
    EvidenceFingerprintError,
    normalize_repo_relative_path,
    snapshot_path,
)
from lib.descriptor_safe_io import read_repo_relative_regular_single_link
from lib.candidate_evidence import (
    CandidateEvidenceError, candidate_identity, validate_candidate_ref,
)
from lib.feature_context_fingerprint import (
    validate_content_addressed_ref,
    validate_current_feature_context_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNER_MANIFEST_REF_RE = re.compile(
    r"\A\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/"
    r"[0-9a-f]{64}\.json\Z"
)
OWNER_MANIFEST_DIRECTORY_PARTS = (
    ".qwq_output",
    "env",
    "repo",
    "runs",
    "feature-tree",
    "by-fingerprint",
)


class ReviewDispatchError(ValueError):
    """Typed refusal emitted before an invalid review can be dispatched."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _refuse(code: str, message: str) -> None:
    raise ReviewDispatchError(code, message)


def _repo_relative(raw_path: str, *, repo_root: Path) -> str:
    try:
        return normalize_repo_relative_path(raw_path, repo_root)
    except EvidenceFingerprintError as exc:
        _refuse("REVIEW.PATH_OUTSIDE_REPOSITORY", str(exc))
    raise AssertionError("unreachable")


def read_owner_manifest_exact_bytes(
    manifest_ref: str, *, repo_root: Path = REPO_ROOT
) -> bytes:
    """Read a canonical manifest through an inode-bound descriptor chain."""

    if OWNER_MANIFEST_REF_RE.fullmatch(manifest_ref) is None:
        raise ValueError(
            "owner manifest ref 不是 canonical content-addressed repo-relative path："
            f"{manifest_ref}"
        )
    return read_repo_relative_regular_single_link(
        repo_root,
        manifest_ref,
        expected_directory_parts=OWNER_MANIFEST_DIRECTORY_PARTS,
    )


def normalize_contexts(
    manifest: dict[str, Any],
    *,
    manifest_ref: str | None,
    candidate_evidence_ref: str | None = None,
    changed_paths: list[str] | None = None,
    expected_scope: str = "",
    required: bool = False,
    repo_root: Path = REPO_ROOT,
    reader: Callable[[str], bytes] | None = None,
    validate_manifest: Callable[
        [dict[str, Any]], None
    ] = validate_feature_context_manifest,
    validate_current_fingerprint: Callable[..., dict[str, Any]] = (
        validate_current_feature_context_fingerprint
    ),
) -> tuple[list[dict[str, Any]], int, str, dict[str, Any], dict[str, Any]]:
    """Validate PRE owner identity plus POST candidate predecessor."""

    if not manifest:
        if required:
            _refuse(
                "REVIEW.OWNER_MANIFEST_REQUIRED",
                "非控制型 workflow 的 POST Review 必须携带 current owner manifest",
            )
        return (
            [],
            0,
            "",
            declared_object(
                {
                    "ref": None,
                    "canonical_bytes_sha256": None,
                    "target": "",
                    "scope": expected_scope,
                    "resolved_owner": "",
                    "fingerprint_ref": None,
                    "fingerprint_digest": None,
                },
                "review_plan",
                "owner_identity_fields",
            ),
            declared_object(
                {"ref": None, "canonical_bytes_sha256": None, "owner_identity_ref": None,
                 "target": "", "resolved_owner": "", "fingerprint_ref": None,
                 "fingerprint_digest": None, "impact_plan_ref": None, "impact_plan_digest": None},
                "review_plan", "candidate_evidence_identity_fields",
            ),
        )
    expected_version = contract_schema_version("feature_context_manifest")
    if manifest.get("schema_version") != expected_version:
        _refuse(
            "IDENTITY.MIGRATION_REQUIRED",
            f"owner identity schema_version 必须为 {expected_version}",
        )
    try:
        validate_manifest(manifest)
    except (KeyError, TypeError, ValueError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", str(exc))
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_limit = int(contract_section("feature_context_manifest")["max_bytes"])
    if len(encoded) > manifest_limit:
        _refuse(
            "REVIEW.CONTEXT_MANIFEST_BUDGET_EXCEEDED",
            f"manifest={len(encoded)} bytes 超过 {manifest_limit}",
        )
    if not manifest_ref:
        _refuse(
            "REVIEW.OWNER_MANIFEST_REQUIRED",
            "POST Review 必须携带 owner manifest exact ref",
        )
    normalized_ref = _repo_relative(manifest_ref, repo_root=repo_root)
    try:
        raw_bytes = (
            reader(normalized_ref)
            if reader is not None
            else read_owner_manifest_exact_bytes(normalized_ref, repo_root=repo_root)
        )
    except (OSError, ValueError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", str(exc))
    try:
        validate_content_addressed_ref(
            normalized_ref, raw_bytes=raw_bytes, repo_root=repo_root
        )
        referenced = json.loads(raw_bytes.decode("utf-8"))
    except EvidenceFingerprintError as exc:
        _refuse("REVIEW.OWNER_MANIFEST_STALE", str(exc))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", str(exc))
    if referenced != manifest:
        _refuse(
            "REVIEW.OWNER_MANIFEST_STALE",
            "owner manifest ref canonical bytes 已被替换",
        )
    target = _repo_relative(str(manifest["target"]), repo_root=repo_root)
    if expected_scope and target != _repo_relative(expected_scope, repo_root=repo_root):
        _refuse(
            "REVIEW.OWNER_MANIFEST_SCOPE_MISMATCH",
            f"owner manifest target={target} 与 Review scope={expected_scope} 不一致",
        )
    chain = manifest.get("owner_chain") or []
    if not chain or chain[-1].get("path") != manifest.get("resolved_owner"):
        _refuse(
            "REVIEW.OWNER_MANIFEST_TARGET_MISMATCH",
            "owner manifest resolved_owner 必须等于 owner_chain 末节点",
        )
    try:
        validate_current_fingerprint(manifest, repo_root=repo_root)
    except EvidenceFingerprintError as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    contexts: list[dict[str, Any]] = []
    for raw in manifest["canonical_contexts"]:
        relative = _repo_relative(str(raw["path"]), repo_root=repo_root)
        snapshot = snapshot_path(relative, repo_root=repo_root)
        contexts.append(
            declared_object(
                {
                    "path": relative,
                    "anchor": raw.get("anchor"),
                    "kind": raw.get("kind"),
                    "exists": snapshot["exists"],
                    "content_digest": snapshot["content_digest"],
                },
                "review_plan",
                "context_fields",
            )
        )
    binding = manifest["evidence_fingerprint"]
    identity = declared_object(
        {
            "ref": normalized_ref,
            "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
            "target": target,
            "scope": expected_scope or target,
            "resolved_owner": str(manifest["resolved_owner"]),
            "fingerprint_ref": binding["ref"],
            "fingerprint_digest": binding["digest"],
        },
        "review_plan",
        "owner_identity_fields",
    )
    candidate = declared_object(
        {"ref": None, "canonical_bytes_sha256": None, "owner_identity_ref": None,
         "target": "", "resolved_owner": "", "fingerprint_ref": None,
         "fingerprint_digest": None, "impact_plan_ref": None, "impact_plan_digest": None},
        "review_plan", "candidate_evidence_identity_fields",
    )
    if required:
        if not candidate_evidence_ref:
            _refuse("IDENTITY.MIGRATION_REQUIRED", "POST Review 必须携带 --candidate-evidence")
        try:
            candidate_ref, candidate_raw, candidate_payload, candidate_fp = validate_candidate_ref(
                candidate_evidence_ref, repo_root=repo_root,
                expected_owner_identity_ref=normalized_ref,
                expected_changed_paths=changed_paths or [],
            )
        except CandidateEvidenceError as exc:
            _refuse(exc.code, exc.message)
        candidate = candidate_identity(candidate_ref, candidate_raw, candidate_payload, candidate_fp)
        contexts = list(candidate_payload["context_snapshots"])
    return contexts, len(encoded), target, identity, candidate


def validate_current_owner_manifest(
    plan: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    reader: Callable[[str], bytes] | None = None,
    validate_manifest: Callable[[dict[str, Any]], None] = validate_feature_context_manifest,
    validate_current_fingerprint: Callable[..., dict[str, Any]] = validate_current_feature_context_fingerprint,
) -> dict[str, Any]:
    """Revalidate stable PRE owner identity and current POST candidate bytes."""

    if "owner_manifest_identity" in plan or "candidate_evidence_identity" not in plan:
        _refuse("IDENTITY.MIGRATION_REQUIRED", "旧 Review identity schema 不再支持")
    identity = plan.get("owner_identity")
    candidate = plan.get("candidate_evidence_identity")
    if not isinstance(identity, dict) or not isinstance(candidate, dict):
        _refuse("IDENTITY.MIGRATION_REQUIRED", "Review plan 缺双身份")
    validate_declared_fields(identity, "review_plan", "owner_identity_fields")
    validate_declared_fields(candidate, "review_plan", "candidate_evidence_identity_fields")
    raw_ref = identity.get("ref")
    if not isinstance(raw_ref, str) or not raw_ref:
        _refuse("REVIEW.OWNER_MANIFEST_REQUIRED", "Review plan 缺 owner identity ref")
    ref = _repo_relative(raw_ref, repo_root=repo_root)
    try:
        raw_bytes = reader(ref) if reader is not None else read_owner_manifest_exact_bytes(ref, repo_root=repo_root)
        validate_content_addressed_ref(ref, raw_bytes=raw_bytes, repo_root=repo_root)
        manifest = json.loads(raw_bytes.decode("utf-8"))
        validate_manifest(manifest)
        validate_current_fingerprint(manifest, repo_root=repo_root)
    except (OSError, ValueError, EvidenceFingerprintError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    if "sha256:" + hashlib.sha256(raw_bytes).hexdigest() != identity.get("canonical_bytes_sha256"):
        _refuse("IDENTITY.MIGRATION_REQUIRED", "owner identity canonical bytes 漂移")
    if manifest.get("target") != identity.get("target") or manifest.get("resolved_owner") != identity.get("resolved_owner") or identity.get("scope") != plan.get("scope"):
        _refuse("CANDIDATE.OWNER_DRIFT", "owner target/scope/owner 已漂移")
    raw_candidate_ref = candidate.get("ref")
    if not isinstance(raw_candidate_ref, str) or not raw_candidate_ref:
        _refuse("IDENTITY.MIGRATION_REQUIRED", "Review plan 缺 candidate evidence ref")
    try:
        candidate_ref, candidate_raw, payload, fingerprint = validate_candidate_ref(
            raw_candidate_ref, repo_root=repo_root, expected_owner_identity_ref=ref,
            expected_changed_paths=list(plan.get("changed_paths") or []),
        )
    except CandidateEvidenceError as exc:
        _refuse(exc.code, exc.message)
    expected_candidate = candidate_identity(candidate_ref, candidate_raw, payload, fingerprint)
    if expected_candidate != candidate:
        _refuse("CANDIDATE.STALE", "Review plan candidate identity 已漂移")
    return payload


__all__ = [
    "OWNER_MANIFEST_DIRECTORY_PARTS",
    "ReviewDispatchError",
    "normalize_contexts",
    "read_owner_manifest_exact_bytes",
    "validate_current_owner_manifest",
]
