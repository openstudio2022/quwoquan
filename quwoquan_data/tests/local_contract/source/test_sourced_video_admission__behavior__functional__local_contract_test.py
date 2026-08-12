"""真实源视频的媒体、水印、权利、规划与交付包闭环。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from email.message import Message
from pathlib import Path

import cv2
import numpy as np
import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for _path in (DATA_ROOT, DATA_ROOT / "tests", DATA_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.execution.controller.content_plan_video import (  # noqa: E402
    sourced_video_object_title,
)
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
from content.source import (
    handler_fetch_video,  # noqa: E402
    sourced_video_admission,  # noqa: E402
    sourced_video_unit,  # noqa: E402
)
from content.source.professional_video_probe import (  # noqa: E402
    probe_professional_video,
)
from content.source.sourced_video_admission import (  # noqa: E402
    probe_sourced_video,
    scan_sourced_video_watermark,
)
from content.source.sourced_video_unit import (  # noqa: E402
    _commercial_source_use_mode,
    write_admitted_sourced_video_unit,
)
from core.content_source_registry import (  # noqa: E402
    load_content_source_registry,
    verify_content_source_registry,
)
from core.image_safety import ImageVerdict  # noqa: E402
from core.paths import execution_root  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.video_source_admission import (  # noqa: E402
    assert_video_distribution_use_allowed,
)
from governance.content_supply_policy import (  # noqa: E402
    load_content_supply_policy,
)
from governance.coverage.distribution import ProductLifecycleState  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

EXECUTION_ID = "20260720--travel-video-supply--test-region-a--pilot-001"


def _video(path: Path, *, seconds: int = 7, motion_step: int = 3) -> Path:
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
            (40 + index * motion_step % 240, 120),
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
    assert_video_distribution_use_allowed(
        registry,
        source_id="douyin",
        source_kind="douyin",
        publication_admission="risk_accepted_attribution_only",
    )
    assert_video_distribution_use_allowed(
        registry,
        source_id="youtube",
        source_kind="tourism_video_site",
        publication_admission="research_release",
    )
    try:
        assert_video_distribution_use_allowed(
            registry,
            source_id="youtube",
            source_kind="tourism_video_site",
            publication_admission="risk_accepted_attribution_only",
        )
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("YouTube without commercial authorization must block")


def test_sample_frames_falls_back_to_ffmpeg_when_opencv_seek_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Commons WebM/VP9 often breaks OpenCV CAP_PROP_POS_FRAMES; ffmpeg must admit."""
    source = _video(tmp_path / "fallback.mp4", seconds=2)

    def fail_opencv(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        sourced_video_admission,
        "_sample_frames_with_opencv",
        fail_opencv,
    )
    with tempfile.TemporaryDirectory(prefix="qwq_ffmpeg_frames_") as temp:
        samples = sourced_video_admission._sample_frames(
            source,
            sample_count=3,
            output_dir=Path(temp),
        )
        assert len(samples) == 3
        assert all(path.suffix == ".png" and path.stat().st_size > 0 for path in samples)


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


def test_anonymous_video_download_records_public_access_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Response:
        def __init__(self) -> None:
            self.headers = Message()
            self.headers["Content-Type"] = "video/webm"
            self.headers["Content-Length"] = "4"
            self.headers["ETag"] = "public-etag"
            self._remaining = [b"test", b""]

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def geturl(self) -> str:
            return "https://upload.wikimedia.org/video.webm"

        def read(self, _size: int) -> bytes:
            return self._remaining.pop(0)

    requests = []

    class Opener:
        def open(self, request, *, timeout: int):
            requests.append((request, timeout))
            return Response()

    monkeypatch.setattr(
        handler_fetch_video,
        "load_runtime_policy",
        lambda _profile: type("Policy", (), {"source_video_read_timeout_seconds": 3})(),
    )
    monkeypatch.setattr(handler_fetch_video.urllib.request, "build_opener", lambda *_handlers: Opener())

    target = tmp_path / "source.webm"
    evidence = handler_fetch_video._download_sourced_video(
        "https://upload.wikimedia.org/video.webm",
        target,
    )

    assert target.read_bytes() == b"test"
    assert requests[0][0].get_header("Cookie") is None
    assert evidence == {
        "schema": "quwoquan_data.anonymous_video_download",
        "anonymousAccess": True,
        "credentialAssertion": "no_cookie_no_api_key_no_account_session",
        "requestedUrl": "https://upload.wikimedia.org/video.webm",
        "finalUrl": "https://upload.wikimedia.org/video.webm",
        "redirectChain": [],
        "httpStatus": 200,
        "contentType": "video/webm",
        "contentLength": 4,
        "responseHeaders": {
            "Content-Type": "video/webm",
            "Content-Length": "4",
            "ETag": "public-etag",
        },
        "sha256": (
            "sha256:9f86d081884c7d659a2feaa0c55ad015"
            "a3bf4f1b2b0b822cd15d6c15b0f00a08"
        ),
    }


