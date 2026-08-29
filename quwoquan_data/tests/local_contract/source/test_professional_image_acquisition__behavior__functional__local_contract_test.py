from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from content.source import professional_image_acquisition as acquisition
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from core.io import write_json
from PIL import Image


@pytest.fixture(autouse=True)
def _governed_handoff_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        acquisition,
        "guard_acquisition_source_identity",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        acquisition,
        "load_bound_safety_evidence",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        acquisition,
        "validate_image_safety_payload",
        lambda *_args, **_kwargs: None,
    )


def _image_bytes(seed: int) -> bytes:
    body = bytes((index * 31 + seed) % 256 for index in range(800 * 640 * 3))
    image = Image.frombytes("RGB", (800, 640), body)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _small_image_bytes(seed: int) -> bytes:
    body = bytes((index * 31 + seed) % 256 for index in range(128 * 128 * 3))
    image = Image.frombytes("RGB", (128, 128), body)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _item(
    asset_id: str,
    source_id: str,
    manual_file: str,
    rights_status: str,
    *,
    acquisition_path: str = "manual_file",
    observed_entity_id: str = "九寨沟",
    anonymous_asset_access: bool | None = None,
    login_required: bool = False,
    watermark_status: str = "absent",
) -> dict:
    if anonymous_asset_access is None:
        anonymous_asset_access = acquisition_path != "manual_file"
    item = {
        "assetId": asset_id,
        "entityId": "九寨沟",
        "observedEntityId": observed_entity_id,
        "entityAliases": ["九寨沟风景名胜区", "Jiuzhaigou"],
        "sourceId": source_id,
        "displayName": "九寨沟专业摄影候选",
        "acquisitionPath": acquisition_path,
        "sourceUrl": f"https://example.invalid/{source_id}/{asset_id}",
        "assetUrl": "",
        "manualFile": manual_file,
        "apiEvidence": "",
        "accessEvidence": {
            "anonymousAssetAccess": anonymous_asset_access,
            "loginRequired": login_required,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "creator": "摄影师甲",
        "capturedAt": "2026-08-05T00:00:00Z",
        "rightsStatus": rights_status,
        "license": "unknown",
        "licenseSnapshot": "source license captured before acquisition",
        "usageScope": "internal_reference",
        "modelReleaseStatus": "not_required",
        "termsUrl": "",
        "authorizationProof": "",
        "rightsIssues": ["distribution authorization has not been verified"],
        "caption": "九寨沟五花海清晨摄影作品",
        "relevance": "画面主体为九寨沟五花海",
        "safetyReview": {
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": watermark_status,
            "reviewedAt": "2026-08-05T00:05:00Z",
            "reviewer": "local-contract-reviewer",
            "evidenceRef": f"evidence/{asset_id}.json",
            "safetyEvidenceFileSha256": "sha256:" + "f" * 64,
        },
    }
    item["sourceAttribution"] = (
        {
            "isOriginal": False,
            "originalCreatorId": None,
            "originalCreatorName": "摄影师甲",
            "originalCreatorProfileUrl": None,
            "platform": "Pinterest" if source_id == "pinterest" else "图虫",
            "sourcePostUrl": item["sourceUrl"],
            "originalAssetUrl": item["sourceUrl"],
            "attributionText": f"摄影师甲 / unknown / {item['sourceUrl']}",
            "rightsBasis": "unknown",
            "commercialAuthorizationStatus": "unverified",
            "publicationAdmission": "research_release",
            "authorizationProofUrl": None,
            "termsUrl": None,
            "riskAcceptanceId": None,
            "watermarkStatus": "absent",
            "audioRightsStatus": "no_audio",
            "modelReleaseStatus": "not_required",
            "propertyReleaseStatus": "not_required",
            "collectedAt": "2026-08-05T00:00:00Z",
            "takedownPolicy": "quwoquan_standard_notice_and_takedown",
            "derivedModifications": [],
        }
        if watermark_status == "absent"
        else None
    )
    return item


def _manifest(items: list[dict], tmp_path: Path) -> dict:
    acquisition_root = tmp_path / "acquisition"
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["九寨沟"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="广角",
        popularity="热门",
        output_root=acquisition_root / "discovery-plans",
    )
    candidates = {}
    for candidate in plan["candidates"]:
        candidates.setdefault(candidate["provider"], candidate)
    for item in items:
        candidate = candidates[item["sourceId"]]
        item["discoveryCandidateId"] = candidate["candidateId"]
        item["discoveryUrl"] = candidate["discoveryUrl"]
        attribution = item.get("sourceAttribution")
        if isinstance(attribution, dict):
            attribution["originalAssetUrl"] = item.get("assetUrl") or item["sourceUrl"]
    return {
        "schema": "quwoquan_data.professional_image_acquisition_manifest",
        "manifestId": "pinterest-tuchong-m3",
        "sourceRevision": "dev1.0@fixture",
        "sourceDigest": _digest("source"),
        "entityCatalogDigest": _digest("entities"),
        "discoveryPlanRef": plan_path.relative_to(acquisition_root).as_posix(),
        "discoveryPlanDigest": plan["planDigest"],
        "items": items,
    }


def test_manual_pinterest_tuchong_files_are_acquired_without_faking_rights(
    tmp_path: Path,
) -> None:
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "pinterest.jpg").write_bytes(_image_bytes(7))
    (manual / "tuchong.jpg").write_bytes(_image_bytes(11))
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [
                _item("pin-1", "pinterest", "pinterest.jpg", "unverified"),
                _item("tuchong-1", "tuchong", "tuchong.jpg", "unknown"),
                _item("pin-duplicate", "pinterest", "pinterest.jpg", "unverified"),
            ],
            tmp_path,
        ),
    )

    acquisition_root = tmp_path / "acquisition"
    receipt, path = acquisition.acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual,
        output_root=acquisition_root,
    )

    assert path.is_file()
    assert receipt["plannedAssetCount"] == 3
    assert receipt["downloadedAssetCount"] == 3
    assert receipt["acceptedAssetCount"] == 2
    assert receipt["rejectedAssetCount"] == 1
    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert by_id["pin-1"]["distributionDecision"] == "research_allowed"
    assert by_id["pin-1"]["authorizationRequired"] is True
    assert by_id["pin-1"]["withdrawalRequired"] is True
    assert by_id["tuchong-1"]["rightsStatus"] == "unknown"
    assert by_id["pin-duplicate"]["distributionDecision"] == "blocked"
    assert by_id["pin-duplicate"]["failureCode"] == "DATA.SOURCE.DUPLICATE_ASSET"
    assert by_id["pin-duplicate"]["failure"].startswith("DATA.SOURCE.DUPLICATE_ASSET")
    assert by_id["pin-duplicate"]["planImageSpec"] is None
    assert by_id["pin-1"]["planImageSpec"]["url"].startswith("file://")
    assert (
        by_id["pin-1"]["planImageSpec"]["collectionPageUrl"]
        == by_id["pin-1"]["planImageSpec"]["sourceUrl"]
    )
    assert by_id["pin-1"]["planImageSpec"]["rightsAuditStatus"] == "unverified"
    for field in (
        "licenseSnapshot",
        "usageScope",
        "modelReleaseStatus",
        "sourceAttribution",
    ):
        assert by_id["pin-1"]["planImageSpec"][field] == by_id["pin-1"][field]
    assert by_id["pin-1"]["observedEntityId"] == "九寨沟"
    assert by_id["pin-1"]["entityAliases"] == ["九寨沟风景名胜区", "Jiuzhaigou"]
    assert by_id["pin-1"]["safetyReview"]["watermarkStatus"] == "absent"
    assert {row["provider"] for row in receipt["providerAssetCounts"]} == {
        "pinterest",
        "tuchong",
    }

    repeated, repeated_path = acquisition.acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual,
        output_root=acquisition_root,
    )
    assert repeated_path == path
    assert repeated == receipt

    receipt_ref = path.relative_to(acquisition_root).as_posix()
    specs = acquisition.acquired_image_specs_for_entity(
        [receipt_ref],
        entity_id="九寨沟",
        root=acquisition_root,
    )
    assert len(specs) == 2
    assert {spec["sourceId"] for spec in specs} == {"pinterest", "tuchong"}
    assert all(spec["acquisitionReceiptRef"] == receipt_ref for spec in specs)
    assert all(spec["collectionPageUrl"] == spec["sourceUrl"] for spec in specs)
    assert {spec["professionalAssetId"] for spec in specs} == {
        "pin-1",
        "tuchong-1",
    }
    assert all(
        spec["professionalContentSha256"] == spec["contentSha256"]
        for spec in specs
    )
    assert all(spec["rightsIssues"] for spec in specs)


