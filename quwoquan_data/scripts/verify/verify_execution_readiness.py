"""Validate one immutable content execution work package before release."""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.identity import parse_execution_id
from content.execution.post_review_closure import load_post_review_closure
from content.execution.runtime_contract import file_sha256
from content.execution.workspace import load_execution_manifest
from core.article_package import compute_document_sha256
from core.control_types import ContentType, expected_content_generator
from core.io import read_json
from core.paths import DATA_EXECUTIONS_ROOT, is_execution_id
from core.schema import assert_valid
from governance.coverage.distribution import (
    DistributionDecision,
    RightsStatus,
    project_asset_admission,
)

from verify.verify_content_execution_layout import content_execution_layout_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report


_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
READINESS_MODES = ("calibration", "research", "commercial")
_LIFECYCLE_MODES = frozenset({"research", "commercial"})


@dataclass(frozen=True, slots=True)
class ReadinessOutcome:
    """准出判定与持续改进统计分离：只有 ``issues`` 决定放行。"""

    issues: list[str]
    statistics: dict[str, Any] | None


def _blocked(issues: list[str], reason: str) -> ReadinessOutcome:
    """Readiness 在拿到对象集之前失败，统计量此时无定义。"""
    return ReadinessOutcome(issues=[*issues, reason], statistics=None)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _normalize_model_id(model: object) -> str:
    text = str(model or "").strip().lower().replace("_", "-")
    text = text.removeprefix("cursor-")
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


def _object_document(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.is_file():
        issues.append(f"{path}: required immutable object evidence is missing")
        return {}
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"{path}: invalid immutable object evidence ({exc})")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{path}: immutable object evidence must be an object")
        return {}
    return payload


def _transaction_object(root: Path, object_root: Path, content_type: ContentType) -> Path:
    kind = "entity" if content_type is ContentType.HOMEPAGE else "post"
    parent = root / ("entities" if kind == "entity" else f"posts/{content_type.value}")
    ref = object_root.relative_to(parent).as_posix()
    if kind == "post":
        ref = f"{content_type.value}/{ref}"
    suffix = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:12]
    return root / "evidence/object-transactions" / f"{root.name}--{kind}-{suffix}" / "object"


