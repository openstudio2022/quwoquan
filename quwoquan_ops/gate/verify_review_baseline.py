#!/usr/bin/env python3
"""Verify the exact evidence-runner Review plan without running tests or reviewers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = ROOT / "quwoquan_ops/cli"
for entry in (ROOT, CLI_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import review_dispatch  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    validate_declared_fields,
    validate_required_fields,
)
from lib.candidate_evidence import (  # noqa: E402
    CandidateEvidenceError,
    candidate_identity,
    validate_candidate_ref,
)
from lib.descriptor_safe_io import (  # noqa: E402
    read_regular_single_link_at,
    read_repo_relative_regular_single_link,
)
from lib.evidence_fingerprint import (  # noqa: E402
    normalize_repo_relative_path,
    validate_evidence_fingerprint,
)
from lib.feature_context_fingerprint import validate_content_addressed_ref  # noqa: E402
from lib.review_owner_manifest import read_owner_manifest_exact_bytes  # noqa: E402

PLAN_PATH_ENV = "QWQ_REVIEW_BASELINE_PLAN_PATH"
PLAN_SHA_ENV = "QWQ_REVIEW_BASELINE_PLAN_SHA256"
PLAN_REF_ENV = "QWQ_REVIEW_BASELINE_PLAN_REF"
REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class BaselineError(ValueError):
    pass


def _exact_plan_bytes() -> tuple[bytes, str]:
    raw_path = os.environ.get(PLAN_PATH_ENV, "")
    expected_sha = os.environ.get(PLAN_SHA_ENV, "")
    plan_ref = os.environ.get(PLAN_REF_ENV, "")
    if not raw_path or not expected_sha or not plan_ref:
        raise BaselineError("缺 evidence_runner 注入的 exact Review plan identity")
    if not SHA_RE.fullmatch(expected_sha):
        raise BaselineError("exact Review plan sha256 格式非法")
    try:
        canonical_plan_ref = normalize_repo_relative_path(plan_ref, ROOT)
    except ValueError as exc:
        raise BaselineError("exact Review plan ref 必须为仓库相对 canonical path") from exc
    if canonical_plan_ref != plan_ref:
        raise BaselineError("exact Review plan ref 未规范化")
    path = Path(raw_path)
    if not path.is_absolute():
        raise BaselineError("exact Review plan path 必须为 evidence_runner absolute temp path")
    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved_path = path.resolve(strict=True)
    try:
        resolved_path.relative_to(temp_root)
    except ValueError as exc:
        raise BaselineError("exact Review plan path 必须位于系统临时目录") from exc
    if not path.parent.name.startswith("qwq-review-evidence-plan-") or path.name != "exact-plan.json":
        raise BaselineError("exact Review plan path 不是 evidence_runner 受控路径")
    parent = path.parent
    try:
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise BaselineError("exact Review plan parent 必须为非 symlink directory")
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            raw = read_regular_single_link_at(
                directory_fd,
                path.name,
                display_path="evidence_runner exact Review plan",
                require_current_name=True,
            )
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise BaselineError(f"无法安全读取 exact Review plan: {exc}") from exc
    actual_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise BaselineError("exact Review plan bytes 与 evidence_runner sha256 不一致")
    try:
        source_raw = read_repo_relative_regular_single_link(ROOT, plan_ref)
    except (OSError, ValueError) as exc:
        raise BaselineError(f"exact Review plan ref 不是当前仓内安全文件: {exc}") from exc
    if source_raw != raw:
        raise BaselineError("exact Review plan ref bytes 与 evidence_runner 输入漂移")
    return raw, plan_ref


def _load_plan(raw: bytes) -> dict[str, Any]:
    try:
        plan = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"exact Review plan JSON 非法: {exc}") from exc
    if not isinstance(plan, dict):
        raise BaselineError("exact Review plan 必须为 JSON object")
    if plan.get("schema_version") != contract_schema_version("review_plan"):
        raise BaselineError("exact Review plan schema_version 漂移")
    validate_required_fields(plan, "review_plan")
    review_dispatch._validate_plan_contract(plan)
    return plan


def _validate_owner_and_candidate(plan: dict[str, Any]) -> None:
    owner = plan["owner_identity"]
    candidate = plan["candidate_evidence_identity"]
    owner_ref = owner.get("ref")
    candidate_ref = candidate.get("ref")
    if not isinstance(owner_ref, str) or not owner_ref:
        raise BaselineError("Review plan 缺 PRE owner identity ref")
    if not isinstance(candidate_ref, str) or not candidate_ref:
        raise BaselineError("Review plan 缺 candidate evidence ref")
    owner_raw = read_owner_manifest_exact_bytes(owner_ref, repo_root=ROOT)
    validate_content_addressed_ref(owner_ref, raw_bytes=owner_raw, repo_root=ROOT)
    if owner.get("canonical_bytes_sha256") != "sha256:" + hashlib.sha256(owner_raw).hexdigest():
        raise BaselineError("PRE owner identity exact bytes binding 漂移")
    try:
        ref, candidate_raw, payload, fingerprint = validate_candidate_ref(
            candidate_ref,
            repo_root=ROOT,
            expected_owner_identity_ref=owner_ref,
            expected_changed_paths=list(plan["changed_paths"]),
        )
    except CandidateEvidenceError as exc:
        raise BaselineError(f"{exc.code}: {exc.message}") from exc
    if candidate_identity(ref, candidate_raw, payload, fingerprint) != candidate:
        raise BaselineError("candidate evidence exact identity binding 漂移")
    if payload["target"] != owner.get("target") or payload["resolved_owner"] != owner.get("resolved_owner"):
        raise BaselineError("PRE owner identity 与 candidate evidence owner facts 漂移")
    if owner.get("scope") != plan.get("scope"):
        raise BaselineError("PRE owner identity 与 Review scope 漂移")


def _validate_registry_closure(plan: dict[str, Any], registry: dict[str, Any]) -> None:
    review_dispatch._validate_registry_header(registry)
    workflow = (registry.get("workflows") or {}).get(plan["workflow"])
    if not isinstance(workflow, dict):
        raise BaselineError("Review workflow 不在 exact registry")
    profiles = review_dispatch.derive_profiles(
        registry.get("profiles") or {}, list(plan["changed_paths"]), str(plan["deliverable"])
    )
    if profiles != plan["profiles"]:
        raise BaselineError("Review changed paths/profile binding 漂移")
    if str(plan["segment"]) != "POST" or workflow.get("automatic_review") is False:
        raise BaselineError("review-baseline 只接受 automatic POST Review plan")
    expected_reviewers = review_dispatch._select_initial_reviewers(
        registry,
        workflow=str(plan["workflow"]),
        segment=str(plan["segment"]),
        workflow_config=workflow,
        active_profiles=profiles,
    )
    expected_evidence = review_dispatch._resolve_evidence(
        registry,
        expected_reviewers,
        segment=str(plan["segment"]),
        baseline_evidence=str(workflow.get("baseline_evidence") or ""),
    )
    for reviewer in expected_reviewers:
        checklist = ROOT / ".agents/skills/review/references" / reviewer["checklist"]
        if not checklist.is_file() or checklist.is_symlink():
            raise BaselineError(f"Review checklist 非 regular canonical file: {reviewer['checklist']}")
        checklist_evidence = review_dispatch._checklist_evidence(reviewer["checklist"])
        expected_ids = list(dict.fromkeys(
            ([str(workflow.get("baseline_evidence"))] if workflow.get("baseline_evidence") else [])
            + checklist_evidence
        ))
        if reviewer["evidence"] != expected_ids:
            raise BaselineError(f"Review checklist/evidence closure 漂移: {reviewer['checklist']}")
    expected_reviewer_projection = [
        {key: item[key] for key in (
            "role", "kind", "required", "profile", "checklist", "evidence",
        )}
        for item in expected_reviewers
    ]
    actual_reviewer_projection = [
        {key: item[key] for key in (
            "role", "kind", "required", "profile", "checklist", "evidence",
        )}
        for item in plan["reviewers"]
    ]
    if expected_reviewer_projection != actual_reviewer_projection:
        raise BaselineError("Review owner/profile/checklist binding 漂移")
    expected_projection = [
        {key: item[key] for key in (
            "id", "command", "segment", "required", "covers", "timeout_seconds",
            "command_digest", "consumers", "result_artifact",
        )}
        for item in expected_evidence
    ]
    actual_projection = [
        {key: item[key] for key in (
            "id", "command", "segment", "required", "covers", "timeout_seconds",
            "command_digest", "consumers", "result_artifact",
        )}
        for item in plan["evidence"]
    ]
    if expected_projection != actual_projection:
        raise BaselineError("Review evidence registry closure 漂移")


def verify() -> dict[str, str]:
    raw, plan_ref = _exact_plan_bytes()
    plan = _load_plan(raw)
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(registry, dict):
        raise BaselineError("Review registry 必须为 mapping")
    _validate_owner_and_candidate(plan)
    _validate_registry_closure(plan, registry)
    expected = validate_evidence_fingerprint(plan["fingerprint_receipt"])
    current = review_dispatch.recompute_plan_fingerprint(plan, registry)
    if any(expected[field] != current[field] for field in ("ref", "digest", "digest_payload")):
        raise BaselineError("Review exact plan fingerprint/registry/checklist binding 漂移")
    if plan.get("fingerprint") != current["digest"]:
        raise BaselineError("Review exact plan fingerprint 字段漂移")
    return {"status": "PASS", "plan_ref": plan_ref, "plan_sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}


def main() -> int:
    try:
        result = verify()
    except (BaselineError, OSError, TypeError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f"[review-baseline] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
