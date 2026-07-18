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
from core.io import read_json
from governance.coverage.cold_start_supply import load_cold_start_supply_policy
from core.paths import execution_root


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

    def as_brief_value(self) -> dict[str, str]:
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
        }


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
                "creator": str(row.get("creator") or row.get("credit") or "").strip(),
                "license": str(row.get("license") or "").strip(),
                "authorizationProof": str(row.get("authorizationProof") or "").strip(),
                "sourceCollectionId": str(row.get("sourceCollectionId") or "").strip(),
                "sha256": str(row.get("sha256") or "").strip(),
            }
            if any(not value for value in required.values()):
                reject("rights_evidence_incomplete")
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
                    creator=required["creator"],
                    license=required["license"],
                    sha256=required["sha256"],
                    caption=str(row.get("caption") or row.get("relevance") or "").strip(),
                    source_collection_id=required["sourceCollectionId"],
                )
            )
    candidates.sort(key=lambda item: (item.source_collection_id, item.asset_ref))
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
    policy = load_cold_start_supply_policy().video_delivery
    frames, rejects = _source_frames(ctx, object_dir)
    frames_per_work = policy.minimum_segment_count
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
                "assetRefs": [frame.asset_ref for frame in selected],
                "sourceFrames": source_frames,
                "sourceUseMode": "licensed_adaptation",
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
