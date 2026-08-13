"""governed stock 视频 provider（Pexels/Pixabay）走同一 acquisition/审查链的本地合同。"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
from content.execution.agent.outcome import AgentRunOutcome
from core.control_types import AgentProvider
from content.source import professional_commons_video_input as commons_input
from content.source import professional_video_acquisition
from content.source.research import auto_plan_video_stock as stock
from content.source.research.network_io import HttpFetchResult
from governance.coverage.distribution import ProductLifecycleState

_SHA = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
_SOURCE_DIGEST = "sha256:" + "1" * 64
_ENTITY_DIGEST = "sha256:" + "2" * 64
_REVISION = "sha256:" + "3" * 64
_BUNDLE_DIGEST = "sha256:" + "4" * 64


def _video(path: Path, *, seed: int) -> Path:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180)
    )
    assert writer.isOpened()
    try:
        for index in range(40):
            frame = np.full((180, 320, 3), 30 + seed, dtype=np.uint8)
            cv2.circle(
                frame,
                (20 + (index * 7) % 280, 90),
                24,
                (240, 180, 30),
                thickness=-1,
            )
            writer.write(frame)
    finally:
        writer.release()
    assert path.stat().st_size > 4_000
    return path


def _pexels_candidate() -> dict[str, object]:
    return {
        "sourceId": "pexels_videos",
        "title": "zhangjiajie mountain aerial",
        "relevance": "zhangjiajie mountain aerial china landscape",
        "platform": "Pexels Videos",
        "assetUrl": "https://videos.pexels.com/video-files/123/123-hd_1920_1080.mp4",
        "sourcePostUrl": "https://www.pexels.com/video/zhangjiajie-mountain-aerial-123/",
        "authorizationProofUrl": "https://www.pexels.com/video/zhangjiajie-mountain-aerial-123/",
        "termsUrl": "https://www.pexels.com/license/",
        "rightsBasis": "Pexels License",
        "originalCreatorName": "Pexels creator",
        "apiEvidenceUrl": "https://api.pexels.com/videos/search?query=Zhangjiajie&per_page=15",
        "popularitySignals": {
            "observedAt": "2026-08-13T08:00:00+00:00",
        },
    }


def _handoff() -> dict[str, object]:
    return {
        "sourceRevision": _REVISION,
        "sourceDigest": {"digest": _SOURCE_DIGEST},
        "entityCatalogDigest": _ENTITY_DIGEST,
        "executionBundle": {"digest": _BUNDLE_DIGEST},
    }


def _review_journal(root: Path, calls: list[str]):
    def run(**kwargs):
        calls.append(str(kwargs["prompt"]))
        journal_root = root / "source-reviews" / "stock-journal"
        request_path = journal_root / "request.json"
        attempt_path = journal_root / "attempts" / "001.json"
        capacity_path = root / "temporary-capacity-receipt.json"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        result = (
            '{"status":"passed","entityMatch":"matched","privacyRisk":"none",'
            '"minorRisk":"none","maliciousMediaRisk":"none",'
            '"watermarkStatus":"absent","qualityStatus":"passed","findings":[]}'
        )
        request_path.write_text("{}", encoding="utf-8")
        attempt = {
            "status": "finished",
            "runId": "stock-grok-review",
            "resultSha256": _SHA(result.encode()),
        }
        attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
        capacity_path.write_text("capacity", encoding="utf-8")
        outcome = AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="stock-grok-review",
            result_text=result,
        )
        return {
            "requestPath": request_path,
            "attemptPath": attempt_path,
            "capacityReceiptPath": capacity_path,
            "attempt": attempt,
            "capacityReceipt": {"recordedAt": "2026-08-13T08:01:00+00:00"},
            "outcome": outcome,
        }, attempt_path

    return run


def _install_stock_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    source: Path,
) -> tuple[list[str], list[bool]]:
    calls: list[str] = []
    supported_api_flags: list[bool] = []

    monkeypatch.setattr(
        commons_input,
        "load_pre_acquisition_handoff",
        lambda _path: _handoff(),
    )
    monkeypatch.setattr(
        professional_video_acquisition,
        "guard_acquisition_source_identity",
        lambda *_args, **_kwargs: _handoff(),
    )
    monkeypatch.setattr(
        professional_video_acquisition,
        "load_content_distribution_policy",
        lambda: type(
            "ResearchPolicy",
            (),
            {"product_lifecycle_state": ProductLifecycleState.RESEARCH},
        )(),
    )

    def fetch(_url: str, destination: Path, *, supported_api: bool) -> str:
        supported_api_flags.append(supported_api)
        shutil.copyfile(source, destination)
        return ".mp4"

    monkeypatch.setattr(commons_input, "fetch_public_video", fetch)
    monkeypatch.setattr(professional_video_acquisition, "fetch_public_video", fetch)
    playable_probe = {
        "width": 320,
        "height": 180,
        "frameCount": 40,
        "framesPerSecond": 10.0,
        "durationMs": 4000,
        "codec": "mp4v",
        "hasAudio": False,
        "sampleCount": 8,
        "distinctFrameCount": 8,
        "movingTransitionCount": 7,
        "meanTransitionDelta": 0.12,
        "motionVideo": True,
        "staticImageSequence": False,
        "playable": True,
        "premiumPlayableEligible": True,
    }
    monkeypatch.setattr(
        commons_input, "probe_professional_video", lambda _path: playable_probe
    )
    monkeypatch.setattr(
        professional_video_acquisition,
        "probe_professional_video",
        lambda _path: playable_probe,
    )
    monkeypatch.setattr(
        commons_input,
        "scan_sourced_video_watermark",
        lambda _path: {
            "schema": "quwoquan_data.sourced_video_watermark_evidence",
            "sampleCount": 12,
            "ocrReviewed": True,
            "watermarkDetected": False,
            "decision": "passed",
            "samples": [],
        },
    )
    monkeypatch.setattr(commons_input, "run_source_review", _review_journal(root, calls))
    return calls, supported_api_flags


def test_pexels_supported_api_walks_the_same_admission_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    video_root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", seed=1)
    calls, supported_api_flags = _install_stock_fakes(
        monkeypatch, root=video_root, source=source
    )
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")

    outcomes = commons_input.acquire_stock_sourced_videos(
        provider="pexels_videos",
        entity_id="张家界",
        entity_aliases=("Zhangjiajie",),
        handoff_ref=handoff,
        output_root=video_root,
        runner=lambda _prompt: pytest.fail("source journal fake must own runner"),
        discovery=lambda *_args, **_kwargs: [_pexels_candidate()],
    )

    assert len(calls) == 1
    assert outcomes[0]["acquisitionStatus"] == "acquired", json.dumps(
        outcomes, ensure_ascii=False
    )
    assert outcomes[0]["distributionDecision"] in {
        "research_allowed",
        "commercial_allowed",
    }
    assert str(outcomes[0]["assetId"]).startswith("pexels-video-")
    manifest = json.loads(
        (video_root / str(outcomes[0]["manifestRef"])).read_text(encoding="utf-8")
    )
    item = manifest["items"][0]
    assert item["provider"] == "pexels_videos"
    assert item["platform"] == "Pexels Videos"
    assert item["acquisitionPath"] == "supported_api"
    assert item["apiEvidence"].startswith("https://api.pexels.com/videos/search")
    assert item["popularitySignals"]["provider"] == "pexels_videos"
    # receipt 侧的重取必须按 supported_api 声明走。
    assert True in supported_api_flags
    safety = json.loads(
        (video_root / item["safetyReview"]["evidenceRef"]).read_text(encoding="utf-8")
    )
    assert safety["sourceAttribution"]["provider"] == "pexels_videos"
    assert safety["sourceAttribution"]["license"] == "Pexels License"

    replay = commons_input.acquire_stock_sourced_videos(
        provider="pexels_videos",
        entity_id="张家界",
        entity_aliases=("Zhangjiajie",),
        handoff_ref=handoff,
        output_root=video_root,
        runner=lambda _prompt: pytest.fail("replay must not re-run review"),
        discovery=lambda *_args, **_kwargs: [_pexels_candidate()],
    )
    assert replay[0]["preflight"] == "replayed"
    assert replay[0]["receiptDigest"] == outcomes[0]["receiptDigest"]
    assert len(calls) == 1


def test_unregistered_stock_provider_is_typed(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")
    with pytest.raises(commons_input.CommonsVideoInputError) as captured:
        commons_input.acquire_stock_sourced_videos(
            provider="youtube",
            entity_id="张家界",
            entity_aliases=(),
            handoff_ref=handoff,
            output_root=tmp_path / "video",
        )
    assert "DATA.SOURCE.PROVIDER_NOT_REGISTERED" in str(captured.value)


def test_missing_stock_api_key_is_a_typed_provider_credential_blocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QWQ_PEXELS_API_KEY_FILE", str(tmp_path / "absent-key"))
    monkeypatch.setenv("QWQ_PIXABAY_API_KEY_FILE", str(tmp_path / "absent-key"))
    for provider in ("pexels_videos", "pixabay_videos"):
        with pytest.raises(stock.StockVideoProviderCredentialMissing) as captured:
            stock.stock_video_api_key(provider)
        assert captured.value.code == "DATA.SOURCE.PROVIDER_CREDENTIAL_MISSING"
        assert provider in str(captured.value)


def test_pexels_discovery_projects_exact_candidates_from_official_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_path = tmp_path / "pexels_api_key"
    key_path.write_text("test-key\n", encoding="utf-8")
    monkeypatch.setenv("QWQ_PEXELS_API_KEY_FILE", str(key_path))
    observed_headers: list[dict[str, str]] = []
    payload = {
        "videos": [
            {
                "id": 123,
                "duration": 16,
                "url": "https://www.pexels.com/video/zhangjiajie-mountain-aerial-123/",
                "user": {"name": "Creator A"},
                "tags": [],
                "video_files": [
                    {
                        "id": 1,
                        "quality": "uhd",
                        "file_type": "video/mp4",
                        "width": 3840,
                        "height": 2160,
                        "link": "https://videos.pexels.com/video-files/123/123-uhd.mp4",
                    },
                    {
                        "id": 2,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "link": "https://videos.pexels.com/video-files/123/123-hd.mp4",
                    },
                ],
            },
            {
                # 与实体无关的候选必须被相关性预筛拒绝。
                "id": 456,
                "duration": 20,
                "url": "https://www.pexels.com/video/city-traffic-timelapse-456/",
                "user": {"name": "Creator B"},
                "tags": [],
                "video_files": [
                    {
                        "id": 3,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "link": "https://videos.pexels.com/video-files/456/456-hd.mp4",
                    }
                ],
            },
            {
                # 超时长候选必须被质量预筛拒绝。
                "id": 789,
                "duration": 3600,
                "url": "https://www.pexels.com/video/zhangjiajie-full-documentary-789/",
                "user": {"name": "Creator C"},
                "tags": [],
                "video_files": [
                    {
                        "id": 4,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "link": "https://videos.pexels.com/video-files/789/789-hd.mp4",
                    }
                ],
            },
        ]
    }

    def fetch(url: str, *, timeout: int, headers=None) -> HttpFetchResult:
        observed_headers.append(dict(headers or {}))
        return HttpFetchResult(
            returncode=0,
            status_code=200,
            final_url=url,
            body=json.dumps(payload).encode("utf-8"),
        )

    monkeypatch.setattr(stock.network_io, "fetch_http", fetch)
    diagnostics: list[dict[str, object]] = []

    candidates = stock.discover_pexels_sourced_videos(
        "张家界",
        entity_aliases=["Zhangjiajie"],
        limit=15,
        selected_limit=3,
        diagnostics=diagnostics,
    )

    assert observed_headers and observed_headers[0] == {"Authorization": "test-key"}
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["sourceId"] == "pexels_videos"
    assert candidate["title"] == "zhangjiajie mountain aerial"
    # 全高清优先于超采样 4K 母带。
    assert candidate["assetUrl"] == "https://videos.pexels.com/video-files/123/123-hd.mp4"
    assert candidate["termsUrl"] == "https://www.pexels.com/license/"
    assert candidate["rightsBasis"] == "Pexels License"
    assert candidate["apiEvidenceUrl"].startswith(
        "https://api.pexels.com/videos/search?"
    )
    assert candidate["rightsStatus"] == "unverified"
    funnel = diagnostics[0]
    assert funnel["provider"] == "pexels_videos"
    assert funnel["rejectedByRelevance"] == 1
    assert funnel["rejectedByQuality"] == 1


def test_pixabay_discovery_projects_exact_candidates_and_masks_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_path = tmp_path / "pixabay_api_key"
    key_path.write_text("pixakey\n", encoding="utf-8")
    monkeypatch.setenv("QWQ_PIXABAY_API_KEY_FILE", str(key_path))
    observed_urls: list[str] = []
    payload = {
        "hits": [
            {
                "id": 99,
                "duration": 30,
                "pageURL": "https://pixabay.com/videos/guilin-river-karst-99/",
                "tags": "guilin, river, karst",
                "user": "PixaCreator",
                "videos": {
                    "large": {
                        "url": "https://cdn.pixabay.com/video/99_large.mp4",
                        "width": 1920,
                        "height": 1080,
                        "size": 1000,
                    }
                },
            }
        ]
    }

    def fetch(url: str, *, timeout: int, headers=None) -> HttpFetchResult:
        observed_urls.append(url)
        return HttpFetchResult(
            returncode=0,
            status_code=200,
            final_url=url,
            body=json.dumps(payload).encode("utf-8"),
        )

    monkeypatch.setattr(stock.network_io, "fetch_http", fetch)

    candidates = stock.discover_pixabay_sourced_videos(
        "桂林",
        entity_aliases=["Guilin"],
        limit=15,
        selected_limit=1,
    )

    assert observed_urls and "key=pixakey" in observed_urls[0]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["sourceId"] == "pixabay_videos"
    assert candidate["assetUrl"] == "https://cdn.pixabay.com/video/99_large.mp4"
    assert candidate["rightsBasis"] == "Pixabay Content License"
    # 冻结的 API 证据 URL 不得泄漏私有 key。
    assert "pixakey" not in str(candidate["apiEvidenceUrl"])
    assert "key=%2A%2A%2A" in str(candidate["apiEvidenceUrl"])
