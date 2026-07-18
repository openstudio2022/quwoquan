"""Formal video work packages are rendered and validated from typed evidence."""
from __future__ import annotations

from pathlib import Path
import hashlib

import cv2
import numpy as np

from content.post.video import (
    VideoRenderRequest,
    VideoSourceBasis,
    VideoSourceFrame,
    render_video_work_package,
    validate_video_work_package,
)
from content.execution.runtime_state import write_execution_runtime_state
from content.post.gate import gate_post
from content.post.materialize_apply import materialize_posts
from content.post.object_index import write_brief_object
from content.post.video.authoring import (
    finalize_video_author_meta,
    prepare_video_brief,
    review_video_draft,
    video_script_path,
)
from content.source.media.check import check_images
from core.io import read_json, write_json
from core.paths import execution_root
from support.execution_manifest_fixture import build_execution_fixture


def _source_frame(root: Path, index: int) -> VideoSourceFrame:
    path = root / f"source-{index}.jpg"
    image = np.zeros((240, 360, 3), dtype=np.uint8)
    image[:, :] = (40 * index, 60, 180 - 20 * index)
    cv2.circle(image, (80 + index * 40, 120), 45, (230, 220, 40), -1)
    assert cv2.imwrite(str(path), image)
    return VideoSourceFrame(
        path=path,
        asset_ref=f"sources/west-lake/assets/source-{index}.jpg",
        source_url=f"https://commons.wikimedia.org/source-{index}",
        rights_ref=f"sources/west-lake/rights/source-{index}.json",
        creator="fixture photographer",
        license="CC BY 4.0",
        basis=VideoSourceBasis.RIGHTS_CLEARED,
    )


def _request(tmp_path: Path) -> VideoRenderRequest:
    return VideoRenderRequest(
        output_dir=tmp_path / "video-package",
        execution_id="20260716--travel-video-cold-start--cn-zhejiang--canary-901",
        execution_sequence=901,
        topic_id="西湖__video_1",
        entity_ref="/entity/地点/景区/西湖",
        tag_refs=("Entity/地点/景区",),
        title="西湖三段光影",
        caption="从湖岸、长桥到暮色的三段观察",
        script_lines=("湖岸晨光", "长桥倒影", "暮色收束"),
        source_frames=tuple(_source_frame(tmp_path, index) for index in range(1, 4)),
        author_id="creator.fixture.video",
        creator_profile_id="creator.fixture.video",
        agent_run_id="agent-run-video-901",
        agent_model="composer",
        created_at="2026-07-16T10:00:00Z",
    )


def test_video_work_package_renders_h264_poster_subtitles_and_provenance(tmp_path: Path) -> None:
    package = render_video_work_package(_request(tmp_path))

    assert validate_video_work_package(package) == []
    assert (package / "assets/video.mp4").is_file()
    assert (package / "assets/poster.webp").is_file()
    assert (package / "subtitles.vtt").read_text(encoding="utf-8").startswith("WEBVTT\n")
    manifest = read_json(package / "manifest.json")
    video = manifest["assets"][0]
    assert video["codec"] == "h264"
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["durationMs"] == 6000
    assert len(read_json(package / "provenance.json")["sources"]) == 3


