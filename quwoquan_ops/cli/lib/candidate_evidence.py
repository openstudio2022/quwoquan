"""Candidate evidence producer/consumer for POST workspace identity."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from .agent_governance_contract import (
    contract_schema_version, declared_object, validate_candidate_evidence_manifest,
    validate_feature_context_manifest,
)
from .descriptor_safe_io import read_repo_relative_regular_single_link
from .evidence_fingerprint import (
    EvidenceFingerprintError, build_evidence_fingerprint, canonical_digest,
    canonical_json_bytes, normalize_repo_relative_path, snapshot_path,
    workspace_digests, validate_evidence_fingerprint,
)
from .feature_context_fingerprint import (
    CONTRACT_PATH, GENERATOR_PATH, resolve_fingerprint_binding,
    validate_content_addressed_ref, validate_current_feature_context_fingerprint,
)

CANDIDATE_GENERATOR_PATH = "quwoquan_ops/cli/lib/candidate_evidence.py"
IMPACT_PLAN_SOURCE = "quwoquan_ops/ci/local_readiness_planner.py"
_REF_RE = re.compile(r"^\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint/[0-9a-f]{64}\.json$")
_OWNER_PARTS = (".qwq_output", "env", "repo", "runs", "feature-tree", "by-fingerprint")
_CANDIDATE_PARTS = (".qwq_output", "env", "repo", "runs", "feature-tree", "by-fingerprint", "candidates", "by-fingerprint")


class CandidateEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _refuse(code: str, message: str) -> None:
    raise CandidateEvidenceError(code, message)


def _read_exact(ref: str, *, repo_root: Path, candidate: bool) -> bytes:
    relative = normalize_repo_relative_path(ref, repo_root)
    parts = _CANDIDATE_PARTS if candidate else _OWNER_PARTS
    try:
        return read_repo_relative_regular_single_link(
            repo_root, relative, expected_directory_parts=parts
        )
    except (OSError, ValueError) as exc:
        _refuse("CANDIDATE.STALE" if candidate else "IDENTITY.MIGRATION_REQUIRED", str(exc))
    raise AssertionError("unreachable")


def _load_owner(owner_identity_ref: str, *, repo_root: Path) -> tuple[str, bytes, dict[str, Any]]:
    relative = normalize_repo_relative_path(owner_identity_ref, repo_root)
    raw = _read_exact(relative, repo_root=repo_root, candidate=False)
    try:
        validate_content_addressed_ref(relative, raw_bytes=raw, repo_root=repo_root)
        value = json.loads(raw.decode("utf-8"))
    except (EvidenceFingerprintError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    if not isinstance(value, dict) or value.get("schema_version") != contract_schema_version("feature_context_manifest"):
        _refuse("IDENTITY.MIGRATION_REQUIRED", "owner identity 使用旧 schema，必须重新生成")
    try:
        validate_feature_context_manifest(value)
        validate_current_feature_context_fingerprint(value, repo_root=repo_root)
    except (KeyError, TypeError, ValueError, EvidenceFingerprintError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    return relative, raw, value


def _current_owner(
    target: str, *, repo_root: Path, canonical_contexts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Recompute current owner facts without rebuilding PRE snapshot sections."""

    from .feature_tree import context as tree_context
    from .feature_tree.nodes import discover_nodes, parent_chain
    from .feature_tree.ownership import resolve_target_details
    old_root, old_tree = tree_context.REPO_ROOT, tree_context.TREE_ROOT
    try:
        tree_context.REPO_ROOT = repo_root
        tree_context.TREE_ROOT = repo_root / "specs/feature-tree"
        nodes = discover_nodes()
        resolution = resolve_target_details(target, nodes)
        by_dir = {node.directory.resolve(): node for node in nodes}
        return {
            "target": normalize_repo_relative_path(resolution.target.as_posix(), repo_root),
            "resolved_owner": resolution.node.rel,
            "owner_chain": [
                {"level": item.level, "node_id": item.node_id, "path": item.rel}
                for item in parent_chain(resolution.node, by_dir)
            ],
            "canonical_contexts": list(canonical_contexts or []),
        }
    finally:
        tree_context.REPO_ROOT, tree_context.TREE_ROOT = old_root, old_tree


def _owner_facts(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in ("target", "resolved_owner", "owner_chain")}


def _context_snapshots(current: dict[str, Any], *, repo_root: Path) -> list[dict[str, Any]]:
    snapshots = []
    for item in current["canonical_contexts"]:
        path = normalize_repo_relative_path(str(item["path"]), repo_root)
        snapshot = snapshot_path(path, repo_root=repo_root)
        snapshots.append(declared_object({
            "path": path, "anchor": item.get("anchor"), "kind": item.get("kind"),
            "exists": snapshot["exists"], "content_digest": snapshot["content_digest"],
        }, "candidate_evidence_manifest", "context_snapshot_fields"))
    return snapshots


