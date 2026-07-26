"""Materialize one approved formal video object."""
from __future__ import annotations

from datetime import datetime, timezone
import shutil
from pathlib import Path

from content.execution.runtime_contract import stage_execution_context
from content.post.materialize_contract import _normalized_runtime_entity_refs
from content.post.review_evidence import write_review_evidence
from content.post.video.codec import (
    VideoScriptDraft,
    VideoWritingPack,
    load_video_draft_meta,
    load_video_writing_pack,
)
from content.post.video.package import (
    VideoRenderRequest,
    VideoSourceBasis,
    VideoSourceFrame,
    render_video_work_package,
)
from content.post.video.authoring import video_script_path
from content.post.video.source_video import SourcedVideoAsset
from core.intersection_signal import build_intersection_hints
from core.io import read_json, write_json
from core.paths import execution_root
from core.schema import assert_valid


def _source_frames(
    execution_id: str,
    pack: VideoWritingPack,
) -> tuple[VideoSourceFrame, ...]:
    root = execution_root(execution_id)
    return tuple(
        VideoSourceFrame(
            path=root / frame.asset_ref,
            asset_ref=frame.asset_ref,
            source_url=frame.source_url,
            rights_ref=frame.rights_ref,
            creator=frame.creator,
            license=frame.license,
            basis=VideoSourceBasis.RIGHTS_CLEARED,
        )
        for frame in pack.source_frames
    )


def _source_video(
    execution_id: str,
    pack: VideoWritingPack,
) -> SourcedVideoAsset | None:
    if pack.source_video is None:
        return None
    return SourcedVideoAsset(
        path=execution_root(execution_id) / pack.source_video.asset_ref,
        evidence=pack.source_video,
    )


def _write_source_refs(post_dir: Path, pack: VideoWritingPack) -> None:
    source_rows = (
        [
            {
                "role": "sourced_video",
                "sourceRef": pack.source_video.source_ref,
                "sourceAssetRef": pack.source_video.asset_ref,
                "rightsRef": pack.source_video.rights_ref,
                "sourceUrl": pack.source_video.source_post_url,
                "sha256": pack.source_video.sha256,
            }
        ]
        if pack.source_video is not None
        else [
            {
                "role": "frame",
                "sourceRef": frame.source_ref,
                "sourceAssetRef": frame.asset_ref,
                "rightsRef": frame.rights_ref,
                "sourceUrl": frame.source_url,
                "sha256": frame.sha256,
            }
            for frame in pack.source_frames
        ]
    )
    write_json(
        post_dir / "1.download" / "source_refs.json",
        {
            "schema": "quwoquan_data.video_source_refs",
            "carrier": "video",
            "sources": source_rows,
        },
    )


def materialize_video_post(
    *,
    execution_id: str,
    ref: str,
    post_dir: Path,
    compose_payload: dict[str, object],
    review_payload: dict[str, object],
    execution_sequence: int,
) -> Path:
    pack = load_video_writing_pack(execution_id, ref)
    meta = load_video_draft_meta(execution_id, ref)
    draft = VideoScriptDraft.load(video_script_path(execution_id, ref))
    author_id = pack.creator.author_id
    profile_id = pack.creator.creator_profile_id
    created_at = meta.created_at or datetime.now(timezone.utc).isoformat()
    for path in (
        post_dir / "assets",
        post_dir / "manifest.json",
        post_dir / "provenance.json",
        post_dir / "subtitles.vtt",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    render_video_work_package(
        VideoRenderRequest(
            output_dir=post_dir,
            execution_id=execution_id,
            execution_sequence=execution_sequence,
            topic_id=ref,
            entity_ref=pack.entity_refs[0] if pack.entity_refs else "",
            tag_refs=pack.tag_refs,
            title=draft.title,
            caption=draft.caption,
            script_lines=draft.script_lines,
            source_frames=_source_frames(execution_id, pack),
            source_video=_source_video(execution_id, pack),
            author_id=author_id,
            creator_profile_id=profile_id,
            agent_run_id=meta.agent_run_id,
            agent_model=meta.model,
            created_at=created_at,
        )
    )
    manifest_path = post_dir / "manifest.json"
    manifest = read_json(manifest_path)
    entity_refs = [str(item) for item in manifest.get("entityRefs") or []]
    story_spine = compose_payload.get("storySpine")
    manifest.update(
        {
            "normalizedEntityRefs": _normalized_runtime_entity_refs(entity_refs),
            "reviewDecision": "approved",
            "publishLayout": "video",
            "publishAngle": str(compose_payload.get("publishAngle") or "体验"),
            "publishTitle": draft.title,
            "publishSeq": int(compose_payload.get("publishSeq") or 1),
            "storySpine": story_spine if isinstance(story_spine, dict) else {},
        }
    )
    creator_payload = pack.creator.to_dict()
    for field in (
        "creatorArchetype",
        "creatorProfileVersion",
        "creatorDisclosure",
        "experienceClaimMode",
        "authorQualitySignals",
    ):
        value = creator_payload.get(field)
        if value not in (None, "", {}):
            manifest[field] = value
    manifest["intersectionHints"] = build_intersection_hints(manifest)
    assert_valid(manifest, "content", "post_manifest", label=f"video_manifest:{ref}")
    write_json(manifest_path, manifest)

    download_dir = post_dir / "1.download"
    review_dir = post_dir / "5.review"
    download_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    _write_source_refs(post_dir, pack)
    provenance = read_json(post_dir / "provenance.json")
    write_json(review_dir / "provenance.json", provenance)
    write_json(
        review_dir / "finalization_report.json",
        {
            "schema": "quwoquan_data.video_finalization_report",
            "ref": ref,
            "scriptRef": "4.draft/video_script.json",
            "videoRef": "assets/video.mp4",
            "posterRef": "assets/poster.webp",
            "subtitlesRef": "subtitles.vtt",
            "renderStrategy": (
                "sourced_video_transcode"
                if pack.source_video is not None
                else "rights_cleared_image_sequence"
            ),
        },
    )
    write_review_evidence(
        review_dir,
        execution=stage_execution_context(execution_id),
        object_ref=ref,
        review_payload=review_payload,
    )
    return post_dir


__all__ = ["materialize_video_post"]