def _asset_admission_issues(
    object_root: Path,
    *,
    content_type: ContentType,
    mode: str,
) -> tuple[list[str], str]:
    label = object_root.as_posix()
    issues: list[str] = []
    package = _object_document(object_root.parent / "object_transaction_package.json", issues)
    target = package.get("target") if isinstance(package.get("target"), Mapping) else {}
    if (
        package.get("schema") != "quwoquan_data.object_transaction_package"
        or not object_root.parent.name.startswith(f"{package.get('executionId')}--")
        or target.get("packageObjectRef") != "object"
        or not str(package.get("objectClosureDigest") or "").startswith("sha256:")
    ):
        issues.append(f"{label}: immutable transaction package binding is invalid")
    manifest = _object_document(object_root / "manifest.json", issues)
    rights = _object_document(object_root / "rights.json", issues)
    manifest_rows = manifest.get("assets")
    rights_rows = rights.get("assets")
    if not isinstance(manifest_rows, list) or not isinstance(rights_rows, list):
        issues.append(f"{label}: manifest/rights assets must both be arrays")
        return issues, "invalid"
    manifest_assets = [row for row in manifest_rows if isinstance(row, Mapping)]
    raw_rights = [row for row in rights_rows if isinstance(row, Mapping)]
    if len(manifest_assets) != len(manifest_rows) or len(raw_rights) != len(rights_rows):
        issues.append(f"{label}: manifest/rights assets must contain only objects")
    manifest_ids = [str(row.get("assetId") or "").strip() for row in manifest_assets]
    rights_ids = [str(row.get("assetId") or "").strip() for row in raw_rights]
    if any(not value for value in (*manifest_ids, *rights_ids)):
        issues.append(f"{label}: manifest/rights assetId is missing")
    if len(manifest_ids) != len(set(manifest_ids)) or len(rights_ids) != len(set(rights_ids)):
        issues.append(f"{label}: manifest/rights asset IDs must be unique")
    if set(manifest_ids) != set(rights_ids):
        issues.append(f"{label}: manifest/rights asset closure drift")

    raw_by_id = {str(row.get("assetId") or "").strip(): row for row in raw_rights}
    physical_paths: dict[str, Path] = {}
    for asset_id, raw in raw_by_id.items():
        try:
            projected = project_asset_admission(raw, object_ref=label)
        except (TypeError, ValueError) as exc:
            issues.append(str(exc))
            continue
        for field in ("sourceUrl", "platform", "creator", "capturedAt", "contentSha256", "license", "termsUrl"):
            if not str(projected.get(field) or "").strip():
                issues.append(f"{label}: asset {asset_id} lacks provenance field {field}")
        if "authorizationProof" not in raw or not any(key in raw for key in ("rightsIssues", "rightsAuditIssues")):
            issues.append(f"{label}: asset {asset_id} lacks authorizationProof/rightsIssues fields")
        for field in ("acquisitionStatus", "rightsStatus", "authorizationRequired", "distributionDecision"):
            if field in raw and raw.get(field) != projected.get(field):
                issues.append(f"{label}: asset {asset_id} declared {field} drifts from evidence")
        if projected["generated"]:
            issues.append(f"{label}: generated image/video asset is blocked: {asset_id}")
        decision = str(projected["distributionDecision"])
        if mode == "research" and decision not in {
            DistributionDecision.RESEARCH_ALLOWED.value,
            DistributionDecision.COMMERCIAL_ALLOWED.value,
        }:
            issues.append(f"{label}: research asset is blocked: {asset_id}")
        if mode == "commercial" and (
            decision != DistributionDecision.COMMERCIAL_ALLOWED.value
            or projected["rightsStatus"] != RightsStatus.VERIFIED.value
            or bool(projected["authorizationRequired"])
        ):
            issues.append(f"{label}: commercial asset requires verified commercial_allowed: {asset_id}")
        physical = raw.get("asset") if isinstance(raw.get("asset"), Mapping) else {}
        physical_ref = str(physical.get("ref") or "").strip()
        relative = Path(physical_ref)
        if not physical_ref or relative.is_absolute() or ".." in relative.parts:
            issues.append(f"{label}: asset {asset_id} lacks a safe acquired blob ref")
            continue
        physical_path = object_root.parent / relative
        if not physical_path.is_file() or physical_path.stat().st_size != int(physical.get("bytes") or 0):
            issues.append(f"{label}: acquired blob is missing or size-drifted: {asset_id}")
            continue
        physical_paths[asset_id] = physical_path

    for row in manifest_assets:
        asset_id = str(row.get("assetId") or "").strip()
        raw = raw_by_id.get(asset_id, {})
        physical = raw.get("asset") if isinstance(raw.get("asset"), Mapping) else {}
        if not str(row.get("sha256") or "").startswith("sha256:") or row.get("sha256") != physical.get("sha256"):
            issues.append(f"{label}: manifest/blob digest closure drift: {asset_id}")

    if content_type is ContentType.ARTICLE:
        text_only = str(manifest.get("publishMediaMode") or "").strip() == "text_only"
        if text_only:
            if manifest_assets or raw_rights:
                issues.append(f"{label}: text_only article must not bind media assets")
            return issues, "text_only"
        images = [row for row in manifest_assets if str(row.get("kind") or "image") == "image"]
        roles = {str(row.get("role") or "").strip() for row in images}
        source_units = {
            str(row.get("sourceUnitRef") or row.get("sourceRef") or "").strip()
            for row in images
        }
        bindings = [row for row in (manifest.get("imageBindings") or []) if isinstance(row, Mapping)]
        if not (
            len(images) >= 2
            and "cover" in roles
            and (roles.intersection({"detail", "embedded"}) or len(bindings) >= 2)
            and len(source_units) == 1
            and "" not in source_units
        ):
            issues.append(f"{label}: article requires same-source cover and body images")
            return issues, "invalid"
        return issues, "illustrated"
    if content_type in {ContentType.HOMEPAGE, ContentType.IMAGE}:
        if not any(str(row.get("kind") or "image") == "image" for row in manifest_assets):
            issues.append(f"{label}: {content_type.value} requires an acquired image")
        return issues, "media"
    if content_type is ContentType.VIDEO:
        by_id = {str(row.get("assetId") or "").strip(): row for row in manifest_assets}
        playable = False
        for row in manifest_assets:
            if str(row.get("kind") or "") != "video":
                continue
            poster = by_id.get(str(row.get("posterAssetId") or "").strip(), {})
            path = physical_paths.get(str(row.get("assetId") or "").strip())
            if not (
                str(row.get("mimeType") or "").lower() in {"video/mp4", "video/webm"}
                and int(row.get("durationMs") or 0) > 0
                and int(row.get("width") or 0) > 0
                and int(row.get("height") or 0) > 0
                and str(row.get("codec") or "").strip()
                and str(poster.get("kind") or "") == "image"
                and str(poster.get("role") or "") == "cover"
                and path is not None
            ):
                continue
            with path.open("rb") as stream:
                header = stream.read(64)
            playable = b"ftyp" in header or header.startswith(b"\x1a\x45\xdf\xa3")
            if playable:
                break
        if not playable:
            issues.append(f"{label}: video requires an acquired playable MP4/WebM with cover")
        return issues, "media"
    return issues, "invalid"


def _resolve_homepage_quota_verdict(execution_id: str) -> Any:
    """Resolve the canonical homepage quota verdict behind an isolation seam."""
    from types import SimpleNamespace

    from content.execution import store as execution_store
    from content.execution.controller.homepage_authoring import (
        homepage_quota_verdict,
    )

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
    mode: str,
) -> list[str]:
    return execution_readiness_outcome(
        execution_id,
        require_reviewed=require_reviewed,
        mode=mode,
    ).issues


