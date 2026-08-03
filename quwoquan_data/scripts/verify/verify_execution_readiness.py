"""Validate one immutable content execution work package before release."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.article_package import compute_document_sha256
from content.execution.runtime_contract import file_sha256
from core.io import read_json
from core.paths import DATA_EXECUTIONS_ROOT, is_execution_id
from core.schema import assert_valid
from content.execution.workspace import load_execution_manifest
from content.execution.identity import parse_execution_id
from content.execution.post_review_closure import load_post_review_closure
from core.control_types import ContentType, expected_content_generator
from verify.verify_content_execution_layout import content_execution_layout_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report


_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")


def _normalize_model_id(model: object) -> str:
    """Normalize provider-prefixed model ids so readiness aliases compare equal.

    Cursor Agent may persist `cursor-grok-4-5` while execution readiness records
    `grok-4.5`; those name the same commercial model family binding.
    """
    text = str(model or "").strip().lower().replace("_", "-")
    if text.startswith("cursor-"):
        text = text[len("cursor-") :]
    text = text.replace("grok-4-5", "grok-4.5")
    return text


def _read_valid_json(path: Path, schema_group: str, schema_name: str, issues: list[str]) -> dict:
    if not path.is_file():
        issues.append(f"{path}: required evidence is missing")
        return {}
    try:
        payload = read_json(path)
        assert_valid(payload, schema_group, schema_name, label=path.as_posix())
    except (OSError, ValueError, TypeError) as exc:
        issues.append(f"{path}: invalid evidence ({exc})")
        return {}
    return payload if isinstance(payload, dict) else {}


def _terminal_execution_issues(root: Path, execution_id: str) -> list[str]:
    state_path = root / "_shared" / "execution_state.json"
    if not state_path.is_file():
        return [f"{state_path}: execution completion state is missing"]
    try:
        state = read_json(state_path)
        assert_valid(state, "execution", "execution_state", label=state_path.as_posix())
    except (OSError, ValueError, TypeError) as exc:
        return [f"{state_path}: execution state is invalid ({exc})"]
    if str(state.get("executionId") or "") != execution_id:
        return [f"{state_path}: executionId drift"]

    issues: list[str] = []
    if str(state.get("status") or "") != "succeeded":
        issues.append(f"execution status is not succeeded ({state.get('status') or 'missing'})")
    if state.get("waitingCheckpoint"):
        issues.append(f"execution still waiting at {state.get('waitingCheckpoint')}")
    for field in ("activeAutoResearch", "activeAgentScheduler"):
        if state.get(field):
            issues.append(f"execution still has {field}")
    for field in ("failedObjects", "completionGateIssues"):
        rows = state.get(field) or []
        if rows:
            issues.append(f"execution has {field}={len(rows)}")
    return issues


def _execution_model_readiness(root: Path, execution_id: str, issues: list[str]) -> dict:
    payload = _read_valid_json(
        root / "evidence" / "model_readiness.json", "execution", "model_readiness", issues
    )
    if not payload:
        return {}
    if str(payload.get("executionId") or "") != execution_id:
        issues.append("execution model readiness executionId drift")
        return {}
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {}
    if not author or not reviewer:
        issues.append("execution model readiness author/reviewer binding is incomplete")
        return {}
    return payload


def _resolve_homepage_quota_verdict(execution_id: str) -> Any:
    """Resolve the canonical homepage quota verdict behind an isolation seam."""
    from content.execution.controller.homepage_authoring import (
        homepage_quota_verdict,
    )
    from content.execution import store as execution_store
    from types import SimpleNamespace

    return homepage_quota_verdict(
        SimpleNamespace(
            execution_id=execution_id,
            spec=execution_store.load_spec_model(execution_id),
        )
    )


def _reviewed_object_issues(
    root: Path,
    object_root: Path,
    execution_id: str,
    *,
    model_readiness: dict,
    content_type: ContentType,
) -> list[str]:
    rel = object_root.relative_to(root)
    issues: list[str] = []
    missing = [stage for stage in _STAGES if not (object_root / stage).is_dir()]
    if missing:
        return [f"{rel}: missing stages {', '.join(missing)}"]

    draft_dir = object_root / "4.draft"
    draft_meta = _read_valid_json(draft_dir / "draft_meta.json", "content", "draft_meta", issues)
    draft_page = draft_dir / "page.md"
    if content_type is ContentType.ARTICLE:
        draft_page = draft_dir / "draft.article.md"
    elif content_type is ContentType.VIDEO:
        draft_page = draft_dir / "video_script.json"
    elif content_type is ContentType.IMAGE:
        draft_page = Path()
    if draft_meta:
        if str(draft_meta.get("executionId") or "") != execution_id:
            issues.append(f"{rel}/4.draft: executionId drift")
        if str(draft_meta.get("executionBinding") or "") != "frozen":
            issues.append(f"{rel}/4.draft: execution binding is not frozen")
        if str(draft_meta.get("status") or "") != "completed":
            issues.append(f"{rel}/4.draft: author status is not completed")
        self_check = draft_meta.get("selfCheck") if isinstance(draft_meta.get("selfCheck"), dict) else {}
        if str(self_check.get("status") or "") != "passed" or list(self_check.get("issues") or []):
            issues.append(f"{rel}/4.draft: author self-check did not pass")
        if not str(draft_meta.get("agentRunId") or "").strip():
            issues.append(f"{rel}/4.draft: agentRunId is missing")
        author = model_readiness.get("author") if isinstance(model_readiness.get("author"), dict) else {}
        if author and _normalize_model_id(draft_meta.get("model")) != _normalize_model_id(
            author.get("model")
        ):
            issues.append(f"{rel}/4.draft: author model drift from execution readiness")
        if content_type is ContentType.IMAGE:
            if not str(draft_meta.get("draftSha256") or "").startswith("sha256:"):
                issues.append(f"{rel}/4.draft: image evidence digest is missing")
        elif not draft_page.is_file():
            issues.append(f"{rel}/4.draft: page.md is missing")
        else:
            try:
                actual_digest = (
                    file_sha256(draft_page)
                    if content_type is ContentType.VIDEO
                    else compute_document_sha256(draft_page.read_text(encoding="utf-8"))
                )
            except OSError as exc:
                issues.append(f"{rel}/4.draft: page.md is unreadable ({exc})")
            else:
                if str(draft_meta.get("draftSha256") or "") != actual_digest:
                    issues.append(f"{rel}/4.draft: draftSha256 drift")

    manifest_path = object_root / "manifest.json"
    if not manifest_path.is_file():
        issues.append(f"{rel}/manifest.json: required evidence is missing")
    else:
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"{rel}/manifest.json: invalid manifest ({exc})")
            manifest = {}
        if not isinstance(manifest, dict):
            issues.append(f"{rel}/manifest.json: manifest must be an object")
            manifest = {}
        if manifest:
            expected_generator = expected_content_generator(content_type)
            if str(manifest.get("generator") or "") != expected_generator.value:
                issues.append(
                    f"{rel}/manifest.json: generator must be {expected_generator.value}"
                )
            if content_type is ContentType.HOMEPAGE:
                if not str(manifest.get("agentRunId") or "").strip():
                    issues.append(f"{rel}/manifest.json: agentRunId is missing")
                if draft_meta and manifest.get("agentRunId") != draft_meta.get("agentRunId"):
                    issues.append(f"{rel}/manifest.json: agentRunId drift from draft_meta")
            elif str(manifest.get("contentType") or "") != content_type.value:
                issues.append(f"{rel}/manifest.json: contentType drift")

    review_dir = object_root / "5.review"
    reviewer_result = _read_valid_json(
        review_dir / "reviewer_result.json", "content", "reviewer_result", issues
    )
    attestation = _read_valid_json(
        review_dir / "attestation.json", "content", "review_attestation", issues
    )
    if reviewer_result:
        if str(reviewer_result.get("executionId") or "") != execution_id:
            issues.append(f"{rel}/5.review: reviewer executionId drift")
        if str(reviewer_result.get("executionBinding") or "") != "frozen":
            issues.append(f"{rel}/5.review: reviewer execution binding is not frozen")
        if str(reviewer_result.get("verdict") or "") != "passed" or list(reviewer_result.get("issues") or []):
            issues.append(f"{rel}/5.review: independent reviewer did not pass")
        reviewer_contract = (
            model_readiness.get("reviewer") if isinstance(model_readiness.get("reviewer"), dict) else {}
        )
        if reviewer_contract and reviewer_result.get("model") != reviewer_contract.get("model"):
            issues.append(f"{rel}/5.review: reviewer model drift from execution readiness")
        if reviewer_contract and reviewer_result.get("modelFamily") != reviewer_contract.get("modelFamily"):
            issues.append(f"{rel}/5.review: reviewer model family drift from execution readiness")
        if draft_meta and reviewer_result.get("runId") == draft_meta.get("agentRunId"):
            issues.append(f"{rel}/5.review: reviewer must use a distinct Cursor SDK run")
        if str(reviewer_result.get("runId") or "").startswith("contract-output:"):
            issues.append(f"{rel}/5.review: reviewer runId must be a real Cursor SDK run")
    if attestation:
        reviewer = attestation.get("independentReviewer")
        reviewer = reviewer if isinstance(reviewer, dict) else {}
        deterministic = attestation.get("deterministicGate")
        deterministic = deterministic if isinstance(deterministic, dict) else {}
        media = attestation.get("mediaRefReview")
        media = media if isinstance(media, dict) else {}
        if str(attestation.get("executionId") or "") != execution_id:
            issues.append(f"{rel}/5.review: attestation executionId drift")
        if str(attestation.get("executionBinding") or "") != "frozen":
            issues.append(f"{rel}/5.review: attestation execution binding is not frozen")
        if str(attestation.get("decision") or "") != "approved":
            issues.append(f"{rel}/5.review: attestation is not approved")
        if str(deterministic.get("status") or "") != "passed" or list(deterministic.get("issues") or []):
            issues.append(f"{rel}/5.review: deterministic gate did not pass")
        if str(media.get("status") or "") != "passed" or list(media.get("issues") or []):
            issues.append(f"{rel}/5.review: media/reference review did not pass")
        if str(reviewer.get("status") or "") != "passed":
            issues.append(f"{rel}/5.review: independent reviewer is not passed")
        if not all(str(reviewer.get(key) or "").strip() for key in ("provider", "model", "modelFamily", "runId", "resultHash")):
            issues.append(f"{rel}/5.review: independent reviewer binding is incomplete")
        if str(reviewer.get("runId") or "").startswith("contract-output:"):
            issues.append(f"{rel}/5.review: independent reviewer runId must be a real Cursor SDK run")
        if reviewer_result:
            for key in ("provider", "model", "modelFamily", "runId", "resultHash"):
                if reviewer.get(key) != reviewer_result.get(key):
                    issues.append(f"{rel}/5.review: independent reviewer {key} drift")
    return issues


def execution_readiness_issues(
    execution_id: str,
    *,
    require_reviewed: bool,
    min_pass_rate: float = 1.0,
    mode: str = "commercial",
    fail_on_no_go: bool = True,
) -> list[str]:
    issues = content_execution_layout_issues(execution_id=execution_id)
    if not 0 <= min_pass_rate <= 1:
        return [*issues, "minPassRate must be between 0 and 1"]
    if mode not in {"calibration", "commercial"}:
        return [*issues, f"readiness mode is invalid: {mode}"]
    if not is_execution_id(execution_id):
        return [*issues, f"invalid executionId: {execution_id}"]
    root = DATA_EXECUTIONS_ROOT / execution_id
    if not root.is_dir():
        return [*issues, f"execution work package does not exist: {root}"]
    try:
        load_execution_manifest(execution_id)
    except (OSError, ValueError) as exc:
        issues.append(f"execution manifest is invalid: {exc}")
        return issues
    if not require_reviewed:
        return issues

    issues.extend(_terminal_execution_issues(root, execution_id))
    model_readiness = _execution_model_readiness(root, execution_id, issues)
    content_type = parse_execution_id(execution_id).content_type
    if content_type is ContentType.HOMEPAGE:
        media_report = homepage_media_completeness_report(execution_id)
        if not bool(media_report.get("passed")):
            for row in media_report.get("issues") or []:
                if not isinstance(row, dict):
                    continue
                issues.append(
                    "homepage media completeness: {code} {ref}: {message}".format(
                        code=str(row.get("code") or "DATA.MEDIA.DOWNLOAD_INCOMPLETE"),
                        ref=str(row.get("ref") or ""),
                        message=str(row.get("message") or "media closure failed"),
                    )
                )
    object_search_root = (
        root / "entities"
        if content_type is ContentType.HOMEPAGE
        else root / "posts" / content_type.value
    )
    objects = [path.parent for path in object_search_root.rglob("1.download")]
    if not objects:
        issues.append("reviewed execution has no content objects")
        return issues
    if content_type is not ContentType.HOMEPAGE and mode == "commercial":
        try:
            closure = load_post_review_closure(
                execution_id,
                root=root,
            )
        except (OSError, TypeError, ValueError) as exc:
            issues.append(f"commercial post review closure is invalid: {exc}")
            return issues
        if closure.carrier != content_type.value:
            issues.append(
                "commercial post review closure carrier drift: "
                f"expected={content_type.value} actual={closure.carrier}"
            )
            return issues
        objects_by_publish_ref = {
            object_root.relative_to(root).as_posix(): object_root
            for object_root in objects
        }
        closure_publish_refs = {
            row.publish_ref for row in closure.objects
        }
        if closure_publish_refs != set(objects_by_publish_ref):
            issues.append(
                "commercial post review closure differs from execution post objects"
            )
            return issues
        objects = [
            objects_by_publish_ref[publish_ref]
            for publish_ref in closure.qualified_publish_refs
        ]

    if content_type is ContentType.HOMEPAGE and mode == "commercial":
        try:
            verdict = _resolve_homepage_quota_verdict(execution_id)
        except (OSError, TypeError, ValueError) as exc:
            issues.append(f"homepage review partition is invalid: {exc}")
            return issues
        qualified_names = {
            str(label).split("/", 2)[-1]
            for label in verdict.qualified_refs
            if str(label).count("/") >= 2
        }
        objects = [
            object_root
            for object_root in objects
            if object_root.name in qualified_names
        ]
        if verdict.qualified_count > 0 and not objects:
            issues.append(
                "homepage readiness could not map qualified refs to objects"
            )
            return issues

    object_issue_groups = [
        _reviewed_object_issues(
            root,
            object_root,
            execution_id,
            model_readiness=model_readiness,
            content_type=content_type,
        )
        for object_root in objects
    ]
    # Pass-rate denominator is the qualified set only; typed discards never veto.
    selected_count = len(objects)
    passed_count = sum(1 for group in object_issue_groups if not group)
    pass_rate = passed_count / selected_count if selected_count else 0.0
    if pass_rate < min_pass_rate:
        issues.append(
            f"reviewed object pass rate below contract: "
            f"required={min_pass_rate:.6f} actual={pass_rate:.6f}"
        )
    if mode == "commercial" or fail_on_no_go:
        for group in object_issue_groups:
            issues.extend(group)
    return issues


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument(
        "--mode",
        choices=("calibration", "commercial"),
        default="commercial",
    )
    parser.add_argument("--fail-on-no-go", action="store_true")
    args = parser.parse_args(argv)
    issues = execution_readiness_issues(
        args.execution_id,
        require_reviewed=bool(args.require_reviewed),
        min_pass_rate=float(args.min_pass_rate),
        mode=str(args.mode),
        fail_on_no_go=bool(args.fail_on_no_go),
    )
    report = {
        "executionId": args.execution_id,
        "requireReviewed": bool(args.require_reviewed),
        "minPassRate": float(args.min_pass_rate),
        "mode": str(args.mode),
        "failOnNoGo": bool(args.fail_on_no_go),
        "passed": not issues,
        "issues": issues,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1
