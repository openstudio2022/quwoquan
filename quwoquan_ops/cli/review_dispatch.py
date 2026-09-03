#!/usr/bin/env python3
"""Generate one bounded Review Board v2 plan from the canonical registry.

PRE never spawns reviewers. POST selects the workflow primary reviewer and at
most one profile specialist. Evidence commands are named registry entries and
are executed by the board before dispatch, never by reviewers.
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / ".agents/skills/review/references"
REGISTRY_PATH = REFERENCES_DIR / "registry.yaml"
GRADING_PATH = REFERENCES_DIR / "grading.md"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
from lib import review_dispatch_cli as _review_dispatch_cli  # noqa: E402
from lib import review_owner_manifest as _review_owner_manifest  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    contract_section,
    declared_object,
    validate_declared_fields,
    validate_required_fields,
)
from lib.feature_context_fingerprint import (  # noqa: E402
    build_feature_context_fingerprint,
    embedded_fingerprint_binding,
)
from lib.evidence_fingerprint import (  # noqa: E402
    EvidenceFingerprintError,
    snapshot_path,
    validate_evidence_fingerprint,
)
from lib.human_agent_delivery.runtime_bridge import (  # noqa: E402
    HumanDecisionBridgeError,
    project_runtime_decision,
)
from lib.review_fingerprint import (  # noqa: E402
    build_review_fingerprint,
    head_sha as _review_head_sha,
    merge_base_sha as _review_merge_base_sha,
    normalize_path as _review_normalize_path,
    sha256_text as _review_sha256_text,
    snapshot as _review_snapshot,
)
from lib.review_context_assembler import (  # noqa: E402
    ReviewerContextBudgetExceeded,
    assemble_reviewer_context,
)
from review_dispatch_terminal import (  # noqa: E402
    classify_terminal as _classify_terminal_impl,
)

_EVIDENCE_LINE_RE = re.compile(r"^\s*evidence:\s*(?P<evidence>[a-z0-9][a-z0-9-]*)\s*$")
ReviewDispatchError = _review_owner_manifest.ReviewDispatchError
_OWNER_MANIFEST_DIRECTORY_PARTS = (
    _review_owner_manifest.OWNER_MANIFEST_DIRECTORY_PARTS
)
os = _review_owner_manifest.os
validate_feature_context_manifest = (
    _review_owner_manifest.validate_feature_context_manifest
)
validate_current_feature_context_fingerprint = (
    _review_owner_manifest.validate_current_feature_context_fingerprint
)

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
    candidate_evidence_ref: str | None = None,
    human_decision_ref: str | None = None,
    admission_class: str = "ordinary",
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
    try:
        human_decision_projection = project_runtime_decision(
            target_kind="review",
            admission_class=admission_class,
            human_decision_ref=human_decision_ref,
        )
    except HumanDecisionBridgeError as exc:
        raise ValueError(f"{exc.code}: {exc.detail}") from exc
    manifest_required = segment == "POST" and automatic_review
    contexts, manifest_bytes, manifest_target, owner_identity, candidate_evidence_identity = _normalize_contexts(
        context_manifest or {},
        manifest_ref=context_manifest_ref,
        candidate_evidence_ref=candidate_evidence_ref,
        changed_paths=normalized_paths,
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
        registry,
        initial_reviewers,
        segment=segment,
        baseline_evidence=(
            str(workflow_config.get("baseline_evidence") or "")
            if automatic_review
            else ""
        ),
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
        owner_identity=owner_identity,
        candidate_evidence_identity=candidate_evidence_identity,
        human_decision_projection=human_decision_projection,
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
        "owner_identity": owner_identity,
        "candidate_evidence_identity": candidate_evidence_identity,
        "human_decision_ref": human_decision_ref,
        "human_decision_projection": human_decision_projection,
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
    owner_identity = plan["owner_identity"]
    candidate_identity = plan["candidate_evidence_identity"]
    if not isinstance(owner_identity, dict) or not isinstance(candidate_identity, dict):
        raise TypeError("review_plan 双身份必须为映射")
    validate_declared_fields(owner_identity, "review_plan", "owner_identity_fields")
    validate_declared_fields(candidate_identity, "review_plan", "candidate_evidence_identity_fields")
    human_projection = plan["human_decision_projection"]
    if not isinstance(human_projection, dict):
        raise TypeError("review_plan.human_decision_projection 必须为映射")
    validate_declared_fields(
        human_projection, "review_plan", "human_decision_projection_fields"
    )
    if plan["human_decision_ref"] != human_projection["human_decision_ref"]:
        raise ValueError("review_plan human decision ref/projection 不一致")
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
    max_evidence_timeout = limits.get("max_evidence_timeout_seconds")
    if max_evidence_timeout != 3600:
        _refuse(
            "REVIEW.INVALID_LIMIT",
            "max_evidence_timeout_seconds 必须为 3600",
        )
    commands: dict[str, str] = {}
    for evidence_id, config in (registry.get("evidence") or {}).items():
        if not isinstance(config, dict):
            _refuse(
                "REVIEW.INVALID_EVIDENCE",
                f"evidence={evidence_id} 必须为 mapping",
            )
        if not isinstance(config.get("covers"), list):
            _refuse(
                "REVIEW.INVALID_EVIDENCE",
                f"evidence={evidence_id} 必须显式声明 covers list",
            )
        timeout_seconds = config.get("timeout_seconds")
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
            or timeout_seconds > max_evidence_timeout
        ):
            _refuse(
                "REVIEW.INVALID_EVIDENCE",
                f"evidence={evidence_id} timeout_seconds 必须为 1..{max_evidence_timeout} 的整数",
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
    baseline_evidence: str = "",
) -> list[dict[str, Any]]:
    catalog = registry.get("evidence") or {}
    resolved: dict[str, dict[str, Any]] = {}
    evidence_consumers: dict[str, list[str]] = {}
    for reviewer in reviewers:
        evidence_ids = list(dict.fromkeys(
            ([baseline_evidence] if baseline_evidence else [])
            + _checklist_evidence(reviewer["checklist"])
        ))
        reviewer["evidence"] = evidence_ids
        for evidence_id in evidence_ids:
            evidence_consumers.setdefault(evidence_id, []).append(reviewer["role"])

    for evidence_id, consumers in evidence_consumers.items():
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
                    "timeout_seconds": int(config["timeout_seconds"]),
                    "command_digest": _sha256_text(command),
                    "consumers": [],
                }
                resolved[evidence_id] = existing
            for role in consumers:
                if role not in existing["consumers"]:
                    existing["consumers"].append(role)
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


def _read_owner_manifest_exact_bytes(manifest_ref: str) -> bytes:
    """Compatibility export for the descriptor-relative exact-ref reader."""

    return _review_owner_manifest.read_owner_manifest_exact_bytes(
        manifest_ref, repo_root=REPO_ROOT
    )


def _normalize_contexts(
    manifest: dict[str, Any],
    *,
    manifest_ref: str | None,
    candidate_evidence_ref: str | None = None,
    changed_paths: list[str] | None = None,
    expected_scope: str = "",
    required: bool = False,
) -> tuple[list[dict[str, Any]], int, str, dict[str, Any]]:
    return _review_owner_manifest.normalize_contexts(
        manifest,
        manifest_ref=manifest_ref,
        candidate_evidence_ref=candidate_evidence_ref,
        changed_paths=changed_paths,
        expected_scope=expected_scope,
        required=required,
        repo_root=REPO_ROOT,
        reader=_read_owner_manifest_exact_bytes,
        validate_manifest=validate_feature_context_manifest,
        validate_current_fingerprint=validate_current_feature_context_fingerprint,
    )

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
    """Record only the configured hard boundary; final bytes are assembled later."""
    del workflow, workflow_config, active_profiles, contexts
    limit = int(registry["limits"]["reviewer_context_bytes"])
    estimates: dict[str, int] = {}
    grading = GRADING_PATH.read_bytes() if GRADING_PATH.is_file() else b""
    system_path = REFERENCES_DIR / "reviewer-executor.md"
    system = system_path.read_bytes() if system_path.is_file() else b""
    for reviewer in reviewers:
        role_path = REFERENCES_DIR / "roles" / reviewer["role"] / "ROLE.md"
        checklist_path = REFERENCES_DIR / reviewer["checklist"]
        if not role_path.is_file():
            _refuse("REVIEW.ROLE_MISSING", f"角色定义不存在：{reviewer['role']}")
        estimates[reviewer["role"]] = (
            len(system) + len(role_path.read_bytes()) + len(checklist_path.read_bytes()) + len(grading)
        )
    return {
        "manifest": manifest_bytes,
        "reviewers": estimates,
        "max_reviewer": max(estimates.values(), default=0),
        "limit": limit,
    }


def _fingerprint_receipt(
    *,
    workflow: str,
    deliverable: str,
    scope: str,
    owner_identity: dict[str, Any],
    candidate_evidence_identity: dict[str, Any],
    terminal: dict[str, Any],
    changed_paths: list[str],
    profiles: list[str],
    contexts: list[dict[str, Any]],
    initial_reviewers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    human_decision_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_review_fingerprint(
        workflow=workflow,
        deliverable=deliverable,
        scope=scope,
        owner_identity=owner_identity,
        candidate_evidence_identity=candidate_evidence_identity,
        human_decision_projection=(
            human_decision_projection
            if human_decision_projection is not None
            else project_runtime_decision(target_kind="review")
        ),
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
        registry,
        initial_reviewers,
        segment=str(plan["segment"]),
        baseline_evidence=str(workflow_config.get("baseline_evidence") or ""),
    )
    contexts = [declared_object(dict(raw), "review_plan", "context_fields") for raw in plan["contexts"]]
    return _fingerprint_receipt(
        workflow=workflow,
        deliverable=deliverable,
        scope=str(plan["scope"]),
        owner_identity=dict(plan["owner_identity"]),
        candidate_evidence_identity=dict(plan["candidate_evidence_identity"]),
        human_decision_projection=dict(plan["human_decision_projection"]),
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
    return _review_owner_manifest.validate_current_owner_manifest(
        plan,
        repo_root=REPO_ROOT,
        reader=_read_owner_manifest_exact_bytes,
        validate_manifest=validate_feature_context_manifest,
        validate_current_fingerprint=validate_current_feature_context_fingerprint,
    )

def validate_current_review_plan(
    plan: dict[str, Any], registry: dict[str, Any], *, phase: str = "evidence"
) -> dict[str, Any]:
    validate_plan_terminal_for_phase(plan, phase=phase)
    try:
        current_human_projection = project_runtime_decision(
            target_kind="review",
            admission_class=str(plan["human_decision_projection"]["admission_class"]),
            human_decision_ref=plan["human_decision_ref"],
        )
    except HumanDecisionBridgeError as exc:
        _refuse("REVIEW.FINGERPRINT_CHANGED", f"{exc.code}: {exc.detail}")
    if current_human_projection != plan["human_decision_projection"]:
        _refuse(
            "REVIEW.FINGERPRINT_CHANGED",
            "Review plan human decision ref/projection 已漂移",
        )
    if current_human_projection["blocks_execution"]:
        _refuse(
            "REVIEW.TERMINAL_CONTRACT_INVALID",
            f"{current_human_projection['terminal']}: human decision 阻止 phase={phase}",
        )
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
    plan: dict[str, Any],
    evidence_identity: dict[str, Any],
    *,
    evidence_summary: dict[str, Any] | None = None,
    reviewer_role: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build one exact final reviewer payload and enforce its canonical byte size."""
    validate_plan_terminal_for_phase(plan, phase="consolidation")
    selected = [
        item for item in plan["reviewers"]
        if reviewer_role is None or item["role"] == reviewer_role
    ]
    if len(selected) != 1:
        _refuse(
            "REVIEW.INVALID_INCOMPLETE_ROLE",
            "reviewer input 必须指定且只指定一个已派发 reviewer role",
        )
    reviewer = selected[0]
    role_path = REFERENCES_DIR / "roles" / reviewer["role"] / "ROLE.md"
    checklist_path = REFERENCES_DIR / reviewer["checklist"]
    system_path = REFERENCES_DIR / "reviewer-executor.md"
    for label, path in (("system", system_path), ("role", role_path), ("checklist", checklist_path), ("grading", GRADING_PATH)):
        if not path.is_file():
            _refuse("REVIEW.ROLE_MISSING", f"{label} reviewer prompt 不存在：{path.relative_to(REPO_ROOT)}")
    try:
        assembled = assemble_reviewer_context(
            plan=plan,
            reviewer=reviewer,
            evidence_identity=evidence_identity,
            evidence_summary=evidence_summary or {},
            system_prompt=system_path.read_text(encoding="utf-8"),
            role_prompt=role_path.read_text(encoding="utf-8"),
            checklist_prompt=checklist_path.read_text(encoding="utf-8"),
            grading_prompt=GRADING_PATH.read_text(encoding="utf-8"),
            repo_root=repo_root,
            limit=int(plan["context_bytes"]["limit"]),
        )
    except ReviewerContextBudgetExceeded as exc:
        _refuse("REVIEW.CONTEXT_BUDGET_EXCEEDED", str(exc))
    payload = {
        "schema_version": contract_schema_version("reviewer_input"),
        "plan_fingerprint_ref": plan["fingerprint_receipt"]["ref"],
        "plan_fingerprint_digest": plan["fingerprint_receipt"]["digest"],
        "evidence_identity": evidence_identity,
        "reviewer": {
            "role": reviewer["role"],
            "kind": reviewer["kind"],
            "required": reviewer["required"],
            "profile": reviewer["profile"],
            "checklist": reviewer["checklist"],
        },
        **assembled,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    validate_required_fields(payload, "reviewer_input")
    validate_declared_fields(payload["reviewer"], "reviewer_input", "reviewer_fields")
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
    return _classify_terminal_impl(
        reviewers,
        evidence,
        incomplete_roles=incomplete_roles,
        failed_evidence_ids=failed_evidence_ids,
        cancelled=cancelled,
        contract_section=contract_section,
        refuse=_refuse,
    )


def _head_sha() -> str:
    return _review_head_sha()


def _sha256_text(value: str) -> str:
    return _review_sha256_text(value)


def _refuse(code: str, message: str) -> None:
    raise ReviewDispatchError(code, message)


def main(argv: list[str] | None = None) -> int:
    runtime_output_root = contract_section("runtime_outputs").get("root")
    return _review_dispatch_cli.main(
        argv,
        description=__doc__.splitlines()[0],
        repo_root=REPO_ROOT,
        registry_path=REGISTRY_PATH,
        runtime_output_root=(
            runtime_output_root if isinstance(runtime_output_root, str) else ""
        ),
        build_plan=build_plan,
        refuse=_refuse,
        error_type=ReviewDispatchError,
    )


if __name__ == "__main__":
    sys.exit(main())