def test_sourced_video_runs_from_source_unit_to_delivery_package(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sourced_video_unit,
        "load_content_distribution_policy",
        lambda: type(
            "CommercialPolicy",
            (),
            {"product_lifecycle_state": ProductLifecycleState.COMMERCIAL},
        )(),
    )
    _patch_output_root(monkeypatch, tmp_path)
    build_execution_fixture(EXECUTION_ID)
    source = _video(tmp_path / "source.mp4")
    evidence_path = write_admitted_sourced_video_unit(
        execution_id=EXECUTION_ID,
        object_ref="/entity/地点/景区/西湖",
        source_unit={
            "ordinal": 1,
            "sourceId": "wikimedia_commons_video",
            "sourceKind": "tourism_video_site",
                "title": "西湖航拍",
                "relevance": "展示西湖水域和苏堤的真实旅行视角",
                "rightsStatus": "verified",
        },
        source_video_path=source,
        original_creator_name="山海旅行者",
        platform="Wikimedia Commons",
        source_post_url="https://commons.wikimedia.org/wiki/File:West_Lake.webm",
        original_asset_url="https://example.com/direct/source.mp4",
        attribution_text="山海旅行者 · Wikimedia Commons · CC BY-SA 4.0",
        rights_basis="CC BY-SA 4.0",
        commercial_authorization_status="verified",
        publication_admission="commercial_release",
        authorization_proof_url="https://commons.wikimedia.org/wiki/File:West_Lake.webm",
        terms_url="https://creativecommons.org/licenses/by-sa/4.0/",
        risk_acceptance_id=None,
        audio_rights_status="no_audio",
        audio_authorization_proof_url=None,
        model_release_status="not_required",
        property_release_status="not_required",
        takedown_policy="notice_and_takedown",
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert_valid(
        payload,
        "content",
        "sourced_video_evidence",
        label="commercial sourced-video evidence",
    )
    for field, invalid in (
        ("commercialAuthorizationStatus", "unverified"),
        ("authorizationProofUrl", None),
        ("termsUrl", "http://insecure.example/terms"),
    ):
        forged = {**payload, field: invalid}
        with pytest.raises(ValueError):
            assert_valid(
                forged,
                "content",
                "sourced_video_evidence",
                label=f"forged commercial sourced-video evidence:{field}",
            )
    evidence, admission_issues = SourcedVideoEvidence.from_mapping(payload)
    assert admission_issues == ()
    _, forged_issues = SourcedVideoEvidence.from_mapping(
        {**payload, "commercialAuthorizationStatus": "unverified"}
    )
    assert "sourceVideo unverified authorization requires research or risk acceptance" in forged_issues
    assert (
        "sourceVideo commercial release requires verified HTTPS authorization and terms proof"
        in forged_issues
    )
    source_meta = json.loads(
        (evidence_path.parent / "meta.json").read_text(encoding="utf-8")
    )
    assert source_meta["sourceUseMode"] == "licensed_adaptation"
    assert source_meta["rightsMode"] == "attribution_no_watermark"
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
    assert manifest["sourceAttribution"]["platform"] == "Wikimedia Commons"
    assert (output / "assets" / "video.mp4").stat().st_size > 0
    assert (output / "assets" / "poster.webp").stat().st_size > 0
    provenance = json.loads(
        (output / "provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["renderStrategy"] == "sourced_video_transcode"
    assert provenance["outputAudioStatus"] == "none"


def test_professional_video_source_unit_preserves_receipt_and_popularity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        sourced_video_unit,
        "load_content_distribution_policy",
        lambda: type(
            "ResearchPolicy",
            (),
            {"product_lifecycle_state": ProductLifecycleState.RESEARCH},
        )(),
    )
    execution_id = "20260805--travel-video-acquisition--china--pilot-912"
    _patch_output_root(monkeypatch, tmp_path)
    build_execution_fixture(execution_id)
    source = _video(tmp_path / "professional.mp4", motion_step=12)
    content_sha256 = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    professional_probe = probe_professional_video(source)
    popularity = {
        "playCount": 10000,
        "likeCount": 1200,
        "commentCount": 80,
        "shareCount": 45,
        "favoriteCount": 300,
        "observedAt": "2026-08-05T00:00:00Z",
        "provider": "pexels_videos",
        "topic": "九寨沟",
        "timeBucket": "2026-W32",
        "popularityScore": 9.2,
        "popularityPercentile": 1.0,
        "rankingEligible": True,
        "ineligibleReason": "",
        "comparisonCandidateCount": 2,
    }
    evidence_path = write_admitted_sourced_video_unit(
        execution_id=execution_id,
        object_ref="/entity/地点/景区/九寨沟",
        source_unit={
            "ordinal": 1,
            "sourceId": "pexels_videos",
            "sourceKind": "tourism_video_site",
            "title": "九寨沟实拍",
            "relevance": "展示九寨沟湖泊与森林的真实运动画面",
            "rightsStatus": "unverified",
            "rightsIssues": ["commercial authorization is unverified"],
            "professionalAcquisitionReceiptRef": f"receipts/{'b' * 64}.json",
            "professionalAssetId": "pexels-jiuzhaigou-1",
            "professionalContentSha256": content_sha256,
            "premiumPlayableEligible": True,
            "mediaProbe": professional_probe,
            "popularitySignals": popularity,
        },
        source_video_path=source,
        original_creator_name="摄影师乙",
        platform="Pexels Videos",
        source_post_url="https://www.pexels.com/video/jiuzhaigou-1/",
        original_asset_url="https://videos.pexels.com/video-files/example.mp4",
        attribution_text="九寨沟实拍 — 摄影师乙 — Pexels Videos",
        rights_basis="platform rights pending verification",
        commercial_authorization_status="unverified",
        publication_admission="research_release",
        authorization_proof_url=None,
        terms_url="https://www.pexels.com/terms-of-service/",
        risk_acceptance_id=None,
        audio_rights_status="no_audio",
        audio_authorization_proof_url=None,
        model_release_status="unverified",
        property_release_status="not_required",
        takedown_policy="notice_and_takedown",
    )
    asset = json.loads(
        (evidence_path.parent / "assets/index.json").read_text(encoding="utf-8")
    )["assets"][0]
    assert asset["professionalAcquisitionReceiptRef"] == f"receipts/{'b' * 64}.json"
    assert asset["professionalAssetId"] == "pexels-jiuzhaigou-1"
    assert asset["professionalContentSha256"] == content_sha256
    assert asset["professionalMediaProbe"] == professional_probe
    assert asset["popularitySignals"] == popularity
    assert asset["premiumPlayableEligible"] is True
    assert asset["usageScope"] == "internal_reference"


def test_risk_only_sourced_video_cannot_claim_licensed_adaptation() -> None:
    with pytest.raises(ValueError, match="risk-only sourced video"):
        _commercial_source_use_mode(
            publication_admission="risk_accepted_attribution_only",
            commercial_authorization_status="unverified",
            rights_basis="risk_accepted_attribution_only",
            authorization_proof_url=None,
        )


def test_unknown_video_rights_basis_cannot_claim_licensed_adaptation() -> None:
    with pytest.raises(ValueError, match="licensed rights basis"):
        _commercial_source_use_mode(
            publication_admission="commercial_release",
            commercial_authorization_status="verified",
            rights_basis="unknown",
            authorization_proof_url="https://rights.example/video",
        )


def test_sourced_video_object_title_preserves_specific_source_identity() -> None:
    assert sourced_video_object_title(
        target="杭州西湖",
        source_title="西湖游船视角下的柳岸与湖面",
    ) == "杭州西湖｜西湖游船视角下的柳岸与湖面"
    assert sourced_video_object_title(
        target="杭州西湖",
        source_title="杭州西湖四季实拍",
    ) == "杭州西湖四季实拍"
    with pytest.raises(ValueError, match="sourced video title"):
        sourced_video_object_title(target="杭州西湖", source_title="")
