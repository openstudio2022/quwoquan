# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
"""外部来源视频进入内容计划时，准入边界必须在投影处重新自证。

`GWT-002`：「unverified/unknown 可记为 `research_allowed`，restricted/未取得/生成/
缺字段素材与不可播放视频被阻断」，且「commercial readiness 不存在，且任何未授权
asset ID 不得进入 `commercialAcceptedCount`」。`REQ-003`（多载体来源）还要求「所有站点、
搜索和 creator shard 只允许公开直链、平台支持接口或人工提供文件，不新增规避登录、
付费墙、验证码、访问控制、DRM 或 robots/服务条款限制的抓取器」。

因此 sourceVideo 的投影必须守住三条边界：

1. 「取得到并且能播」不等于「可商用」：未取得商业授权的素材只能落 research 或
   显式风险接受，商用发布必须有 verified + HTTPS 授权与条款证据；
2. 缺字段、带水印、DRM、绕过访问控制、非直链的素材一律被阻断，且每一条都给出各自
   具名的准入问题，不合并成一句笼统失败；
3. 投影不得声称比冻结证据更宽的权利：落盘证据与 sourceVideo 声明不一致、字节摘要
   不一致或引用逃逸执行根时，投影必须报出问题而不是照抄声明。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from content.post.content_plan_video_validation import _validate_sourced_video
from content.post.video.source_video import SourcedVideoEvidence
from core.io import write_json

_VIDEO_BYTES = b"exact-sourced-video-bytes"
_SHA256 = "sha256:" + hashlib.sha256(_VIDEO_BYTES).hexdigest()


def _payload(**overrides: Any) -> dict[str, Any]:
    """One fully admissible research-release sourced video declaration."""
    payload: dict[str, Any] = {
        "assetRef": "sources/001/assets/source.mp4",
        "sourceRef": "https://www.pexels.com/video/west-lake-1/",
        "rightsRef": "sources/001/rights.json",
        "mediaProbeRef": "sources/001/media-probe.json",
        "watermarkEvidenceRef": "sources/001/watermark.json",
        "audioRightsEvidenceRef": "sources/001/audio-rights.json",
        "sha256": _SHA256,
        "isOriginal": False,
        "originalCreatorName": "摄影师甲",
        "platform": "Pexels Videos",
        "sourcePostUrl": "https://www.pexels.com/video/west-lake-1/",
        "originalAssetUrl": "https://videos.pexels.com/video-files/west-lake.mp4",
        "attributionText": "西湖实拍 — 摄影师甲 — Pexels Videos",
        "rightsBasis": "platform rights pending verification",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "unverified",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-05T02:00:00Z",
        "takedownPolicy": "notice_and_takedown",
        "derivedModifications": [],
        "directDownload": True,
        "accessControlBypassed": False,
        "drmDetected": False,
    }
    payload.update(overrides)
    return payload


def _commercial_payload(**overrides: Any) -> dict[str, Any]:
    commercial: dict[str, Any] = {
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "rightsBasis": "CC BY-SA 4.0",
        "authorizationProofUrl": (
            "https://commons.wikimedia.org/wiki/File:West_Lake.mp4"
        ),
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "audioRightsStatus": "no_audio",
    }
    commercial.update(overrides)
    return _payload(**commercial)


def _issues(payload: dict[str, Any]) -> tuple[str, ...]:
    _evidence, issues = SourcedVideoEvidence.from_mapping(payload)
    return issues


def _materialize(root: Path, payload: dict[str, Any]) -> None:
    """Write the on-disk evidence closure the plan projection must re-prove."""
    asset = root / str(payload["assetRef"])
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(_VIDEO_BYTES)
    write_json(
        root / str(payload["rightsRef"]),
        {
            "rightsBasis": payload["rightsBasis"],
            "commercialAuthorizationStatus": payload["commercialAuthorizationStatus"],
            "publicationAdmission": payload["publicationAdmission"],
            "authorizationProofUrl": payload.get("authorizationProofUrl") or "",
            "termsUrl": payload.get("termsUrl") or "",
            "riskAcceptanceId": payload.get("riskAcceptanceId") or "",
            "sourcePostUrl": payload["sourcePostUrl"],
            "originalAssetUrl": payload["originalAssetUrl"],
        },
    )
    write_json(
        root / str(payload["mediaProbeRef"]),
        {"durationMs": 7_000, "width": 320, "height": 240},
    )
    write_json(
        root / str(payload["watermarkEvidenceRef"]),
        {
            "schema": "quwoquan_data.sourced_video_watermark_evidence",
            "decision": "passed",
            "watermarkDetected": False,
            "ocrReviewed": True,
            "sampleCount": 12,
        },
    )
    write_json(
        root / str(payload["audioRightsEvidenceRef"]),
        {"decision": "passed", "status": payload["audioRightsStatus"]},
    )


def _plan_issues(root: Path, payload: dict[str, Any], **item: Any) -> list[str]:
    claimed: list[tuple[str, str]] = []
    hashes: list[tuple[str, str]] = []
    return _validate_sourced_video(
        root=root,
        item={
            "sourceVideo": payload,
            "assetRefs": [payload["assetRef"]],
            **item,
        },
        ref="西湖_video",
        claim_asset=lambda ref, value: claimed.append((ref, value)),
        claim_asset_sha=lambda ref, value: hashes.append((ref, value)),
    )


def test_a_research_declaration_with_full_evidence_is_admitted() -> None:
    """未取得商业授权但证据齐备的素材可以作为 research 对象准入。"""

    assert _issues(_payload()) == ()


def test_a_verified_commercial_declaration_with_https_proof_is_admitted() -> None:
    """商用发布在 verified + HTTPS 授权与条款证据齐备时准入。"""

    assert _issues(_commercial_payload()) == ()


def test_unverified_authorization_cannot_claim_commercial_release() -> None:
    """未取得商业授权的素材不得冒充商用，这是准入边界的核心。"""

    issues = _issues(
        _payload(
            publicationAdmission="commercial_release",
            authorizationProofUrl="https://rights.example.test/proof",
            termsUrl="https://rights.example.test/terms",
        )
    )

    assert (
        "sourceVideo unverified authorization requires research_allowed"
        in issues
    )
    assert (
        "sourceVideo commercial_allowed requires verified HTTPS authorization and terms proof"
        in issues
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"authorizationProofUrl": None},
        {"termsUrl": None},
        {"authorizationProofUrl": "http://insecure.example.test/proof"},
        {"termsUrl": "http://insecure.example.test/terms"},
    ],
)
def test_commercial_release_requires_https_authorization_and_terms(
    overrides: dict[str, Any],
) -> None:
    """商用证据必须是 HTTPS 且两项齐全，缺一项或降级为 HTTP 都不成立。"""

    issues = _issues(_commercial_payload(**overrides))

    assert (
        "sourceVideo commercial_allowed requires verified HTTPS authorization and terms proof"
        in issues
    )


def test_risk_accepted_admission_requires_an_explicit_acceptance_id() -> None:
    """风险接受必须留下显式受理编号，不得只声明一个状态字符串。"""

    issues = _issues(_payload(publicationAdmission="risk_accepted_attribution_only"))

    assert "sourceVideo riskAcceptanceId is required" in issues
    assert (
        _issues(
            _payload(
                publicationAdmission="risk_accepted_attribution_only",
                riskAcceptanceId="RISK-2026-0001",
            )
        )
        == ()
    )


def test_unverified_audio_is_restricted_to_research_release() -> None:
    """音轨权利未取得时只能进 research，不得随对象一起进入商用范围。"""

    issues = _issues(_commercial_payload(audioRightsStatus="unverified"))

    assert "sourceVideo unverified audio is restricted to research_release" in issues
    assert _issues(_payload(audioRightsStatus="unverified")) == ()


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("watermarkStatus", "sourceVideo watermarkStatus must be absent"),
        ("audioRightsStatus", "sourceVideo audioRightsStatus is not publishable"),
        (
            "commercialAuthorizationStatus",
            "sourceVideo commercialAuthorizationStatus is not publishable",
        ),
        ("publicationAdmission", "sourceVideo publicationAdmission is not publishable"),
    ],
)
def test_an_out_of_closed_set_status_is_not_publishable(
    field: str,
    expected: str,
) -> None:
    """状态取值是闭集，未知取值不得被当作可发布，也不得静默通过。"""

    assert expected in _issues(_payload(**{field: "unknown-value"}))


def test_a_watermarked_video_is_blocked() -> None:
    """带水印素材被阻断。"""

    assert "sourceVideo watermarkStatus must be absent" in _issues(
        _payload(watermarkStatus="present")
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"directDownload": False}, "sourceVideo must be directly downloadable"),
        (
            {"accessControlBypassed": True},
            "sourceVideo must not bypass access control",
        ),
        ({"drmDetected": True}, "sourceVideo must not contain DRM"),
    ],
)
def test_bypassed_access_and_drm_are_blocked(
    overrides: dict[str, Any],
    expected: str,
) -> None:
    """`REQ-003` 禁止规避访问控制与 DRM，取得成功不改变这条边界。"""

    assert expected in _issues(_payload(**overrides))


def test_a_truthy_looking_boolean_is_not_accepted_as_true() -> None:
    """布尔证据必须是真正的 True，字符串不得被当作已直链下载。"""

    assert "sourceVideo must be directly downloadable" in _issues(
        _payload(directDownload="true")
    )


@pytest.mark.parametrize(
    "field",
    [
        "assetRef",
        "sourceRef",
        "rightsRef",
        "mediaProbeRef",
        "watermarkEvidenceRef",
        "audioRightsEvidenceRef",
        "sha256",
        "originalCreatorName",
        "platform",
        "sourcePostUrl",
        "originalAssetUrl",
        "attributionText",
        "rightsBasis",
        "collectedAt",
        "takedownPolicy",
    ],
)
def test_each_missing_evidence_field_is_named_on_its_own(field: str) -> None:
    """缺字段素材被阻断，且每个缺失字段各自具名，不合并为一句笼统失败。"""

    assert f"sourceVideo missing {field}" in _issues(_payload(**{field: ""}))


def test_a_blank_field_is_missing_rather_than_present_and_empty() -> None:
    """只有空白的字段是缺失，不得被当作「在场为空」的合法取值。"""

    assert "sourceVideo missing platform" in _issues(_payload(platform="   "))


def test_admission_issues_are_returned_not_raised() -> None:
    """准入结论是可聚合的 typed 结果，一个坏对象不得抛断整份计划。"""

    evidence, issues = SourcedVideoEvidence.from_mapping(_payload(platform=""))

    assert evidence.platform == ""
    assert issues
    assert isinstance(issues, tuple)


def test_the_plan_projection_admits_a_closed_research_object(tmp_path: Path) -> None:
    """证据闭合的 research 对象在内容计划投影处准入。"""

    payload = _payload()
    _materialize(tmp_path, payload)

    assert _plan_issues(tmp_path, payload) == []


def test_the_plan_projection_claims_the_asset_and_its_real_digest(
    tmp_path: Path,
) -> None:
    """投影必须以磁盘实际字节的摘要认领资产，而不是照抄声明。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    claimed: list[tuple[str, str]] = []
    hashes: list[tuple[str, str]] = []

    issues = _validate_sourced_video(
        root=tmp_path,
        item={"sourceVideo": payload, "assetRefs": [payload["assetRef"]]},
        ref="西湖_video",
        claim_asset=lambda ref, value: claimed.append((ref, value)),
        claim_asset_sha=lambda ref, value: hashes.append((ref, value)),
    )

    assert issues == []
    assert claimed == [("西湖_video", payload["assetRef"])]
    assert hashes == [("西湖_video", _SHA256)]


