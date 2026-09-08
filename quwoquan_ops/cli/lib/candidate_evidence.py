"""Candidate v3 的无损路径闭包与单个原子交付身份。"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .agent_governance_contract import (
    contract_schema_version, contract_section, declared_object, validate_candidate_evidence_manifest,
    validate_candidate_path_set, validate_feature_context_manifest,
)
from .descriptor_safe_io import read_repo_relative_regular_single_link
from .evidence_fingerprint import (
    EvidenceFingerprintError, build_evidence_fingerprint, canonical_digest,
    canonical_json_bytes, normalize_repo_relative_path, snapshot_paths,
    workspace_digests, validate_evidence_fingerprint,
)
from .feature_context_fingerprint import (
    CONTRACT_PATH, GENERATOR_PATH,
    validate_content_addressed_ref, validate_current_feature_context_fingerprint, owner_identity_projection,
)

CANDIDATE_GENERATOR_PATH = "quwoquan_ops/cli/lib/candidate_evidence.py"
IMPACT_PLAN_SOURCE = "quwoquan_ops/ci/local_readiness_planner.py"
BRANCH_POLICY_PATH = "quwoquan_ops/policies/branch_policy.yaml"
LANE_OWNERSHIP_PATH = "quwoquan_ops/policies/lane_ownership.yaml"
_REF_RE = re.compile(r"^\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint/[0-9a-f]{64}\.json$")
_OWNER_PARTS = (".qwq_output", "env", "repo", "runs", "feature-tree", "by-fingerprint")
_CANDIDATE_PARTS = (*_OWNER_PARTS, "candidates", "by-fingerprint")


class CandidateEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _refuse(code: str, message: str) -> None:
    raise CandidateEvidenceError(code, message)


def _read_exact(ref: str, *, repo_root: Path, candidate: bool) -> bytes:
    relative = normalize_repo_relative_path(ref, repo_root)
    parts = _CANDIDATE_PARTS if candidate else _OWNER_PARTS
    section = "candidate_evidence_manifest" if candidate else "feature_context_manifest"
    try:
        return read_repo_relative_regular_single_link(
            repo_root, relative, expected_directory_parts=parts,
            max_bytes=int(contract_section(section)["max_bytes"]), require_current_name=True,
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
    paths = [normalize_repo_relative_path(str(item["path"]), repo_root) for item in current["canonical_contexts"]]
    # 一次有界Git批读；保留原context顺序与同路径的不同anchor，不跨调用缓存。
    by_path = {item["path"]: item for item in snapshot_paths(paths, repo_root=repo_root)}
    snapshots = []
    for item, path in zip(current["canonical_contexts"], paths):
        snapshot = by_path[path]
        snapshots.append(declared_object({
            "path": path, "anchor": item.get("anchor"), "kind": item.get("kind"),
            "exists": snapshot["exists"], "content_digest": snapshot["content_digest"],
        }, "candidate_evidence_manifest", "context_snapshot_fields"))
    return snapshots


def _policy_digest(relative: str, *, repo_root: Path) -> str:
    path = repo_root / relative
    if not path.is_file() or path.is_symlink():
        _refuse("CANDIDATE.OWNER_DRIFT", f"delivery identity policy 不可用：{relative}")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _allowed_delivery_lanes(*, repo_root: Path) -> set[str]:
    try:
        import yaml
        payload = yaml.safe_load((repo_root / BRANCH_POLICY_PATH).read_text(encoding="utf-8"))
        lanes = payload["allowed_local_branches"]
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        _refuse("CANDIDATE.OWNER_DRIFT", f"branch policy 无法确定 delivery lane：{exc}")
    if not isinstance(lanes, list):
        _refuse("CANDIDATE.OWNER_DRIFT", "branch policy allowed_local_branches 必须为列表")
    return {item for item in lanes if isinstance(item, str) and item.startswith("lane/")}


def _delivery_identity(*, repo_root: Path) -> tuple[str, str, dict[str, str]]:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(repo_root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    branch = result.stdout.strip()
    if result.returncode != 0:
        # actions/checkout intentionally leaves pull-request jobs on an exact,
        # detached merge SHA. GitHub's reviewed head ref is the logical lane;
        # the canonical branch gate validates the same hosted context first.
        if (
            os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
        ):
            branch = os.environ.get("GITHUB_HEAD_REF", "").strip()
        else:
            branch = ""
    if branch not in _allowed_delivery_lanes(repo_root=repo_root):
        _refuse("CANDIDATE.OWNER_DRIFT", f"current branch 不是版本化 policy 允许的逻辑 lane：{branch or 'detached'}")
    policy_digests = declared_object({
        "branch_policy_digest": _policy_digest(BRANCH_POLICY_PATH, repo_root=repo_root),
        "lane_ownership_digest": _policy_digest(LANE_OWNERSHIP_PATH, repo_root=repo_root),
    }, "candidate_evidence_manifest", "delivery_policy_digest_fields")
    # 最小 v2 中一个 current logical lane 同时承担 delivery owner 与 lead lane；
    # 不携带本机 worktree/clone inventory 或绝对路径。
    return branch, branch, policy_digests


def _impacted_owner_groups(paths: list[str], *, repo_root: Path) -> list[dict[str, Any]]:
    from .feature_tree import context as tree_context
    from .feature_tree.nodes import discover_nodes
    from .feature_tree.ownership import ownership_batch
    if tree_context.REPO_ROOT.resolve() != repo_root.resolve():
        _refuse("CANDIDATE.STALE", "owner batch repository root 不一致")
    try:
        with ownership_batch(discover_nodes()):
            return _resolve_impacted_owner_groups(paths, repo_root=repo_root)
    except CandidateEvidenceError:
        raise
    except (OSError, ValueError) as exc:
        _refuse("CANDIDATE.OWNER_RESOLUTION_FAILED", str(exc))
    raise AssertionError("unreachable")


def _resolve_impacted_owner_groups(paths: list[str], *, repo_root: Path) -> list[dict[str, Any]]:
    from .feature_tree import context as tree_context
    from .feature_tree.nodes import discover_nodes, parent_chain
    from .feature_tree.ownership import resolve_target_details

    old_root, old_tree = tree_context.REPO_ROOT, tree_context.TREE_ROOT
    try:
        tree_context.REPO_ROOT = repo_root
        tree_context.TREE_ROOT = repo_root / "specs/feature-tree"
        nodes = discover_nodes()
        by_dir = {node.directory.resolve(): node for node in nodes}
        groups: dict[str, dict[str, Any]] = {}
        for path in paths:
            try:
                resolution = resolve_target_details(path, nodes)
            except ValueError as exc:
                _refuse("CANDIDATE.OWNER_RESOLUTION_FAILED", f"changed path 无唯一 owner：{path}: {exc}")
            owner = resolution.node.rel
            chain = [
                {"level": item.level, "node_id": item.node_id, "path": item.rel}
                for item in parent_chain(resolution.node, by_dir)
            ]
            identity = declared_object(
                {
                    "resolved_owner": owner,
                    "owner_chain_digest": canonical_digest(chain),
                },
                "candidate_evidence_manifest", "impacted_owner_identity_fields",
            )
            existing = groups.get(owner)
            if existing is None:
                groups[owner] = {"owner_identity": identity, "paths": [path]}
            elif existing["owner_identity"] != identity:
                _refuse("CANDIDATE.OWNER_RESOLUTION_FAILED", f"owner identity 非确定：{owner}")
            else:
                existing["paths"].append(path)
        return [
            declared_object(groups[key], "candidate_evidence_manifest", "impacted_owner_group_fields")
            for key in sorted(groups, key=lambda item: item.encode("utf-8"))
        ]
    finally:
        tree_context.REPO_ROOT, tree_context.TREE_ROOT = old_root, old_tree


def _path_set_identity(document: dict[str, Any]) -> dict[str, Any]:
    raw = canonical_json_bytes(document)
    digest = canonical_digest(document)
    groups = document["impacted_owner_groups"]
    paths = sorted((p for group in groups for p in group["paths"]), key=lambda p: p.encode("utf-8"))
    return declared_object({
        "ref": f"{contract_section('candidate_path_set')['directory']}/{digest[7:]}.json",
        "canonical_bytes_sha256": digest, "byte_count": len(raw),
        "path_count": len(paths), "owner_count": len(groups),
        "changed_paths_digest": canonical_digest(paths),
        "impacted_owner_groups_digest": canonical_digest(groups),
    }, "candidate_path_set", "identity_fields")


def _decode_exact(raw: bytes, ref: str, *, limit: int) -> dict[str, Any]:
    if len(raw) > limit:
        _refuse("CANDIDATE.STALE", "candidate closure 超出读取预算")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
            _refuse("CANDIDATE.STALE", "candidate closure 非 canonical object")
    except (UnicodeError, ValueError, RecursionError) as exc:
        _refuse("CANDIDATE.STALE", f"candidate closure JSON 非法：{exc}")
    if hashlib.sha256(raw).hexdigest() != Path(ref).stem:
        _refuse("CANDIDATE.STALE", "candidate closure ref/digest 漂移")
    return value


def _validate_path_set(raw: bytes, payload: dict[str, Any]) -> dict[str, Any]:
    identity = payload["path_set_identity"]
    expected_ref = f"{contract_section('candidate_path_set')['directory']}/{identity['canonical_bytes_sha256'][7:]}.json"
    if identity["ref"] != expected_ref or len(raw) != identity["byte_count"]:
        _refuse("CANDIDATE.STALE", "candidate path set ref/length 漂移")
    document = _decode_exact(raw, expected_ref, limit=int(contract_section("candidate_path_set")["max_bytes"]))
    validate_candidate_path_set(document)
    for field in ("owner_identity_ref", "owner_identity_canonical_bytes_sha256"):
        if document[field] != payload[field]:
            _refuse("CANDIDATE.OWNER_DRIFT", "candidate path set predecessor 不一致")
    if _path_set_identity(document) != identity:
        _refuse("CANDIDATE.STALE", "candidate path set identity/coverage 漂移")
    if payload["resolved_owner"] not in {g["owner_identity"]["resolved_owner"] for g in document["impacted_owner_groups"]}:
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate primary owner 不在 path set")
    # 不依赖宿主的词法路径校验，current resolver 另在本地 freshness 边界重算。
    for group in document["impacted_owner_groups"]:
        for path in group["paths"]:
            if path.startswith("/") or "\\" in path or any(c in path for c in ("\x00", "\n", "\r")) or any(p in ("", ".", "..") for p in path.split("/")):
                _refuse("CANDIDATE.STALE", "candidate path set 路径非法")
    return document


def load_candidate_path_set(payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    validate_candidate_evidence_manifest(payload)
    identity = payload["path_set_identity"]
    directory = str(contract_section("candidate_path_set")["directory"])
    expected_ref = f"{directory}/{identity['canonical_bytes_sha256'][7:]}.json"
    if identity["ref"] != expected_ref:
        _refuse("CANDIDATE.STALE", "candidate path set ref 非canonical")
    try:
        raw = read_repo_relative_regular_single_link(
            repo_root, expected_ref, expected_directory_parts=tuple(directory.split("/")),
            max_bytes=identity["byte_count"], require_current_name=True,
        )
        return _validate_path_set(raw, payload)
    except (OSError, ValueError) as exc:
        if isinstance(exc, CandidateEvidenceError):
            raise
        _refuse("CANDIDATE.STALE", f"candidate path set closure 不可用：{exc}")
    raise AssertionError("unreachable")


def _changed_paths(payload: dict[str, Any], *, repo_root: Path) -> list[str]:
    document = load_candidate_path_set(payload, repo_root=repo_root)
    return sorted(
        [path for group in document["impacted_owner_groups"] for path in group["paths"]],
        key=lambda item: item.encode("utf-8"),
    )


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
    changed = _changed_paths(payload, repo_root=repo_root)
    return _candidate_fingerprint(payload, workspace_digests(changed, repo_root=repo_root), captured_by=captured_by)


def _candidate_fingerprint(payload: dict[str, Any], workspace: dict[str, Any], *, captured_by: str) -> dict[str, Any]:
    identity = {key: payload[key] for key in payload if key != "evidence_fingerprint"}
    return build_evidence_fingerprint({
        "git": {
            "head_sha": canonical_digest("candidate-head-independent"),
            "merge_base_sha": canonical_digest("candidate-merge-base-independent"),
        },
        "workspace": workspace,
        "assets": {
            "canonical_assets_digest": canonical_digest(identity),
            "review_assets_digest": canonical_digest({
                "delivery_owner": payload["delivery_owner"],
                "lead_lane": payload["lead_lane"],
                "delivery_policy_digests": payload["delivery_policy_digests"],
                "path_set_identity": payload["path_set_identity"],
                "context_snapshots": payload["context_snapshots"],
                "impact_plan_identity": payload["impact_plan_identity"],
            }),
        },
        "execution": {
            "commands_digest": canonical_digest(payload["impact_plan_identity"]),
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
    }, captured_at="candidate-evidence-v3", captured_by=captured_by, captured_metadata={"consumer": "candidate_evidence_manifest"})


def _assemble_candidate(owner_identity_ref: str, changed_paths: list[str], *, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    owner_ref, owner_raw, owner = _load_owner(owner_identity_ref, repo_root=repo_root)
    normalized = sorted(
        {normalize_repo_relative_path(path, repo_root) for path in changed_paths},
        key=lambda item: item.encode("utf-8"),
    )
    if not normalized:
        _refuse("CANDIDATE.EMPTY_CHANGED_PATHS", "candidate changed_paths 不得为空")
    current = _current_owner(str(owner["target"]), repo_root=repo_root, canonical_contexts=list(owner["canonical_contexts"]))
    if _owner_facts(current) != _owner_facts(owner):
        _refuse("CANDIDATE.OWNER_DRIFT", "PRE owner identity 与当前 owner 解析漂移")
    impacted_groups = _impacted_owner_groups(normalized, repo_root=repo_root)
    impacted_owners = {item["owner_identity"]["resolved_owner"] for item in impacted_groups}
    if owner["resolved_owner"] not in impacted_owners:
        _refuse("CANDIDATE.OWNER_DRIFT", "primary PRE target owner 未出现在 impacted owner groups")
    delivery_owner, lead_lane, policy_digests = _delivery_identity(repo_root=repo_root)
    _, impact_identity = _impact_plan(normalized, repo_root=repo_root)
    document = {
        "schema_version": contract_schema_version("candidate_path_set"),
        "owner_identity_ref": owner_ref,
        "owner_identity_canonical_bytes_sha256": "sha256:" + hashlib.sha256(owner_raw).hexdigest(),
        "impacted_owner_groups": impacted_groups,
    }
    validate_candidate_path_set(document)
    path_identity = _path_set_identity(document)
    if path_identity["byte_count"] > int(contract_section("candidate_path_set")["max_bytes"]):
        _refuse("CANDIDATE.STALE", "candidate path set 超出资源边界")
    payload: dict[str, Any] = {
        "schema_version": contract_schema_version("candidate_evidence_manifest"),
        "owner_identity_ref": owner_ref,
        "owner_identity_canonical_bytes_sha256": "sha256:" + hashlib.sha256(owner_raw).hexdigest(),
        "delivery_owner": delivery_owner,
        "lead_lane": lead_lane,
        "delivery_policy_digests": policy_digests,
        "target": owner["target"], "resolved_owner": owner["resolved_owner"],
        # 完整owner/path字节已先发布；manifest只绑定无损对象identity。
        "path_set_identity": path_identity,
        "workspace_digests": workspace_digests(normalized, repo_root=repo_root),
        "context_snapshots": _context_snapshots(current, repo_root=repo_root),
        # Candidate 只内嵌 content-addressed ImpactPlan identity。完整 projection
        # 可由 changed_paths + current planner 重建；重复嵌入会让大原子候选突破预算。
        "impact_plan_identity": impact_identity,
        "evidence_fingerprint": {},
    }
    payload["evidence_fingerprint"] = _candidate_fingerprint(payload, payload["workspace_digests"], captured_by="candidate_evidence")
    validate_candidate_evidence_manifest(payload)
    return payload, document


def build_candidate_evidence(owner_identity_ref: str, changed_paths: list[str], *, repo_root: Path) -> dict[str, Any]:
    payload, document = _assemble_candidate(owner_identity_ref, changed_paths, repo_root=repo_root)
    from .feature_tree.content_addressed_writer import _write_content_addressed_bytes
    from .feature_tree import context as tree_context
    if tree_context.REPO_ROOT.resolve() != repo_root.resolve():
        _refuse("CANDIDATE.STALE", "candidate producer repository root 不一致")
    _write_content_addressed_bytes(canonical_json_bytes(document), subdirectory="candidate-paths")
    load_candidate_path_set(payload, repo_root=repo_root)
    return payload


def validate_candidate_ref(raw_ref: str, *, repo_root: Path, expected_owner_identity_ref: str | None = None, expected_changed_paths: list[str] | None = None) -> tuple[str, bytes, dict[str, Any], dict[str, Any]]:
    relative = normalize_repo_relative_path(raw_ref, repo_root)
    if _REF_RE.fullmatch(relative) is None:
        _refuse("IDENTITY.MIGRATION_REQUIRED", f"candidate ref 非 canonical content-addressed path：{relative}")
    raw = _read_exact(relative, repo_root=repo_root, candidate=True)
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    if hashlib.sha256(raw).hexdigest() != Path(relative).stem or canonical_json_bytes(decoded) != raw:
        _refuse("CANDIDATE.STALE", "candidate ref bytes/filename/canonical JSON 不一致")
    try:
        payload = decoded
        if not isinstance(payload, dict) or payload.get("schema_version") != contract_schema_version("candidate_evidence_manifest"):
            _refuse("IDENTITY.MIGRATION_REQUIRED", "candidate evidence 使用旧 schema")
        validate_candidate_evidence_manifest(payload)
    except CandidateEvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        _refuse("IDENTITY.MIGRATION_REQUIRED", str(exc))
    if expected_owner_identity_ref and payload["owner_identity_ref"] != normalize_repo_relative_path(expected_owner_identity_ref, repo_root):
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate predecessor owner identity 不匹配")
    changed = _changed_paths(payload, repo_root=repo_root)
    if expected_changed_paths is not None:
        expected = sorted(
            {normalize_repo_relative_path(path, repo_root) for path in expected_changed_paths},
            key=lambda item: item.encode("utf-8"),
        )
        if changed != expected:
            _refuse("CANDIDATE.STALE", "candidate owner groups 与 Review exact changed_paths 不一致")
    owner_ref, owner_raw, owner = _load_owner(payload["owner_identity_ref"], repo_root=repo_root)
    if payload["owner_identity_canonical_bytes_sha256"] != "sha256:" + hashlib.sha256(owner_raw).hexdigest():
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate owner identity raw sha 漂移")
    current = _current_owner(str(owner["target"]), repo_root=repo_root, canonical_contexts=list(owner["canonical_contexts"]))
    if _owner_facts(current) != _owner_facts(owner):
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate 当前 owner 重算漂移")
    # consumer 重建事实不得发布或补全缺失对象。
    rebuilt, _ = _assemble_candidate(owner_ref, changed, repo_root=repo_root)
    owner_fields = {
        "target", "resolved_owner", "path_set_identity", "delivery_owner",
        "lead_lane", "delivery_policy_digests",
    }
    for field in (
        "delivery_owner", "lead_lane", "delivery_policy_digests", "target", "resolved_owner",
        "path_set_identity", "workspace_digests", "context_snapshots",
        "impact_plan_identity",
    ):
        if rebuilt[field] != payload[field]:
            code = "CANDIDATE.OWNER_DRIFT" if field in owner_fields else "CANDIDATE.STALE"
            _refuse(code, f"candidate current {field} 已漂移")
    actual = validate_evidence_fingerprint(payload["evidence_fingerprint"])
    expected = build_candidate_fingerprint(payload, repo_root=repo_root, captured_by="candidate_evidence_consumer")
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != expected[field]:
            _refuse("CANDIDATE.STALE", f"candidate fingerprint {field} 已漂移")
    return relative, raw, payload, actual


def export_candidate_closure(ref: str, *, repo_root: Path) -> list[dict[str, str]]:
    """输出已验证的portable exact bytes；不是新的authority或candidate。"""
    ref, _, _, _ = validate_candidate_ref(ref, repo_root=repo_root)
    return read_candidate_closure(ref, repo_root=repo_root)


def read_candidate_closure(ref: str, *, repo_root: Path) -> list[dict[str, str]]:
    """每次安全读回完整闭包；current工作树/owner解析仍由调用方freshness边界复核。"""
    if _REF_RE.fullmatch(ref) is None:
        _refuse("IDENTITY.MIGRATION_REQUIRED", "candidate closure ref 非canonical")
    raw = _read_exact(ref, repo_root=repo_root, candidate=True)
    candidate = _decode_exact(raw, ref, limit=int(contract_section("candidate_evidence_manifest")["max_bytes"]))
    validate_candidate_evidence_manifest(candidate)
    owner_ref = candidate["owner_identity_ref"]
    owner_raw = _read_exact(owner_ref, repo_root=repo_root, candidate=False)
    owner = _decode_exact(owner_raw, owner_ref, limit=int(contract_section("feature_context_manifest")["max_bytes"]))
    validate_feature_context_manifest(owner)
    document = load_candidate_path_set(candidate, repo_root=repo_root)
    members = {ref: raw, owner_ref: owner_raw,
               candidate["path_set_identity"]["ref"]: canonical_json_bytes(document)}
    binding = owner["evidence_fingerprint"]
    if binding["mode"] == "referenced":
        receipt_ref = binding["receipt_ref"]
        members[receipt_ref] = read_repo_relative_regular_single_link(
            repo_root, receipt_ref, expected_directory_parts=(*_OWNER_PARTS, "receipts"),
            max_bytes=int(contract_section("feature_context_manifest")["fingerprint_receipt_max_bytes"]), require_current_name=True,
        )
    closure = [{"ref": key, "canonical_json": members[key].decode("utf-8")} for key in sorted(members)]
    validate_candidate_closure(closure, candidate_ref=ref, owner_identity_ref=owner_ref)
    return closure


def validate_candidate_closure(
    closure: list[dict[str, str]], *, candidate_ref: str, owner_identity_ref: str,
) -> tuple[dict[str, Any], list[str]]:
    """离线验证传输闭包；不读取本机工作树，不将其升级为current准出。"""
    definition = contract_section("handoff_manifest")
    if not isinstance(closure, list) or not 3 <= len(closure) <= int(definition["candidate_closure_max_members"]):
        _refuse("CANDIDATE.STALE", "candidate closure member count 非法")
    members: dict[str, bytes] = {}
    cap = int(contract_section("candidate_path_set")["max_bytes"])
    for item in closure:
        if not isinstance(item, dict) or set(item) != {"ref", "canonical_json"}:
            _refuse("CANDIDATE.STALE", "candidate closure member schema 非法")
        ref, text = item["ref"], item["canonical_json"]
        if not isinstance(ref, str) or ref in members or not isinstance(text, str) or len(text) > cap:
            _refuse("CANDIDATE.STALE", "candidate closure duplicate/size 非法")
        members[ref] = text.encode("utf-8")
    def member(ref: str, limit: int) -> dict[str, Any]:
        if ref not in members:
            _refuse("CANDIDATE.STALE", f"candidate closure missing {ref}")
        return _decode_exact(members[ref], ref, limit=limit)
    if not isinstance(candidate_ref, str) or _REF_RE.fullmatch(candidate_ref) is None:
        _refuse("IDENTITY.MIGRATION_REQUIRED", "candidate closure ref 非canonical")
    candidate = member(candidate_ref, int(contract_section("candidate_evidence_manifest")["max_bytes"]))
    if candidate.get("schema_version") != contract_schema_version("candidate_evidence_manifest"):
        _refuse("IDENTITY.MIGRATION_REQUIRED", "candidate closure schema 已过期")
    validate_candidate_evidence_manifest(candidate)
    if candidate["owner_identity_ref"] != owner_identity_ref:
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate closure predecessor 不一致")
    owner = member(owner_identity_ref, int(contract_section("feature_context_manifest")["max_bytes"]))
    validate_content_addressed_ref(owner_identity_ref, raw_bytes=members[owner_identity_ref], repo_root=Path("/"))
    validate_feature_context_manifest(owner)
    if canonical_digest(owner) != candidate["owner_identity_canonical_bytes_sha256"]:
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate closure owner bytes 漂移")
    if any(owner[field] != candidate[field] for field in ("target", "resolved_owner")):
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate closure owner identity 漂移")
    path_ref = candidate["path_set_identity"]["ref"]
    if path_ref not in members:
        _refuse("CANDIDATE.STALE", "candidate closure missing path set")
    document = _validate_path_set(members[path_ref], candidate)
    expected = {candidate_ref, owner_identity_ref, path_ref}
    binding = owner["evidence_fingerprint"]
    if binding["mode"] == "referenced":
        if binding["receipt"] is not None:
            _refuse("CANDIDATE.STALE", "referenced owner 不得同时内嵌receipt")
        receipt_ref = binding["receipt_ref"]
        receipt = member(receipt_ref, int(contract_section("feature_context_manifest")["fingerprint_receipt_max_bytes"]))
        validate_content_addressed_ref(receipt_ref, raw_bytes=members[receipt_ref], repo_root=Path("/"), receipt=True)
        expected.add(receipt_ref)
    else:
        if binding["receipt_ref"] is not None:
            _refuse("CANDIDATE.STALE", "embedded owner 不得同时携带receipt ref")
        receipt = binding["receipt"]
    fingerprint = validate_evidence_fingerprint(receipt)
    owner_digest = canonical_digest(owner_identity_projection(owner, repo_root=Path("/")))
    if fingerprint["digest_payload"]["assets"]["canonical_assets_digest"] != owner_digest:
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate closure owner facts 漂移")
    if binding["digest"] != fingerprint["digest"] or binding["ref"] != fingerprint["ref"]:
        _refuse("CANDIDATE.OWNER_DRIFT", "candidate closure owner fingerprint 漂移")
    actual = validate_evidence_fingerprint(candidate["evidence_fingerprint"])
    rebuilt = _candidate_fingerprint(candidate, candidate["workspace_digests"], captured_by="portable-candidate-consumer")
    if any(actual[field] != rebuilt[field] for field in ("ref", "digest", "digest_payload")):
        _refuse("CANDIDATE.STALE", "candidate closure fingerprint identity 漂移")
    if set(members) != expected:
        _refuse("CANDIDATE.STALE", "candidate closure unexpected members")
    paths = sorted((p for group in document["impacted_owner_groups"] for p in group["paths"]), key=lambda p: p.encode("utf-8"))
    return candidate, paths


def candidate_identity(ref: str, raw: bytes, payload: dict[str, Any], fingerprint: dict[str, Any]) -> dict[str, Any]:
    return declared_object({
        "ref": ref,
        "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "schema_version": payload["schema_version"],
        "owner_identity_ref": payload["owner_identity_ref"],
        "delivery_owner": payload["delivery_owner"],
        "lead_lane": payload["lead_lane"],
        "delivery_policy_digests": payload["delivery_policy_digests"],
        "target": payload["target"],
        "resolved_owner": payload["resolved_owner"],
        "impacted_owner_groups_digest": payload["path_set_identity"]["impacted_owner_groups_digest"],
        "changed_paths_digest": payload["path_set_identity"]["changed_paths_digest"],
        "workspace_digests": payload["workspace_digests"],
        "fingerprint_ref": fingerprint["ref"],
        "fingerprint_digest": fingerprint["digest"],
        "impact_plan_ref": payload["impact_plan_identity"]["projection_ref"],
        "impact_plan_digest": payload["impact_plan_identity"]["digest"],
    }, "review_plan", "candidate_evidence_identity_fields")
