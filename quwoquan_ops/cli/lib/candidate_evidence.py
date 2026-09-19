"""Candidate v4：绑定 actual changed paths、workspace 与 ImpactPlan，无 feature-tree write authority 前驱。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .agent_governance_contract import (
    allowed_delivery_sources, contract_schema_version, contract_section, declared_object,
    validate_candidate_evidence_manifest, validate_candidate_path_set, validate_declared_fields,
)
from .descriptor_safe_io import read_repo_relative_regular_single_link
from .evidence_fingerprint import (
    build_evidence_fingerprint, canonical_digest, canonical_json_bytes,
    normalize_repo_relative_path, snapshot_paths, validate_evidence_fingerprint, workspace_digests,
)
from .review_fingerprint import dependency_root, repository_inputs, validate_git_range

CANDIDATE_GENERATOR_PATH = "quwoquan_ops/cli/lib/candidate_evidence.py"
IMPACT_PLAN_SOURCE = "quwoquan_ops/ci/local_readiness_planner.py"
CONTRACT_PATH = "quwoquan_ops/policies/agent_governance_contract.yaml"
BRANCH_POLICY_PATH = "quwoquan_ops/policies/branch_policy.yaml"
LANE_OWNERSHIP_PATH = "quwoquan_ops/policies/lane_ownership.yaml"
_REF_RE = re.compile(r"^\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint/[0-9a-f]{64}\.json$")
_CANDIDATE_PARTS = (".qwq_output", "env", "repo", "runs", "feature-tree", "by-fingerprint", "candidates", "by-fingerprint")


class CandidateEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message); self.code, self.message = code, message


def _refuse(code: str, message: str) -> None:
    raise CandidateEvidenceError(code, message)


def _normalized_paths(paths: list[str], repo_root: Path) -> list[str]:
    result = sorted({normalize_repo_relative_path(path, repo_root) for path in paths}, key=lambda p: p.encode("utf-8"))
    if not result: _refuse("CANDIDATE.EMPTY_CHANGED_PATHS", "candidate changed_paths 不得为空")
    return result


def _policy_digest(path: str, repo_root: Path) -> str:
    source = repo_root / path
    if not source.is_file() or source.is_symlink(): _refuse("CANDIDATE.STALE", f"policy 不可用：{path}")
    return "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()


def _delivery_identity(repo_root: Path) -> tuple[str, str, dict[str, str]]:
    result = subprocess.run(["git", "-C", str(repo_root), "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True, text=True)
    branch = result.stdout.strip()
    if result.returncode and os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        branch = os.environ.get("GITHUB_HEAD_REF", "").strip()
    if branch not in allowed_delivery_sources(repo_root): _refuse("CANDIDATE.STALE", f"交付来源不合法：{branch or 'detached'}")
    digests = declared_object({"branch_policy_digest": _policy_digest(BRANCH_POLICY_PATH, repo_root), "lane_ownership_digest": _policy_digest(LANE_OWNERSHIP_PATH, repo_root)}, "candidate_evidence_manifest", "delivery_policy_digest_fields")
    return branch, branch, digests


def _source_delivery(identity: dict | None, paths: list[str], repo_root: Path) -> tuple[str, str, dict[str, str]]:
    if identity is None: return _delivery_identity(repo_root)
    validate_declared_fields(identity, "candidate_evidence_manifest", "source_identity_fields")
    validate_git_range({k: identity[k] for k in ("base_sha", "head_sha", "head_tree")}, repo_root=repo_root)
    lane = identity["producer_lane"]
    if lane not in allowed_delivery_sources(repo_root): _refuse("CANDIDATE.STALE", "producer lane 不在政策内")
    def git(*args: str) -> str: return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()
    if git("rev-parse", f"refs/heads/{lane}") != identity["head_sha"]: _refuse("CANDIDATE.STALE", "producer lane ref 漂移")
    if git("status", "--porcelain", "--untracked-files=normal"): _refuse("CANDIDATE.STALE", "跨阶段 source 必须 clean")
    changed = git("diff", "--name-only", "--no-renames", identity["base_sha"], identity["head_sha"]).splitlines()
    if sorted(changed) != sorted(paths): _refuse("CANDIDATE.STALE", "source identity 未覆盖完整 range paths")
    return lane, lane, {"branch_policy_digest": _policy_digest(BRANCH_POLICY_PATH, repo_root), "lane_ownership_digest": _policy_digest(LANE_OWNERSHIP_PATH, repo_root)}


def _impact_plan(paths: list[str], repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try: from quwoquan_ops.ci.local_readiness_planner import build_impact_plan
    except ModuleNotFoundError:
        import sys; sys.path.insert(0, str(repo_root)); from quwoquan_ops.ci.local_readiness_planner import build_impact_plan
    plan = build_impact_plan(paths, level="scope", repo_root=repo_root)
    projection = {k: plan[k] for k in ("schema", "impact_planner", "timeout_policy", "level", "paths", "scopes", "checks", "lockfiles", "deferred")}
    digest = canonical_digest(projection); timeout = plan["timeout_policy"]
    identity = declared_object({"schema": str(plan["schema"]), "digest": digest, "projection_ref": f"local-readiness-plan:{digest}", "timeout_policy_ref": str(timeout["source"]), "timeout_policy_digest": str(timeout["digest"])}, "candidate_evidence_manifest", "impact_plan_identity_fields")
    return projection, identity


def _path_set_identity(document: dict[str, Any]) -> dict[str, Any]:
    raw = canonical_json_bytes(document); paths = document["changed_paths"]; digest = canonical_digest(document)
    return declared_object({"ref": f"{contract_section('candidate_path_set')['directory']}/{digest[7:]}.json", "canonical_bytes_sha256": digest, "byte_count": len(raw), "path_count": len(paths), "changed_paths_digest": canonical_digest(paths)}, "candidate_path_set", "identity_fields")


def _context_snapshots(paths: list[str], repo_root: Path) -> list[dict[str, Any]]:
    # Context is optional and non-authoritative; candidate identity derives from actual paths and ImpactPlan.
    return []


def _candidate_fingerprint(payload: dict[str, Any], workspace: dict[str, Any], captured_by: str) -> dict[str, Any]:
    identity = {k: v for k, v in payload.items() if k != "evidence_fingerprint"}
    return build_evidence_fingerprint({"git": {"head_sha": canonical_digest("candidate-head-independent"), "merge_base_sha": canonical_digest("candidate-merge-base-independent")}, "workspace": workspace, "assets": {"canonical_assets_digest": canonical_digest(identity), "review_assets_digest": canonical_digest({"path_set_identity": payload["path_set_identity"], "impact_plan_identity": payload["impact_plan_identity"], "delivery_writer": payload["delivery_writer"]})}, "execution": {"commands_digest": canonical_digest(payload["impact_plan_identity"]), "toolchain_digest": canonical_digest({"candidate_schema": contract_schema_version("candidate_evidence_manifest")}), "provider_digest": canonical_digest("feature_tree.candidate_evidence"), "generator_digest": canonical_digest({"candidate_generator": CANDIDATE_GENERATOR_PATH, "contract": CONTRACT_PATH, "impact_plan": IMPACT_PLAN_SOURCE})}}, captured_at="candidate-evidence-v4", captured_by=captured_by, captured_metadata={"consumer": "candidate_evidence_manifest"})


def _assemble_candidate(changed_paths: list[str], *, repo_root: Path, source_identity: dict | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = _normalized_paths(changed_paths, repo_root); writer, lane, policies = _source_delivery(source_identity, paths, repo_root); _, impact = _impact_plan(paths, repo_root)
    document = {"schema_version": contract_schema_version("candidate_path_set"), "changed_paths": paths}; validate_candidate_path_set(document)
    path_identity = _path_set_identity(document)
    payload: dict[str, Any] = {"schema_version": contract_schema_version("candidate_evidence_manifest"), "delivery_writer": writer, "lead_lane": lane, "delivery_policy_digests": policies, "path_set_identity": path_identity, "workspace_digests": workspace_digests(paths, repo_root=repo_root), "context_snapshots": _context_snapshots(paths, repo_root), "impact_plan_identity": impact, "evidence_fingerprint": {}}
    if source_identity is not None: payload["source_identity"] = dict(source_identity)
    payload["evidence_fingerprint"] = _candidate_fingerprint(payload, payload["workspace_digests"], "candidate_evidence")
    validate_candidate_evidence_manifest(payload); return payload, document


@repository_inputs
def build_candidate_evidence(changed_paths: list[str], *, repo_root: Path, source_identity: dict | None = None) -> dict[str, Any]:
    payload, document = _assemble_candidate(changed_paths, repo_root=repo_root, source_identity=source_identity)
    from .feature_tree.content_addressed_writer import _write_content_addressed_bytes
    from .feature_tree import context as tree_context
    with tree_context.source_repository(repo_root): _write_content_addressed_bytes(canonical_json_bytes(document), subdirectory="candidate-paths")
    return payload


def _read_candidate(ref: str, repo_root: Path) -> bytes:
    try: return read_repo_relative_regular_single_link(dependency_root(repo_root), ref, expected_directory_parts=_CANDIDATE_PARTS, max_bytes=int(contract_section("candidate_evidence_manifest")["max_bytes"]), require_current_name=True)
    except (OSError, ValueError) as exc: _refuse("CANDIDATE.STALE", str(exc))


def load_candidate_path_set(payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    identity = payload["path_set_identity"]; ref = identity["ref"]
    try: raw = read_repo_relative_regular_single_link(dependency_root(repo_root), ref, expected_directory_parts=tuple(str(contract_section("candidate_path_set")["directory"]).split("/")), max_bytes=int(contract_section("candidate_path_set")["max_bytes"]), require_current_name=True)
    except (OSError, ValueError) as exc: _refuse("CANDIDATE.STALE", str(exc))
    value = json.loads(raw); validate_candidate_path_set(value)
    if canonical_json_bytes(value) != raw or _path_set_identity(value) != identity: _refuse("CANDIDATE.STALE", "candidate path set identity 漂移")
    return value


def validate_candidate_ref(raw_ref: str, *, repo_root: Path, expected_changed_paths: list[str] | None = None) -> tuple[str, bytes, dict[str, Any], dict[str, Any]]:
    ref = normalize_repo_relative_path(raw_ref, repo_root)
    if not _REF_RE.fullmatch(ref): _refuse("IDENTITY.MIGRATION_REQUIRED", f"candidate ref 非 canonical：{ref}")
    raw = _read_candidate(ref, repo_root); payload = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != Path(ref).stem or canonical_json_bytes(payload) != raw: _refuse("CANDIDATE.STALE", "candidate ref bytes 漂移")
    validate_candidate_evidence_manifest(payload); paths = load_candidate_path_set(payload, repo_root=repo_root)["changed_paths"]
    if expected_changed_paths is not None and paths != _normalized_paths(expected_changed_paths, repo_root): _refuse("CANDIDATE.STALE", "candidate changed_paths 与 actual paths 不一致")
    rebuilt, _ = _assemble_candidate(paths, repo_root=repo_root, source_identity=payload.get("source_identity"))
    for field in ("delivery_writer", "lead_lane", "delivery_policy_digests", "path_set_identity", "workspace_digests", "impact_plan_identity"):
        if rebuilt[field] != payload[field]: _refuse("CANDIDATE.STALE", f"candidate current {field} 已漂移")
    actual = validate_evidence_fingerprint(payload["evidence_fingerprint"]); expected = _candidate_fingerprint(payload, payload["workspace_digests"], "candidate_evidence_consumer")
    if any(actual[k] != expected[k] for k in ("ref", "digest", "digest_payload")): _refuse("CANDIDATE.STALE", "candidate fingerprint 漂移")
    return ref, raw, payload, actual


def read_candidate_closure(ref: str, *, repo_root: Path) -> list[dict[str, str]]:
    ref, raw, payload, _ = validate_candidate_ref(ref, repo_root=repo_root); path_doc = load_candidate_path_set(payload, repo_root=repo_root)
    return [{"ref": key, "canonical_json": value.decode()} for key, value in sorted({ref: raw, payload["path_set_identity"]["ref"]: canonical_json_bytes(path_doc)}.items())]

export_candidate_closure = read_candidate_closure


def validate_candidate_closure(closure: list[dict[str, str]], *, candidate_ref: str) -> tuple[dict[str, Any], list[str]]:
    members = {item["ref"]: item["canonical_json"].encode() for item in closure}
    if len(members) != 2 or candidate_ref not in members: _refuse("CANDIDATE.STALE", "candidate closure 必须恰含 candidate 与 path set")
    candidate = json.loads(members[candidate_ref]); validate_candidate_evidence_manifest(candidate)
    path_ref = candidate["path_set_identity"]["ref"]
    if path_ref not in members: _refuse("CANDIDATE.STALE", "candidate closure 缺 path set")
    document = json.loads(members[path_ref]); validate_candidate_path_set(document)
    if _path_set_identity(document) != candidate["path_set_identity"]: _refuse("CANDIDATE.STALE", "portable path set 漂移")
    return candidate, document["changed_paths"]


def candidate_identity(ref: str, raw: bytes, payload: dict[str, Any], fingerprint: dict[str, Any]) -> dict[str, Any]:
    return declared_object({"ref": ref, "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "schema_version": payload["schema_version"], "delivery_writer": payload["delivery_writer"], "lead_lane": payload["lead_lane"], "delivery_policy_digests": payload["delivery_policy_digests"], "changed_paths_digest": payload["path_set_identity"]["changed_paths_digest"], "workspace_digests": payload["workspace_digests"], "fingerprint_ref": fingerprint["ref"], "fingerprint_digest": fingerprint["digest"], "impact_plan_ref": payload["impact_plan_identity"]["projection_ref"], "impact_plan_digest": payload["impact_plan_identity"]["digest"]}, "review_plan", "candidate_evidence_identity_fields")
