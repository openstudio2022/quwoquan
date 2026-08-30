# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#req-003
"""已冻结的专业视频字节必须被复用，而不是重新采集。

`REQ-003`（媒体字节唯一持有方）：「原始采集素材在对象产出后被回收，重新采集也不再
是可依赖的退路，因此不得被计为恢复手段。」同一 REQ 还要求：「引用不可兑现必须是
typed 失败，不得静默：被记录的媒体引用在库中缺席，或字节与记录的摘要、大小不一致
时，读取方必须 fail closed……不得返回空路径、空字节或零大小。」

因此一次已冻结的取得必须满足：

1. 复用而非重采：给定 `frozenAsset` 时不得再走任何传输面（网络或人工文件），也不
   得向 CAS 另写一份字节，行必须指向既有 CAS 对象；
2. 复用不等于重复：同一 asset 显式复用自己冻结的摘要不算跨 receipt 重复，但该豁免
   是 asset 级的，换一个 assetId 或同一 manifest 内重复仍然是重复；
3. 引用不可兑现是 typed 失败：缺席、摘要漂移、大小漂移都必须 fail closed，且不得
   退化成空路径或零大小的「成功」。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from content.source.professional_video_asset_acquisition import acquire_video_item
from content.source.professional_video_deduplication import duplicate_source
from content.source.professional_video_frozen_asset import resolve_frozen_video_asset
from content.source.professional_video_receipt import document_digest, file_digest
from content.source.professional_video_store import put_video_cas
from core.io import write_json
from governance.coverage.distribution import RightsStatus

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_REVISION = "sha256:" + "c" * 64
_PLAYABLE_PROBE = {
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


def _item(asset_id: str = "frozen-1") -> dict[str, Any]:
    return {
        "assetId": asset_id,
        "entityId": "西湖",
        "observedEntityId": "西湖",
        "entityAliases": ["杭州西湖"],
        "provider": "pexels_videos",
        "platform": "Pexels Videos",
        "displayName": "Pexels 专业旅行视频",
        "sourceKind": "tourism_video_site",
        "acquisitionPath": "manual_file",
        "sourceUrl": f"https://videos.example.test/posts/{asset_id}",
        "assetUrl": "",
        "manualFile": f"{asset_id}.mp4",
        "apiEvidence": "",
        "accessEvidence": {
            "anonymousAssetAccess": False,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "title": f"西湖旅行实拍 {asset_id}",
        "relevance": "杭州西湖风景名胜区水面与沿岸旅行实景",
        "creator": f"Creator {asset_id}",
        "capturedAt": "2026-08-05T02:00:00Z",
        "rightsStatus": "unverified",
        "license": "platform rights pending verification",
        "termsUrl": "https://videos.example.test/terms",
        "authorizationProof": "",
        "rightsIssues": ["commercial redistribution authorization is unverified"],
        "modelReleaseStatus": "unverified",
        "propertyReleaseStatus": "not_required",
        "safetyReview": {
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "reviewedAt": "2026-08-05T02:05:00Z",
            "reviewer": "local-contract-reviewer",
            "evidenceRef": f"evidence/{asset_id}.json",
            "safetyEvidenceFileSha256": "sha256:" + "f" * 64,
        },
        "popularitySignals": {
            "playCount": 1_000,
            "likeCount": 20,
            "commentCount": 2,
            "shareCount": 1,
            "favoriteCount": 3,
            "observedAt": "2026-08-05T01:00:00Z",
            "provider": "pexels_videos",
            "topic": "west-lake-travel",
            "timeBucket": "2026-W32",
        },
    }


def _freeze_cas_object(root: Path, *, payload: bytes) -> tuple[str, str, int]:
    """Put exact bytes into the acquisition CAS and return its frozen binding."""
    staging = root / "staging.mp4"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(payload)
    cas_path, content_sha256 = put_video_cas(staging, ".mp4", output_root=root)
    staging.unlink()
    return (
        cas_path.relative_to(root).as_posix(),
        content_sha256,
        cas_path.stat().st_size,
    )


def _frozen_history(
    root: Path,
    *,
    items: list[dict[str, Any]],
    payloads: dict[str, bytes],
) -> dict[str, Any]:
    """Write one immutable historical receipt whose rows own frozen CAS bytes."""
    bindings: dict[str, tuple[str, str, int]] = {
        str(item["assetId"]): _freeze_cas_object(
            root, payload=payloads[str(item["assetId"])]
        )
        for item in items
    }
    manifest_body = {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": "video-frozen-history",
        "sourceRevision": _REVISION,
        "sourceDigest": _DIGEST_A,
        "entityCatalogDigest": _DIGEST_B,
        "items": items,
    }
    manifest_digest = document_digest(manifest_body)
    stable = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": manifest_body["manifestId"],
        "manifestDigest": manifest_digest,
        "sourceRevision": _REVISION,
        "sourceDigest": _DIGEST_A,
        "entityCatalogDigest": _DIGEST_B,
        "assets": [
            {
                **item,
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
                "authorizationRequired": True,
                "assetRef": bindings[str(item["assetId"])][0],
                "contentSha256": bindings[str(item["assetId"])][1],
                "bytes": bindings[str(item["assetId"])][2],
            }
            for item in items
        ],
    }
    receipt = {**stable, "receiptDigest": document_digest(stable)}
    receipt_ref = f"receipts/{manifest_digest.removeprefix('sha256:')}.json"
    receipt_path = root / receipt_ref
    write_json(receipt_path, receipt)
    return {
        "manifestDigest": manifest_digest,
        "receipt": receipt,
        "receiptRef": receipt_ref,
        "receiptFileSha256": file_digest(receipt_path),
        "receiptPath": receipt_path,
        "bindings": bindings,
    }


def _rebound_item(item: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    asset_ref, content_sha256, byte_count = history["bindings"][str(item["assetId"])]
    return {
        **item,
        "frozenAsset": {
            "assetRef": asset_ref,
            "contentSha256": content_sha256,
            "bytes": byte_count,
            "sourceReceiptRef": history["receiptRef"],
            "sourceReceiptDigest": history["receipt"]["receiptDigest"],
            "sourceReceiptFileSha256": history["receiptFileSha256"],
        },
    }


def _rebound_manifest(history: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": "video-frozen-reuse",
        "sourceRevision": "sha256:" + "d" * 64,
        "sourceDigest": "sha256:" + "e" * 64,
        "entityCatalogDigest": _DIGEST_B,
        "frozenPhysicalInput": {
            "sourceRevision": _REVISION,
            "sourceDigest": _DIGEST_A,
            "entityCatalogDigest": _DIGEST_B,
            "sourceManifestDigest": history["manifestDigest"],
            "sourceReceiptRef": history["receiptRef"],
            "sourceReceiptDigest": history["receipt"]["receiptDigest"],
            "sourceReceiptFileSha256": history["receiptFileSha256"],
        },
        "items": items,
    }


@pytest.fixture()
def frozen_reuse(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "acquisition"
    base = _item()
    history = _frozen_history(
        root,
        items=[base],
        payloads={"frozen-1": b"exact-frozen-video-bytes"},
    )
    item = _rebound_item(base, history)
    return {
        "root": root,
        "history": history,
        "item": item,
        "manifest": _rebound_manifest(history, [item]),
    }


def _acquire_from_frozen(
    frozen_reuse: dict[str, Any],
    *,
    tmp_path: Path,
    frozen_asset: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    transport: list[str] = []

    def network_fetcher(url: str, destination: Path, *, supported_api: bool) -> str:
        transport.append(f"network:{url}")
        raise AssertionError("frozen reuse must not re-acquire bytes")

    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    row = acquire_video_item(
        frozen_reuse["item"],
        rights=RightsStatus.UNVERIFIED,
        safety_evidence={},
        manual_root=None,
        output_root=frozen_reuse["root"],
        temporary_root=temporary_root,
        safety_validator=lambda *_args, **_kwargs: None,
        network_fetcher=network_fetcher,
        media_probe=lambda _path: dict(_PLAYABLE_PROBE),
        frozen_asset=frozen_asset,
    )
    return row, transport


def test_frozen_asset_resolves_to_the_exact_historical_cas_object(
    frozen_reuse: dict[str, Any],
) -> None:
    """复用必须解析回历史 receipt 与 CAS 中那一份精确字节。"""

    resolved = resolve_frozen_video_asset(
        frozen_reuse["item"],
        manifest=frozen_reuse["manifest"],
        output_root=frozen_reuse["root"],
        receipt_cache={},
    )

    frozen = frozen_reuse["item"]["frozenAsset"]
    assert resolved == frozen_reuse["root"] / frozen["assetRef"]
    assert file_digest(resolved) == frozen["contentSha256"]
    assert resolved.stat().st_size == frozen["bytes"]


def test_an_item_without_a_frozen_declaration_is_absent_not_a_failure(
    frozen_reuse: dict[str, Any],
) -> None:
    """未声明复用是「缺席」，不是失败；缺席才允许走正常取得。"""

    item = {key: value for key, value in frozen_reuse["item"].items() if key != "frozenAsset"}

    assert (
        resolve_frozen_video_asset(
            item,
            manifest=frozen_reuse["manifest"],
            output_root=frozen_reuse["root"],
            receipt_cache={},
        )
        is None
    )


def test_reuse_never_touches_a_transport_or_writes_a_second_cas_copy(
    frozen_reuse: dict[str, Any],
    tmp_path: Path,
) -> None:
    """给定冻结字节后不得再走传输面，也不得向 CAS 另写一份副本。"""

    root = frozen_reuse["root"]
    frozen = frozen_reuse["item"]["frozenAsset"]
    cas_before = sorted(path.name for path in (root / "cas").rglob("*") if path.is_file())

    row, transport = _acquire_from_frozen(
        frozen_reuse,
        tmp_path=tmp_path,
        frozen_asset=root / frozen["assetRef"],
    )

    assert transport == []
    assert row["acquisitionStatus"] == "acquired"
    assert row["assetRef"] == frozen["assetRef"]
    assert row["contentSha256"] == frozen["contentSha256"]
    assert row["bytes"] == frozen["bytes"]
    assert sorted(
        path.name for path in (root / "cas").rglob("*") if path.is_file()
    ) == cas_before


def test_reuse_leaves_no_temporary_download_behind(
    frozen_reuse: dict[str, Any],
    tmp_path: Path,
) -> None:
    """复用路径不建立下载临时件，因此不存在需要清理的中间字节。"""

    root = frozen_reuse["root"]
    frozen = frozen_reuse["item"]["frozenAsset"]

    _row, _transport = _acquire_from_frozen(
        frozen_reuse,
        tmp_path=tmp_path,
        frozen_asset=root / frozen["assetRef"],
    )

    assert list((tmp_path / "temporary").iterdir()) == []


def test_a_missing_frozen_object_is_a_typed_failure_not_an_empty_success(
    frozen_reuse: dict[str, Any],
    tmp_path: Path,
) -> None:
    """引用不可兑现必须 fail closed，不得返回空路径或零大小。"""

    root = frozen_reuse["root"]
    frozen = frozen_reuse["item"]["frozenAsset"]
    (root / frozen["assetRef"]).unlink()

    row, transport = _acquire_from_frozen(
        frozen_reuse,
        tmp_path=tmp_path,
        frozen_asset=root / frozen["assetRef"],
    )

    assert transport == []
    assert row["acquisitionStatus"] == "failed"
    assert row["failureCode"] == "DATA.SOURCE.ACQUISITION_FAILED"
    assert "frozen CAS object is missing or unsafe" in row["failure"]
    assert row["assetRef"] == ""
    assert row["bytes"] == 0
    assert row["contentSha256"] == ""


def test_frozen_bytes_drift_fails_closed_before_any_reuse(
    frozen_reuse: dict[str, Any],
) -> None:
    """CAS 字节与记录摘要不一致时必须 fail closed，而不是照旧复用。"""

    root = frozen_reuse["root"]
    frozen = frozen_reuse["item"]["frozenAsset"]
    (root / frozen["assetRef"]).write_bytes(b"tampered-frozen-video-bytes")

    with pytest.raises(ValueError, match="frozen CAS bytes drift"):
        resolve_frozen_video_asset(
            frozen_reuse["item"],
            manifest=frozen_reuse["manifest"],
            output_root=root,
            receipt_cache={},
        )


def test_frozen_receipt_identity_drift_fails_closed(
    frozen_reuse: dict[str, Any],
) -> None:
    """复用绑定的历史身份必须与 manifest 冻结的物理输入完全一致。"""

    manifest = dict(frozen_reuse["manifest"])
    manifest["frozenPhysicalInput"] = {
        **manifest["frozenPhysicalInput"],
        "sourceRevision": "sha256:" + "9" * 64,
    }

    with pytest.raises(ValueError, match="frozen physical receipt identity drift"):
        resolve_frozen_video_asset(
            frozen_reuse["item"],
            manifest=manifest,
            output_root=frozen_reuse["root"],
            receipt_cache={},
        )


def test_a_frozen_binding_that_disagrees_with_the_manifest_header_fails_closed(
    frozen_reuse: dict[str, Any],
) -> None:
    """逐资产的 frozen 头必须与 manifest 级冻结头同源，不允许各说一套。"""

    item = dict(frozen_reuse["item"])
    item["frozenAsset"] = {
        **item["frozenAsset"],
        "sourceReceiptFileSha256": "sha256:" + "1" * 64,
    }

    with pytest.raises(ValueError, match="frozen receipt binding differs from manifest"):
        resolve_frozen_video_asset(
            item,
            manifest=frozen_reuse["manifest"],
            output_root=frozen_reuse["root"],
            receipt_cache={},
        )


def test_a_frozen_row_that_was_never_admitted_cannot_be_reused(
    tmp_path: Path,
) -> None:
    """历史行未被取得或未准入时不得作为复用来源。"""

    root = tmp_path / "acquisition"
    base = _item("blocked-1")
    history = _frozen_history(
        root,
        items=[base],
        payloads={"blocked-1": b"blocked-frozen-video-bytes"},
    )
    receipt = history["receipt"]
    stable = {
        key: value for key, value in receipt.items() if key != "receiptDigest"
    }
    stable["assets"] = [
        {**receipt["assets"][0], "distributionDecision": "blocked"}
    ]
    rewritten = {**stable, "receiptDigest": document_digest(stable)}
    write_json(history["receiptPath"], rewritten)
    history["receipt"] = rewritten
    history["receiptFileSha256"] = file_digest(history["receiptPath"])
    item = _rebound_item(base, history)

    with pytest.raises(
        ValueError, match="frozen asset provenance or bytes binding drift"
    ):
        resolve_frozen_video_asset(
            item,
            manifest=_rebound_manifest(history, [item]),
            output_root=root,
            receipt_cache={},
        )


def test_one_frozen_receipt_is_verified_once_and_reused_across_assets(
    tmp_path: Path,
) -> None:
    """同一份历史 receipt 只验证一次，其后按缓存复用而不重读冻结字节。"""

    root = tmp_path / "acquisition"
    first = _item("frozen-a")
    second = _item("frozen-b")
    history = _frozen_history(
        root,
        items=[first, second],
        payloads={
            "frozen-a": b"exact-frozen-video-bytes-a",
            "frozen-b": b"exact-frozen-video-bytes-b",
        },
    )
    items = [_rebound_item(first, history), _rebound_item(second, history)]
    manifest = _rebound_manifest(history, items)
    cache: dict[str, tuple[dict[str, Any], str]] = {}

    resolved = [
        resolve_frozen_video_asset(
            item,
            manifest=manifest,
            output_root=root,
            receipt_cache=cache,
        )
        for item in items
    ]

    assert list(cache) == [history["receiptRef"]]
    assert len({path for path in resolved}) == 2


def test_frozen_reuse_of_its_own_digest_is_evidence_not_a_duplicate() -> None:
    """显式复用自己冻结的摘要不是跨 receipt 碰撞，否则复用永远无法通过。"""

    digest = "sha256:" + "7" * 64
    row = {"assetId": "frozen-1", "contentSha256": digest}

    assert (
        duplicate_source(
            row,
            seen={},
            prior={digest: "receipts/history.json#frozen-1"},
            frozen_reuse_digests={"frozen-1": digest},
        )
        == ""
    )


def test_the_frozen_reuse_exemption_is_scoped_to_its_own_asset() -> None:
    """豁免是 asset 级的：换一个 assetId 复用同一摘要仍然是重复。"""

    digest = "sha256:" + "7" * 64
    row = {"assetId": "frozen-2", "contentSha256": digest}

    assert (
        duplicate_source(
            row,
            seen={},
            prior={digest: "receipts/history.json#frozen-1"},
            frozen_reuse_digests={"frozen-1": digest},
        )
        == "receipts/history.json#frozen-1"
    )


def test_the_frozen_reuse_exemption_never_covers_a_repeat_inside_one_manifest() -> None:
    """同一 manifest 内重复同一份字节仍是重复，复用豁免不覆盖它。"""

    digest = "sha256:" + "7" * 64
    row = {"assetId": "frozen-1", "contentSha256": digest}

    assert (
        duplicate_source(
            row,
            seen={digest: "frozen-0"},
            prior={},
            frozen_reuse_digests={"frozen-1": digest},
        )
        == "frozen-0"
    )


def test_an_asset_without_bytes_is_never_deduplicated_against_history() -> None:
    """未取得字节的行没有可比对的摘要，不得被判为重复。"""

    assert (
        duplicate_source(
            {"assetId": "failed-1", "contentSha256": ""},
            seen={},
            prior={"sha256:" + "7" * 64: "receipts/history.json#frozen-1"},
            frozen_reuse_digests={},
        )
        == ""
    )


def test_reused_bytes_keep_the_historical_content_digest(
    frozen_reuse: dict[str, Any],
    tmp_path: Path,
) -> None:
    """复用后的内容摘要必须仍是历史摘要，字节身份不因换 manifest 而变。"""

    root = frozen_reuse["root"]
    frozen = frozen_reuse["item"]["frozenAsset"]
    payload = (root / frozen["assetRef"]).read_bytes()

    row, _transport = _acquire_from_frozen(
        frozen_reuse,
        tmp_path=tmp_path,
        frozen_asset=root / frozen["assetRef"],
    )

    assert row["contentSha256"] == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert row["contentSha256"] == frozen_reuse["history"]["receipt"]["assets"][0][
        "contentSha256"
    ]