def test_the_plan_projection_rejects_a_declared_digest_that_bytes_contradict(
    tmp_path: Path,
) -> None:
    """声明摘要与磁盘字节不一致时投影必须报错，不得采信声明。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    (tmp_path / str(payload["assetRef"])).write_bytes(b"tampered-video-bytes")

    assert "item[西湖_video]: sourced video sha256 mismatch" in _plan_issues(
        tmp_path, payload
    )


def test_the_plan_projection_rejects_rights_wider_than_frozen_evidence(
    tmp_path: Path,
) -> None:
    """投影不得声称比落盘权利证据更宽的权利。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    upgraded = _payload(
        commercialAuthorizationStatus="verified",
        publicationAdmission="commercial_release",
        authorizationProofUrl="https://rights.example.test/proof",
        termsUrl="https://rights.example.test/terms",
    )

    assert (
        "item[西湖_video]: sourced video permission evidence mismatch"
        in _plan_issues(tmp_path, upgraded)
    )


def test_the_plan_projection_rejects_audio_evidence_that_contradicts_the_claim(
    tmp_path: Path,
) -> None:
    """音轨权利证据必须与声明状态同源。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    write_json(
        tmp_path / str(payload["audioRightsEvidenceRef"]),
        {"decision": "passed", "status": "licensed"},
    )

    assert (
        "item[西湖_video]: sourced video audio rights evidence mismatch"
        in _plan_issues(tmp_path, payload)
    )


@pytest.mark.parametrize(
    "watermark",
    [
        {"decision": "blocked", "watermarkDetected": True, "ocrReviewed": True, "sampleCount": 12},
        {"decision": "passed", "watermarkDetected": True, "ocrReviewed": True, "sampleCount": 12},
        {"decision": "passed", "watermarkDetected": False, "ocrReviewed": False, "sampleCount": 12},
        {"decision": "passed", "watermarkDetected": False, "ocrReviewed": True, "sampleCount": 11},
    ],
)
def test_the_plan_projection_rejects_unpassed_watermark_evidence(
    tmp_path: Path,
    watermark: dict[str, Any],
) -> None:
    """水印/OCR 证据未通过或抽样不足时不得准入。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    write_json(tmp_path / str(payload["watermarkEvidenceRef"]), watermark)

    assert (
        "item[西湖_video]: sourced video watermark/OCR evidence is not passed"
        in _plan_issues(tmp_path, payload)
    )


