#!/usr/bin/env python3
"""Generate one bounded Review Board v2 plan from the canonical registry.

PRE never spawns reviewers. POST selects the workflow primary reviewer and at
most one profile specialist. Evidence commands are named registry entries and
are executed by the board before dispatch, never by reviewers.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / ".agents/skills/review/references"
REGISTRY_PATH = REFERENCES_DIR / "registry.yaml"
GRADING_PATH = REFERENCES_DIR / "grading.md"

sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
from lib.agent_governance_contract import (  # noqa: E402
    canonical_bytes_sha256,
    contract_schema_version,
    contract_section,
    declared_object,
    validate_declared_fields,
    validate_feature_context_manifest,
    validate_required_fields,
)
from lib.feature_context_fingerprint import (  # noqa: E402
    build_feature_context_fingerprint,
    embedded_fingerprint_binding,
    validate_current_feature_context_fingerprint,
)
from lib.evidence_fingerprint import (  # noqa: E402
    EvidenceFingerprintError,
    snapshot_path,
    validate_evidence_fingerprint,
)
from lib.review_fingerprint import (  # noqa: E402
    build_review_fingerprint,
    head_sha as _review_head_sha,
    merge_base_sha as _review_merge_base_sha,
    normalize_path as _review_normalize_path,
    sha256_text as _review_sha256_text,
    snapshot as _review_snapshot,
)

_EVIDENCE_LINE_RE = re.compile(r"^\s*evidence:\s*(?P<evidence>[a-z0-9][a-z0-9-]*)\s*$")


class ReviewDispatchError(ValueError):
    """Typed refusal emitted before an invalid review can be dispatched."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def derive_profiles(
    profiles: dict[str, Any], changed_paths: list[str], deliverable: str
) -> list[str]:
    """Activate profiles in registry order by path or deliverable."""

    active: list[str] = []
    for name, raw_config in profiles.items():
        config = raw_config or {}
        patterns = config.get("paths") or []
        path_hit = any(
            fnmatch.fnmatch(path, pattern)
            for path in changed_paths
            for pattern in patterns
        )
        if path_hit or deliverable in (config.get("deliverables") or []):
            active.append(name)
    return active


from lib.review_terminal_contract import (  # noqa: E402
    EMITTED_REVIEW_CODES,
    validate_emitted_terminal_closure as _validate_emitted_terminal_closure,
)


def validate_emitted_terminal_closure() -> None:
    _validate_emitted_terminal_closure(contract_section)


