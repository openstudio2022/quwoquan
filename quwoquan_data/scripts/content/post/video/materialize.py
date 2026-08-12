"""Materialize one approved formal video object."""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.intersection_signal import build_intersection_hints
from core.io import read_json, write_json
from core.paths import execution_root
from core.schema import assert_valid
from governance.content_supply_policy import load_content_supply_policy

from content.execution.identity import parse_execution_id
from content.execution.runtime_contract import stage_execution_context
from content.post.materialize_contract import _normalized_runtime_entity_refs
from content.post.review_evidence import write_review_evidence
from content.post.video.authoring import video_script_path
from content.post.video.codec import (
    VideoScriptDraft,
    VideoWritingPack,
    load_video_draft_meta,
    load_video_writing_pack,
)
from content.post.video.source_video import SourcedVideoAsset
from content.post.video.sourced_package import (
    SourcedVideoPackageRequest,
    render_sourced_video_package,
)


def _source_video(
    execution_id: str,
    pack: VideoWritingPack,
) -> SourcedVideoAsset:
    if pack.source_video is None:
        raise ValueError("video materialization requires sourceVideo")
    return SourcedVideoAsset(
        path=execution_root(execution_id) / pack.source_video.asset_ref,
        evidence=pack.source_video,
    )


def _write_source_refs(post_dir: Path, pack: VideoWritingPack) -> None:
    if pack.source_video is None:
        raise ValueError("video source refs require sourceVideo")
    source_rows = [{
        "role": "sourced_video",
        "sourceRef": pack.source_video.source_ref,
        "sourceAssetRef": pack.source_video.asset_ref,
        "rightsRef": pack.source_video.rights_ref,
        "sourceUrl": pack.source_video.source_post_url,
        "sha256": pack.source_video.sha256,
    }]
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
    render_sourced_video_package(
        SourcedVideoPackageRequest(
            output_dir=post_dir,
            execution_id=execution_id,
            execution_sequence=execution_sequence,
            topic_id=ref,
            entity_ref=pack.entity_refs[0] if pack.entity_refs else "",
            tag_refs=pack.tag_refs,
            title=draft.title,
            caption=draft.caption,
            script_lines=draft.script_lines,
            source=_source_video(execution_id, pack),
            author_id=author_id,
            creator_profile_id=profile_id,
            agent_run_id=meta.agent_run_id,
            agent_model=meta.model,
            created_at=created_at,
        ),
        policy=load_content_supply_policy(
            parse_execution_id(execution_id).vertical
        ).video_delivery,
    )
    manifest_path = post_dir / "manifest.json"
    manifest = read_json(manifest_path)
    entity_refs = [str(item) for item in manifest.get("entityRefs") or []]
    story_spine = compose_payload.get("storySpine")
    manifest.update(
        {
            "contentId": "qwq_data_"
            + hashlib.sha256(f"{execution_id}|{ref}".encode()).hexdigest()[:24],
            "version": 1,
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
        "creatorProfileDigest",
        "creatorDisclosure",
        "experienceClaimMode",
        "authorQualitySignals",
    ):
        value = creator_payload.get(field)
        if value not in (None, "", {}):
            manifest[field] = value
    from content.execution.planning.rewrite import apply_execution_rewrite_identity

    manifest = apply_execution_rewrite_identity(
        manifest,
        execution_id=execution_id,
        ref=ref,
    )
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
            "renderStrategy": "sourced_video_transcode",
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