def execution_readiness_outcome(
    execution_id: str,
    *,
    require_reviewed: bool,
    mode: str,
) -> ReadinessOutcome:
    """Admission is「至少 1 个合格对象 + 每个将发布对象逐条硬校验」。

    合格率与配图率只作为持续改进的统计量随 outcome 返回，不参与判定。
    """
    issues = content_execution_layout_issues(execution_id=execution_id)
    if mode not in READINESS_MODES:
        return _blocked(issues, f"readiness mode is invalid: {mode}")
    if mode in _LIFECYCLE_MODES and not require_reviewed:
        return _blocked(
            issues, f"{mode} readiness requires independently reviewed objects"
        )
    if not is_execution_id(execution_id):
        return _blocked(issues, f"invalid executionId: {execution_id}")
    root = DATA_EXECUTIONS_ROOT / execution_id
    if not root.is_dir():
        return _blocked(issues, f"execution work package does not exist: {root}")
    try:
        load_execution_manifest(execution_id)
    except (OSError, ValueError) as exc:
        return _blocked(issues, f"execution manifest is invalid: {exc}")
    if not require_reviewed:
        return ReadinessOutcome(issues=issues, statistics=None)

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
        return _blocked(issues, "reviewed execution has no content objects")
    discovered_count = len(objects)
    if content_type is not ContentType.HOMEPAGE and mode in _LIFECYCLE_MODES:
        try:
            closure = load_post_review_closure(
                execution_id,
                root=root,
            )
        except (OSError, TypeError, ValueError) as exc:
            return _blocked(issues, f"{mode} post review closure is invalid: {exc}")
        if closure.carrier != content_type.value:
            return _blocked(
                issues,
                f"{mode} post review closure carrier drift: "
                f"expected={content_type.value} actual={closure.carrier}",
            )
        objects_by_publish_ref = {
            object_root.relative_to(root).as_posix(): object_root
            for object_root in objects
        }
        closure_publish_refs = {row.publish_ref for row in closure.objects}
        if closure_publish_refs != set(objects_by_publish_ref):
            return _blocked(
                issues,
                f"{mode} post review closure differs from execution post objects",
            )
        objects = [
            objects_by_publish_ref[publish_ref]
            for publish_ref in closure.qualified_publish_refs
        ]

    if content_type is ContentType.HOMEPAGE and mode in _LIFECYCLE_MODES:
        try:
            verdict = _resolve_homepage_quota_verdict(execution_id)
        except (OSError, TypeError, ValueError) as exc:
            return _blocked(issues, f"homepage review partition is invalid: {exc}")
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
            return _blocked(
                issues, "homepage readiness could not map qualified refs to objects"
            )

    object_issue_groups: list[list[str]] = []
    article_states: list[str] = []
    for object_root in objects:
        group = _reviewed_object_issues(
            root,
            object_root,
            execution_id,
            model_readiness=model_readiness,
            content_type=content_type,
        )
        if mode in _LIFECYCLE_MODES:
            admission, state = _asset_admission_issues(
                _transaction_object(root, object_root, content_type),
                content_type=content_type,
                mode=mode,
            )
            group.extend(admission)
            article_states.append(state)
        object_issue_groups.append(group)
    # Denominator is the qualified set only; objects discarded upstream never count.
    selected_count = len(objects)
    passed_count = sum(1 for group in object_issue_groups if not group)
    illustrated_count = article_states.count("illustrated")
    statistics = {
        "discoveredCount": discovered_count,
        "selectedCount": selected_count,
        "passedCount": passed_count,
        "discardedCount": max(0, discovered_count - selected_count),
        "objectPassRate": _rate(passed_count, selected_count),
        "discardRate": _rate(discovered_count - selected_count, discovered_count),
    }
    if content_type is ContentType.ARTICLE and mode in _LIFECYCLE_MODES:
        statistics["illustratedCount"] = illustrated_count
        statistics["illustratedRate"] = _rate(illustrated_count, len(article_states))
    # 批次级唯一硬条件：至少一个合格对象。比率不参与判定。
    if not passed_count:
        issues.append("reviewed execution has no qualified content object")
    # 逐对象硬校验对所有模式无条件展开：进入发布的对象必须逐条成立。
    for group in object_issue_groups:
        issues.extend(group)
    return ReadinessOutcome(issues=issues, statistics=statistics)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--mode", choices=READINESS_MODES, required=True)
    args = parser.parse_args(argv)
    outcome = execution_readiness_outcome(
        args.execution_id,
        require_reviewed=bool(args.require_reviewed),
        mode=str(args.mode),
    )
    report = {
        "executionId": args.execution_id,
        "requireReviewed": bool(args.require_reviewed),
        "mode": str(args.mode),
        "passed": not outcome.issues,
        "issues": outcome.issues,
        "statistics": outcome.statistics,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not outcome.issues else 1