def test_public_and_supported_api_paths_use_anonymous_asset_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        "https://cdn.example.invalid/pin.jpg": _image_bytes(17),
        "https://cdn.example.invalid/tuchong.jpg": _image_bytes(19),
    }
    observed: list[str] = []

    def fake_network(url: str, *, supported_api: bool) -> dict:
        observed.append(f"{url}:{supported_api}")
        return {"bytes": payloads[url], "ext": ".jpg", "contentType": "image/jpeg"}

    monkeypatch.setattr(acquisition, "_network_payload", fake_network)
    pin = _item(
        "pin-api",
        "pinterest",
        "",
        "unverified",
        acquisition_path="supported_api",
    )
    pin.update(
        assetUrl="https://cdn.example.invalid/pin.jpg",
        apiEvidence="https://api.example.invalid/responses/pinterest-123",
    )
    tuchong = _item(
        "tuchong-public",
        "tuchong",
        "",
        "unverified",
        acquisition_path="public_direct",
    )
    tuchong.update(
        assetUrl="https://cdn.example.invalid/tuchong.jpg",
    )
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, _manifest([pin, tuchong], tmp_path))

    receipt, _ = acquisition.acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        output_root=tmp_path / "acquisition",
    )

    assert observed == [f"{pin['assetUrl']}:True", f"{tuchong['assetUrl']}:False"]
    assert receipt["acceptedAssetCount"] == 2


