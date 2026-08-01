"""Formal video work packages are rendered and validated from typed evidence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib

import cv2
import numpy as np
import pytest

import content.post.video.package as video_package_module
import content.execution.controller.content_plan_video as content_plan_video
from content.execution.context import ExecutionContext
from content.post.video import (
    VideoRenderRequest,
    VideoSourceBasis,
    VideoSourceFrame,
    render_video_work_package,
    validate_video_work_package,
)
from governance.coverage.license import RightsAuditStatus
from governance.creators.assignment import creator_profile_digest
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
from content.post.video.codec import VideoSourceFrameEvidence
from content.templates.registry import TemplateRegistry
from content.source.media.check import check_images
from core.io import read_json, write_json
from core.paths import execution_root
from support.execution_manifest_fixture import (
    ExecutionFixtureBuilder,
    build_execution_fixture,
)

LANDSCAPE_CREATOR_PROFILE_DIGEST = creator_profile_digest(
    TemplateRegistry.load().creators["qwq_creator_landscape_photographer_001"]
)


def _source_frame(root: Path, index: int) -> VideoSourceFrame:
    path = root / f"source-{index}.jpg"
    image = np.zeros((240, 360, 3), dtype=np.uint8)
    image[:, :] = (40 * index, 60, 180 - 20 * index)
    cv2.circle(image, (80 + index * 40, 120), 45, (230, 220, 40), -1)
    assert cv2.imwrite(str(path), image)
    return VideoSourceFrame(
        path=path,
        asset_ref=f"sources/测试实体甲/assets/source-{index}.jpg",
        source_url=f"https://commons.wikimedia.org/source-{index}",
        rights_ref=f"sources/测试实体甲/rights/source-{index}.json",
        creator="fixture photographer",
        license="CC BY 4.0",
        basis=VideoSourceBasis.RIGHTS_CLEARED,
        source_use_mode="licensed_adaptation",
        rights_audit_status=RightsAuditStatus.VERIFIED,
        rights_audit_issues=(),
    )


def _request(tmp_path: Path) -> VideoRenderRequest:
    return VideoRenderRequest(
        output_dir=tmp_path / "video-package",
        execution_id="20260716--travel-video-supply--test-region-a--pilot-901",
        execution_sequence=901,
        topic_id="测试实体甲__video_1",
        entity_ref="/entity/地点/景区/测试实体甲",
        tag_refs=("Entity/地点/景区",),
        title="测试实体甲三段光影",
        caption="从湖岸、长桥到暮色的三段观察",
        script_lines=("湖岸晨光", "长桥倒影", "暮色收束"),
        source_frames=tuple(_source_frame(tmp_path, index) for index in range(1, 3)),
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
    assert manifest["vertical"] == "travel"
    video = manifest["assets"][0]
    assert all(
        asset["rightsAuditStatus"] == "verified"
        and asset["rightsAuditIssues"] == []
        for asset in manifest["assets"]
    )
    assert video["codec"] == "h264"
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["durationMs"] == 6000
    assert len(read_json(package / "provenance.json")["sources"]) == 2


def test_video_work_package_detects_evidence_tampering(tmp_path: Path) -> None:
    package = render_video_work_package(_request(tmp_path))
    (package / "subtitles.vtt").write_text("tampered", encoding="utf-8")

    issues = validate_video_work_package(package)
    assert "video subtitlesSha256 mismatch" in issues
    assert "video subtitles are not a valid non-empty WebVTT document" in issues


def test_video_work_package_requires_explicit_rights_audit_status(tmp_path: Path) -> None:
    package = render_video_work_package(_request(tmp_path))
    manifest_path = package / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["assets"][0].pop("rightsAuditStatus")
    write_json(manifest_path, manifest)

    assert "video asset rightsAuditStatus is invalid" in validate_video_work_package(
        package
    )


def test_video_frame_contract_has_no_rights_or_source_mode_fallback() -> None:
    payload = {
        "assetRef": "sources/fixture/assets/frame.jpg",
        "sourceRef": "sources/fixture/source.md",
        "rightsRef": "sources/fixture/assets/index.json#001",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Frame.jpg",
        "creator": "Fixture Photographer",
        "license": "CC BY 4.0",
        "sha256": "sha256:" + "a" * 64,
    }

    with pytest.raises(ValueError, match="sourceUseMode is invalid or missing"):
        VideoSourceFrameEvidence.from_mapping(payload, index=0)

    payload["sourceUseMode"] = "factual_reference_only"
    with pytest.raises(ValueError, match="rightsAuditStatus is invalid or missing"):
        VideoSourceFrameEvidence.from_mapping(payload, index=0)


def test_commercial_video_work_package_rejects_unverified_source_frame(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    unverified = replace(
        request.source_frames[0],
        rights_audit_status=RightsAuditStatus.UNVERIFIED,
        rights_audit_issues=("imageRights: source terms not yet verified",),
    )

    with pytest.raises(ValueError, match="rights are not verified"):
        render_video_work_package(
            replace(request, source_frames=(unverified, *request.source_frames[1:]))
        )


def test_frame_montage_preserves_unverified_audit_instead_of_upgrading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    issue = "imageRights: source terms not yet verified"
    frames = tuple(
        replace(
            frame,
            rights_audit_status=RightsAuditStatus.UNVERIFIED,
            rights_audit_issues=(issue,),
        )
        for frame in request.source_frames
    )
    monkeypatch.setattr(
        video_package_module,
        "rights_proof_required",
        lambda _vertical: False,
    )

    package = render_video_work_package(replace(request, source_frames=frames))

    manifest = read_json(package / "manifest.json")
    assert all(
        asset["rightsAuditStatus"] == "unverified"
        and asset["rightsAuditIssues"] == [issue]
        for asset in manifest["assets"]
    )
    provenance = read_json(package / "provenance.json")
    assert all(
        source["rightsAuditStatus"] == "unverified"
        and source["rightsAuditIssues"] == [issue]
        for source in provenance["sources"]
    )


def _content_plan_frame_source(
    *,
    execution_id: str,
    source_use_mode: str,
    rights_audit_status: str,
    rights_audit_issues: list[str],
) -> tuple[ExecutionContext, Path]:
    root = execution_root(execution_id)
    source_dir = (
        root
        / "entities/地点/景区/测试实体甲/1.download/sources/001__video_frames"
    )
    assets_dir = source_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text("# 测试实体甲视频帧\n", encoding="utf-8")
    write_json(
        source_dir / "meta.json",
        {
            "researchLane": "video",
            "sourceUseMode": source_use_mode,
        },
    )
    image_path = assets_dir / "frame.jpg"
    rng = np.random.default_rng(20260728)
    image = rng.integers(0, 256, size=(240, 360, 3), dtype=np.uint8)
    assert cv2.imwrite(str(image_path), image)
    write_json(
        assets_dir / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "001_001",
                    "fileName": image_path.name,
                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Frame.jpg",
                    "sourceCollectionId": "fixture:video-frames",
                    "sha256": _sha256(image_path),
                    "creator": "Fixture Photographer",
                    "credit": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "usageScope": "app_publish",
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Frame.jpg"
                    ),
                    "modelReleaseStatus": "not_required",
                    "rightsAuditStatus": rights_audit_status,
                    "rightsAuditIssues": rights_audit_issues,
                }
            ]
        },
    )
    return (
        ExecutionContext(
            execution_id=execution_id,
            entity_ids=("测试实体甲",),
            spec=ExecutionFixtureBuilder(execution_id).spec(),
        ),
        source_dir,
    )


def test_video_content_plan_rejects_unverified_commercial_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, source_dir = _content_plan_frame_source(
        execution_id="20260716--travel-video-plan--test-region-a--pilot-903",
        source_use_mode="factual_reference_only",
        rights_audit_status="unverified",
        rights_audit_issues=["imageRights: source terms not yet verified"],
    )
    monkeypatch.setattr(
        content_plan_video,
        "iter_source_units",
        lambda _object_dir: [source_dir],
    )

    candidates, rejects = content_plan_video._source_frames(ctx, source_dir.parent)

    assert candidates == []
    assert rejects == {"rights_not_verified": 1}


def test_video_content_plan_preserves_source_unit_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, source_dir = _content_plan_frame_source(
        execution_id="20260716--travel-video-plan--test-region-a--pilot-904",
        source_use_mode="factual_reference_only",
        rights_audit_status="verified",
        rights_audit_issues=[],
    )
    monkeypatch.setattr(
        content_plan_video,
        "iter_source_units",
        lambda _object_dir: [source_dir],
    )

    candidates, rejects = content_plan_video._source_frames(ctx, source_dir.parent)

    assert rejects == {}
    assert len(candidates) == 1
    assert candidates[0].source_use_mode == "factual_reference_only"
    assert candidates[0].as_brief_value()["sourceUseMode"] == (
        "factual_reference_only"
    )


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_prepare_video_brief_shortfall_uses_post_compose_stage() -> None:
    """Frame shortfall must emit a typed issue, not crash on a removed stage enum."""
    from content.execution.stage_reports import stage_result_path

    execution_id = "20260716--travel-video-supply--test-region-a--pilot-905"
    ref = "测试实体甲_video_shortfall"
    build_execution_fixture(
        execution_id,
        targets=[{"name": "测试实体甲", "entityType": "地点/景区"}],
    )
    write_execution_runtime_state(execution_id, command="post")
    write_brief_object(
        execution_id,
        ref,
        {
            "titleHint": "帧不足短视频",
            "carrier": "video",
            "entityRefs": ["/entity/地点/景区/测试实体甲"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍", "Format/内容载体/视频/短视频"],
            "templateId": "travel.entity.short_video",
            "sourceFrames": [],
            "authorId": "builtin_travel_landscape_photographer",
            "creatorProfileId": "qwq_creator_landscape_photographer_001",
            "creatorArchetype": "landscape_photographer",
            "creatorProfileDigest": LANDSCAPE_CREATOR_PROFILE_DIGEST,
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
        },
        content_type="video",
    )

    pack = prepare_video_brief(execution_id, ref)
    assert pack["sourceFrames"] == []

    envelope = read_json(
        stage_result_path(execution_id, "post", "compose_brief_gate", ref)
    )
    gate = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    assert gate["passed"] is False
    issues = gate.get("issues") or []
    assert any(
        isinstance(issue, dict)
        and issue.get("code") == "DATA.MEDIA.PUBLISHABLE_SHORTFALL"
        and issue.get("stage") == "post_compose"
        for issue in issues
    ), issues


def test_video_execution_reaches_review_materialization_and_post_gate() -> None:
    execution_id = "20260716--travel-video-supply--test-region-a--pilot-902"
    ref = "测试实体甲_video"
    build_execution_fixture(
        execution_id,
        targets=[{"name": "测试实体甲", "entityType": "地点/景区"}],
    )
    write_execution_runtime_state(execution_id, command="post")
    root = execution_root(execution_id)
    source_dir = root / "entities/地点/景区/测试实体甲/1.download/sources/测试实体甲__video_fixture"
    assets_dir = source_dir / "assets"
    rights_dir = source_dir / "rights"
    assets_dir.mkdir(parents=True, exist_ok=True)
    rights_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text("# 测试实体甲视频来源\n\n三张已清权的景观画面。\n", encoding="utf-8")
    write_json(
        source_dir / "meta.json",
        {
            "sourceUseMode": "licensed_adaptation",
            "researchLane": "video",
        },
    )
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
                "sourceUrl": f"https://commons.wikimedia.org/wiki/File:测试实体甲-{index}.jpg",
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
                "sourceUrl": f"https://commons.wikimedia.org/wiki/File:测试实体甲-{index}.jpg",
                "creator": f"Fixture Creator {index}",
                "license": "CC BY 4.0",
                "sha256": _sha256(image_path),
                "caption": f"测试实体甲景观画面 {index}",
                "sourceCollectionId": "fixture:测试实体甲-video",
                "sourceUseMode": "licensed_adaptation",
                "rightsAuditStatus": "verified",
                "rightsAuditIssues": [],
            }
        )
    brief = {
        "titleHint": "测试实体甲三段光影",
        "carrier": "video",
        "entityRefs": ["/entity/地点/景区/测试实体甲"],
        "tagRefs": ["Topic/旅行/玩法/摄影旅拍", "Format/内容载体/视频/短视频"],
        "templateId": "travel.entity.short_video",
        "sourceFrames": source_frames,
        "authorId": "builtin_travel_landscape_photographer",
        "creatorProfileId": "qwq_creator_landscape_photographer_001",
        "creatorArchetype": "landscape_photographer",
        "creatorProfileDigest": LANDSCAPE_CREATOR_PROFILE_DIGEST,
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
            "title": "测试实体甲三段光影",
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
    assert manifest["contentIdentity"] == "work"
    assert manifest["publishAngle"] == "体验"
    assert manifest["reviewDecision"] == "approved"
    gate_issues = gate_post(execution_id, "video", refs=[ref])
    assert gate_issues == [], "\n".join(gate_issues)