def _impact_plan(paths: list[str], *, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from quwoquan_ops.ci.local_readiness_planner import build_impact_plan
    except ModuleNotFoundError:
        import sys
        root_text = str(repo_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        from quwoquan_ops.ci.local_readiness_planner import build_impact_plan
    plan = build_impact_plan(paths, level="scope", repo_root=repo_root)
    projection = {key: plan[key] for key in (
        "schema", "impact_planner", "timeout_policy", "level", "paths", "scopes", "checks", "lockfiles", "deferred"
    )}
    digest = canonical_digest(projection)
    timeout_policy = plan["timeout_policy"]
    identity = declared_object({
        "schema": str(plan["schema"]), "digest": digest,
        "projection_ref": f"local-readiness-plan:{digest}",
        "timeout_policy_ref": str(timeout_policy["source"]),
        "timeout_policy_digest": str(timeout_policy["digest"]),
    }, "candidate_evidence_manifest", "impact_plan_identity_fields")
    return projection, identity


def build_candidate_fingerprint(payload: dict[str, Any], *, repo_root: Path, captured_by: str = "candidate_evidence") -> dict[str, Any]:
    identity = {key: payload[key] for key in payload if key != "evidence_fingerprint"}
    changed = list(payload["changed_paths"])
    return build_evidence_fingerprint({
        "git": {
            "head_sha": canonical_digest("candidate-head-independent"),
            "merge_base_sha": canonical_digest("candidate-merge-base-independent"),
        },
        "workspace": workspace_digests(changed, repo_root=repo_root),
        "assets": {
            "canonical_assets_digest": canonical_digest(identity),
            "review_assets_digest": canonical_digest({
                "context_snapshots": payload["context_snapshots"],
                "impact_plan_identity": payload["impact_plan_identity"],
            }),
        },
        "execution": {
            "commands_digest": canonical_digest(payload["impact_plan"].get("checks", [])),
            "toolchain_digest": canonical_digest({
                "candidate_schema": contract_schema_version("candidate_evidence_manifest"),
                "impact_plan_schema": payload["impact_plan_identity"]["schema"],
            }),
            "provider_digest": canonical_digest("feature_tree.candidate_evidence"),
            "generator_digest": canonical_digest({
                "candidate_generator": CANDIDATE_GENERATOR_PATH,
                "owner_generator": GENERATOR_PATH, "contract": CONTRACT_PATH,
                "impact_plan": IMPACT_PLAN_SOURCE,
            }),
        },
    }, captured_at="candidate-evidence-v1", captured_by="candidate_evidence", captured_metadata={"consumer": "candidate_evidence_manifest"})


def build_candidate_evidence(owner_identity_ref: str, changed_paths: list[str], *, repo_root: Path) -> dict[str, Any]:
    owner_ref, owner_raw, owner = _load_owner(owner_identity_ref, repo_root=repo_root)
    normalized = sorted({normalize_repo_relative_path(path, repo_root) for path in changed_paths}, key=lambda item: item.encode("utf-8"))
    if not normalized:
        _refuse("CANDIDATE.SPLIT_REQUIRED", "candidate changed_paths 不得为空")
    current = _current_owner(str(owner["target"]), repo_root=repo_root, canonical_contexts=list(owner["canonical_contexts"]))
    if _owner_facts(current) != _owner_facts(owner):
        _refuse("CANDIDATE.OWNER_DRIFT", "PRE owner identity 与当前 owner 解析漂移")
    from .feature_tree import context as tree_context
    from .feature_tree.nodes import discover_nodes
    from .feature_tree.ownership import resolve_target_details
    old_root, old_tree = tree_context.REPO_ROOT, tree_context.TREE_ROOT
    try:
        tree_context.REPO_ROOT = repo_root
        tree_context.TREE_ROOT = repo_root / "specs/feature-tree"
        nodes = discover_nodes()
        owners = []
        for path in normalized:
            try:
                resolution = resolve_target_details(path, nodes)
            except ValueError as exc:
                _refuse("CANDIDATE.SPLIT_REQUIRED", f"changed path 无唯一 owner：{path}: {exc}")
            owners.append(resolution.node.rel)
    finally:
        tree_context.REPO_ROOT, tree_context.TREE_ROOT = old_root, old_tree
    if set(owners) != {owner["resolved_owner"]}:
        _refuse("CANDIDATE.SPLIT_REQUIRED", f"changed_paths 跨 owner：{dict(zip(normalized, owners))}")
    impact_plan, impact_identity = _impact_plan(normalized, repo_root=repo_root)
    payload: dict[str, Any] = {
        "schema_version": contract_schema_version("candidate_evidence_manifest"),
        "owner_identity_ref": owner_ref,
        "owner_identity_canonical_bytes_sha256": "sha256:" + hashlib.sha256(owner_raw).hexdigest(),
        "target": owner["target"], "resolved_owner": owner["resolved_owner"],
        "owner_chain": owner["owner_chain"], "changed_paths": normalized,
        "workspace_digests": workspace_digests(normalized, repo_root=repo_root),
        "context_snapshots": _context_snapshots(current, repo_root=repo_root),
        "impact_plan": impact_plan, "impact_plan_identity": impact_identity,
    }
    payload["evidence_fingerprint"] = build_candidate_fingerprint(payload, repo_root=repo_root)
    validate_candidate_evidence_manifest(payload)
    return payload


def validate_candidate_ref(raw_ref: str, *, repo_root: Path, expected_owner_identity_ref: str | None = None, expected_changed_paths: list[str] | None = None) -> tuple[str, bytes, dict[str, Any], dict[str, Any]]:
    relative = normalize_repo_relative_path(raw_ref, repo_root)
    if _REF_RE.fullmatch(relative) is None:
        _refuse("IDENTITY.MIGRATION_REQUIRED", f"candidate ref 非 canonical content-addressed path：{relative}")
    raw = _read_exact(relative, repo_root=repo_root, candidate=True)
    if hashlib.sha256(raw).hexdigest() != Path(relative).stem or canonical_json_bytes(json.loads(raw)) != raw:
        _refuse("CANDIDATE.STALE", "candidate ref bytes/filename/canonical JSON 不一致")
    try:
        payload = json.loads(raw)
        if payload.get("schema_version") != contract_schema_version("candidate_evidence_manifest"):
            _refuse("IDENTITY.MIGRATION_REQUIRED", "candidate evidence 使用旧 schema")
        validate_candidate_evidence_manifest(payload)
    except CandidateEvidenceError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    if expected_owner_identity_ref and payload["owner_identity_ref"] != normalize_repo_relative_path(expected_owner_identity_ref, repo_root):
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate predecessor owner identity 不匹配")
    if expected_changed_paths is not None:
        expected = sorted({normalize_repo_relative_path(path, repo_root) for path in expected_changed_paths}, key=lambda item: item.encode("utf-8"))
        if payload["changed_paths"] != expected:
            _refuse("CANDIDATE.STALE", "candidate changed_paths 与 Review exact changed_paths 不一致")
    owner_ref, owner_raw, owner = _load_owner(payload["owner_identity_ref"], repo_root=repo_root)
    if payload["owner_identity_canonical_bytes_sha256"] != "sha256:" + hashlib.sha256(owner_raw).hexdigest():
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate owner identity raw sha 漂移")
    current = _current_owner(str(owner["target"]), repo_root=repo_root, canonical_contexts=list(owner["canonical_contexts"]))
    if _owner_facts(current) != _owner_facts(owner):
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate 当前 owner 重算漂移")
    rebuilt = build_candidate_evidence(owner_ref, list(payload["changed_paths"]), repo_root=repo_root)
    for field in ("target", "resolved_owner", "owner_chain", "workspace_digests", "context_snapshots", "impact_plan", "impact_plan_identity"):
        if rebuilt[field] != payload[field]:
            code = "CANDIDATE.OWNER_DRIFT" if field in {"target", "resolved_owner", "owner_chain"} else "CANDIDATE.STALE"
            _refuse(code, f"candidate current {field} 已漂移")
    actual = validate_evidence_fingerprint(payload["evidence_fingerprint"])
    expected = build_candidate_fingerprint(payload, repo_root=repo_root, captured_by="candidate_evidence_consumer")
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != expected[field]:
            _refuse("CANDIDATE.STALE", f"candidate fingerprint {field} 已漂移")
    return relative, raw, payload, actual


def candidate_identity(ref: str, raw: bytes, payload: dict[str, Any], fingerprint: dict[str, Any]) -> dict[str, Any]:
    return declared_object({
        "ref": ref, "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "owner_identity_ref": payload["owner_identity_ref"], "target": payload["target"],
        "resolved_owner": payload["resolved_owner"], "fingerprint_ref": fingerprint["ref"],
        "fingerprint_digest": fingerprint["digest"],
        "impact_plan_ref": payload["impact_plan_identity"]["projection_ref"],
        "impact_plan_digest": payload["impact_plan_identity"]["digest"],
    }, "review_plan", "candidate_evidence_identity_fields")
