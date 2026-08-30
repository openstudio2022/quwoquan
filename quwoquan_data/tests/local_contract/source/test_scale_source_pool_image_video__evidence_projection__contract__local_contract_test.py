from __future__ import annotations

import json
from pathlib import Path

import pytest

import content.source.research.scale_source_pool_image_materialize as image_materialize
import content.source.research.scale_source_pool_image_video as media_projection
from content.source.media_source_admission import MediaSourceAdmissionCommandWriter
from content.source.research.scale_source_pool_image_materialize import (
    _materialize_frozen_image_source_unit,
)
from content.source.research.scale_source_pool_image_video import (
    project_scale_source_pool_image_video,
)
from quwoquan_data.tests.local_contract.source.test_media_source_admission__portable_bridge__contract__local_contract_test import (
    ENTITY_CATALOG_REF,
    IDENTITY,
    _admit,
    _portable_evidence,
    _write_json,
)


@pytest.fixture(autouse=True)
def _entity_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_projection,
        "load_entity_bindings",
        lambda _path: (
            ENTITY_CATALOG_REF,
            IDENTITY["entityCatalogDigest"],
            {
                "entity-1": {
                    "entityId": "entity-1",
                    "entityType": "地点/景区",
                    "entityAliases": ["entity-1"],
                }
            },
        ),
    )


def _project(
    root: Path,
    *,
    image_refs: list[str] | None,
    video_refs: list[str] | None,
) -> dict[str, object]:
    return project_scale_source_pool_image_video(
        evidence_root=root,
        target_scale="WORKLOAD",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        entity_catalog_ref=ENTITY_CATALOG_REF,
        image_source_admission_refs=image_refs,
        video_source_admission_refs=video_refs,
    )


def _admit_materializable_image(root: Path) -> tuple[dict[str, object], str]:
    asset_id, evidence_refs = _portable_evidence(root, kind="image")
    original_acquisition = root / evidence_refs["acquisition"]
    acquisition = json.loads(original_acquisition.read_text(encoding="utf-8"))
    asset = acquisition["assets"][0]
    asset.update(
        {
            "displayName": "Frozen professional image",
            "license": "unknown",
            "licenseSnapshot": "captured",
            "usageScope": "internal_reference",
            "modelReleaseStatus": "not_required",
            "termsUrl": "https://source.example/image/terms",
            "authorizationProof": "",
            "rightsIssues": ["authorization pending"],
            "caption": "Landscape",
            "relevance": "entity landscape",
            "planImageSpec": {
                "url": f"file://{root / asset['assetRef']}",
                "sourceUrl": asset["sourceUrl"],
                "collectionPageUrl": asset["sourceUrl"],
                "originalAssetUrl": asset["sourceAttribution"]["originalAssetUrl"],
                "platform": asset["platform"],
                "sourceId": asset["provider"],
                "creator": asset["creator"],
                "credit": asset["creator"],
                "capturedAt": asset["capturedAt"],
                "contentSha256": asset["contentSha256"],
                "sourceAttribution": asset["sourceAttribution"],
            },
        }
    )
    acquisition.update(
        {
            "schema": "quwoquan_data.professional_image_acquisition_receipt",
            "manifestId": "image-manifest",
        }
    )
    acquisition_ref = (
        "local/workspace/source-acquisition/provider/preparations/"
        "professional-image/receipts/image.json"
    )
    _write_json(root, acquisition_ref, acquisition)
    evidence_refs["acquisition"] = acquisition_ref
    receipt, receipt_ref = MediaSourceAdmissionCommandWriter(root).write(
        asset_kind="image",
        asset_id=asset_id,
        object_ref=f"posts/image/{asset_id}",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        evidence_refs=evidence_refs,
        recorded_at="2026-08-20T00:01:00Z",
    )
    return receipt, receipt_ref


def test_projection_is_deterministic_and_consumes_only_accepted_admissions(
    tmp_path: Path,
) -> None:
    image_receipt, image_ref, _ = _admit(tmp_path, kind="image")
    video_receipt, video_ref, _ = _admit(tmp_path, kind="video")

    first = _project(tmp_path, image_refs=[image_ref], video_refs=[video_ref])
    second = _project(tmp_path, image_refs=[image_ref], video_refs=[video_ref])

    assert first == second
    assert [row["carrier"] for row in first["candidates"]] == ["image", "video"]
    by_carrier = {row["carrier"]: row for row in first["candidates"]}
    assert by_carrier["image"]["sourceAdmissionDigest"] == image_receipt["receiptDigest"]
    assert by_carrier["video"]["sourceAdmissionDigest"] == video_receipt["receiptDigest"]
    assert by_carrier["video"]["videoReadiness"]["premiumEligible"] is True
    assert {row["kind"] for row in first["inputDocuments"]} == {
        "image_source_admission",
        "video_source_admission",
    }


def test_projection_accepts_image_only_without_video_review_or_acquisition_args(
    tmp_path: Path,
) -> None:
    _receipt, image_ref, _ = _admit(tmp_path, kind="image")

    projected = _project(tmp_path, image_refs=[image_ref], video_refs=None)

    assert [row["carrier"] for row in projected["candidates"]] == ["image"]
    assert set(projected["candidates"][0]).isdisjoint(
        {"sourceUnitRef", "acquisitionRef", "rightsRef", "qualityRef"}
    )


def test_frozen_image_materializes_from_source_admission_without_publish_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, receipt_ref = _admit_materializable_image(tmp_path)
    projected = _project(tmp_path, image_refs=[receipt_ref], video_refs=None)
    row = dict(projected["candidates"][0])
    row["sourcePoolEvidenceRoot"] = tmp_path
    captured: dict[str, object] = {}

    monkeypatch.setattr(image_materialize, "assert_valid", lambda *_args, **_kwargs: None)

    from content.source.research import scale_source_pool_runtime as runtime

    monkeypatch.setattr(runtime, "resolve_entity_object_dir", lambda *_args, **_kwargs: tmp_path)

    def write_source_unit(_object_dir: Path, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"sourceUnitId": kwargs["frozen_source_unit_id"], "assetCount": 1}

    monkeypatch.setattr(runtime, "write_source_unit", write_source_unit)

    result = _materialize_frozen_image_source_unit(
        execution_id="20260820--travel-image--china--scale-001",
        entity_id="entity-1",
        entity_type="地点/景区",
        row=row,
    )

    assert result["assetCount"] == 1
    assert row["sourceAdmissionDigest"] == receipt["receiptDigest"]
    assert captured["quality"]["reasons"] == [
        "frozen_scale_source_pool",
        "media_source_admission",
    ]
    image = captured["images"][0]
    assert image["professionalAssetId"] == "image-asset-1"
    assert image["sourcePath"] == tmp_path / receipt["assetSnapshot"]["assetRef"]
    assert "independentAssetReview" not in row
