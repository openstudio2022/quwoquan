# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t4
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from content.source import professional_image_acquisition as image_acquisition
from content.source.atomic_source_io import materialize_source_candidate
from core.io import read_json

EXECUTION_ID = "20260905--travel-article-image-mime--test--pilot-001"
TARGET_REF = "entities/地点/景区/西湖"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (800, 640), color=(32, 96, 160)).save(
        output,
        format="JPEG",
        quality=92,
    )
    return output.getvalue()


def _source_attribution() -> dict[str, object]:
    source_url = "https://commons.wikimedia.org/wiki/File:West_Lake.jpg"
    asset_url = "https://upload.wikimedia.org/wikipedia/commons/west-lake.jpg"
    terms_url = "https://creativecommons.org/licenses/by/4.0/"
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "Commons Creator",
        "originalCreatorProfileUrl": None,
        "platform": "Wikimedia Commons",
        "sourcePostUrl": source_url,
        "originalAssetUrl": asset_url,
        "attributionText": "West Lake — Commons Creator — CC BY 4.0",
        "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "authorizationProofUrl": source_url,
        "termsUrl": terms_url,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-09-05T00:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": [],
    }


def _manifest() -> dict[str, object]:
    source_url = "https://commons.wikimedia.org/wiki/File:West_Lake.jpg"
    return {
        "schema": "quwoquan_data.professional_image_acquisition_manifest",
        "manifestId": "professional-image-mime-contract",
        "sourceRevision": "fresh-test-revision",
        "sourceDigest": "sha256:" + "a" * 64,
        "entityCatalogDigest": "sha256:" + "b" * 64,
        "items": [
            {
                "assetId": "commons-west-lake-1",
                "entityId": "西湖",
                "observedEntityId": "西湖",
                "entityAliases": ["西湖", "杭州西湖"],
                "sourceId": "wikimedia_commons",
                "displayName": "Wikimedia Commons",
                "acquisitionPath": "supported_api",
                "sourceUrl": source_url,
                "assetUrl": "https://upload.wikimedia.org/wikipedia/commons/west-lake.jpg",
                "manualFile": "",
                "apiEvidence": "commons-api-pageid-1",
                "accessEvidence": {
                    "anonymousAssetAccess": True,
                    "loginRequired": False,
                    "captchaRequired": False,
                    "paywallRequired": False,
                    "drmProtected": False,
                    "accessControlBypass": False,
                },
                "creator": "Commons Creator",
                "capturedAt": "2026-09-05T00:00:00Z",
                "rightsStatus": "verified",
                "license": "CC BY 4.0",
                "licenseSnapshot": "CC BY 4.0 frozen at source capture",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": source_url,
                "rightsIssues": [],
                "caption": "西湖苏堤春景与湖岸实景",
                "relevance": "西湖苏堤春景直接呈现目标景区湖岸风貌",
                "safetyReview": {
                    "status": "passed",
                    "entityMatch": "matched",
                    "privacyRisk": "none",
                    "minorRisk": "none",
                    "maliciousMediaRisk": "none",
                    "watermarkStatus": "absent",
                    "reviewedAt": "2026-09-05T00:00:00Z",
                    "reviewer": "contract-reviewer",
                    "evidenceRef": "evidence/commons-west-lake-1.json",
                    "safetyEvidenceFileSha256": "sha256:" + "c" * 64,
                },
                "sourceAttribution": _source_attribution(),
            }
        ],
    }


def _acquire_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, bytes, dict[str, Any]]:
    body = _image_bytes()
    acquisition_root = tmp_path / "output/data/local/workspace/source-acquisition/image"
    manifest_path = _write(tmp_path / "manifest.json", _manifest())
    monkeypatch.setattr(
        image_acquisition,
        "_network_payload",
        lambda *_args, **_kwargs: {
            "bytes": body,
            "ext": ".jpg",
            "contentType": "image/jpeg",
            "requestedUrl": "https://upload.wikimedia.org/wikipedia/commons/west-lake.jpg",
            "normalizedFromUrl": "",
        },
    )
    monkeypatch.setattr(
        image_acquisition,
        "load_bound_safety_evidence",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        image_acquisition,
        "validate_image_safety_payload",
        lambda *_args, **_kwargs: None,
    )
    receipt, receipt_path = image_acquisition.acquire_professional_images(
        manifest_path,
        output_root=acquisition_root,
    )
    return acquisition_root, receipt_path, body, receipt


