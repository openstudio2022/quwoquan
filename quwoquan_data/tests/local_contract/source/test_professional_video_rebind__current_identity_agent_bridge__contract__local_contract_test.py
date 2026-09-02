# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-005
"""历史视频字节改挂当前来源身份时，必须由一次全新的宿主源审做桥。

`REQ-005`：「上游历史 `sourceDigests/executionIds` 只能以冻结 provenance 留在 adoption
receipt，不得被提升为新 release 的多 source active identity。」`REQ-001` 进一步禁止
「把 pending 改写或冒充旧 `reviewer_result`」。`REQ-003` 只允许「通过安全/相关性门的
真实视频文件」进入 research release，且「下载成功不得把 rights 状态升级为 verified」。

因此这条桥必须同时满足：

1. 身份分层：新 manifest 的 active identity 只来自当前 handoff，历史身份与历史
   receipt 只能作为冻结 provenance 出现在 `frozenPhysicalInput` 与 `frozenAsset`；
2. 评审重做：历史 safetyReview 不得被复制，评审请求必须绑定当前身份与这份精确字节，
   评审结论只能由宿主经 create-once host source review 记录；
3. 结论不放宽：评审 blocked、词表外或宿主缺席都是 typed exclusion，只作废它自己；
   零成功时 fail closed 且不落 manifest；权利事实原样透传，不因重挂而升级；
4. 同一身份不重复评审：同身份同字节重放只读回同一 create-once 结果；身份一变必须
   重新评审。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.planning.scale import campaign_workload_targets
from content.source.pre_acquisition_handoff import (
    write_pre_acquisition_handoff,
)
from content.source import professional_video_rebind as rebind
from content.source.host_source_review import (
    HOST_SOURCE_REVIEW_INVALID,
    HostSourceReviewError,
    record_host_source_review_result,
)
from content.source.professional_safety_evidence import file_sha256
from content.source.professional_video_receipt import document_digest, file_digest
from content.source.professional_video_rebind import (
    ProfessionalVideoRebindError,
    rebind_professional_video_acquisition_manifest,
)
from content.source.professional_video_store import put_video_cas
from content.source.source_review_journal import run_source_review
from core.control_types import AgentProvider
from core.io import read_json, write_json

_HISTORICAL_REVISION = "sha256:" + "c" * 64
_HISTORICAL_SOURCE = "sha256:" + "a" * 64
_HISTORICAL_CATALOG = "sha256:" + "b" * 64
_PROBE = {
    "width": 640,
    "height": 360,
    "frameCount": 48,
    "framesPerSecond": 12.0,
    "durationMs": 4000,
    "codec": "mp4v",
    "hasAudio": False,
    "sampleCount": 12,
    "distinctFrameCount": 12,
    "movingTransitionCount": 11,
    "meanTransitionDelta": 0.18,
    "motionVideo": True,
    "staticImageSequence": False,
    "playable": True,
    "premiumPlayableEligible": True,
}
_PASSED_JUDGMENT = {
    "status": "passed",
    "entityMatch": "matched",
    "privacyRisk": "none",
    "minorRisk": "none",
    "maliciousMediaRisk": "none",
    "watermarkStatus": "absent",
    "qualityStatus": "passed",
    "findings": [],
}
_HISTORICAL_REVIEWER = "historical-operator"


def _item(asset_id: str) -> dict[str, Any]:
    """One historical item carrying its own already-recorded safety decision."""
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
            "reviewer": _HISTORICAL_REVIEWER,
            "evidenceRef": f"history/{asset_id}-safety.json",
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
        "popularCandidateId": f"pexels_videos:{asset_id}",
        "popularCatalogRef": "history/popular-catalog.json",
        "popularCatalogDigest": "sha256:" + "d" * 64,
        "popularCatalogFileSha256": "sha256:" + "e" * 64,
    }


def _freeze(root: Path, *, payload: bytes) -> tuple[str, str, int]:
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


def _history(root: Path, *, asset_ids: tuple[str, ...]) -> dict[str, Any]:
    """One immutable historical manifest/receipt pair owning frozen CAS bytes."""
    items = [_item(asset_id) for asset_id in asset_ids]
    bindings = {
        asset_id: _freeze(root, payload=f"frozen-video-bytes-{asset_id}".encode())
        for asset_id in asset_ids
    }
    manifest = {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": "video-legacy-history",
        "sourceRevision": _HISTORICAL_REVISION,
        "sourceDigest": _HISTORICAL_SOURCE,
        "entityCatalogDigest": _HISTORICAL_CATALOG,
        "items": items,
    }
    manifest_path = root / "history" / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_digest = document_digest(manifest)
    stable = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": manifest["manifestId"],
        "manifestDigest": manifest_digest,
        "sourceRevision": _HISTORICAL_REVISION,
        "sourceDigest": _HISTORICAL_SOURCE,
        "entityCatalogDigest": _HISTORICAL_CATALOG,
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
        "manifestPath": manifest_path,
        "manifestDigest": manifest_digest,
        "receipt": receipt,
        "receiptRef": receipt_ref,
        "receiptFileSha256": file_digest(receipt_path),
        "bindings": bindings,
    }


def _handoff(
    output_root: Path,
    *,
    handoff_id: str,
    source_digest: str,
    entity_catalog_digest: str,
    execution_bundle_digest: str,
) -> Path:
    from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot

    _document, path = write_pre_acquisition_handoff(
        handoff_id=handoff_id,
        handoff_revision=1,
        supersedes_handoff=None,
        scale="M100",
        vertical="travel",
        lifecycle="research",
        scope_type="region",
        region_ref="china",
        primary_topic_ref=None,
        related_topic_refs=(),
        source_selection={
            "homepage": {"mode": "site_primary", "providers": ["wikipedia"]},
            "article": {"mode": "site_primary", "providers": ["mafengwo"]},
            "image": {"mode": "search_supplement", "providers": ["adobe_stock"]},
            "video": {"mode": "site_primary", "providers": ["bilibili"]},
        },
        run_date="20260819",
        campaign_sequence=1,
        campaign_retry_of=None,
        source_digest=SourceDefinitionSnapshot(digest=source_digest).to_document(),
        execution_bundle=ExecutionBundleIdentity(
            digest=execution_bundle_digest
        ).to_document(),
        entity_catalog_digest=entity_catalog_digest,
        workload_targets=campaign_workload_targets("M100"),
        output_root=output_root,
    )
    return path


@pytest.fixture()
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Isolate media decoding so the identity/review bridge is what is measured."""

    def contact_sheet(
        asset: Path,
        destination: Path,
        *,
        frame_count: int,
        fail: Any,
    ) -> None:
        assert frame_count == _PROBE["frameCount"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"contact-sheet-" + asset.name.encode())

    monkeypatch.setattr(
        rebind, "probe_professional_video", lambda _asset: dict(_PROBE)
    )
    monkeypatch.setattr(
        rebind,
        "scan_sourced_video_watermark",
        lambda _asset: {
            "schema": "quwoquan_data.sourced_video_watermark_evidence",
            "decision": "passed",
            "watermarkDetected": False,
            "ocrReviewed": True,
            "sampleCount": 12,
        },
    )
    monkeypatch.setattr(rebind, "render_contact_sheet", contact_sheet)

    root = tmp_path / "acquisition"
    history = _history(root, asset_ids=("legacy-a", "legacy-b"))
    return {
        "root": root,
        "history": history,
        "handoff": _handoff(
            tmp_path / "handoff-output",
            handoff_id="travel-m100-video-rebind-bridge",
            source_digest="sha256:" + "1" * 64,
            entity_catalog_digest="sha256:" + "2" * 64,
            execution_bundle_digest="sha256:" + "3" * 64,
        ),
    }


