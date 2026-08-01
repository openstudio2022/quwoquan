"""Formal video content-plan adapter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.support import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    data_issue,
)
from content.execution.workspace import relative_execution_ref
from content.post.object_index import write_brief_object
from content.source.source_unit import iter_source_units
from core.image_safety import assess_image_publish_prefilter
from core.article_package import sha256_file
from core.io import read_json
from governance.content_supply_policy import load_content_supply_policy
from core.paths import execution_root
from content.execution.identity import parse_execution_id
from content.post.video.source_video import SourcedVideoEvidence
from governance.coverage.license import (
    RightsAuditStatus,
    rights_proof_required,
    validate_image_rights,
)


@dataclass(frozen=True, slots=True)
class VideoFrameCandidate:
    asset_ref: str
    source_ref: str
    rights_ref: str
    source_url: str
    creator: str
    license: str
    sha256: str
    caption: str
    source_collection_id: str
    source_use_mode: str
    rights_audit_status: str
    rights_audit_issues: tuple[str, ...]

    def as_brief_value(self) -> dict[str, object]:
        return {
            "assetRef": self.asset_ref,
            "sourceRef": self.source_ref,
            "rightsRef": self.rights_ref,
            "sourceUrl": self.source_url,
            "creator": self.creator,
            "license": self.license,
            "sha256": self.sha256,
            "caption": self.caption,
            "sourceCollectionId": self.source_collection_id,
            "sourceUseMode": self.source_use_mode,
            "rightsAuditStatus": self.rights_audit_status,
            "rightsAuditIssues": list(self.rights_audit_issues),
        }


@dataclass(frozen=True, slots=True)
class SourcedVideoCandidate:
    evidence: SourcedVideoEvidence
    source_use_mode: str

    def as_brief_value(self) -> dict[str, object]:
        return self.evidence.to_dict()


@dataclass(frozen=True, slots=True)
class VideoPlanOutcome:
    items: tuple[dict[str, Any], ...]
    issues: tuple[DataIssue, ...]
    diagnostic: dict[str, Any]


def _source_frames(
    ctx: ExecutionContext,
    object_dir: Path,
) -> tuple[list[VideoFrameCandidate], dict[str, int]]:
    root = execution_root(ctx.execution_id)
    candidates: list[VideoFrameCandidate] = []
    rejects: dict[str, int] = {}
    seen_sha: set[str] = set()
    require_rights_proof = rights_proof_required(ctx.spec.vertical)

    def reject(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    for source_dir in iter_source_units(object_dir):
        try:
            meta = read_json(source_dir / "meta.json")
        except (OSError, TypeError, ValueError):
            reject("source_meta_unreadable")
            continue
        if str(meta.get("researchLane") or "") != "video":
            continue
        source_use_mode = str(meta.get("sourceUseMode") or "").strip()
        if source_use_mode not in {
            "licensed_adaptation",
            "factual_reference_only",
        }:
            reject("source_use_mode_invalid")
            continue
        index_path = source_dir / "assets" / "index.json"
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, TypeError, ValueError):
            reject("asset_index_unreadable")
            continue
        source_path = source_dir / "source.md"
        source_ref = relative_execution_ref(source_path, ctx.execution_id)
        rights_index_ref = relative_execution_ref(index_path, ctx.execution_id)
        for row in rows:
            if not isinstance(row, dict):
                reject("asset_row_invalid")
                continue
            file_name = str(row.get("fileName") or "").strip()
            source_asset_id = str(row.get("sourceAssetId") or "").strip()
            asset_path = source_dir / "assets" / file_name
            asset_ref = relative_execution_ref(asset_path, ctx.execution_id)
            required = {
                "fileName": file_name,
                "sourceAssetId": source_asset_id,
                "sourceUrl": str(row.get("sourceUrl") or "").strip(),
                "sourceCollectionId": str(row.get("sourceCollectionId") or "").strip(),
                "sha256": str(row.get("sha256") or "").strip(),
            }
            if any(not value for value in required.values()):
                reject("frame_source_evidence_incomplete")
                continue
            creator = str(row.get("creator") or row.get("credit") or "").strip()
            license_name = str(row.get("license") or "").strip()
            authorization_proof = str(row.get("authorizationProof") or "").strip()
            rights_audit_status = str(row.get("rightsAuditStatus") or "").strip()
            rights_audit_issues = tuple(
                str(issue).strip()
                for issue in (row.get("rightsAuditIssues") or [])
                if str(issue).strip()
            )
            if require_rights_proof and validate_image_rights(
                row,
                vertical=ctx.spec.vertical,
            ):
                reject("rights_evidence_incomplete")
                continue
            if rights_audit_status not in {
                item.value for item in RightsAuditStatus
            }:
                reject("rights_audit_status_missing")
                continue
            if (
                rights_audit_status == RightsAuditStatus.UNVERIFIED.value
                and not rights_audit_issues
            ):
                reject("rights_audit_issues_missing")
                continue
            if require_rights_proof and (
                rights_audit_status != RightsAuditStatus.VERIFIED.value
                or rights_audit_issues
            ):
                reject("rights_not_verified")
                continue
            if not asset_path.is_file():
                reject("asset_file_missing")
                continue
            if required["sha256"] in seen_sha:
                reject("duplicate_asset")
                continue
            verdict = assess_image_publish_prefilter(asset_path)
            if verdict.blocks_image_publish:
                reject("image_safety_blocked")
                continue
            seen_sha.add(required["sha256"])
            candidates.append(
                VideoFrameCandidate(
                    asset_ref=asset_ref,
                    source_ref=source_ref,
                    rights_ref=f"{rights_index_ref}#{source_asset_id}",
                    source_url=required["sourceUrl"],
                    creator=creator,
                    license=license_name,
                    sha256=required["sha256"],
                    caption=str(row.get("caption") or row.get("relevance") or "").strip(),
                    source_collection_id=required["sourceCollectionId"],
                    source_use_mode=source_use_mode,
                    rights_audit_status=rights_audit_status,
                    rights_audit_issues=rights_audit_issues,
                )
            )
    candidates.sort(key=lambda item: (item.source_collection_id, item.asset_ref))
    return candidates, rejects


def _sourced_videos(
    ctx: ExecutionContext,
    object_dir: Path,
) -> tuple[list[SourcedVideoCandidate], dict[str, int]]:
    root = execution_root(ctx.execution_id)
    candidates: list[SourcedVideoCandidate] = []
    rejects: dict[str, int] = {}
    seen_sha: set[str] = set()
    require_rights_proof = rights_proof_required(ctx.spec.vertical)

    def reject(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    for source_dir in iter_source_units(object_dir):
        try:
            meta = read_json(source_dir / "meta.json")
        except (OSError, TypeError, ValueError):
            reject("source_meta_unreadable")
            continue
        source_use_mode = str(meta.get("sourceUseMode") or "").strip()
        if source_use_mode not in {
            "licensed_adaptation",
            "factual_reference_only",
        }:
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
        if require_rights_proof and not (
            evidence.commercial_authorization_status == "verified"
            and evidence.publication_admission == "commercial_release"
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
    policy = load_content_supply_policy(
        parse_execution_id(ctx.execution_id).vertical
    ).video_delivery
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
            brief = {
                "titleHint": target,
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
                    "title": target,
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
    frames, rejects = _source_frames(ctx, object_dir)
    frames_per_work = policy.minimum_source_frames
    required_frames = videos_per_target * frames_per_work
    if len(frames) < required_frames:
        issue = data_issue(
            DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=target,
            recovery=DataRecoveryAction.STOP,
            message=(
                f"{target}: video requires {required_frames} distinct rights-cleared "
                f"frame(s), retained {len(frames)}"
            ),
            attributes={
                "carrier": "video",
                "required": required_frames,
                "retained": len(frames),
            },
        )
        return VideoPlanOutcome(
            items=(),
            issues=(issue,),
            diagnostic={
                "desiredVideoWorks": videos_per_target,
                "requiredVideoFrames": required_frames,
                "qualifiedVideoFrames": len(frames),
                "videoRejects": rejects,
                "minimumQualityPassed": False,
            },
        )
    selected_modes = {
        frame.source_use_mode for frame in frames[:required_frames]
    }
    if len(selected_modes) != 1:
        issue = data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=target,
            recovery=DataRecoveryAction.STOP,
            message=f"{target}: video source frames have mixed sourceUseMode values",
            attributes={"carrier": "video"},
        )
        return VideoPlanOutcome(
            items=(),
            issues=(issue,),
            diagnostic={
                "desiredVideoWorks": videos_per_target,
                "requiredVideoFrames": required_frames,
                "qualifiedVideoFrames": len(frames),
                "videoRejects": rejects,
                "minimumQualityPassed": False,
            },
        )
    source_use_mode = next(iter(selected_modes))
    items: list[dict[str, Any]] = []
    entity_ref = f"/entity/{entity_type}/{target}"
    for index in range(videos_per_target):
        selected = frames[index * frames_per_work : (index + 1) * frames_per_work]
        ref = f"{target}_video" if videos_per_target == 1 else f"{target}_video_{index + 1}"
        creator_assignment = scheduler.assign(
            carrier="video",
            target=target,
            intent="video",
        )
        publish_schedule = scheduler.schedule(creator_assignment)
        source_frames = [frame.as_brief_value() for frame in selected]
        evidence_refs = list(dict.fromkeys(frame.source_ref for frame in selected))
        brief = {
            "titleHint": target,
            "carrier": "video",
            "entityRefs": [entity_ref],
            "entityTags": [target],
            "templateId": "travel.entity.short_video",
            "sourceMode": "rights_cleared_image_sequence",
            "sourceUseMode": source_use_mode,
            "sourceFrames": source_frames,
            "assetRefs": [frame.asset_ref for frame in selected],
            "publishSchedule": publish_schedule,
            **creator_assignment,
        }
        write_brief_object(ctx.execution_id, ref, brief, content_type="video")
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "video",
                "researchLane": "video",
                "title": target,
                "entityRefs": [entity_ref],
                "entityTags": [target],
                "evidenceRefs": evidence_refs,
                "rationale": "Agent-authored short video from rights-cleared source frames",
                "sourceMode": "rights_cleared_image_sequence",
                "assetRefs": [frame.asset_ref for frame in selected],
                "sourceFrames": source_frames,
                "sourceUseMode": source_use_mode,
                "publishSchedule": publish_schedule,
                **creator_assignment,
            }
        )
    return VideoPlanOutcome(
        items=tuple(items),
        issues=(),
        diagnostic={
            "desiredVideoWorks": videos_per_target,
            "requiredVideoFrames": required_frames,
            "qualifiedVideoFrames": len(frames),
            "pickedVideoWorks": len(items),
            "videoRejects": rejects,
            "minimumQualityPassed": True,
        },
    )


__all__ = ["VideoPlanOutcome", "build_video_plan_for_target"]