def _candidate(execution: Path) -> Path:
    planned = {
        "sourceId": "wikimedia_commons",
        "title": "西湖 Commons 专业图片",
        "sourceClass": "open_license_media",
        "sourceUseMode": "licensed_adaptation",
        "purpose": "西湖文章图片素材",
        "rightsClue": "CC BY 4.0",
        "url": "https://commons.wikimedia.org/wiki/File:West_Lake.jpg",
    }
    plan = {
        "schema": "quwoquan_data.source_plan",
        "executionId": EXECUTION_ID,
        "targetRef": TARGET_REF,
        "carrier": "article",
        "candidates": [planned],
    }
    plan_ref = "sources/plans/" + hashlib.sha256(TARGET_REF.encode()).hexdigest() + ".json"
    plan_path = _write(execution / plan_ref, plan)
    return _write(
        execution.parent.parent.parent.parent / "candidate-image.json",
        {
            "schema": "quwoquan_data.source_candidate",
            "sourcePlanRef": plan_ref,
            "sourcePlanDigest": "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            **planned,
            "fetchedAt": "2026-09-05T00:00:00Z",
        },
    )


def _rewrite_receipt(receipt_path: Path, receipt: dict[str, Any]) -> None:
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    receipt["receiptDigest"] = image_acquisition._digest(stable)
    _write(receipt_path, receipt)


def test_accepted_image_mime_propagates_into_atomic_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, receipt_path, body, receipt = _acquire_receipt(
        tmp_path,
        monkeypatch,
    )
    row = receipt["assets"][0]
    assert row["mimeType"] == "image/jpeg"

    output = tmp_path / "output"
    execution = output / "data/tasks" / EXECUTION_ID
    from content.source import atomic_source_io

    monkeypatch.setattr(atomic_source_io, "execution_root", lambda _execution_id: execution)
    monkeypatch.setattr(
        atomic_source_io,
        "execution_source_unit_dir",
        lambda _execution_id, unit_id: execution / "sources" / unit_id,
    )
    meta, unit = materialize_source_candidate(
        _candidate(execution),
        execution_id=EXECUTION_ID,
        target_ref=TARGET_REF,
        receipt_path=receipt_path,
        receipt_asset_id=str(row["assetId"]),
        acquisition_root=acquisition_root,
    )

    index = read_json(unit / "assets/index.json")
    materialized = index["assets"][0]
    assert meta["acquisition"]["mimeType"] == "image/jpeg"
    assert materialized["mimeType"] == "image/jpeg"
    assert Path(materialized["fileName"]).suffix == ".jpg"
    assert (unit / "assets" / materialized["fileName"]).read_bytes() == body


def test_non_acquired_image_row_records_explicit_empty_mime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root = tmp_path / "output/data/local/workspace/source-acquisition/image"
    manifest = _manifest()
    item = manifest["items"][0]
    assert isinstance(item, dict)
    safety_review = item["safetyReview"]
    assert isinstance(safety_review, dict)
    safety_review["status"] = "blocked"
    manifest_path = _write(tmp_path / "blocked-manifest.json", manifest)
    monkeypatch.setattr(
        image_acquisition,
        "load_bound_safety_evidence",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(image_acquisition.ProfessionalImageAcquisitionError) as caught:
        image_acquisition.acquire_professional_images(
            manifest_path,
            output_root=acquisition_root,
        )

    receipt_ref = caught.value.receipt_ref
    receipt = image_acquisition.load_professional_image_acquisition_receipt(
        receipt_ref,
        root=acquisition_root,
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "blocked"
    assert row["distributionDecision"] == "blocked"
    assert row["mimeType"] == ""


def test_receipt_reload_rejects_tampered_image_mime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, receipt_path, _body, receipt = _acquire_receipt(
        tmp_path,
        monkeypatch,
    )
    receipt["assets"][0]["mimeType"] = "image/png"
    _rewrite_receipt(receipt_path, receipt)

    with pytest.raises(ValueError, match="MIME"):
        image_acquisition.load_professional_image_acquisition_receipt(
            receipt_path.relative_to(acquisition_root).as_posix(),
            root=acquisition_root,
        )


def test_receipt_reload_rejects_extension_and_body_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, receipt_path, _body, receipt = _acquire_receipt(
        tmp_path,
        monkeypatch,
    )
    row = receipt["assets"][0]
    original = acquisition_root / row["assetRef"]
    extension_drift = original.with_suffix(".png")
    original.replace(extension_drift)
    row["assetRef"] = extension_drift.relative_to(acquisition_root).as_posix()
    row["planImageSpec"]["url"] = extension_drift.resolve().as_uri()
    _rewrite_receipt(receipt_path, receipt)

    with pytest.raises(ValueError, match="extension"):
        image_acquisition.load_professional_image_acquisition_receipt(
            receipt_path.relative_to(acquisition_root).as_posix(),
            root=acquisition_root,
        )

    extension_drift.replace(original)
    row["assetRef"] = original.relative_to(acquisition_root).as_posix()
    row["planImageSpec"]["url"] = original.resolve().as_uri()
    original.write_bytes(original.read_bytes() + b"tampered")
    _rewrite_receipt(receipt_path, receipt)

    with pytest.raises(ValueError, match="digest"):
        image_acquisition.load_professional_image_acquisition_receipt(
            receipt_path.relative_to(acquisition_root).as_posix(),
            root=acquisition_root,
        )
