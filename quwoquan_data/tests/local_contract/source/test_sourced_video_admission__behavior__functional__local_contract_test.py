"""真实源视频的媒体、水印、权利、规划与交付包闭环。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import cv2
import numpy as np


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for _path in (DATA_ROOT, DATA_ROOT / "tests", DATA_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.post.content_plan_video_validation import (  # noqa: E402
    _validate_sourced_video,
)
from content.post.video.source_video import (  # noqa: E402
    SourcedVideoAsset,
    SourcedVideoEvidence,
)
from content.post.video.sourced_package import (  # noqa: E402
    SourcedVideoPackageRequest,
    render_sourced_video_package,
)
from content.source import sourced_video_admission  # noqa: E402
from content.source.sourced_video_admission import (  # noqa: E402
    probe_sourced_video,
    scan_sourced_video_watermark,
)
from content.source.sourced_video_unit import (  # noqa: E402
    write_admitted_sourced_video_unit,
)
from core.image_safety import ImageVerdict  # noqa: E402
from core.content_source_registry import (  # noqa: E402
    load_content_source_registry,
    verify_content_source_registry,
)
from core.paths import execution_root  # noqa: E402
from core.video_source_admission import (  # noqa: E402
    assert_video_source_admitted,
)
from governance.content_supply_policy import (  # noqa: E402
    load_content_supply_policy,
)
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402


EXECUTION_ID = "20260720--travel-video-supply--test-region-a--pilot-001"


def _video(path: Path, *, seconds: int = 7) -> Path:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        8,
        (320, 240),
    )
    assert writer.isOpened()
    for index in range(seconds * 8):
        x = np.linspace(20, 180, 320, dtype=np.uint8)
        frame = np.empty((240, 320, 3), dtype=np.uint8)
        frame[:, :, 0] = x
        frame[:, :, 1] = 80 + (index % 20)
        frame[:, :, 2] = 35
        cv2.circle(
            frame,
            (40 + index * 3 % 240, 120),
            24,
            (210, 190, 80),
            -1,
        )
        writer.write(frame)
    writer.release()
    assert path.is_file()
    return path


def _patch_output_root(monkeypatch, tmp_path: Path) -> None:
    from core import paths

    root = tmp_path / ".qwq_output" / "data" / "tasks"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", root)
    monkeypatch.setattr(paths, "RUNTIME_ROOT", root)


def test_real_media_probe_and_sampled_ocr_admit_clean_video(tmp_path: Path) -> None:
    source = _video(tmp_path / "clean.mp4")
    probe = probe_sourced_video(source)
    watermark = scan_sourced_video_watermark(source)
    assert probe["durationMs"] >= 6_000
    assert probe["width"] == 320
    assert probe["height"] == 240
    assert watermark["sampleCount"] == 12
    assert watermark["ocrReviewed"] is True
    assert watermark["watermarkDetected"] is False
    assert watermark["decision"] == "passed"


def test_video_commercial_matrix_covers_all_sources_and_blocks_wrong_mode() -> None:
    registry = load_content_source_registry()
    assert verify_content_source_registry() == []
    assert_video_source_admitted(
        registry,
        source_id="douyin",
        source_kind="douyin",
        publication_admission="risk_accepted_attribution_only",
    )
    try:
        assert_video_source_admitted(
            registry,
            source_id="youtube",
            source_kind="tourism_video_site",
            publication_admission="risk_accepted_attribution_only",
        )
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("YouTube without commercial authorization must block")


def test_sampled_watermark_hit_is_fail_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = _video(tmp_path / "blocked.mp4", seconds=1)

    def fake_assess(path: Path, *, require_ocr: bool) -> ImageVerdict:
        del require_ocr
        blocked = path.name == "sample-005.jpg"
        return ImageVerdict(
            path=str(path),
            status="unsafe" if blocked else "safe",
            faces=0,
            has_watermark=blocked,
            text_area_ratio=0.01,
            ocr_text="抖音" if blocked else "",
            reasons=("watermark_text",) if blocked else (),
            backends=("cv", "ocr"),
        )

    monkeypatch.setattr(sourced_video_admission, "assess_image", fake_assess)
    evidence = scan_sourced_video_watermark(source)
    assert evidence["watermarkDetected"] is True
    assert evidence["decision"] == "blocked"


def test_sourced_video_runs_from_source_unit_to_delivery_package(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_output_root(monkeypatch, tmp_path)
    build_execution_fixture(EXECUTION_ID)
    source = _video(tmp_path / "source.mp4")
    evidence_path = write_admitted_sourced_video_unit(
        execution_id=EXECUTION_ID,
        object_ref="/entity/地点/景区/西湖",
        source_unit={
            "ordinal": 1,
            "sourceId": "toutiao_video",
            "sourceKind": "toutiao",
            "title": "西湖航拍",
            "relevance": "展示西湖水域和苏堤的真实旅行视角",
        },
        source_video_path=source,
        original_creator_name="山海旅行者",
        platform="头条",
        source_post_url="https://www.toutiao.com/video/123456",
        original_asset_url="https://example.com/direct/source.mp4",
        attribution_text="原创：山海旅行者 · 来源：头条",
        rights_basis="risk_accepted_attribution_only",
        commercial_authorization_status="not_verified",
        publication_admission="risk_accepted_attribution_only",
        authorization_proof_url=None,
        terms_url="https://www.toutiao.com/user/terms",
        risk_acceptance_id="RA-VIDEO-CANARY-001",
        audio_rights_status="no_audio",
        audio_authorization_proof_url=None,
        model_release_status="not_required",
        property_release_status="not_required",
        takedown_policy="notice_and_takedown",
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence, admission_issues = SourcedVideoEvidence.from_mapping(payload)
    assert admission_issues == ()
    asset_index = json.loads(
        (evidence_path.parent / "assets/index.json").read_text(encoding="utf-8")
    )
    indexed_asset = asset_index["assets"][0]
    assert indexed_asset["fileName"] == "source.mp4"
    assert indexed_asset["sha256"] == evidence.sha256
    assert indexed_asset["rightsAuditStatus"] == "verified"
    author_prompt = evidence.author_prompt_dict()
    assert "authorizationProofUrl" not in author_prompt
    assert "commercialAuthorizationStatus" not in author_prompt
    assert author_prompt["originalCreatorName"] == "山海旅行者"
    root = execution_root(EXECUTION_ID)
    claimed_assets: list[tuple[str, str]] = []
    claimed_hashes: list[tuple[str, str]] = []
    plan_issues = _validate_sourced_video(
        root=root,
        item={
            "sourceVideo": payload,
            "assetRefs": [evidence.asset_ref],
        },
        ref="西湖_video",
        claim_asset=lambda ref, value: claimed_assets.append((ref, value)),
        claim_asset_sha=lambda ref, value: claimed_hashes.append((ref, value)),
    )
    assert plan_issues == []
    assert claimed_assets == [("西湖_video", evidence.asset_ref)]
    assert claimed_hashes == [("西湖_video", evidence.sha256)]

    output = tmp_path / "package"
    render_sourced_video_package(
        SourcedVideoPackageRequest(
            output_dir=output,
            execution_id=EXECUTION_ID,
            execution_sequence=1,
            topic_id="西湖_video",
            entity_ref="/entity/地点/景区/西湖",
            tag_refs=("浙江", "西湖"),
            title="西湖水岸七秒",
            caption="沿苏堤看西湖水岸层次",
            script_lines=("沿苏堤看湖岸层次。", "画面由原创者授权归属信息伴随展示。"),
            source=SourcedVideoAsset(
                path=root / evidence.asset_ref,
                evidence=evidence,
            ),
            author_id="builtin_travel_video_editor",
            creator_profile_id="qwq_creator_travel_video_editor_001",
            agent_run_id="test-agent-run",
            agent_model="test-model",
            created_at="2026-07-20T12:00:00Z",
        ),
        policy=load_content_supply_policy("travel").video_delivery,
    )
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["vertical"] == "travel"
    assert all(
        asset["rightsAuditStatus"] == "verified"
        and asset["rightsAuditIssues"] == []
        for asset in manifest["assets"]
    )
    assert manifest["sourceAttribution"]["originalCreatorName"] == "山海旅行者"
    assert manifest["sourceAttribution"]["platform"] == "头条"
    assert (output / "assets" / "video.mp4").stat().st_size > 0
    assert (output / "assets" / "poster.webp").stat().st_size > 0
    provenance = json.loads(
        (output / "provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["renderStrategy"] == "sourced_video_transcode"
    assert provenance["outputAudioStatus"] == "none"