def test_the_plan_projection_rejects_an_invalid_media_probe(tmp_path: Path) -> None:
    """不可播放（零时长或零尺寸）的视频被阻断。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    write_json(
        tmp_path / str(payload["mediaProbeRef"]),
        {"durationMs": 0, "width": 320, "height": 240},
    )

    assert "item[西湖_video]: sourced video media probe is invalid" in _plan_issues(
        tmp_path, payload
    )


def test_the_plan_projection_reports_each_absent_evidence_file(tmp_path: Path) -> None:
    """引用的证据文件缺席必须逐项报出，不得跳过继续。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    for field in ("rightsRef", "mediaProbeRef", "watermarkEvidenceRef"):
        (tmp_path / str(payload[field])).unlink()

    issues = _plan_issues(tmp_path, payload)

    for field in ("rightsRef", "mediaProbeRef", "watermarkEvidenceRef"):
        assert f"item[西湖_video]: sourced video {field} not found" in issues


def test_the_plan_projection_rejects_an_evidence_ref_escaping_the_root(
    tmp_path: Path,
) -> None:
    """证据引用逃逸执行根时必须被拒绝。"""

    payload = _payload()
    _materialize(tmp_path, payload)
    escaping = _payload(rightsRef="../outside/rights.json")

    assert "item[西湖_video]: rightsRef escapes execution root" in _plan_issues(
        tmp_path, escaping
    )


