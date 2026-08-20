"""Professional video admission, planning, and failure-recovery contracts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.local_contract.source.test_professional_video_acquisition__behavior__functional__local_contract_test import (
    ProfessionalVideoAcquisitionBlocked,
    ProfessionalVideoCasCollision,
    _DIGEST_A,
    _DIGEST_B,
    _acquisition_dependencies,
    _acquire,
    _item,
    _manifest,
    _write_slideshow,
    _write_video,
    acquire_professional_videos,
    build_professional_video_popular_candidate_catalog,
    load_professional_video_acquisition_receipt,
    professional_video_acquisition,
    put_video_cas,
    read_json,
    write_create_once_professional_video_popular_candidate_catalog,
    write_json,
    write_video_lane,
)

def test_acquisition_physically_consumes_popular_catalog_binding(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "high.mp4", moving=True, seed=21)
    response = {
        "provider": "bilibili",
        "sourcePageUrl": "https://www.bilibili.com/video/BV-popular",
        "apiEvidenceUrl": "https://api.bilibili.com/x/web-interface/archive/stat",
        "statusCode": 200,
        "contentType": "application/json",
        "accessEvidence": {
            "supportedApi": True, "cookiesSent": False, "loginRequired": False,
            "paywallRequired": False, "drmProtected": False,
            "accessControlBypass": False,
        },
        "items": [
            {
                "sourceId": source_id, "entityId": "西湖", "observedEntityId": "西湖",
                "creator": f"Creator {source_id}", "title": f"西湖热门旅行 {source_id}",
                "observedAt": "2026-08-08T09:00:00Z", "topic": "west-lake-travel",
                "timeBucket": "2026-W32", "playCount": score * 100,
                "likeCount": score * 10, "commentCount": score,
                "shareCount": score, "favoriteCount": score * 2,
            }
            for source_id, score in (("low", 10), ("high", 20))
        ],
    }
    catalog = build_professional_video_popular_candidate_catalog(
        source_revision="sha256:" + "1" * 64,
        source_digest=_DIGEST_A,
        entity_catalog_digest=_DIGEST_B,
        metadata_responses=[response],
        manual_file_manifests=[{
            "provider": "bilibili", "sourceId": "high",
            "sourcePageUrl": response["sourcePageUrl"], "manualFileRef": "high.mp4",
        }],
        evidence_root=manual_root,
    )
    output_root = tmp_path / "acquisition"
    catalog_ref = (
        "professional-video-popular-catalogs/"
        f"{catalog['catalogDigest'][7:]}.json"
    )
    catalog_path = output_root / catalog_ref
    write_create_once_professional_video_popular_candidate_catalog(catalog_path, catalog)
    catalog_sha = "sha256:" + __import__("hashlib").sha256(
        catalog_path.read_bytes()
    ).hexdigest()
    candidate = next(row for row in catalog["candidates"] if row["sourceId"] == "high")
    popularity = candidate["popularity"]
    item = _item(
        "popular", "high.mp4",
        counts=tuple(popularity[field] for field in (
            "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
        )),
    )
    item.update(
        provider="bilibili", platform="B站", displayName="B站热门旅行视频",
        sourceUrl=candidate["sourcePageUrl"], title=candidate["title"],
        creator=candidate["creator"],
        popularitySignals={
            **{field: popularity[field] for field in (
                "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
            )},
            "observedAt": candidate["observedAt"], "provider": candidate["provider"],
            "topic": candidate["topic"], "timeBucket": candidate["timeBucket"],
        },
        popularCandidateId=candidate["candidateId"], popularCatalogRef=catalog_ref,
        popularCatalogDigest=catalog["catalogDigest"],
        popularCatalogFileSha256=catalog_sha,
    )
    manifest_path = tmp_path / "popular.json"
    write_json(manifest_path, _manifest(
        [item], manifest_id="popular-catalog-bound",
        source_revision="sha256:" + "1" * 64,
    ))
    receipt, _receipt_path = acquire_professional_videos(
        manifest_path, handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root, output_root=output_root,
    )
    row = receipt["assets"][0]
    assert row["popularCatalogRef"] == catalog_ref
    assert row["contentSha256"] == candidate["manualFileSha256"]
    assert row["popularitySignals"] == {
        **popularity, "observedAt": candidate["observedAt"],
        "provider": candidate["provider"], "topic": candidate["topic"],
        "timeBucket": candidate["timeBucket"], "rankingEligible": True,
        "ineligibleReason": "",
    }


def test_slideshow_is_not_counted_as_sourced_or_premium_video(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_slideshow(manual_root / "slides.mp4")
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("slides", "slides.mp4", counts=(1_000, 20, 2, 1, 3))],
            manifest_id="slides",
        ),
    )
    with pytest.raises(ProfessionalVideoAcquisitionBlocked) as captured:
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual_root,
            output_root=tmp_path / "acquisition",
        )
    receipt = captured.value.receipt
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "blocked"
    assert row["mediaProbe"]["staticImageSequence"] is True
    assert row["mediaProbe"]["premiumPlayableEligible"] is False
    assert row["planVideoSpec"] is None


def test_unverified_acquired_video_is_retained_for_research(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "research-only.mp4", moving=True, seed=11)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [
                _item(
                    "research-only",
                    "research-only.mp4",
                    counts=(1_000, 20, 2, 1, 3),
                )
            ],
            manifest_id="commercial-filter",
        ),
    )
    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "research_allowed"
    assert row["failureCode"] == ""
    assert receipt["acceptedAssetCount"] == 1


def test_verified_video_emits_commercial_eligible_plan(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "commercial.mp4", moving=True, seed=17)
    item = _item(
        "commercial",
        "commercial.mp4",
        counts=(8_000, 420, 36, 24, 180),
    )
    item.update(
        rightsStatus="verified",
        license="Pexels License",
        authorizationProof="https://www.pexels.com/license/",
        rightsIssues=[],
        modelReleaseStatus="not_required",
    )
    manifest_path = tmp_path / "commercial.json"
    write_json(manifest_path, _manifest([item], manifest_id="commercial"))

    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )

    row = receipt["assets"][0]
    assert row["distributionDecision"] == "commercial_allowed"
    assert row["planVideoSpec"]["distributionDecision"] == "commercial_allowed"
    assert row["planVideoSpec"]["commercialAuthorizationStatus"] == "verified"


@pytest.mark.parametrize(
    ("path_name", "api_evidence"),
    [
        ("public_direct", ""),
        ("supported_api", "https://api.pexels.example.test/evidence/asset"),
    ],
)
def test_public_and_supported_api_paths_freeze_transport_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_name: str,
    api_evidence: str,
) -> None:
    source = tmp_path / "source.mp4"
    _write_video(source, moving=True, seed=6)

    def fake_fetch(url: str, destination: Path, *, supported_api: bool) -> str:
        assert url == "https://cdn.pexels.example.test/video.mp4"
        assert supported_api is (path_name == "supported_api")
        shutil.copyfile(source, destination)
        return ".mp4"

    monkeypatch.setattr(
        "content.source.professional_video_acquisition.fetch_public_video",
        fake_fetch,
    )
    item = _item(
        path_name,
        "",
        counts=(200, 10, 2, 1, 4),
        acquisition_path=path_name,
        asset_url="https://cdn.pexels.example.test/video.mp4",
        api_evidence=api_evidence,
    )
    receipt, _path, output_root = _acquire(
        tmp_path,
        [item],
        manifest_id=f"network-{path_name}",
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "research_allowed"
    assert (output_root / row["assetRef"]).is_file()


def test_receipt_and_plan_bindings_fail_closed_on_tamper(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "accepted.mp4", moving=True, seed=7)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("accepted", "accepted.mp4", counts=(20, 3, 1, 1, 1))],
            manifest_id="tamper",
        ),
    )
    output_root = tmp_path / "acquisition"
    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    receipt_ref = receipt_path.relative_to(output_root).as_posix()
    tampered = json.loads(json.dumps(receipt))
    tampered["acceptedAssetCount"] = 0
    write_json(receipt_path, tampered)
    with pytest.raises(ValueError, match="digest mismatch"):
        load_professional_video_acquisition_receipt(receipt_ref, root=output_root)


def test_auto_plan_selects_highest_comparable_professional_video(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "low.mp4", moving=True, seed=8)
    _write_video(manual_root / "high.mp4", moving=True, seed=9)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest([
            _item("low", "low.mp4", counts=(10, 1, 0, 0, 0)),
            _item("high", "high.mp4", counts=(10_000, 300, 30, 20, 50)),
        ], manifest_id="auto-plan"),
    )
    output_root = tmp_path / "acquisition"
    _receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    plan_dir = tmp_path / "plan"
    report: dict[str, object] = {"sourceUnavailable": []}
    write_video_lane(
        entity_id="西湖",
        plan_dir=plan_dir,
        force=True,
        report=report,
        updated=[],
        sourced_video_pool=[],
        acquisition_receipt_refs=[receipt_path.relative_to(output_root).as_posix()],
        acquisition_root=output_root,
    )
    plan = read_json(plan_dir / "video_source_plan.json")
    payload = plan["payload"]
    assert plan["acquisitionReceiptRefs"] == [
        receipt_path.relative_to(output_root).as_posix()
    ]
    assert "acquisitionReceiptRefs" not in payload
    assert payload["videos"][0]["professionalAssetId"] == "high"
    assert report["videoDiscovery"][0]["professionalAcquisitionCandidates"] == 2
    assert report["videoDiscovery"][0]["rankingEligibleCandidates"] == 2


def test_failed_acquisition_allows_new_attempt_without_rewriting_history(
    tmp_path: Path,
) -> None:
    """429/网络失败被冻结进 receipt 后，同一 manifest 必须能开新 attempt 而不篡改历史。"""
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("retry", "retry.mp4", counts=(1_000, 10, 2, 1, 2))],
            manifest_id="retry-attempts",
        ),
    )
    output_root = tmp_path / "acquisition"

    with pytest.raises(ProfessionalVideoAcquisitionBlocked) as captured:
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual_root,
            output_root=output_root,
        )
    first = captured.value.receipt
    first_path = captured.value.receipt_path
    assert first["assets"][0]["acquisitionStatus"] == "failed"
    assert first["assets"][0]["failureCode"] == "DATA.SOURCE.ACQUISITION_FAILED"
    first_bytes = first_path.read_bytes()

    _write_video(manual_root / "retry.mp4", moving=True, seed=41)
    second, second_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    assert second_path != first_path
    assert second_path.name.endswith("-attempt-002.json")
    assert second["manifestDigest"] == first["manifestDigest"]
    assert second["assets"][0]["acquisitionStatus"] == "acquired"
    assert second["assets"][0]["distributionDecision"] == "research_allowed"
    assert first_path.read_bytes() == first_bytes

    replay, replay_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    assert replay_path == second_path
    assert replay == second
    assert load_professional_video_acquisition_receipt(
        second_path.relative_to(output_root).as_posix(), root=output_root
    ) == second


def test_item_prevalidation_safety_frozen_and_popular_failures_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "accepted.mp4", moving=True, seed=51)
    items = [
        _item("accepted", "accepted.mp4", counts=(200, 10, 2, 1, 4)),
        _item("bad-prevalidation", "missing.mp4", counts=(1, 1, 1, 1, 1)),
        _item("bad-safety", "missing.mp4", counts=(1, 1, 1, 1, 1)),
        _item("bad-frozen", "missing.mp4", counts=(1, 1, 1, 1, 1)),
        _item("bad-popular", "missing.mp4", counts=(1, 1, 1, 1, 1)),
    ]
    items[1]["platform"] = "wrong platform"

    def safety(item, **_kwargs):
        if item["assetId"] == "bad-safety":
            raise ValueError("safety evidence drift")
        return {}

    def frozen(item, **_kwargs):
        if item["assetId"] == "bad-frozen":
            raise ValueError("frozen asset drift")
        return None

    def popular(item, **_kwargs):
        if item["assetId"] == "bad-popular":
            raise ValueError("popular binding drift")
        return None

    monkeypatch.setattr(professional_video_acquisition, "load_bound_safety_evidence", safety)
    monkeypatch.setattr(professional_video_acquisition, "resolve_frozen_video_asset", frozen)
    monkeypatch.setattr(professional_video_acquisition, "resolve_popular_candidate_binding", popular)
    manifest_path = tmp_path / "isolated-bindings.json"
    write_json(manifest_path, _manifest(items, manifest_id="isolated-bindings"))

    receipt, _path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )

    assert receipt["acceptedAssetCount"] == 1
    assert receipt["rejectedAssetCount"] == 4
    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert by_id["accepted"]["distributionDecision"] == "research_allowed"
    assert {
        asset_id: by_id[asset_id]["failureCode"]
        for asset_id in (
            "bad-prevalidation", "bad-safety", "bad-frozen", "bad-popular"
        )
    } == {
        "bad-prevalidation": "DATA.SOURCE.ITEM_PREVALIDATION_FAILED",
        "bad-safety": "DATA.SOURCE.SAFETY_EVIDENCE_INVALID",
        "bad-frozen": "DATA.SOURCE.FROZEN_ASSET_INVALID",
        "bad-popular": "DATA.SOURCE.POPULAR_BINDING_INVALID",
    }


def test_acquisition_and_plan_failures_do_not_cancel_successful_siblings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "accepted.mp4", moving=True, seed=52)
    _write_video(manual_root / "bad-plan.mp4", moving=True, seed=53)
    items = [
        _item("accepted", "accepted.mp4", counts=(200, 10, 2, 1, 4)),
        _item("missing", "missing.mp4", counts=(100, 5, 1, 1, 2)),
        _item("bad-plan", "bad-plan.mp4", counts=(150, 8, 2, 1, 3)),
    ]
    original = professional_video_acquisition.build_video_plan_spec

    def plan(row, *, receipt_ref):
        if row["assetId"] == "bad-plan":
            raise ValueError("plan projection rejected one candidate")
        return original(row, receipt_ref=receipt_ref)

    monkeypatch.setattr(professional_video_acquisition, "build_video_plan_spec", plan)
    manifest_path = tmp_path / "isolated-work.json"
    write_json(manifest_path, _manifest(items, manifest_id="isolated-work"))

    receipt, _path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )

    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert receipt["acceptedAssetCount"] == 1
    assert by_id["accepted"]["planVideoSpec"] is not None
    assert by_id["missing"]["failureCode"] == "DATA.SOURCE.ACQUISITION_FAILED"
    assert by_id["bad-plan"]["failureCode"] == "DATA.SOURCE.PLAN_SPEC_INVALID"
    assert by_id["bad-plan"]["distributionDecision"] == "blocked"


def test_zero_success_blocks_with_frozen_typed_receipt(tmp_path: Path) -> None:
    item = _item("invalid", "missing.mp4", counts=(1, 1, 1, 1, 1))
    item["platform"] = "wrong platform"
    manifest_path = tmp_path / "zero-success.json"
    write_json(manifest_path, _manifest([item], manifest_id="zero-success"))

    with pytest.raises(ProfessionalVideoAcquisitionBlocked) as captured:
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=tmp_path / "manual",
            output_root=tmp_path / "acquisition",
        )

    assert captured.value.code == "DATA.SOURCE.VIDEO_BATCH_NO_SUCCESS"
    assert captured.value.receipt["acceptedAssetCount"] == 0
    assert captured.value.receipt_path.is_file()
    assert captured.value.receipt["assets"][0]["failureCode"] == (
        "DATA.SOURCE.ITEM_PREVALIDATION_FAILED"
    )


def test_cas_collision_is_a_global_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    item = _item("collision", "collision.mp4", counts=(1, 1, 1, 1, 1))
    manifest_path = tmp_path / "cas-collision.json"
    write_json(manifest_path, _manifest([item], manifest_id="cas-collision"))

    def collide(*_args, **_kwargs):
        raise ProfessionalVideoCasCollision("professional video CAS collision: exact")

    monkeypatch.setattr(professional_video_acquisition, "acquire_video_item", collide)
    with pytest.raises(ProfessionalVideoCasCollision):
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=tmp_path / "manual",
            output_root=tmp_path / "acquisition",
        )
    assert not list((tmp_path / "acquisition" / "receipts").glob("*.json"))


def test_cas_store_collision_is_typed(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"exact-video-content")
    digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "cas" / "sha256" / digest[:2] / f"{digest}.mp4"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"corrupt-cas-content")

    with pytest.raises(ProfessionalVideoCasCollision):
        put_video_cas(source, ".mp4", output_root=tmp_path)