def test_safety_entity_and_access_failures_block_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def public_item(asset_id: str, **kwargs: object) -> dict:
        item = _item(
            asset_id,
            "tuchong",
            "",
            "unverified",
            acquisition_path="public_direct",
            **kwargs,
        )
        item["assetUrl"] = f"https://cdn.example.invalid/{asset_id}.jpg"
        return item

    passed = public_item("passed")
    watermark = public_item("watermark", watermark_status="present")
    mismatch = public_item("mismatch", observed_entity_id="黄山")
    evidence_mismatch = public_item("evidence-mismatch")
    evidence_mismatch["caption"] = "山水摄影作品"
    evidence_mismatch["relevance"] = "画面为群山和湖泊"
    access_blocked = public_item("access-blocked", login_required=True)
    anonymous_blocked = public_item(
        "anonymous-blocked",
        anonymous_asset_access=False,
    )

    def fake_network(url: str, *, supported_api: bool) -> dict:
        assert supported_api is False
        observed.append(url)
        return {
            "bytes": _image_bytes(23),
            "ext": ".jpg",
            "contentType": "image/jpeg",
        }

    monkeypatch.setattr(acquisition, "_network_payload", fake_network)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [
                passed,
                watermark,
                mismatch,
                evidence_mismatch,
                access_blocked,
                anonymous_blocked,
            ],
            tmp_path,
        ),
    )

    receipt, _ = acquisition.acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        output_root=tmp_path / "acquisition",
    )

    assert observed == [passed["assetUrl"]]
    assert receipt["downloadedAssetCount"] == 1
    assert receipt["acceptedAssetCount"] == 1
    assert receipt["rejectedAssetCount"] == 5
    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert by_id["passed"]["rightsStatus"] == "unverified"
    assert by_id["passed"]["distributionDecision"] == "research_allowed"
    assert by_id["passed"]["planImageSpec"] is not None
    assert by_id["watermark"]["failureCode"] == "DATA.SOURCE.WATERMARK_BLOCKED"
    # An observed entity that contradicts the frozen discovery candidate is caught
    # at binding, before any safety evidence is read: the plan is the earlier
    # authority on which entity this asset was ever allowed to be about.
    assert (
        by_id["mismatch"]["failureCode"] == "DATA.SOURCE.DISCOVERY_BINDING_FAILED"
    )
    assert by_id["evidence-mismatch"]["failureCode"] == "DATA.SOURCE.ENTITY_MISMATCH"
    assert (
        by_id["access-blocked"]["failureCode"] == "DATA.SOURCE.ACCESS_CONTROL_BLOCKED"
    )
    assert (
        by_id["anonymous-blocked"]["failureCode"]
        == "DATA.SOURCE.ANONYMOUS_ACCESS_REQUIRED"
    )
    assert all(
        by_id[asset_id]["acquisitionStatus"] == "blocked"
        and by_id[asset_id]["planImageSpec"] is None
        for asset_id in (
            "watermark",
            "mismatch",
            "evidence-mismatch",
            "access-blocked",
            "anonymous-blocked",
        )
    )


def test_manual_file_cannot_escape_operator_root(tmp_path: Path) -> None:
    manual = tmp_path / "manual"
    manual.mkdir()
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("pin-escape", "pinterest", "../outside.jpg", "unknown")],
            tmp_path,
        ),
    )

    with pytest.raises(ValueError, match="escapes"):
        acquisition.acquire_professional_images(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual,
            output_root=tmp_path / "acquisition",
        )


