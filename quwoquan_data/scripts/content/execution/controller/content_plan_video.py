"""Formal video content-plan adapter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.support import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    data_issue,
)
from content.post.object_index import write_brief_object
from content.source.source_unit import iter_source_units
from core.article_package import sha256_file
from core.io import read_json
from core.paths import execution_root
from content.post.video.source_video import SourcedVideoEvidence
from governance.coverage.license import (
    rights_proof_required,
)
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)


@dataclass(frozen=True, slots=True)
class SourcedVideoCandidate:
    evidence: SourcedVideoEvidence
    source_use_mode: str
    source_title: str

    def as_brief_value(self) -> dict[str, object]:
        return self.evidence.to_dict()


@dataclass(frozen=True, slots=True)
class VideoPlanOutcome:
    items: tuple[dict[str, Any], ...]
    issues: tuple[DataIssue, ...]
    diagnostic: dict[str, Any]


def sourced_video_object_title(*, target: str, source_title: str) -> str:
    """Freeze one source-specific, entity-bound video object coordinate."""
    normalized_target = str(target or "").strip()
    normalized_source_title = str(source_title or "").strip()
    if not normalized_target:
        raise ValueError("video target is required for immutable object routing")
    if not normalized_source_title:
        raise ValueError("sourced video title is required for immutable object routing")
    if normalized_target in normalized_source_title:
        return normalized_source_title[:80]
    return f"{normalized_target}｜{normalized_source_title}"[:80]


def _sourced_videos(
    ctx: ExecutionContext,
    object_dir: Path,
) -> tuple[list[SourcedVideoCandidate], dict[str, int]]:
    root = execution_root(ctx.execution_id)
    candidates: list[SourcedVideoCandidate] = []
    rejects: dict[str, int] = {}
    seen_sha: set[str] = set()
    require_rights_proof = rights_proof_required(ctx.spec.vertical)
    lifecycle = load_content_distribution_policy().product_lifecycle_state

    def reject(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    for source_dir in iter_source_units(object_dir):
        try:
            meta = read_json(source_dir / "meta.json")
        except (OSError, TypeError, ValueError):
            reject("source_meta_unreadable")
            continue
        source_use_mode = str(meta.get("sourceUseMode") or "").strip()
        source_title = str(meta.get("title") or "").strip()
        if not source_title:
            reject("source_title_missing")
            continue
        allowed_source_modes = (
            {"rights_audit_only", "licensed_adaptation"}
            if lifecycle is ProductLifecycleState.RESEARCH
            else {"licensed_adaptation"}
        )
        if source_use_mode not in allowed_source_modes:
            reject("source_use_mode_invalid")
            continue
        evidence_path = source_dir / "sourced_video_evidence.json"
        if not evidence_path.is_file():
            continue
        try:
            payload = read_json(evidence_path)
        except (OSError, TypeError, ValueError):
            reject("sourced_video_evidence_unreadable")
            continue
        if not isinstance(payload, dict):
            reject("sourced_video_evidence_invalid")
            continue
        evidence, issues = SourcedVideoEvidence.from_mapping(payload)
        if issues:
            reject("sourced_video_admission_blocked")
            continue
        if (
            lifecycle is ProductLifecycleState.RESEARCH
            and evidence.publication_admission != "research_release"
        ):
            reject("sourced_video_release_class_mismatch")
            continue
        if (
            require_rights_proof
            and lifecycle is not ProductLifecycleState.RESEARCH
            and not (
                evidence.commercial_authorization_status == "verified"
                and evidence.publication_admission == "commercial_release"
            )
        ):
            reject("sourced_video_rights_not_verified")
            continue
        refs = (
            evidence.asset_ref,
            evidence.rights_ref,
            evidence.media_probe_ref,
            evidence.watermark_evidence_ref,
            evidence.audio_rights_evidence_ref,
        )
        paths = [(root / relative).resolve() for relative in refs]
        if any(
            not path.is_file()
            or not path.is_relative_to(root.resolve())
            for path in paths
        ):
            reject("sourced_video_evidence_missing")
            continue
        if sha256_file(paths[0]) != evidence.sha256:
            reject("sourced_video_sha_mismatch")
            continue
        if evidence.sha256 in seen_sha:
            reject("duplicate_sourced_video")
            continue
        seen_sha.add(evidence.sha256)
        candidates.append(
            SourcedVideoCandidate(
                evidence=evidence,
                source_use_mode=source_use_mode,
                source_title=source_title,
            )
        )
    candidates.sort(key=lambda item: item.evidence.asset_ref)
    return candidates, rejects


def build_video_plan_for_target(
    *,
    ctx: ExecutionContext,
    scheduler: Any,
    entity_type: str,
    target: str,
    object_dir: Path,
    videos_per_target: int,
) -> VideoPlanOutcome:
    sourced_videos, sourced_rejects = _sourced_videos(ctx, object_dir)
    if len(sourced_videos) >= videos_per_target:
        items: list[dict[str, Any]] = []
        entity_ref = f"/entity/{entity_type}/{target}"
        for index, candidate in enumerate(
            sourced_videos[:videos_per_target],
            start=1,
        ):
            ref = (
                f"{target}_video"
                if videos_per_target == 1
                else f"{target}_video_{index}"
            )
            creator_assignment = scheduler.assign(
                carrier="video",
                target=target,
                intent="video",
            )
            publish_schedule = scheduler.schedule(creator_assignment)
            source_video = candidate.as_brief_value()
            title = sourced_video_object_title(
                target=target,
                source_title=candidate.source_title,
            )
            brief = {
                "titleHint": title,
                "carrier": "video",
                "entityRefs": [entity_ref],
                "entityTags": [target],
                "templateId": "travel.entity.short_video",
                "sourceMode": "sourced_video",
                "sourceUseMode": candidate.source_use_mode,
                "sourceVideo": source_video,
                "assetRefs": [candidate.evidence.asset_ref],
                "publishSchedule": publish_schedule,
                **creator_assignment,
            }
            write_brief_object(
                ctx.execution_id,
                ref,
                brief,
                content_type="video",
            )
            # evidenceRefs must be execution-local files; sourceVideo.sourceRef
            # remains the HTTP(S) source post URL for admission/attribution.
            local_evidence_ref = str(candidate.evidence.rights_ref or "").strip()
            asset_ref = str(candidate.evidence.asset_ref or "").strip()
            if asset_ref:
                local_evidence_ref = (
                    str(Path(asset_ref).parent.parent / "sourced_video_evidence.json")
                )
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "video",
                    "researchLane": "video",
                    "title": title,
                    "entityRefs": [entity_ref],
                    "entityTags": [target],
                    "evidenceRefs": [local_evidence_ref],
                    "rationale": (
                        "Agent-authored caption for one admitted sourced video"
                    ),
                    "sourceMode": "sourced_video",
                    "sourceVideo": source_video,
                    "assetRefs": [candidate.evidence.asset_ref],
                    "sourceUseMode": candidate.source_use_mode,
                    "publishSchedule": publish_schedule,
                    **creator_assignment,
                }
            )
        return VideoPlanOutcome(
            items=tuple(items),
            issues=(),
            diagnostic={
                "desiredVideoWorks": videos_per_target,
                "qualifiedSourcedVideos": len(sourced_videos),
                "pickedVideoWorks": len(items),
                "sourcedVideoRejects": sourced_rejects,
                "sourceMode": "sourced_video",
                "minimumQualityPassed": True,
            },
        )
    issue = data_issue(
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        stage=DataIssueStage.CONTENT_PLAN,
        ref=target,
        lane=DataIssueLane.VIDEO,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message=(
            f"{target}: video requires {videos_per_target} acquired playable "
            f"video file(s), retained {len(sourced_videos)}"
        ),
        attributes={
            "carrier": "video",
            "required": videos_per_target,
            "retained": len(sourced_videos),
        },
    )
    return VideoPlanOutcome(
        items=(),
        issues=(issue,),
        diagnostic={
            "desiredVideoWorks": videos_per_target,
            "qualifiedSourcedVideos": len(sourced_videos),
            "pickedVideoWorks": 0,
            "sourcedVideoRejects": sourced_rejects,
            "sourceMode": "sourced_video",
            "minimumQualityPassed": False,
        },
    )


__all__ = ["VideoPlanOutcome", "build_video_plan_for_target"]