def test_the_plan_projection_requires_asset_refs_to_be_exactly_the_source_asset(
    tmp_path: Path,
) -> None:
    """assetRefs 必须恰好只包含 sourceVideo 的资产，不得混入其他资产。"""

    payload = _payload()
    _materialize(tmp_path, payload)

    assert (
        "item[西湖_video]: sourced video assetRefs must contain only sourceVideo.assetRef"
        in _plan_issues(tmp_path, payload, assetRefs=[payload["assetRef"], "other.mp4"])
    )


def test_the_plan_projection_requires_an_http_source_post_url(tmp_path: Path) -> None:
    """sourceRef 必须是 HTTP(S) 来源作品页，不得是本地路径或其它协议。"""

    payload = _payload(sourceRef="file:///tmp/source.html")
    _materialize(tmp_path, payload)

    assert (
        "item[西湖_video]: sourceRef must be an HTTP(S) source post URL"
        in _plan_issues(tmp_path, payload)
    )


def test_a_non_object_source_video_is_rejected_without_partial_admission(
    tmp_path: Path,
) -> None:
    """sourceVideo 不是对象时直接拒绝，不进入逐字段部分准入。"""

    issues = _validate_sourced_video(
        root=tmp_path,
        item={"sourceVideo": "sources/001/assets/source.mp4", "assetRefs": []},
        ref="西湖_video",
        claim_asset=lambda *_args: None,
        claim_asset_sha=lambda *_args: None,
    )

    assert issues == ["item[西湖_video]: sourceVideo must be an object"]