def test_downloaded_thumbnail_is_retained_but_not_accepted(tmp_path: Path) -> None:
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "thumbnail.jpg").write_bytes(_small_image_bytes(31))
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("pin-thumbnail", "pinterest", "thumbnail.jpg", "unverified")],
            tmp_path,
        ),
    )
    root = tmp_path / "acquisition"
    # A batch where nothing reached admission is not a success, but the evidence of
    # why survives: the receipt is written before the typed failure is raised, and
    # the failure names it, so the retained thumbnail stays auditable.
    with pytest.raises(acquisition.ProfessionalImageAcquisitionError) as blocked:
        acquisition.acquire_professional_images(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual,
            output_root=root,
        )

    assert blocked.value.code == "DATA.SOURCE.ACQUISITION_NO_SUCCESS"
    receipt = acquisition.load_professional_image_acquisition_receipt(
        blocked.value.receipt_ref,
        root=root,
    )
    row = receipt["assets"][0]
    assert receipt["downloadedAssetCount"] == 1
    assert receipt["acceptedAssetCount"] == 0
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "blocked"
    assert row["failureCode"] == "DATA.SOURCE.IMAGE_QUALITY_BLOCKED"
    assert row["planImageSpec"] is None


def test_acquisition_rejects_discovery_candidate_drift_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item(
        "tuchong-drift",
        "tuchong",
        "",
        "unverified",
        acquisition_path="public_direct",
    )
    item["assetUrl"] = "https://cdn.example.invalid/tuchong-drift.jpg"
    manifest = _manifest([item], tmp_path)
    manifest["items"][0]["discoveryUrl"] = "https://example.invalid/drift"
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    called = False

    def fake_network(_url: str, *, supported_api: bool) -> dict:
        nonlocal called
        assert supported_api is False
        called = True
        return {"bytes": _image_bytes(29), "ext": ".jpg", "contentType": "image/jpeg"}

    monkeypatch.setattr(acquisition, "_network_payload", fake_network)
    with pytest.raises(ValueError, match="discovery URL mismatch"):
        acquisition.acquire_professional_images(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            output_root=tmp_path / "acquisition",
        )
    assert called is False


def _single_manual_receipt(tmp_path: Path) -> tuple[Path, dict, Path]:
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "accepted.jpg").write_bytes(_image_bytes(37))
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("accepted", "pinterest", "accepted.jpg", "unverified")],
            tmp_path,
        ),
    )
    root = tmp_path / "acquisition"
    receipt, path = acquisition.acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual,
        output_root=root,
    )
    return root, receipt, path


def _rewrite_self_digested(path: Path, receipt: dict) -> None:
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    receipt["receiptDigest"] = acquisition._digest(stable)
    write_json(path, receipt)


def test_receipt_schema_closes_provider_and_asset_objects(tmp_path: Path) -> None:
    root, receipt, path = _single_manual_receipt(tmp_path)
    receipt["providerAssetCounts"][0]["undeclaredCount"] = 1
    receipt["assets"][0]["undeclaredAdmission"] = True
    _rewrite_self_digested(path, receipt)

    with pytest.raises(ValueError, match="未知字段.*undeclared"):
        acquisition.load_professional_image_acquisition_receipt(
            path.relative_to(root).as_posix(),
            root=root,
        )


@pytest.mark.parametrize(
    "tamper, expected",
    [
        (
            lambda row: (
                row.__setitem__("caption", "generic landscape"),
                row.__setitem__("relevance", "mountains and water"),
                row["planImageSpec"].__setitem__("caption", "generic landscape"),
                row["planImageSpec"].__setitem__("relevance", "mountains and water"),
            ),
            "fails admission.*DATA.SOURCE.ENTITY_MISMATCH",
        ),
        (
            lambda row: row["planImageSpec"].__setitem__(
                "contentSha256",
                "sha256:" + "f" * 64,
            ),
            "planImageSpec field drift",
        ),
        (
            lambda row: row["planImageSpec"].__setitem__(
                "usageScope",
                "app_publish",
            ),
            "planImageSpec field drift",
        ),
        (
            lambda row: (
                row.__setitem__("width", int(row["width"]) + 1),
                row["planImageSpec"].__setitem__(
                    "width",
                    int(row["planImageSpec"]["width"]) + 1,
                ),
            ),
            "CAS quality drift",
        ),
    ],
)
def test_self_digested_receipt_cannot_bypass_accepted_asset_revalidation(
    tmp_path: Path,
    tamper,
    expected: str,
) -> None:
    root, receipt, path = _single_manual_receipt(tmp_path)
    tamper(receipt["assets"][0])
    _rewrite_self_digested(path, receipt)

    with pytest.raises(ValueError, match=expected):
        acquisition.load_professional_image_acquisition_receipt(
            path.relative_to(root).as_posix(),
            root=root,
        )
