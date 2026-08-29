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
import hashlib
import json
import os
import re
import subprocess
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
    contract_schema_version,
    contract_section,
    declared_object,
    validate_declared_fields,
    validate_feature_context_manifest,
    validate_required_fields,
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
    resolved_scope = scope or (normalized_previous or {}).get("scope") or ""
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

    contexts, manifest_bytes = _normalize_contexts(context_manifest or {})
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
    fingerprint = _fingerprint(
        workflow=workflow,
        deliverable=resolved_deliverable,
        scope=resolved_scope,
        changed_paths=normalized_paths,
        profiles=active_profiles,
        contexts=contexts,
        initial_reviewers=initial_reviewers,
        evidence=evidence,
    )
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

    normalized_incomplete, terminal = _classify_terminal(
        reviewers,
        evidence,
        incomplete_roles=incomplete_roles or [],
        failed_evidence_ids=failed_evidence_ids or [],
        cancelled=cancelled,
    )
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
        "changed_paths": normalized_paths,
        "profiles": active_profiles,
        "contexts": contexts,
        "reviewers": reviewers,
        "skipped_reviewers": skipped_reviewers,
        "evidence": evidence,
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
) -> tuple[list[dict[str, Any]], int]:
    if not manifest:
        return [], 0
    try:
        validate_feature_context_manifest(manifest)
    except (KeyError, TypeError, ValueError) as exc:
        _refuse("REVIEW.CONTEXT_MANIFEST_INVALID", str(exc))
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest_limit = int(contract_section("feature_context_manifest")["max_bytes"])
    if len(encoded) > manifest_limit:
        _refuse(
            "REVIEW.CONTEXT_MANIFEST_BUDGET_EXCEEDED",
            f"manifest={len(encoded)} bytes 超过 {manifest_limit}",
        )
    raw_contexts = manifest["canonical_contexts"]
    contexts: list[dict[str, Any]] = []
    for raw in raw_contexts:
        if not isinstance(raw, dict) or "path" not in raw:
            _refuse("REVIEW.CONTEXT_MANIFEST_INVALID", "canonical_contexts 项缺 path")
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
    return contexts, len(encoded)


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


def _fingerprint(
    *,
    workflow: str,
    deliverable: str,
    scope: str,
    changed_paths: list[str],
    profiles: list[str],
    contexts: list[dict[str, Any]],
    initial_reviewers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> str:
    assets: list[dict[str, Any]] = [_snapshot_path(REGISTRY_PATH.relative_to(REPO_ROOT).as_posix())]
    if GRADING_PATH.is_file():
        assets.append(_snapshot_path(GRADING_PATH.relative_to(REPO_ROOT).as_posix()))
    for reviewer in initial_reviewers:
        assets.append(
            _snapshot_path(
                f".agents/skills/review/references/roles/{reviewer['role']}/ROLE.md"
            )
        )
        assets.append(
            _snapshot_path(
                (REFERENCES_DIR / reviewer["checklist"])
                .relative_to(REPO_ROOT)
                .as_posix()
            )
        )
    payload = declared_object(
        {
            "head_sha": _head_sha(),
            "workflow": workflow,
            "deliverable": deliverable,
            "scope": scope,
            "changed_paths": [_snapshot_path(path) for path in changed_paths],
            "profiles": profiles,
            "contexts": contexts,
            "reviewers": [
                declared_object(
                    {
                        "role": item["role"],
                        "kind": item["kind"],
                        "required": item["required"],
                        "profile": item["profile"],
                        "checklist": item["checklist"],
                    },
                    "review_plan",
                    "fingerprint_reviewer_fields",
                )
                for item in initial_reviewers
            ],
            "review_assets": assets,
            "evidence": [
                declared_object(
                    {
                        "id": item["id"],
                        "required": item["required"],
                        "covers": item["covers"],
                        "command_digest": item["command_digest"],
                    },
                    "review_plan",
                    "fingerprint_evidence_fields",
                )
                for item in evidence
            ],
        },
        "review_plan",
        "fingerprint_inputs",
    )
    rendered = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _sha256_text(rendered)


def _snapshot_path(relative: str) -> dict[str, Any]:
    normalized = _repo_relative(relative)
    path = REPO_ROOT / normalized
    tracked = _is_tracked(normalized)
    status = _git_status(normalized)
    if path.is_symlink():
        target = os.readlink(path)
        return _fingerprint_snapshot(
            normalized, True, "symlink", tracked, status, _sha256_text(target)
        )
    if path.is_file():
        return _fingerprint_snapshot(
            normalized,
            True,
            "file",
            tracked,
            status,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    if path.is_dir():
        children: list[dict[str, str]] = []
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            child_relative = child.relative_to(REPO_ROOT).as_posix()
            children.append(
                {
                    "path": child_relative,
                    "digest": hashlib.sha256(child.read_bytes()).hexdigest(),
                }
            )
        return _fingerprint_snapshot(
            normalized,
            True,
            "directory",
            tracked,
            status,
            _sha256_text(
                json.dumps(children, sort_keys=True, separators=(",", ":"))
            ),
        )
    return _fingerprint_snapshot(
        normalized,
        False,
        "deleted" if _exists_at_head(normalized) else "missing",
        tracked,
        status,
        _head_blob_digest(normalized),
    )


def _fingerprint_snapshot(
    path: str,
    exists: bool,
    state: str,
    tracked: bool,
    git_status: str,
    content_digest: str | None,
) -> dict[str, Any]:
    return declared_object(
        {
            "path": path,
            "exists": exists,
            "state": state,
            "tracked": tracked,
            "git_status": git_status,
            "content_digest": content_digest,
        },
        "review_plan",
        "fingerprint_snapshot_fields",
    )


def _repo_relative(raw_path: str) -> str:
    path = Path(raw_path)
    resolved = path.resolve(strict=False) if path.is_absolute() else (REPO_ROOT / path).resolve(strict=False)
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        _refuse("REVIEW.PATH_OUTSIDE_REPOSITORY", f"路径不在仓库内：{raw_path}")
    raise AssertionError("unreachable")


def _is_tracked(relative: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _git_status(relative: str) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", relative],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _exists_at_head(relative: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{relative}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _head_blob_digest(relative: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None


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
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
