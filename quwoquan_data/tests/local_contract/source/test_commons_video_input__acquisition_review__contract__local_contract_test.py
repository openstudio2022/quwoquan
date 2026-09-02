"""Commons 视频以既有 acquisition receipt 进入 campaign 的本地合同。"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
from content.execution.source_pool.external_inputs import (
    bind_external_input_refs,
    payload_digest,
)
from content.source import professional_commons_video_input as commons_input
from content.source import professional_video_acquisition
from content.source.host_source_review import record_host_source_review_result
from content.source.professional_safety_evidence import file_sha256

_SHA = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
_SOURCE_DIGEST = "sha256:" + "1" * 64
_ENTITY_DIGEST = "sha256:" + "2" * 64
_REVISION = "sha256:" + "3" * 64
_BUNDLE_DIGEST = "sha256:" + "4" * 64


def _video(path: Path, *, moving: bool, seed: int) -> Path:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180)
    )
    assert writer.isOpened()
    try:
        for index in range(40):
            frame = np.full((180, 320, 3), 30 + seed, dtype=np.uint8)
            if moving:
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


def _candidate() -> dict[str, object]:
    return {
        "sourceId": "wikimedia_commons_video",
        "title": "西湖匿名公开直链样例",
        "relevance": "西湖真实旅行动态影像",
        "platform": "Wikimedia Commons",
        "assetUrl": "https://upload.wikimedia.org/example/west-lake.mp4",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:West_Lake.mp4",
        "authorizationProofUrl": "https://commons.wikimedia.org/wiki/File:West_Lake.mp4",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "rightsBasis": "CC BY-SA 4.0",
        "originalCreatorName": "Commons creator",
        "popularitySignals": {
            "observedAt": "2026-08-12T12:00:00+00:00",
        },
    }


def _handoff() -> dict[str, object]:
    return {
        "sourceRevision": _REVISION,
        "sourceDigest": {"digest": _SOURCE_DIGEST},
        "entityCatalogDigest": _ENTITY_DIGEST,
        "executionBundle": {"digest": _BUNDLE_DIGEST},
    }


def _record_pending_reviews(root: Path, outcomes) -> int:
    """宿主对每个 HOST_REVIEW_PENDING 请求记录一次 passed 语义结论。"""
    recorded = 0
    for row in outcomes:
        if row.get("failureCode") != "DATA.SOURCE.HOST_REVIEW_PENDING":
            continue
        request_ref = str(row["requestRef"])
        request = json.loads((root / request_ref).read_text(encoding="utf-8"))
        record_host_source_review_result(
            evidence_root=root,
            result_input={
                "schema": "quwoquan_data.host_source_review_result_input",
                "requestRef": request_ref,
                "requestDigest": request["requestDigest"],
                "actor": {
                    "host": "cursor",
                    "sessionId": "commons-review-session",
                    "modelFamily": "gpt-5",
                    "auditRunId": "commons-review-audit-001",
                },
                "reviewedAt": "2026-08-12T12:01:00Z",
                "verdict": {
                    "status": "passed",
                    "entityMatch": "matched",
                    "qualityStatus": "passed",
                    "privacyRisk": "none",
                    "minorRisk": "none",
                    "maliciousMediaRisk": "none",
                    "watermarkStatus": "absent",
                    "findings": [],
                },
            },
        )
        recorded += 1
    return recorded


def _result_files(root: Path) -> list[Path]:
    results_root = root / "host-source-reviews" / "results"
    if not results_root.is_dir():
        return []
    return sorted(results_root.glob("*.json"))


def _install_common_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    source: Path,
    replacement: Path | None = None,
) -> None:
    fetch_count = 0

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
        commons_input,
        "discover_commons_sourced_videos",
        lambda *_args, **_kwargs: [_candidate()],
    )

    def fetch(_url: str, destination: Path, *, supported_api: bool) -> str:
        nonlocal fetch_count
        assert supported_api is False
        fetch_count += 1
        shutil.copyfile(
            replacement if replacement is not None and fetch_count > 1 else source,
            destination,
        )
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


def _acquire_once(
    root: Path,
    *,
    discovery=commons_input.discover_commons_sourced_videos,
) -> list[dict[str, object]]:
    handoff = root.parent / "handoff.json"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("{}", encoding="utf-8")
    return commons_input.acquire_commons_sourced_videos(
        entity_id="西湖",
        entity_aliases=("杭州西湖",),
        handoff_ref=handoff,
        output_root=root,
        discovery=discovery,
    )


def _acquire(
    root: Path,
    *,
    discovery=commons_input.discover_commons_sourced_videos,
) -> list[dict[str, object]]:
    """两阶段驱动：宿主对 pending 审核请求记录结论后重入同一命令。"""
    try:
        return _acquire_once(root, discovery=discovery)
    except commons_input.CommonsVideoBatchBlocked as blocked:
        if not _record_pending_reviews(root, blocked.outcomes):
            raise
        return _acquire_once(root, discovery=discovery)


def test_commons_public_direct_bytes_review_and_campaign_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    acquisition_root = tmp_path / "acquisition"
    video_root = acquisition_root / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=1)
    _install_common_fakes(monkeypatch, root=video_root, source=source)

    outcomes = _acquire(video_root, discovery=commons_input.discover_commons_sourced_videos)

    assert len(_result_files(video_root)) == 1, json.dumps(outcomes, ensure_ascii=False)
    assert outcomes[0]["acquisitionStatus"] == "acquired", json.dumps(
        outcomes, ensure_ascii=False
    )
    assert outcomes[0]["distributionDecision"] == "commercial_allowed"
    assert outcomes[0]["contentSha256"] == file_sha256(source)
    manifest = json.loads(
        (video_root / str(outcomes[0]["manifestRef"])).read_text(encoding="utf-8")
    )
    item = manifest["items"][0]
    safety = json.loads(
        (video_root / item["safetyReview"]["evidenceRef"]).read_text(encoding="utf-8")
    )
    assert safety["sourceAttribution"] == {
        "provider": "wikimedia_commons_video",
        "sourcePostUrl": _candidate()["sourcePostUrl"],
        "originalAssetUrl": _candidate()["assetUrl"],
        "creator": _candidate()["originalCreatorName"],
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": _candidate()["authorizationProofUrl"],
    }
    review_evidence = safety["reviewEvidence"]
    assert review_evidence["actor"]["host"] == "cursor"
    assert "model" not in review_evidence
    assert "provider" not in review_evidence
    result_document = json.loads(
        (video_root / review_evidence["resultRef"]).read_text(encoding="utf-8")
    )
    assert result_document["resultDigest"] == review_evidence["resultDigest"]
    refs = bind_external_input_refs(
        "video",
        [
            {
                "kind": "professional_video_acquisition",
                "acquisitionRootRef": "video",
                "manifestRef": str(outcomes[0]["manifestRef"]),
                "receiptRef": str(outcomes[0]["receiptRef"]),
            }
        ],
        acquisition_root=acquisition_root,
        source_revision=_REVISION,
        source_digest=_SOURCE_DIGEST,
        entity_catalog_digest=_ENTITY_DIGEST,
    )
    assert refs[0]["manifestDigest"] == payload_digest(manifest)
    assert refs[0]["receiptDigest"] == outcomes[0]["receiptDigest"]
    assert refs[0]["blobRefs"][0]["contentSha256"] == outcomes[0]["contentSha256"]

    replay = _acquire(
        video_root, discovery=commons_input.discover_commons_sourced_videos
    )
    assert replay[0]["preflight"] == "replayed"
    assert replay[0]["receiptRef"] == outcomes[0]["receiptRef"]
    assert replay[0]["receiptDigest"] == outcomes[0]["receiptDigest"]
    assert replay[0]["contentSha256"] == outcomes[0]["contentSha256"]
    assert len(_result_files(video_root)) == 1


def test_commons_download_failure_is_typed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acquisition" / "video"
    monkeypatch.setattr(commons_input, "load_pre_acquisition_handoff", lambda _path: _handoff())
    monkeypatch.setattr(
        commons_input,
        "fetch_public_video",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("network down")),
    )
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")

    with pytest.raises(commons_input.CommonsVideoInputError) as captured:
        commons_input.acquire_commons_sourced_videos(
            entity_id="西湖",
            entity_aliases=("杭州西湖",),
            handoff_ref=handoff,
            output_root=root,
            discovery=lambda *_args, **_kwargs: [_candidate()],
        )

    assert captured.value.code == "DATA.SOURCE.VIDEO_BATCH_NO_SUCCESS"
    assert captured.value.outcomes[0]["failureCode"] == (
        "DATA.SOURCE.ACQUISITION_FAILED"
    )


def test_commons_bytes_drift_is_recorded_by_existing_acquisition_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=2)
    drifted = _video(tmp_path / "drifted.mp4", moving=True, seed=3)
    _install_common_fakes(
        monkeypatch, root=root, source=source, replacement=drifted
    )

    with pytest.raises(commons_input.CommonsVideoBatchBlocked) as captured:
        _acquire(root, discovery=commons_input.discover_commons_sourced_videos)
    outcome = captured.value.outcomes[0]

    assert outcome["acquisitionStatus"] == "acquired", json.dumps(
        outcome, ensure_ascii=False
    )
    assert outcome["distributionDecision"] == "blocked"
    assert outcome["failureCode"] == "DATA.SOURCE.SOURCE_BYTES_DRIFT"


def test_commons_unplayable_preflight_is_typed_without_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "static.mp4", moving=False, seed=4)
    _install_common_fakes(monkeypatch, root=root, source=source)
    unplayable_probe = {
        "width": 320,
        "height": 180,
        "frameCount": 40,
        "framesPerSecond": 10.0,
        "durationMs": 4000,
        "codec": "mp4v",
        "hasAudio": False,
        "sampleCount": 8,
        "distinctFrameCount": 1,
        "movingTransitionCount": 0,
        "meanTransitionDelta": 0.0,
        "motionVideo": False,
        "staticImageSequence": True,
        "playable": True,
        "premiumPlayableEligible": False,
    }
    monkeypatch.setattr(
        commons_input, "probe_professional_video", lambda _path: unplayable_probe
    )

    with pytest.raises(commons_input.CommonsVideoBatchBlocked) as captured:
        _acquire(root, discovery=commons_input.discover_commons_sourced_videos)
    outcome = captured.value.outcomes[0]

    assert outcome["preflight"] == "DATA.SOURCE.NOT_PLAYABLE_MOTION_VIDEO"
    assert outcome["distributionDecision"] == "blocked"
    assert outcome["failureCode"] == "DATA.SOURCE.SAFETY_REVIEW_BLOCKED"
    assert _result_files(root) == []


def test_commons_resume_adopts_frozen_candidate_despite_fresh_observed_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """发现层每次运行都会盖新的 observedAt；resume 必须采纳冻结观测而非 create-once 冲突。"""
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=6)
    _install_common_fakes(monkeypatch, root=root, source=source)
    with pytest.raises(commons_input.CommonsVideoBatchBlocked) as captured:
        _acquire_once(root, discovery=commons_input.discover_commons_sourced_videos)
    assert captured.value.outcomes[0]["failureCode"] == (
        "DATA.SOURCE.HOST_REVIEW_PENDING"
    )
    metadata_files = list(root.glob("commons-direct/*/metadata.json"))
    assert len(metadata_files) == 1
    frozen_observed_at = json.loads(metadata_files[0].read_text(encoding="utf-8"))[
        "source"
    ]["popularitySignals"]["observedAt"]

    fresh = _candidate()
    fresh["popularitySignals"] = {"observedAt": "2026-08-13T09:00:00+00:00"}

    outcome = _acquire(root, discovery=lambda *_args, **_kwargs: [fresh])[0]

    assert outcome["acquisitionStatus"] == "acquired"
    manifest = json.loads(
        (root / str(outcome["manifestRef"])).read_text(encoding="utf-8")
    )
    item = manifest["items"][0]
    assert item["popularitySignals"]["observedAt"] == frozen_observed_at
    assert item["capturedAt"] == frozen_observed_at


def test_commons_resume_still_blocks_stable_field_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=7)
    _install_common_fakes(monkeypatch, root=root, source=source)
    with pytest.raises(commons_input.CommonsVideoBatchBlocked) as captured:
        _acquire_once(root, discovery=commons_input.discover_commons_sourced_videos)
    assert captured.value.outcomes[0]["failureCode"] == (
        "DATA.SOURCE.HOST_REVIEW_PENDING"
    )
    # relevance 不参与 candidate token，但属于冻结 metadata 的稳定字段。
    drifted = _candidate()
    drifted["relevance"] = "被篡改的证据描述"

    with pytest.raises(commons_input.CommonsVideoInputError) as captured:
        _acquire(root, discovery=lambda *_args, **_kwargs: [drifted])

    assert captured.value.code == "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT"


@pytest.mark.parametrize(
    ("field", "drifted"),
    (
        ("license", "CC BY-NC 4.0"),
        ("sourcePostUrl", "https://commons.wikimedia.org/wiki/File:Replacement.mp4"),
    ),
)
def test_commons_source_and_license_drift_fail_before_reacquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    drifted: str,
) -> None:
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=5)
    _install_common_fakes(monkeypatch, root=root, source=source)
    outcome = _acquire(root, discovery=commons_input.discover_commons_sourced_videos)[0]
    manifest_path = root / str(outcome["manifestRef"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    safety_path = root / manifest["items"][0]["safetyReview"]["evidenceRef"]
    safety = json.loads(safety_path.read_text(encoding="utf-8"))
    safety["sourceAttribution"][field] = drifted
    safety_path.write_text(json.dumps(safety), encoding="utf-8")
    manifest["items"][0]["safetyReview"]["safetyEvidenceFileSha256"] = file_sha256(
        safety_path
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    handoff = root.parent / "handoff.json"

    with pytest.raises(professional_video_acquisition.ProfessionalVideoAcquisitionBlocked) as captured:
        professional_video_acquisition.acquire_professional_videos(
            manifest_path,
            handoff_ref=handoff,
            output_root=root,
        )
    assert captured.value.receipt["assets"][0]["failureCode"] == (
        "DATA.SOURCE.SAFETY_EVIDENCE_INVALID"
    )
    assert "source/rights drift" in captured.value.receipt["assets"][0]["failure"]


def test_commons_candidate_failure_is_isolated_when_a_sibling_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "acquisition" / "video"
    source = _video(tmp_path / "source.mp4", moving=True, seed=8)
    _install_common_fakes(monkeypatch, root=root, source=source)
    good = _candidate()
    bad = _candidate()
    bad.update(
        title="西湖失效候选",
        assetUrl="https://upload.wikimedia.org/example/broken-west-lake.mp4",
        sourcePostUrl="https://commons.wikimedia.org/wiki/File:Broken_West_Lake.mp4",
        authorizationProofUrl=(
            "https://commons.wikimedia.org/wiki/File:Broken_West_Lake.mp4"
        ),
    )
    original_fetch = commons_input.fetch_public_video

    def fetch(url: str, destination: Path, *, supported_api: bool) -> str:
        if "broken-west-lake" in url:
            raise OSError("candidate transport failed")
        return original_fetch(url, destination, supported_api=supported_api)

    monkeypatch.setattr(commons_input, "fetch_public_video", fetch)

    outcomes = _acquire(root, discovery=lambda *_args, **_kwargs: [bad, good])

    assert len(outcomes) == 2
    assert outcomes[0]["status"] == "excluded"
    assert outcomes[0]["failureCode"] == "DATA.SOURCE.ACQUISITION_FAILED"
    assert outcomes[1]["status"] == "accepted"
    assert outcomes[1]["distributionDecision"] == "commercial_allowed"


def test_commons_create_once_collision_remains_a_global_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(commons_input, "load_pre_acquisition_handoff", lambda _path: _handoff())
    monkeypatch.setattr(
        commons_input,
        "_prepared_candidate",
        lambda **_kwargs: (_ for _ in ()).throw(
            commons_input.CommonsVideoInputError(
                "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT", "exact collision"
            )
        ),
    )

    with pytest.raises(commons_input.CommonsVideoInputError) as captured:
        commons_input.acquire_commons_sourced_videos(
            entity_id="西湖",
            entity_aliases=("杭州西湖",),
            handoff_ref=handoff,
            output_root=tmp_path / "video",
            discovery=lambda *_args, **_kwargs: [_candidate(), _candidate()],
        )

    assert captured.value.code == "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT"


def test_commons_cc_license_url_protocol_is_normalized_to_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commons CC0 条目的 http:// canonical license URL 归一为 https://。"""
    from content.source.research import auto_plan_video

    page = {
        "pageid": 1,
        "title": "File:Lushan summit.webm",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/lushan.webm",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Lushan_summit.webm",
                "size": 1024,
                "duration": 12.0,
                "mediatype": "VIDEO",
                "extmetadata": {
                    "ImageDescription": {"value": "庐山 Lushan summit"},
                    "LicenseShortName": {"value": "CC0"},
                    "LicenseUrl": {
                        "value": "http://creativecommons.org/publicdomain/zero/1.0/deed.en"
                    },
                    "Artist": {"value": "Photographer"},
                    "Categories": {"value": "Lushan"},
                },
            }
        ],
    }
    monkeypatch.setattr(
        auto_plan_video.network_io,
        "wiki_api",
        lambda *_args, **_kwargs: {"query": {"pages": [page]}},
    )
    candidates = auto_plan_video.discover_commons_sourced_videos(
        "庐山", entity_aliases=["Lushan"]
    )
    assert candidates, "CC0 http license URL must not be dropped by rights gate"
    assert candidates[0]["termsUrl"] == (
        "https://creativecommons.org/publicdomain/zero/1.0/deed.en"
    )