def _run_once(
    bridge: dict[str, Any],
    *,
    destination: str = "manifests/rebound.json",
    asset_ids: tuple[str, ...] = (),
) -> tuple[dict[str, Any], Path | None]:
    return rebind_professional_video_acquisition_manifest(
        bridge["history"]["manifestPath"],
        source_receipt_ref=bridge["history"]["receiptRef"],
        handoff_ref=bridge["handoff"],
        destination=bridge["root"] / destination,
        output_root=bridge["root"],
        asset_ids=asset_ids,
    )


def _pending_requests(root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Frozen review requests that the host has not answered yet."""
    requests_root = root / "host-source-reviews" / "requests"
    results_root = root / "host-source-reviews" / "results"
    pending: list[tuple[str, dict[str, Any]]] = []
    if not requests_root.is_dir():
        return pending
    for path in sorted(requests_root.glob("*.json")):
        if (results_root / path.name).exists():
            continue
        pending.append(
            (f"host-source-reviews/requests/{path.name}", read_json(path))
        )
    return pending


def _result_input(
    request_ref: str,
    request: dict[str, Any],
    *,
    passed: bool,
) -> dict[str, Any]:
    asset_id = str(request["assetBinding"]["assetId"])
    return {
        "schema": "quwoquan_data.host_source_review_result_input",
        "requestRef": request_ref,
        "requestDigest": request["requestDigest"],
        "actor": {
            "host": "cursor",
            "sessionId": "rebind-review-session",
            "modelFamily": "gpt-5",
            "auditRunId": f"rebind-audit-{asset_id}",
        },
        "reviewedAt": "2026-08-19T00:05:00Z",
        "verdict": {
            "status": "passed" if passed else "blocked",
            "entityMatch": "matched",
            "qualityStatus": "passed",
            "privacyRisk": "none" if passed else "present",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "findings": [] if passed else ["privacy risk is present in frame samples"],
        },
    }


def _record_reviews(
    root: Path,
    *,
    blocked: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> int:
    recorded = 0
    for request_ref, request in _pending_requests(root):
        asset_id = str(request["assetBinding"]["assetId"])
        if asset_id in skip:
            continue
        record_host_source_review_result(
            evidence_root=root,
            result_input=_result_input(
                request_ref, request, passed=asset_id not in blocked
            ),
        )
        recorded += 1
    return recorded


def _run(
    bridge: dict[str, Any],
    *,
    blocked: frozenset[str] = frozenset(),
    destination: str = "manifests/rebound.json",
    asset_ids: tuple[str, ...] = (),
) -> tuple[dict[str, Any], Path | None]:
    """两阶段驱动：宿主对 pending 审核请求记录结论后重入同一命令。"""
    try:
        return _run_once(bridge, destination=destination, asset_ids=asset_ids)
    except ProfessionalVideoRebindError as error:
        if "DATA.SOURCE.HOST_REVIEW_PENDING" not in error.detail:
            raise
        if not _record_reviews(bridge["root"], blocked=blocked):
            raise
        return _run_once(bridge, destination=destination, asset_ids=asset_ids)


def _current_identity(bridge: dict[str, Any]) -> dict[str, str]:
    handoff = read_json(bridge["handoff"])
    return {
        "sourceRevision": str(handoff["sourceRevision"]),
        "sourceDigest": str(handoff["sourceDigest"]["digest"]),
        "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
        "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
        "handoffDigest": file_sha256(bridge["handoff"]),
    }


def _review_requests(root: Path) -> dict[str, list[dict[str, Any]]]:
    requests_root = root / "host-source-reviews" / "requests"
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not requests_root.is_dir():
        return grouped
    for path in sorted(requests_root.glob("*.json")):
        document = read_json(path)
        grouped.setdefault(
            str(document["assetBinding"]["assetId"]), []
        ).append(document)
    return grouped


def _evidence_document(
    root: Path, request: dict[str, Any], *, role: str
) -> dict[str, Any]:
    binding = next(
        row for row in request["evidenceBindings"] if row["role"] == role
    )
    return read_json(root / binding["ref"])


def test_the_new_manifest_active_identity_is_only_the_current_handoff(
    bridge: dict[str, Any],
) -> None:
    """新 manifest 的 active identity 只能是当前 handoff 身份。"""

    _result, manifest_path = _run(bridge)
    manifest = read_json(manifest_path)
    identity = _current_identity(bridge)

    assert manifest["sourceRevision"] == identity["sourceRevision"]
    assert manifest["sourceDigest"] == identity["sourceDigest"]
    assert manifest["entityCatalogDigest"] == identity["entityCatalogDigest"]
    assert manifest["executionBundle"]["digest"] == identity["executionBundleDigest"]


def test_the_historical_identity_survives_only_as_frozen_provenance(
    bridge: dict[str, Any],
) -> None:
    """历史身份只能作为冻结 provenance，不得成为第二个 active source identity。"""

    _result, manifest_path = _run(bridge)
    manifest = read_json(manifest_path)
    frozen = manifest["frozenPhysicalInput"]
    history = bridge["history"]

    assert frozen == {
        "sourceRevision": _HISTORICAL_REVISION,
        "sourceDigest": _HISTORICAL_SOURCE,
        "entityCatalogDigest": _HISTORICAL_CATALOG,
        "sourceManifestDigest": history["manifestDigest"],
        "sourceReceiptRef": history["receiptRef"],
        "sourceReceiptDigest": history["receipt"]["receiptDigest"],
        "sourceReceiptFileSha256": history["receiptFileSha256"],
    }
    assert manifest["sourceDigest"] != _HISTORICAL_SOURCE
    assert manifest["entityCatalogDigest"] != _HISTORICAL_CATALOG


def test_each_rebound_item_binds_the_exact_historical_bytes(
    bridge: dict[str, Any],
) -> None:
    """每个重挂对象都必须指回历史 CAS 中那一份精确字节。"""

    _result, manifest_path = _run(bridge)
    manifest = read_json(manifest_path)
    history = bridge["history"]

    for item in manifest["items"]:
        asset_ref, content_sha256, byte_count = history["bindings"][item["assetId"]]
        assert item["frozenAsset"] == {
            "assetRef": asset_ref,
            "contentSha256": content_sha256,
            "bytes": byte_count,
            "sourceReceiptRef": history["receiptRef"],
            "sourceReceiptDigest": history["receipt"]["receiptDigest"],
            "sourceReceiptFileSha256": history["receiptFileSha256"],
        }
        assert file_digest(bridge["root"] / asset_ref) == content_sha256


def test_the_review_request_binds_the_current_identity_and_the_frozen_bytes(
    bridge: dict[str, Any],
) -> None:
    """评审请求是身份桥：当前身份 + 这份精确历史字节，两者都必须在请求里。"""

    _result, _manifest_path = _run(bridge)
    requests = _review_requests(bridge["root"])
    history = bridge["history"]
    identity = _current_identity(bridge)

    assert set(requests) == {"legacy-a", "legacy-b"}
    for asset_id, documents in requests.items():
        assert len(documents) == 1
        request = documents[0]
        asset_ref, content_sha256, byte_count = history["bindings"][asset_id]
        assert request["sourceIdentity"] == identity
        assert request["assetBinding"]["assetRef"] == asset_ref
        assert request["assetBinding"]["contentSha256"] == content_sha256
        assert request["assetBinding"]["bytes"] == byte_count
        acquisition = _evidence_document(
            bridge["root"], request, role="acquisition"
        )
        assert acquisition["sourceReceiptRef"] == history["receiptRef"]
        assert (
            acquisition["sourceReceiptDigest"]
            == history["receipt"]["receiptDigest"]
        )
        assert (
            acquisition["sourceReceiptFileSha256"] == history["receiptFileSha256"]
        )


def test_the_review_request_carries_the_frozen_rights_without_upgrading_them(
    bridge: dict[str, Any],
) -> None:
    """权利事实原样透传给评审者，重挂不得把 unverified 升级为 verified。"""

    _result, manifest_path = _run(bridge)
    request = _review_requests(bridge["root"])["legacy-a"][0]
    rights = _evidence_document(bridge["root"], request, role="rights_attribution")
    item = next(
        row for row in read_json(manifest_path)["items"] if row["assetId"] == "legacy-a"
    )

    assert rights["rightsSnapshot"] == {
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "rightsIssues": ["commercial redistribution authorization is unverified"],
        "modelReleaseStatus": "unverified",
        "propertyReleaseStatus": "not_required",
    }
    assert "untrusted input" in request["rubric"]["untrustedEvidencePolicy"]
    assert item["rightsStatus"] == "unverified"
    assert item["rightsIssues"] == [
        "commercial redistribution authorization is unverified"
    ]


def test_the_historical_safety_decision_is_never_copied_into_the_rebound_item(
    bridge: dict[str, Any],
) -> None:
    """历史 safetyReview 不得被复制；重挂对象只能带本次评审的结论。"""

    _result, manifest_path = _run(bridge)
    item = next(
        row for row in read_json(manifest_path)["items"] if row["assetId"] == "legacy-a"
    )
    safety = item["safetyReview"]

    assert safety["reviewer"] == "host:rebind-audit-legacy-a"
    assert safety["reviewer"] != _HISTORICAL_REVIEWER
    assert safety["reviewedAt"] != "2026-08-05T02:05:00Z"
    assert safety["evidenceRef"].startswith("video-rebind/")
    assert (
        file_sha256(bridge["root"] / safety["evidenceRef"])
        == safety["safetyEvidenceFileSha256"]
    )


def test_the_fresh_safety_evidence_binds_its_own_host_review_result(
    bridge: dict[str, Any],
) -> None:
    """本次 safety 证据必须精确绑定本次 host review 的 request/result 与摘要。"""

    _result, manifest_path = _run(bridge)
    item = next(
        row for row in read_json(manifest_path)["items"] if row["assetId"] == "legacy-a"
    )
    root = bridge["root"]
    evidence = read_json(root / item["safetyReview"]["evidenceRef"])
    review = evidence["reviewEvidence"]
    request = read_json(root / review["requestRef"])
    result = read_json(root / review["resultRef"])

    assert request["sourceIdentity"] == _current_identity(bridge)
    assert review["requestDigest"] == request["requestDigest"]
    assert review["requestDigest"] == result["requestDigest"]
    assert review["resultDigest"] == result["resultDigest"]
    assert review["actor"]["host"] == "cursor"
    assert "provider" not in review
    assert "model" not in review
    assert evidence["reviewedAt"] == result["reviewedAt"]
    assert item["safetyReview"]["reviewedAt"] == result["reviewedAt"]


def test_the_historical_popularity_catalog_binding_is_dropped(
    bridge: dict[str, Any],
) -> None:
    """历史热度目录绑定属于上一次运行，不得随字节一起进入当前 manifest。"""

    _result, manifest_path = _run(bridge)
    item = next(
        row for row in read_json(manifest_path)["items"] if row["assetId"] == "legacy-a"
    )

    for field in (
        "popularCandidateId",
        "popularCatalogRef",
        "popularCatalogDigest",
        "popularCatalogFileSha256",
    ):
        assert field not in item
    assert item["popularitySignals"]["playCount"] == 1_000


def test_the_reviewer_is_handed_exactly_the_persisted_review_request(
    bridge: dict[str, Any],
) -> None:
    """宿主只消费落盘的 create-once 请求文件，结果必须指回同一请求摘要。"""

    _result, _manifest_path = _run(bridge)
    root = bridge["root"]
    requests = _review_requests(root)

    assert set(requests) == {"legacy-a", "legacy-b"}
    for documents in requests.values():
        assert len(documents) == 1
        request = documents[0]
        result_path = (
            root
            / "host-source-reviews"
            / "results"
            / f"{request['requestDigest'].removeprefix('sha256:')}.json"
        )
        result = read_json(result_path)
        assert result["requestDigest"] == request["requestDigest"]


def test_one_identity_reviews_once_and_replay_reads_back_the_same_result(
    bridge: dict[str, Any],
) -> None:
    """同身份同字节重放只读回同一 create-once 结果，不得再开一次评审。"""

    first, first_path = _run(bridge)
    second, second_path = _run_once(bridge)

    assert second_path == first_path
    assert second == first
    requests = _review_requests(bridge["root"])
    assert sorted(requests) == ["legacy-a", "legacy-b"]
    assert all(len(documents) == 1 for documents in requests.values())


def test_a_new_current_identity_requires_a_new_review(
    bridge: dict[str, Any],
    tmp_path: Path,
) -> None:
    """身份一变必须重新评审，旧结论不得被复用来顶替新身份。"""

    _first, _first_path = _run(bridge, asset_ids=("legacy-a",))
    first_request = _review_requests(bridge["root"])["legacy-a"][0]

    bridge["handoff"] = _handoff(
        tmp_path / "handoff-output-2",
        handoff_id="travel-m100-video-rebind-bridge-next",
        source_digest="sha256:" + "4" * 64,
        entity_catalog_digest="sha256:" + "5" * 64,
        execution_bundle_digest="sha256:" + "6" * 64,
    )
    _second, second_path = _run(
        bridge,
        destination="manifests/rebound-next.json",
        asset_ids=("legacy-a",),
    )
    requests = _review_requests(bridge["root"])["legacy-a"]

    assert len(requests) == 2
    review = read_json(
        bridge["root"]
        / next(
            row
            for row in read_json(second_path)["items"]
            if row["assetId"] == "legacy-a"
        )["safetyReview"]["evidenceRef"]
    )["reviewEvidence"]
    assert review["requestDigest"] != first_request["requestDigest"]
    second_request = read_json(bridge["root"] / review["requestRef"])
    assert second_request["sourceIdentity"]["sourceDigest"] == "sha256:" + "4" * 64


def test_a_blocked_fresh_review_excludes_only_its_own_asset(
    bridge: dict[str, Any],
) -> None:
    """一次 blocked 评审只作废它自己，兄弟对象照常进入当前 manifest。"""

    result, manifest_path = _run(bridge, blocked=frozenset({"legacy-a"}))
    manifest = read_json(manifest_path)

    assert result["reboundCount"] == 1
    assert result["excludedCount"] == 1
    assert [row["assetId"] for row in manifest["items"]] == ["legacy-b"]
    exclusion = result["exclusions"][0]
    assert exclusion["assetId"] == "legacy-a"
    assert exclusion["failureCode"] == "DATA.SOURCE.REBIND_FRESH_REVIEW_BLOCKED"
    assert "evidence=video-rebind/" in exclusion["failure"]


def test_a_blocked_review_still_leaves_its_own_typed_evidence(
    bridge: dict[str, Any],
) -> None:
    """blocked 也必须留下可复核证据，失败不得退化为无痕跳过。"""

    result, _manifest_path = _run(bridge, blocked=frozenset({"legacy-a"}))
    reference = result["exclusions"][0]["failure"].split("evidence=")[1]
    evidence = read_json(bridge["root"] / reference)

    assert evidence["assetId"] == "legacy-a"
    assert evidence["status"] == "blocked"
    assert evidence["privacyRisk"] == "present"
    assert evidence["reviewer"] == "host:rebind-audit-legacy-a"


@pytest.mark.parametrize(
    "verdict",
    [
        "the video looks fine to me",
        {"status": "passed"},
        {**_PASSED_JUDGMENT, "extraField": "ignored"},
        {**_PASSED_JUDGMENT, "privacyRisk": "detected"},
    ],
)
def test_an_out_of_vocabulary_verdict_cannot_be_written_as_admission_evidence(
    bridge: dict[str, Any],
    verdict: Any,
) -> None:
    """评审词表是闭集：词表外或字段集不符的结论不得落成证据，也不得让该资产通过。"""

    with pytest.raises(ProfessionalVideoRebindError):
        _run_once(bridge)
    pending = {
        str(request["assetBinding"]["assetId"]): (request_ref, request)
        for request_ref, request in _pending_requests(bridge["root"])
    }
    request_ref, request = pending["legacy-a"]
    invalid_input = _result_input(request_ref, request, passed=True)
    invalid_input["verdict"] = verdict

    with pytest.raises(HostSourceReviewError) as rejected:
        record_host_source_review_result(
            evidence_root=bridge["root"], result_input=invalid_input
        )
    assert rejected.value.code == HOST_SOURCE_REVIEW_INVALID

    _record_reviews(bridge["root"], skip=frozenset({"legacy-a"}))
    result, manifest_path = _run_once(bridge)

    assert [row["assetId"] for row in read_json(manifest_path)["items"]] == ["legacy-b"]
    exclusion = result["exclusions"][0]
    assert exclusion["assetId"] == "legacy-a"
    assert exclusion["failureCode"] == "DATA.SOURCE.HOST_REVIEW_PENDING"
    result_path = (
        bridge["root"]
        / "host-source-reviews"
        / "results"
        / f"{request['requestDigest'].removeprefix('sha256:')}.json"
    )
    assert not result_path.exists()


def test_zero_admitted_assets_fails_closed_without_writing_a_manifest(
    bridge: dict[str, Any],
) -> None:
    """零成功必须 fail closed，且不得留下一份空的当前 manifest。"""

    with pytest.raises(ProfessionalVideoRebindError) as error:
        _run(bridge, blocked=frozenset({"legacy-a", "legacy-b"}))

    assert error.value.code == "DATA.SOURCE.REBIND_NO_SUCCESS"
    assert "DATA.SOURCE.REBIND_FRESH_REVIEW_BLOCKED" in error.value.detail
    assert not (bridge["root"] / "manifests" / "rebound.json").exists()


def test_an_absent_host_review_is_a_typed_exclusion_not_an_admission(
    bridge: dict[str, Any],
) -> None:
    """宿主缺席（不记录结论）是失败，不得被当作缺席或默认通过。"""

    with pytest.raises(ProfessionalVideoRebindError) as error:
        _run_once(bridge)

    assert error.value.code == "DATA.SOURCE.REBIND_NO_SUCCESS"
    assert "DATA.SOURCE.HOST_REVIEW_PENDING" in error.value.detail

    with pytest.raises(ProfessionalVideoRebindError) as replay:
        _run_once(bridge)

    assert replay.value.code == "DATA.SOURCE.REBIND_NO_SUCCESS"
    assert not (bridge["root"] / "manifests" / "rebound.json").exists()


def test_a_review_from_an_ungoverned_host_cannot_stand_in(
    bridge: dict[str, Any],
) -> None:
    """actor.host 是闭集：非 cursor/codex 宿主的结论不得顶替 host review 证据。"""

    with pytest.raises(ProfessionalVideoRebindError):
        _run_once(bridge)
    request_ref, request = _pending_requests(bridge["root"])[0]
    foreign_input = _result_input(request_ref, request, passed=True)
    foreign_input["actor"]["host"] = "external-sdk"

    with pytest.raises(HostSourceReviewError) as rejected:
        record_host_source_review_result(
            evidence_root=bridge["root"], result_input=foreign_input
        )
    assert rejected.value.code == HOST_SOURCE_REVIEW_INVALID


def test_an_asset_absent_from_the_historical_pair_is_excluded_by_name(
    bridge: dict[str, Any],
) -> None:
    """请求一个历史证据里不存在的资产时排除它自己并具名。"""

    result, manifest_path = _run(
        bridge, asset_ids=("legacy-a", "legacy-missing")
    )

    assert result["reboundCount"] == 1
    assert [row["assetId"] for row in read_json(manifest_path)["items"]] == ["legacy-a"]
    assert result["exclusions"] == [
        {
            "assetId": "legacy-missing",
            "failureCode": "DATA.SOURCE.REBIND_ASSET_MISSING",
            "failure": "asset is absent from source manifest or receipt",
        }
    ]


def test_the_review_identity_is_a_closed_set(
    tmp_path: Path,
) -> None:
    """评审 journal 的身份是闭集：多一项、少一项都不成立。"""

    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
        "requestDigest": "sha256:" + "6" * 64,
    }

    for mutated in (
        {key: value for key, value in identity.items() if key != "handoffDigest"},
        {**identity, "executionId": "20260819--travel-video--west-lake--scale-001"},
    ):
        with pytest.raises(ValueError, match="source review identity or model"):
            run_source_review(
                source_evidence_root=tmp_path,
                source_review=mutated,
                model="grok-4.6",
                prompt="{}",
                runner=lambda _prompt: AgentRunOutcome.finished(
                    provider=AgentProvider.CURSOR_SDK
                ),
            )


def test_an_ungoverned_model_cannot_open_a_review_journal(tmp_path: Path) -> None:
    """model 不是受治理主选时不得开出评审 journal。"""

    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
        "requestDigest": "sha256:" + "6" * 64,
    }

    with pytest.raises(ValueError, match="source review identity or model"):
        run_source_review(
            source_evidence_root=tmp_path,
            source_review=identity,
            model="grok-legacy",
            prompt="{}",
            runner=lambda _prompt: AgentRunOutcome.finished(
                provider=AgentProvider.CURSOR_SDK
            ),
        )
