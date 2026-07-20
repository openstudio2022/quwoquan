"""Strongly typed authoring and review service for formal video posts."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

from content.execution.stage_reports import (
    clear_repair_report,
    write_gate_report,
    write_stage_result,
)
from content.post.article.draft_io import (
    draft_meta_path,
    draft_package_dir,
    prompt_path,
    write_prompt,
    write_writing_pack,
)
from content.post.object_index import read_brief_object
from content.post.video.codec import (
    VideoDraftMeta,
    VideoReviewDecision,
    VideoScriptDraft,
    VideoWritingPack,
    load_video_draft_meta,
    load_video_writing_pack,
)
from core.article_package import sha256_file
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import write_json
from core.prompt_render import render as render_prompt
from governance.coverage.cold_start_supply import load_cold_start_supply_policy


VIDEO_SCRIPT_FILE = "video_script.json"


def video_script_path(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / VIDEO_SCRIPT_FILE


def _issue(
    code: DataIssueCode,
    *,
    stage: DataIssueStage,
    ref: str,
    recovery: DataRecoveryAction,
    message: str,
    attributes: dict[str, object] | None = None,
) -> DataIssue:
    return data_issue(
        code,
        stage=stage,
        lane=DataIssueLane.VIDEO,
        ref=ref,
        recovery=recovery,
        message=message,
        attributes=attributes,
    )


def prepare_video_brief(execution_id: str, ref: str) -> dict[str, object]:
    raw_brief = read_brief_object(execution_id, ref)
    if not isinstance(raw_brief, dict):
        raw_brief = {}
    pack, admission_failures = VideoWritingPack.from_brief(ref, raw_brief)
    frame_issues = [
        _issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.COMPOSE_BRIEF,
            ref=ref,
            recovery=DataRecoveryAction.REWIND_DOWNLOAD,
            message=message,
        )
        for message in admission_failures
    ]
    minimum_frames = (
        load_cold_start_supply_policy().video_delivery.minimum_segment_count
    )
    if pack.source_video is None and len(pack.source_frames) < minimum_frames:
        frame_issues.append(
            _issue(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                stage=DataIssueStage.QUALITY,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_DOWNLOAD,
                message="video source frame count is below delivery policy",
                attributes={
                    "actual": len(pack.source_frames),
                    "required": minimum_frames,
                },
            )
        )
    pack_payload = pack.to_dict()
    write_writing_pack(execution_id, ref, pack_payload)
    write_prompt(
        execution_id,
        ref,
        render_prompt(
            "video_author",
            task_vars={
                "content_ref": ref,
                "entity_name": pack.primary_entity,
                "segment_count": minimum_frames,
                "source_frames_json": json.dumps(
                    (
                        pack_payload["sourceVideo"]
                        if pack.source_video is not None
                        else pack_payload["sourceFrames"]
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                "video_script_path": str(video_script_path(execution_id, ref)),
                "draft_meta_path": str(draft_meta_path(execution_id, ref)),
            },
        ),
        template_family="video_author",
        variables={"writingPack": pack_payload},
        output_refs=(
            f"4.draft/{VIDEO_SCRIPT_FILE}",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ),
    )
    script_path = video_script_path(execution_id, ref)
    if script_path.is_file():
        script_path.unlink()
    write_json(
        draft_meta_path(execution_id, ref),
        VideoDraftMeta.pending(
            ref=ref,
            cited_source_paths=pack.source_paths,
        ).to_dict(),
    )
    quality_payload = {
        "recommendation": "compose",
        "carrier": "video",
        "sourceMode": pack_payload["sourceMode"],
        "sourceFrameCount": len(pack.source_frames),
        "sourcePaths": list(pack.source_paths),
        "sourceUrls": list(pack.source_urls),
    }
    write_stage_result(
        execution_id,
        "post",
        "quality_analysis",
        ref,
        quality_payload,
    )
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="quality_analysis",
        ref=ref,
        passed=not frame_issues,
        issues=tuple(frame_issues),
        evidence_summary={
            "carrier": "video",
            "sourceMode": pack_payload["sourceMode"],
            "sourceFrameCount": len(pack.source_frames),
        },
        next_step="compose_brief" if not frame_issues else None,
    )
    write_stage_result(
        execution_id,
        "post",
        "compose_brief",
        ref,
        pack_payload,
    )
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="compose_brief",
        ref=ref,
        passed=not frame_issues,
        issues=tuple(frame_issues),
        evidence_summary={
            "carrier": "video",
            "sourceMode": pack_payload["sourceMode"],
            "sourceFrameCount": len(pack.source_frames),
        },
        next_step="agent_compose" if not frame_issues else None,
    )
    return pack_payload


def video_author_issues(
    execution_id: str,
    ref: str,
    *,
    require_agent_run: bool,
) -> tuple[DataIssue, ...]:
    script_path = video_script_path(execution_id, ref)
    if not script_path.is_file():
        return (
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video script is missing",
            ),
        )
    try:
        draft = VideoScriptDraft.load(script_path)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return (
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video script failed schema admission",
                attributes={"errorType": type(exc).__name__},
            ),
        )
    issues: list[DataIssue] = []
    required_lines = (
        load_cold_start_supply_policy().video_delivery.minimum_segment_count
    )
    if len(draft.script_lines) != required_lines:
        issues.append(
            _issue(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video script line count does not match delivery policy",
                attributes={
                    "actual": len(draft.script_lines),
                    "required": required_lines,
                },
            )
        )
    try:
        meta = load_video_draft_meta(execution_id, ref)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        issues.append(
            _issue(
                DataIssueCode.AGENT_REVIEW_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video draft metadata failed admission",
                attributes={"errorType": type(exc).__name__},
            )
        )
        return tuple(issues)
    if meta.generator != "agent":
        issues.append(
            _issue(
                DataIssueCode.AGENT_REVIEW_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video draft generator is not the configured agent",
            )
        )
    if not meta.model:
        issues.append(
            _issue(
                DataIssueCode.AGENT_REVIEW_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video draft model evidence is missing",
            )
        )
    if require_agent_run and not meta.agent_run_id:
        issues.append(
            _issue(
                DataIssueCode.AGENT_REVIEW_INVALID,
                stage=DataIssueStage.POST_AUTHOR,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video Agent run evidence is missing",
            )
        )
    return tuple(issues)


def finalize_video_author_meta(
    execution_id: str,
    ref: str,
    *,
    run_id: str,
    agent_id: str | None,
    model: str,
) -> bool:
    script_path = video_script_path(execution_id, ref)
    if not script_path.is_file():
        return False
    try:
        VideoScriptDraft.load(script_path)
        pack = load_video_writing_pack(execution_id, ref)
        meta = load_video_draft_meta(execution_id, ref)
    except (OSError, TypeError, ValueError, KeyError):
        return False
    pack_path = (
        draft_package_dir(execution_id, ref).parent
        / "3.compose"
        / "writing_pack.json"
    )
    now = datetime.now(UTC).isoformat()
    finalized = replace(
        meta,
        ref=ref,
        generator="agent",
        status="completed",
        model=meta.model or model,
        agent_run_id=run_id,
        agent_id=agent_id or "",
        cited_source_paths=meta.cited_source_paths or pack.source_paths,
        prompt_sha256=sha256_file(prompt_path(execution_id, ref)),
        writing_pack_sha256=sha256_file(pack_path),
        draft_sha256=sha256_file(script_path),
        created_at=meta.created_at or now,
        updated_at=now,
    )
    write_json(draft_meta_path(execution_id, ref), finalized.to_dict())
    return True


def _compose_payload(
    ref: str,
    pack: VideoWritingPack,
    draft: VideoScriptDraft,
    meta: VideoDraftMeta,
) -> dict[str, object]:
    return {
        "topicId": ref,
        "contentType": "video",
        "carrier": "video",
        "title": draft.title,
        "caption": draft.caption,
        "entityRefs": list(pack.entity_refs),
        "tagRefs": list(pack.tag_refs),
        "sourceUrls": list(pack.source_urls),
        "sourcePaths": list(pack.source_paths),
        "sourceFrames": [frame.to_dict() for frame in pack.source_frames],
        "sourceMode": (
            "sourced_video"
            if pack.source_video is not None
            else "rights_cleared_image_sequence"
        ),
        **(
            {"sourceVideo": pack.source_video.to_dict()}
            if pack.source_video is not None
            else {}
        ),
        "storySpine": pack.to_dict()["storySpine"],
        "publishLayout": "video",
        "publishAngle": "体验",
        "publishTitle": draft.title,
        "publishSeq": 1,
        "scriptLines": list(draft.script_lines),
        "generator": "agent",
        "generatorModel": meta.model,
        "agentRunId": meta.agent_run_id,
        "createdAt": meta.created_at,
        "updatedAt": meta.updated_at,
        **pack.creator.to_dict(),
    }


def review_video_draft(execution_id: str, ref: str) -> dict[str, object]:
    issues = list(
        video_author_issues(
            execution_id,
            ref,
            require_agent_run=True,
        )
    )
    pack: VideoWritingPack | None = None
    meta: VideoDraftMeta | None = None
    try:
        pack = load_video_writing_pack(execution_id, ref)
        meta = load_video_draft_meta(execution_id, ref)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        issues.append(
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.REVIEW,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="video author package failed review admission",
                attributes={"errorType": type(exc).__name__},
            )
        )
    draft = None
    if not issues:
        draft = VideoScriptDraft.load(video_script_path(execution_id, ref))
    if pack is not None and meta is not None and draft is not None:
        compose_payload = _compose_payload(ref, pack, draft, meta)
    else:
        compose_payload = {
            "topicId": ref,
            "contentType": "video",
            "carrier": "video",
            "entityRefs": list(pack.entity_refs) if pack else [],
            "tagRefs": list(pack.tag_refs) if pack else [],
            "generator": meta.generator if meta else "pending",
        }
    write_stage_result(execution_id, "post", "compose", ref, compose_payload)
    typed_issues = tuple(issues)
    decision = (
        VideoReviewDecision.APPROVED
        if not typed_issues
        else VideoReviewDecision.REVISION_NEEDED
    )
    payload = {
        "topicId": ref,
        "decision": decision.value,
        "qualityScore": 100.0 if decision is VideoReviewDecision.APPROVED else 0.0,
        "issues": [issue.as_dict() for issue in typed_issues],
        "checks": {
            "videoScriptContract": {
                "passed": not typed_issues,
                "issues": [issue.message for issue in typed_issues],
            },
        },
        "generator": compose_payload.get("generator"),
    }
    write_stage_result(execution_id, "post", "review", ref, payload)
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="review",
        ref=ref,
        passed=not typed_issues,
        issues=typed_issues,
        evidence_summary={
            "carrier": "video",
            "generator": compose_payload.get("generator"),
        },
        next_step="materialize" if not typed_issues else None,
    )
    if not typed_issues:
        clear_repair_report(execution_id=execution_id, command="post", ref=ref)
    return payload


__all__ = [
    "VIDEO_SCRIPT_FILE",
    "VideoScriptDraft",
    "finalize_video_author_meta",
    "prepare_video_brief",
    "review_video_draft",
    "video_author_issues",
    "video_script_path",
]