def test_video_work_package_detects_evidence_tampering(tmp_path: Path) -> None:
    package = render_video_work_package(_request(tmp_path))
    (package / "subtitles.vtt").write_text("tampered", encoding="utf-8")

    issues = validate_video_work_package(package)
    assert "video subtitlesSha256 mismatch" in issues
    assert "video subtitles are not a valid non-empty WebVTT document" in issues


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_video_execution_reaches_review_materialization_and_post_gate() -> None:
    execution_id = "20260716--travel-video-cold-start--cn-zhejiang--canary-902"
    ref = "西湖_video"
    build_execution_fixture(
        execution_id,
        targets=[{"name": "西湖", "entityType": "地点/景区"}],
    )
    write_execution_runtime_state(execution_id, command="post")
    root = execution_root(execution_id)
    source_dir = root / "entities/地点/景区/西湖/1.download/sources/西湖__video_fixture"
    assets_dir = source_dir / "assets"
    rights_dir = source_dir / "rights"
    assets_dir.mkdir(parents=True, exist_ok=True)
    rights_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text("# 西湖视频来源\n\n三张已清权的景观画面。\n", encoding="utf-8")
    source_frames: list[dict[str, str]] = []
    for index in range(1, 4):
        image_path = assets_dir / f"frame-{index}.jpg"
        image = np.zeros((240, 360, 3), dtype=np.uint8)
        image[:, :] = (30 * index, 70, 170 - 15 * index)
        cv2.circle(image, (70 + index * 55, 120), 38, (225, 210, 45), -1)
        assert cv2.imwrite(str(image_path), image)
        rights_path = rights_dir / f"frame-{index}.json"
        write_json(
            rights_path,
            {
                "sourceUrl": f"https://commons.wikimedia.org/wiki/File:west-lake-{index}.jpg",
                "creator": f"Fixture Creator {index}",
                "license": "CC BY 4.0",
                "authorizationProof": "fixture rights proof",
            },
        )
        source_frames.append(
            {
                "assetRef": image_path.relative_to(root).as_posix(),
                "sourceRef": source_path.relative_to(root).as_posix(),
                "rightsRef": rights_path.relative_to(root).as_posix(),
                "sourceUrl": f"https://commons.wikimedia.org/wiki/File:west-lake-{index}.jpg",
                "creator": f"Fixture Creator {index}",
                "license": "CC BY 4.0",
                "sha256": _sha256(image_path),
                "caption": f"西湖景观画面 {index}",
                "sourceCollectionId": "fixture:west-lake-video",
            }
        )
    brief = {
        "titleHint": "西湖三段光影",
        "carrier": "video",
        "entityRefs": ["/entity/地点/景区/西湖"],
        "tagRefs": ["Topic/旅行/玩法/摄影旅拍", "Format/内容载体/视频/短视频"],
        "templateId": "travel.entity.short_video",
        "sourceFrames": source_frames,
        "authorId": "builtin_travel_landscape_photographer",
        "creatorProfileId": "qwq_creator_landscape_photographer_001",
        "creatorArchetype": "landscape_photographer",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
            "visible": True,
        },
        "experienceClaimMode": "visual_discovery",
        "authorQualitySignals": {
            "qualityScore": 0.87,
            "fatigueScore": 0.2,
            "riskTier": "low",
        },
    }
    write_brief_object(execution_id, ref, brief, content_type="video")
    pack = prepare_video_brief(execution_id, ref)
    assert len(pack["sourceFrames"]) == 3
    write_json(
        video_script_path(execution_id, ref),
        {
            "title": "西湖三段光影",
            "caption": "从湖岸、长桥到暮色的三段观察",
            "scriptLines": ["湖岸晨光", "长桥倒影", "暮色收束"],
        },
    )
    assert finalize_video_author_meta(
        execution_id,
        ref,
        run_id="agent-run-video-902",
        agent_id="agent-video-902",
        model="composer",
    )
    review = review_video_draft(execution_id, ref)
    assert review["decision"] == "approved", review["issues"]
    media_status = check_images(execution_id, [ref], allow_needs_review=True)
    assert media_status == [
        {
            "ref": ref,
            "passed": True,
            "summary": media_status[0]["summary"],
        }
    ]
    materialized = materialize_posts(execution_id, "video", refs=[ref])
    assert len(materialized) == 1
    post_dir = materialized[0]
    assert (post_dir / "assets/video.mp4").is_file()
    assert (post_dir / "assets/poster.webp").is_file()
    assert (post_dir / "subtitles.vtt").is_file()
    assert not (post_dir / "article.md").exists()
    manifest = read_json(post_dir / "manifest.json")
    assert manifest["contentType"] == "video"
    assert manifest["publishAngle"] == "体验"
    assert manifest["reviewDecision"] == "approved"
    gate_issues = gate_post(execution_id, "video", refs=[ref])
    assert gate_issues == [], "\n".join(gate_issues)