def build_plan(
    registry: dict[str, Any],
    workflow: str,
    segment: str,
    deliverable: str | None,
    changed_paths: list[str],
    *,
    round_name: str = "initial",
    finding_owners: list[str] | None = None,
    previous_plan: dict[str, Any] | None = None,
    context_manifest: dict[str, Any] | None = None,
    context_manifest_ref: str | None = None,
    scope: str = "",
    incomplete_roles: list[dict[str, str] | str] | None = None,
    failed_evidence_ids: list[str] | None = None,
    cancelled: bool = False,
) -> dict[str, Any]:
    """Build a deterministic review plan without executing evidence or reviewers.

    The first five positional parameters intentionally retain the v1 Python API.
    New review-round controls are keyword-only so existing CLI callers remain
    compatible.
    """

    validate_emitted_terminal_closure()
    _validate_registry_header(registry)
    workflows = registry.get("workflows") or {}
    workflow_config = workflows.get(workflow)
    if workflow_config is None:
        _refuse(
            "REVIEW.UNKNOWN_WORKFLOW",
            f"workflow={workflow} 不在 registry.yaml 的 workflows 中",
        )
    if segment not in (workflow_config.get("segments") or []):
        _refuse(
            "REVIEW.SEGMENT_NOT_ALLOWED",
            f"workflow={workflow} 不接受 segment={segment}",
        )
    if round_name not in {"initial", "rereview"}:
        _refuse("REVIEW.INVALID_ROUND", f"未知 round={round_name}")

    normalized_previous = previous_plan or None
    if normalized_previous is not None:
        try:
            _validate_plan_contract(normalized_previous)
        except (KeyError, TypeError, ValueError) as exc:
            _refuse("REVIEW.PREVIOUS_PLAN_INVALID", str(exc))
    if round_name == "rereview" and normalized_previous is None:
        _refuse(
            "REVIEW.PREVIOUS_PLAN_REQUIRED",
            "rereview 必须提供首次评审的 previous plan",
        )

    if normalized_previous and not changed_paths:
        changed_paths = list(normalized_previous.get("changed_paths") or [])
    normalized_paths = sorted({_repo_relative(path) for path in changed_paths})
    resolved_deliverable = (
        deliverable
        or (normalized_previous or {}).get("deliverable")
        or workflow_config.get("deliverable")
        or ""
    )
    automatic_review = workflow_config.get("automatic_review") is not False
    canonical_deliverable = str(workflow_config.get("deliverable") or "")
    if not automatic_review and deliverable and deliverable != canonical_deliverable:
        _refuse(
            "REVIEW.CONTROL_WORKFLOW_DELIVERABLE_FORBIDDEN",
            f"控制型 workflow={workflow} 只能声明 deliverable={canonical_deliverable}",
        )

    requested_scope = scope or (normalized_previous or {}).get("scope") or ""
    manifest_required = segment == "POST" and automatic_review
    contexts, manifest_bytes, manifest_target, owner_manifest_identity = _normalize_contexts(
        context_manifest or {},
        manifest_ref=context_manifest_ref,
        expected_scope=requested_scope,
        required=manifest_required,
    )
    resolved_scope = requested_scope or manifest_target
    active_profiles = derive_profiles(
        registry.get("profiles") or {}, normalized_paths, resolved_deliverable
    )

    initial_reviewers = _select_initial_reviewers(
        registry,
        workflow=workflow,
        segment=segment,
        workflow_config=workflow_config,
        active_profiles=active_profiles,
    )
    all_initial_evidence = _resolve_evidence(
        registry, initial_reviewers, segment=segment
    )

    previous_fingerprint: str | None = None
    invocation_count = len(initial_reviewers)
    reviewers = initial_reviewers
    invalidations: list[dict[str, str]] = []
    if round_name == "rereview":
        assert normalized_previous is not None
        reviewers, invocation_count = _select_rereviewers(
            initial_reviewers,
            normalized_previous,
            finding_owners or [],
            workflow=workflow,
            deliverable=resolved_deliverable,
            scope=resolved_scope,
            changed_paths=normalized_paths,
            profiles=active_profiles,
            max_invocations=int(registry["limits"]["max_role_invocations"]),
        )
        previous_fingerprint = str(normalized_previous.get("fingerprint") or "")

    context_bytes = _measure_reviewer_contexts(
        registry,
        workflow=workflow,
        workflow_config=workflow_config,
        active_profiles=active_profiles,
        reviewers=reviewers,
        contexts=contexts,
        manifest_bytes=manifest_bytes,
    )
    for reviewer in reviewers:
        reviewer["context_bytes"] = context_bytes["reviewers"].get(
            reviewer["role"], 0
        )

    # A fix invalidates prior evidence, but directed re-review remains legal when
    # owner/profile/scope are unchanged. Evidence is therefore derived from the
    # complete initial bundle and rerun once before finding owners are dispatched.
    evidence = all_initial_evidence
    normalized_incomplete, terminal = _classify_terminal(
        reviewers,
        evidence,
        incomplete_roles=incomplete_roles or [],
        failed_evidence_ids=failed_evidence_ids or [],
        cancelled=cancelled,
    )
    fingerprint_receipt = _fingerprint_receipt(
        workflow=workflow,
        deliverable=resolved_deliverable,
        scope=resolved_scope,
        owner_manifest_identity=owner_manifest_identity,
        terminal=terminal,
        changed_paths=normalized_paths,
        profiles=active_profiles,
        contexts=contexts,
        initial_reviewers=initial_reviewers,
        evidence=evidence,
    )
    fingerprint = fingerprint_receipt["digest"]
    evidence_reusable = bool(
        round_name == "rereview"
        and previous_fingerprint
        and previous_fingerprint == fingerprint
    )
    if round_name == "rereview" and not evidence_reusable:
        invalidations.append(
            {
                "code": "REVIEW.FINGERPRINT_CHANGED",
                "message": "变更或上下文指纹已变化，旧 evidence 失效并须重新执行",
            }
        )
    for item in evidence:
        item["reusable"] = evidence_reusable

    skipped_reviewers: list[dict[str, Any]] = []
    if "REVIEW.EVIDENCE_FAILED" in terminal["codes"]:
        # Evidence is executed before role dispatch. A required failure must
        # therefore leave no callable reviewer in the emitted plan.
        skipped_reviewers = reviewers
        reviewers = []
        invocation_count = (
            int((normalized_previous or {}).get("invocation_count") or 0)
            if round_name == "rereview"
            else 0
        )

    plan = {
        "schema_version": contract_schema_version("review_plan"),
        "workflow": workflow,
        "segment": segment,
        "round": round_name,
        "deliverable": resolved_deliverable,
        "scope": resolved_scope,
        "owner_manifest_identity": owner_manifest_identity,
        "changed_paths": normalized_paths,
        "profiles": active_profiles,
        "contexts": contexts,
        "reviewers": reviewers,
        "skipped_reviewers": skipped_reviewers,
        "evidence": evidence,
        "fingerprint_receipt": fingerprint_receipt,
        "fingerprint": fingerprint,
        "previous_fingerprint": previous_fingerprint,
        "evidence_reusable": evidence_reusable,
        "invocation_count": invocation_count,
        "context_bytes": context_bytes,
        "incomplete_roles": normalized_incomplete,
        "invalidations": invalidations,
        "terminal": terminal,
        "head_sha": _head_sha(),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    _validate_plan_contract(plan)
    return plan


def _validate_plan_contract(plan: dict[str, Any]) -> None:
    """Validate the complete plan shape against the canonical machine contract."""

    expected_version = contract_schema_version("review_plan")
    if plan.get("schema_version") != expected_version:
        raise ValueError(
            "review_plan.schema_version 必须为 "
            f"{expected_version}，实际为 {plan.get('schema_version')!r}"
        )
    validate_required_fields(plan, "review_plan")
    receipt = validate_evidence_fingerprint(plan.get("fingerprint_receipt"))
    fingerprint = plan.get("fingerprint")
    if receipt["digest"] != fingerprint:
        raise ValueError("review_plan.fingerprint_receipt 与 fingerprint 不一致")
    if (
        not isinstance(fingerprint, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint)
    ):
        raise ValueError(
            "review_plan.fingerprint 必须为 canonical EvidenceFingerprint digest"
        )
    previous_fingerprint = plan.get("previous_fingerprint")
    if previous_fingerprint is not None and (
        not isinstance(previous_fingerprint, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", previous_fingerprint)
    ):
        raise ValueError(
            "review_plan.previous_fingerprint 必须为空或 canonical EvidenceFingerprint digest"
        )
    for field, declaration in (
        ("contexts", "context_fields"),
        ("reviewers", "reviewer_fields"),
        ("skipped_reviewers", "reviewer_fields"),
        ("evidence", "evidence_fields"),
        ("incomplete_roles", "incomplete_role_fields"),
        ("invalidations", "invalidation_fields"),
    ):
        values = plan[field]
        if not isinstance(values, list):
            raise TypeError(f"review_plan.{field} 必须为列表")
        for value in values:
            if not isinstance(value, dict):
                raise TypeError(f"review_plan.{field} 项必须为映射")
            validate_declared_fields(value, "review_plan", declaration)
    owner_identity = plan["owner_manifest_identity"]
    if not isinstance(owner_identity, dict):
        raise TypeError("review_plan.owner_manifest_identity 必须为映射")
    validate_declared_fields(
        owner_identity, "review_plan", "owner_manifest_identity_fields"
    )
    for field, declaration in (
        ("context_bytes", "context_bytes_fields"),
        ("terminal", "terminal_fields"),
    ):
        value = plan[field]
        if not isinstance(value, dict):
            raise TypeError(f"review_plan.{field} 必须为映射")
        validate_declared_fields(value, "review_plan", declaration)


def _validate_registry_header(registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != 2:
        _refuse("REVIEW.REGISTRY_VERSION_UNSUPPORTED", "registry schema 必须为 2")
    limits = registry.get("limits") or {}
    if limits.get("max_parallel") != 2:
        _refuse("REVIEW.INVALID_LIMIT", "max_parallel 必须为 2")
    max_invocations = limits.get("max_role_invocations")
    if not isinstance(max_invocations, int) or max_invocations > 4:
        _refuse("REVIEW.INVALID_LIMIT", "max_role_invocations 必须是不大于 4 的整数")
    commands: dict[str, str] = {}
    for evidence_id, config in (registry.get("evidence") or {}).items():
        if not isinstance(config.get("covers"), list):
            _refuse(
                "REVIEW.INVALID_EVIDENCE",
                f"evidence={evidence_id} 必须显式声明 covers list",
            )
        command = str(config.get("command") or "")
        if not command:
            _refuse(
                "REVIEW.INVALID_EVIDENCE",
                f"evidence={evidence_id} 缺 command",
            )
        prior = commands.get(command)
        if prior:
            _refuse(
                "REVIEW.DUPLICATE_EVIDENCE_COMMAND",
                f"evidence={prior}/{evidence_id} 复制同一 command",
            )
        commands[command] = evidence_id


def _select_initial_reviewers(
    registry: dict[str, Any],
    *,
    workflow: str,
    segment: str,
    workflow_config: dict[str, Any],
    active_profiles: list[str],
) -> list[dict[str, Any]]:
    if segment == "PRE" or workflow_config.get("automatic_review") is False:
        return []

    reviewers: list[dict[str, Any]] = []
    primary = workflow_config.get("primary")
    if primary:
        reviewers.append(
            _reviewer(
                role=primary["role"],
                kind="primary",
                required=bool(primary.get("required", True)),
                checklist=primary["checklist"],
                profile=None,
            )
        )

    primary_roles = {reviewer["role"] for reviewer in reviewers}
    candidates: list[tuple[int, int, str, dict[str, Any], str]] = []
    profile_registry = registry.get("profiles") or {}
    for order, profile_name in enumerate(active_profiles):
        specialist = (profile_registry.get(profile_name) or {}).get("specialist") or {}
        checklist = (specialist.get("checklists") or {}).get(workflow)
        role = specialist.get("role")
        if not checklist or not role or role in primary_roles:
            continue
        candidates.append(
            (
                -int(specialist.get("priority", 0)),
                order,
                profile_name,
                specialist,
                checklist,
            )
        )
    if candidates:
        _, _, profile_name, specialist, checklist = sorted(candidates)[0]
        reviewers.append(
            _reviewer(
                role=specialist["role"],
                kind="specialist",
                required=bool(specialist.get("required", False)),
                checklist=checklist,
                profile=profile_name,
            )
        )

    if len(reviewers) > int(registry["limits"]["max_parallel"]):
        _refuse("REVIEW.PARALLEL_LIMIT_EXCEEDED", "首次评审角色超过 max_parallel")
    return reviewers


def _reviewer(
    *, role: str, kind: str, required: bool, checklist: str, profile: str | None
) -> dict[str, Any]:
    return {
        "role": role,
        "kind": kind,
        "required": required,
        "profile": profile,
        "checklist": checklist,
        "evidence": [],
    }


def _select_rereviewers(
    initial_reviewers: list[dict[str, Any]],
    previous_plan: dict[str, Any],
    finding_owners: list[str],
    *,
    workflow: str,
    deliverable: str,
    scope: str,
    changed_paths: list[str],
    profiles: list[str],
    max_invocations: int,
) -> tuple[list[dict[str, Any]], int]:
    if previous_plan.get("round") != "initial":
        _refuse(
            "REVIEW.REREVIEW_CHAIN_FORBIDDEN",
            "复审只能直接引用 initial plan，不自动形成第二轮复审链",
        )
    stable_fields = {
        "workflow": workflow,
        "deliverable": deliverable,
        "scope": scope,
        "changed_paths": changed_paths,
        "profiles": profiles,
    }
    changed_fields = [
        key for key, value in stable_fields.items() if previous_plan.get(key) != value
    ]
    if changed_fields:
        _refuse(
            "REVIEW.NEW_REVIEW_REQUIRED",
            "归属/profile/scope 已变化，必须重新首次评审：" + ", ".join(changed_fields),
        )

    owners = list(dict.fromkeys(finding_owners))
    if not owners or len(owners) > 2:
        _refuse(
            "REVIEW.INVALID_FINDING_OWNER",
            "rereview 必须提供 1 到 2 个 finding-owner",
        )
    previous_roles = {
        item.get("role") for item in (previous_plan.get("reviewers") or [])
    }
    invalid = [owner for owner in owners if owner not in previous_roles]
    if invalid:
        _refuse(
            "REVIEW.INVALID_FINDING_OWNER",
            "finding-owner 不在 initial reviewers 中：" + ", ".join(invalid),
        )
    by_role = {item["role"]: item for item in initial_reviewers}
    reviewers = [dict(by_role[owner]) for owner in owners if owner in by_role]
    if len(reviewers) != len(owners):
        _refuse(
            "REVIEW.NEW_REVIEW_REQUIRED",
            "当前 owner/profile 解析已改变，必须重新首次评审",
        )
    total = int(previous_plan.get("invocation_count") or 0) + len(reviewers)
    if total > max_invocations:
        _refuse(
            "REVIEW.INVOCATION_LIMIT_EXCEEDED",
            f"累计角色调用 {total} 超过上限 {max_invocations}",
        )
    return reviewers, total


def _resolve_evidence(
    registry: dict[str, Any],
    reviewers: list[dict[str, Any]],
    *,
    segment: str,
) -> list[dict[str, Any]]:
    catalog = registry.get("evidence") or {}
    resolved: dict[str, dict[str, Any]] = {}
    for reviewer in reviewers:
        evidence_ids = _checklist_evidence(reviewer["checklist"])
        reviewer["evidence"] = evidence_ids
        for evidence_id in evidence_ids:
            config = catalog.get(evidence_id)
            if config is None:
                _refuse(
                    "REVIEW.UNKNOWN_EVIDENCE",
                    f"checklist 引用了未注册 evidence={evidence_id}",
                )
            if config.get("segment") != segment:
                continue
            existing = resolved.get(evidence_id)
            if existing is None:
                command = str(config["command"])
                existing = {
                    "id": evidence_id,
                    "command": command,
                    "segment": segment,
                    "required": bool(config.get("required", True)),
                    "covers": list(config.get("covers") or []),
                    "command_digest": _sha256_text(command),
                    "consumers": [],
                }
                resolved[evidence_id] = existing
            if reviewer["role"] not in existing["consumers"]:
                existing["consumers"].append(reviewer["role"])
    return list(resolved.values())


def _checklist_evidence(checklist: str) -> list[str]:
    path = REFERENCES_DIR / checklist
    if not path.is_file():
        _refuse("REVIEW.CHECKLIST_MISSING", f"checklist 不存在：{checklist}")
    evidence: dict[str, None] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _EVIDENCE_LINE_RE.match(line)
        if match:
            evidence.setdefault(match.group("evidence"))
    return list(evidence)


def _normalize_contexts(
    manifest: dict[str, Any],
    *,
    manifest_ref: str | None,
    expected_scope: str = "",
    required: bool = False,
) -> tuple[list[dict[str, Any]], int, str, dict[str, Any]]:
    if not manifest:
        if required:
            _refuse(
                "REVIEW.OWNER_MANIFEST_REQUIRED",
                "非控制型 workflow 的 POST Review 必须携带 current owner manifest",
            )
        return [], 0, "", declared_object(
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
            "owner_manifest_identity_fields",
        )
    expected_version = contract_schema_version("feature_context_manifest")
    if manifest.get("schema_version") != expected_version:
        _refuse(
            "REVIEW.OWNER_MANIFEST_SCHEMA_UNSUPPORTED",
            f"owner manifest schema_version 必须为 {expected_version}",
        )
    try:
        validate_feature_context_manifest(manifest)
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
    normalized_manifest_ref = _repo_relative(manifest_ref)
    manifest_path = REPO_ROOT / normalized_manifest_ref
    if not manifest_path.is_file() or manifest_path.is_symlink():
        _refuse(
            "REVIEW.OWNER_MANIFEST_INVALID",
            f"owner manifest ref 必须为仓库内 regular file：{normalized_manifest_ref}",
        )
    try:
        referenced = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", str(exc))
    if referenced != manifest:
        _refuse(
            "REVIEW.OWNER_MANIFEST_STALE",
            "owner manifest ref canonical bytes 已被替换",
        )
    target = _repo_relative(str(manifest["target"]))
    if expected_scope and target != _repo_relative(expected_scope):
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
        validate_current_feature_context_fingerprint(manifest, repo_root=REPO_ROOT)
    except EvidenceFingerprintError as exc:
        _refuse("REVIEW.OWNER_MANIFEST_STALE", str(exc))
    contexts: list[dict[str, Any]] = []
    for raw in manifest["canonical_contexts"]:
        relative = _repo_relative(str(raw["path"]))
        snapshot = _snapshot_path(relative)
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
    owner_identity = declared_object(
        {
            "ref": normalized_manifest_ref,
            "canonical_bytes_sha256": "sha256:" + __import__("hashlib").sha256(
                manifest_path.read_bytes()
            ).hexdigest(),
            "target": target,
            "scope": expected_scope or target,
            "resolved_owner": str(manifest["resolved_owner"]),
            "fingerprint_ref": binding["ref"],
            "fingerprint_digest": binding["digest"],
        },
        "review_plan",
        "owner_manifest_identity_fields",
    )
    return contexts, len(encoded), target, owner_identity


def _measure_reviewer_contexts(
    registry: dict[str, Any],
    *,
    workflow: str,
    workflow_config: dict[str, Any],
    active_profiles: list[str],
    reviewers: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
    manifest_bytes: int,
) -> dict[str, Any]:
    role_bytes: dict[str, int] = {}
    limit = int(registry["limits"]["reviewer_context_bytes"])
    grading = GRADING_PATH.read_bytes() if GRADING_PATH.is_file() else b""
    for reviewer in reviewers:
        role_path = REFERENCES_DIR / "roles" / reviewer["role"] / "ROLE.md"
        checklist_path = REFERENCES_DIR / reviewer["checklist"]
        if not role_path.is_file():
            _refuse("REVIEW.ROLE_MISSING", f"角色定义不存在：{reviewer['role']}")
        registry_slice = {
            "limits": registry["limits"],
            "workflow": {workflow: workflow_config},
            "profile": {
                reviewer["profile"]: (registry.get("profiles") or {}).get(
                    reviewer["profile"]
                )
            }
            if reviewer["profile"]
            else {},
            "evidence": reviewer.get("evidence") or [],
            "contexts": contexts,
        }
        total = (
            len(role_path.read_bytes())
            + len(checklist_path.read_bytes())
            + len(grading)
            + len(
                json.dumps(registry_slice, ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                )
            )
        )
        if total > limit:
            _refuse(
                "REVIEW.CONTEXT_BUDGET_EXCEEDED",
                f"role={reviewer['role']} context={total} bytes 超过 {limit}",
            )
        role_bytes[reviewer["role"]] = total
    return {
        "manifest": manifest_bytes,
        "reviewers": role_bytes,
        "max_reviewer": max(role_bytes.values(), default=0),
        "limit": limit,
    }


def _fingerprint_receipt(
    *,
    workflow: str,
    deliverable: str,
    scope: str,
    owner_manifest_identity: dict[str, Any],
    terminal: dict[str, Any],
    changed_paths: list[str],
    profiles: list[str],
    contexts: list[dict[str, Any]],
    initial_reviewers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_review_fingerprint(
        workflow=workflow,
        deliverable=deliverable,
        scope=scope,
        owner_manifest_identity=owner_manifest_identity,
        terminal=terminal,
        changed_paths=changed_paths,
        profiles=profiles,
        contexts=contexts,
        initial_reviewers=initial_reviewers,
        evidence=evidence,
    )


def recompute_plan_fingerprint(
    plan: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    """Rebuild current plan identity from workspace and canonical review assets."""

    _validate_plan_contract(plan)
    _validate_registry_header(registry)
    workflow = str(plan["workflow"])
    workflow_config = (registry.get("workflows") or {}).get(workflow)
    if not isinstance(workflow_config, dict):
        _refuse("REVIEW.UNKNOWN_WORKFLOW", f"workflow={workflow} 不在 registry")
    changed_paths = sorted({_repo_relative(path) for path in plan["changed_paths"]})
    deliverable = str(plan["deliverable"])
    profiles = derive_profiles(
        registry.get("profiles") or {}, changed_paths, deliverable
    )
    initial_reviewers = _select_initial_reviewers(
        registry,
        workflow=workflow,
        segment=str(plan["segment"]),
        workflow_config=workflow_config,
        active_profiles=profiles,
    )
    evidence = _resolve_evidence(
        registry, initial_reviewers, segment=str(plan["segment"])
    )
    contexts: list[dict[str, Any]] = []
    for raw in plan["contexts"]:
        relative = _repo_relative(str(raw["path"]))
        snapshot = _snapshot_path(relative)
        contexts.append(
            declared_object(
                {
                    "path": relative,
                    "anchor": raw["anchor"],
                    "kind": raw["kind"],
                    "exists": snapshot["exists"],
                    "content_digest": snapshot["content_digest"],
                },
                "review_plan",
                "context_fields",
            )
        )
    return _fingerprint_receipt(
        workflow=workflow,
        deliverable=deliverable,
        scope=str(plan["scope"]),
        owner_manifest_identity=dict(plan["owner_manifest_identity"]),
        terminal=dict(plan["terminal"]),
        changed_paths=changed_paths,
        profiles=profiles,
        contexts=contexts,
        initial_reviewers=initial_reviewers,
        evidence=evidence,
    )


def validate_plan_terminal_for_phase(
    plan: dict[str, Any], *, phase: str
) -> dict[str, Any]:
    terminal = plan.get("terminal")
    if not isinstance(terminal, dict):
        _refuse("REVIEW.TERMINAL_CONTRACT_INVALID", "Review plan terminal 缺失")
    validate_declared_fields(terminal, "review_plan", "terminal_fields")
    if phase not in {"evidence", "consolidation", "handoff"}:
        _refuse("REVIEW.TERMINAL_CONTRACT_INVALID", f"未知 Review phase={phase}")
    if terminal.get("status") != "READY" or terminal.get("codes") or terminal.get("failed_evidence"):
        _refuse(
            "REVIEW.TERMINAL_CONTRACT_INVALID",
            f"phase={phase} 只接受 initial READY plan；实际={terminal}",
        )
    return terminal


def _validate_current_owner_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    identity = plan.get("owner_manifest_identity")
    if not isinstance(identity, dict):
        _refuse("REVIEW.OWNER_MANIFEST_REQUIRED", "Review plan 缺 owner manifest identity")
    validate_declared_fields(
        identity, "review_plan", "owner_manifest_identity_fields"
    )
    raw_ref = identity.get("ref")
    if not isinstance(raw_ref, str) or not raw_ref:
        _refuse("REVIEW.OWNER_MANIFEST_REQUIRED", "Review plan 缺 owner manifest ref")
    ref = _repo_relative(raw_ref)
    path = REPO_ROOT / ref
    if not path.is_file() or path.is_symlink():
        _refuse("REVIEW.OWNER_MANIFEST_STALE", f"owner manifest ref stale：{ref}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", str(exc))
    if not isinstance(manifest, dict):
        _refuse("REVIEW.OWNER_MANIFEST_INVALID", "owner manifest 必须为 JSON object")
    if (
        "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        != identity.get("canonical_bytes_sha256")
    ):
        _refuse("REVIEW.OWNER_MANIFEST_STALE", "owner manifest canonical bytes 已漂移")
    if (
        manifest.get("target") != identity.get("target")
        or manifest.get("resolved_owner") != identity.get("resolved_owner")
        or identity.get("scope") != plan.get("scope")
    ):
        _refuse("REVIEW.OWNER_MANIFEST_TARGET_MISMATCH", "owner target/scope/owner 已漂移")
    binding = manifest.get("evidence_fingerprint") or {}
    if (
        binding.get("ref") != identity.get("fingerprint_ref")
        or binding.get("digest") != identity.get("fingerprint_digest")
    ):
        _refuse("REVIEW.OWNER_MANIFEST_STALE", "owner manifest fingerprint binding 已漂移")
    try:
        validate_feature_context_manifest(manifest)
        validate_current_feature_context_fingerprint(manifest, repo_root=REPO_ROOT)
        from lib.feature_tree.commands import _context_manifest, discover_nodes
        from lib.feature_tree.ownership import resolve_target_details

        nodes = discover_nodes()
        current = _context_manifest(
            str(manifest["target"]),
            resolve_target_details(str(manifest["target"]), nodes),
            nodes,
        )
    except (EvidenceFingerprintError, KeyError, TypeError, ValueError) as exc:
        _refuse("REVIEW.OWNER_MANIFEST_STALE", str(exc))
    for field in (
        "target", "resolved_owner", "owner_chain", "canonical_contexts",
        "applicable_agents", "profiles", "open_items",
    ):
        if current[field] != manifest[field]:
            _refuse(
                "REVIEW.OWNER_MANIFEST_STALE",
                f"current owner manifest {field} 已漂移",
            )
    return manifest


def validate_current_review_plan(
    plan: dict[str, Any], registry: dict[str, Any], *, phase: str = "evidence"
) -> dict[str, Any]:
    validate_plan_terminal_for_phase(plan, phase=phase)
    _validate_current_owner_manifest(plan)
    expected = validate_evidence_fingerprint(plan.get("fingerprint_receipt"))
    current = recompute_plan_fingerprint(plan, registry)
    for field in ("ref", "digest", "digest_payload"):
        if current[field] != expected[field]:
            _refuse(
                "REVIEW.FINGERPRINT_CHANGED",
                f"Review plan {field} 已 stale，必须对 current workspace 重跑 evidence",
            )
    return current


def build_reviewer_input(
    plan: dict[str, Any], evidence_identity: dict[str, Any]
) -> dict[str, Any]:
    validate_plan_terminal_for_phase(plan, phase="consolidation")
    payload = {
        "schema_version": contract_schema_version("reviewer_input"),
        "plan_fingerprint_ref": plan["fingerprint_receipt"]["ref"],
        "plan_fingerprint_digest": plan["fingerprint_receipt"]["digest"],
        "evidence_identity": evidence_identity,
        "reviewers": [
            {
                "role": item["role"],
                "kind": item["kind"],
                "required": item["required"],
                "checklist": item["checklist"],
            }
            for item in plan["reviewers"]
        ],
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    validate_required_fields(payload, "reviewer_input")
    for item in payload["reviewers"]:
        validate_declared_fields(item, "reviewer_input", "reviewer_fields")
    return payload


def _snapshot_path(relative: str) -> dict[str, Any]:
    """Compatibility helper retained for Review callers and tests."""

    return _review_snapshot(relative)


def _repo_relative(raw_path: str) -> str:
    try:
        return _review_normalize_path(raw_path)
    except EvidenceFingerprintError as exc:
        _refuse("REVIEW.PATH_OUTSIDE_REPOSITORY", str(exc))
    raise AssertionError("unreachable")


def _merge_base_sha() -> str:
    return _review_merge_base_sha()


def _classify_terminal(
    reviewers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    incomplete_roles: list[dict[str, str] | str],
    failed_evidence_ids: list[str],
    cancelled: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    typed: list[dict[str, Any]] = []
    codes: list[str] = []
    reviewer_map = {item["role"]: item for item in reviewers}
    for raw in incomplete_roles:
        if isinstance(raw, str):
            role, separator, reason = raw.partition("=")
            if not separator:
                role, reason = raw, "unspecified"
        else:
            role = str(raw.get("role") or "")
            reason = str(raw.get("reason") or "unspecified")
        reviewer = reviewer_map.get(role)
        if reviewer is None:
            _refuse(
                "REVIEW.INVALID_INCOMPLETE_ROLE",
                f"incomplete role 不在本轮 reviewers 中：{role}",
            )
        code = (
            "REVIEW.REQUIRED_REVIEWER_INCOMPLETE"
            if reviewer["required"]
            else "REVIEW.OPTIONAL_REVIEWER_INCOMPLETE"
        )
        typed.append(
            {
                "role": role,
                "required": reviewer["required"],
                "reason": reason,
                "code": code,
            }
        )
        codes.append(code)

    evidence_ids = {item["id"] for item in evidence}
    invalid_evidence = [item for item in failed_evidence_ids if item not in evidence_ids]
    if invalid_evidence:
        _refuse(
            "REVIEW.INVALID_EVIDENCE_RESULT",
            "失败 evidence 不在本轮计划中：" + ", ".join(invalid_evidence),
        )
    if failed_evidence_ids:
        codes.append("REVIEW.EVIDENCE_FAILED")
    if cancelled:
        codes.append("REVIEW.CANCELLED")

    unique_codes = list(dict.fromkeys(codes))
    terminal_contract = contract_section("terminal_codes")
    unknown_codes = [code for code in unique_codes if code not in terminal_contract]
    if unknown_codes:
        _refuse(
            "REVIEW.TERMINAL_CONTRACT_INVALID",
            "terminal code 未注册：" + ", ".join(unknown_codes),
        )
    status = "READY"
    if any(
        (terminal_contract.get(code) or {}).get("severity") == "GATE_BLOCK"
        for code in unique_codes
    ):
        status = "GATE_BLOCK"
    elif any(
        (terminal_contract.get(code) or {}).get("severity") == "PR_WARN"
        for code in unique_codes
    ):
        status = "PR_WARN"
    return typed, {
        "status": status,
        "codes": unique_codes,
        "failed_evidence": list(dict.fromkeys(failed_evidence_ids)),
    }


def _head_sha() -> str:
    return _review_head_sha()


def _sha256_text(value: str) -> str:
    return _review_sha256_text(value)


def _refuse(code: str, message: str) -> None:
    raise ReviewDispatchError(code, message)


def _load_json(path: str | None, *, label: str) -> dict[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.is_file():
        _refuse(f"REVIEW.{label.upper()}_MISSING", f"{label} 不存在：{path}")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _refuse(f"REVIEW.{label.upper()}_INVALID", f"{label} 必须是 JSON object")
    return value


def _resolve_output_dir(raw_path: str) -> Path:
    runtime_root_value = contract_section("runtime_outputs").get("root")
    if not isinstance(runtime_root_value, str) or not runtime_root_value:
        _refuse(
            "REVIEW.RUNTIME_OUTPUT_CONTRACT_INVALID",
            "runtime_outputs.root 必须为非空仓库相对路径",
        )
    runtime_root = (REPO_ROOT / runtime_root_value).resolve(strict=False)
    try:
        runtime_root.relative_to(REPO_ROOT.resolve())
    except ValueError:
        _refuse(
            "REVIEW.RUNTIME_OUTPUT_CONTRACT_INVALID",
            f"runtime_outputs.root 越出仓库：{runtime_root_value}",
        )
    candidate = Path(raw_path)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (REPO_ROOT / candidate).resolve(strict=False)
    )
    try:
        resolved.relative_to(runtime_root)
    except ValueError:
        _refuse(
            "REVIEW.OUTPUT_PATH_OUTSIDE_RUNTIME_ROOT",
            f"--out 必须位于 {runtime_root_value}/ 下：{raw_path}",
        )
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--segment", required=True, choices=["PRE", "POST"])
    parser.add_argument("--deliverable", default=None)
    parser.add_argument("--changed-paths", nargs="*", default=[])
    parser.add_argument("--scope", default="")
    parser.add_argument("--round", dest="round_name", choices=["initial", "rereview"], default="initial")
    parser.add_argument("--finding-owner", action="append", default=[])
    parser.add_argument("--previous-plan", default=None)
    parser.add_argument("--context-manifest", default=None)
    parser.add_argument("--incomplete-role", action="append", default=[])
    parser.add_argument("--evidence-failed", action="append", default=[])
    parser.add_argument("--cancelled", action="store_true")
    parser.add_argument("--out", default=None, help="评审产物目录；plan.json 写入其中")
    args = parser.parse_args(argv)

    try:
        out_dir = _resolve_output_dir(args.out) if args.out else None
        registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        plan = build_plan(
            registry,
            args.workflow,
            args.segment,
            args.deliverable,
            args.changed_paths,
            round_name=args.round_name,
            finding_owners=args.finding_owner,
            previous_plan=_load_json(args.previous_plan, label="previous_plan"),
            context_manifest=_load_json(args.context_manifest, label="context_manifest"),
            context_manifest_ref=args.context_manifest,
            scope=args.scope,
            incomplete_roles=args.incomplete_role,
            failed_evidence_ids=args.evidence_failed,
            cancelled=args.cancelled,
        )
    except (ReviewDispatchError, json.JSONDecodeError) as exc:
        if isinstance(exc, ReviewDispatchError):
            code, message = exc.code, exc.message
        else:
            code, message = "REVIEW.JSON_INVALID", str(exc)
        print(f"[review_dispatch] {code}: {message}", file=sys.stderr)
        return 2

    rendered = json.dumps(plan, ensure_ascii=False, indent=2)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "plan.json"
        plan_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"[review_dispatch] 派发清单已落盘：{plan_path}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
