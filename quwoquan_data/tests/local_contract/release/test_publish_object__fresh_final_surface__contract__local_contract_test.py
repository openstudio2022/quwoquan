# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from content.release.canonical.final_surface_projection import (
    project_publish_final_surface,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.schema import assert_valid

EXECUTION_ID = "20260906--travel-image-final-surface--test-region-a--pilot-001"
TARGET_REF = "posts/image/建筑/西门入口/1"
SOURCE_REF = "sources/commons/source.md"
ASSET_REF = "sources/commons/assets/cover.jpg"
CREATOR_PROFILE = "qwq_creator_landscape_photographer_001"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / EXECUTION_ID
    obj = root / TARGET_REF
    source = root / SOURCE_REF
    source.parent.mkdir(parents=True)
    source.write_text("# Commons source\n", encoding="utf-8")
    asset = root / ASSET_REF
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"reviewed-image-bytes")
    _write_json(
        root / "sources/commons/meta.json",
        {
            "sourceId": "commons",
            "canonicalUrl": "https://commons.example.test/file",
            "sourceUseMode": "licensed_adaptation",
            "sourceClass": "open_license_media",
            "fetchedAt": "2026-09-06T00:00:00Z",
            "rightsClue": "作者 Fixture Photographer，CC BY 4.0。",
        },
    )
    _write_json(
        root / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "fileName": "cover.jpg",
                    "sourceAssetId": "cover",
                    "assetRole": "image",
                    "mimeType": "image/jpeg",
                    "sourceUrl": "https://commons.example.test/file",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0",
                    "authorizationProof": "https://commons.example.test/file",
                    "rightsStatus": "verified",
                    "rightsIssues": [],
                    "distributionDecision": "commercial_allowed",
                    "acquisitionReceiptRef": "receipts/acquired.json",
                }
            ]
        },
    )
    _write_json(
        obj / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceId": "commons",
                    "sourceRef": SOURCE_REF,
                    "metaRef": "sources/commons/meta.json",
                    "sourceUrl": "https://commons.example.test/file",
                }
            ]
        },
    )
    _write_json(
        obj / "3.compose/writing_pack.json",
        {
            "vertical": "travel",
            "title": "西门入口",
            "publishLayout": "image",
            "creatorProfileRef": CREATOR_PROFILE,
            "selectedSourceRefs": [SOURCE_REF],
            "tagRefs": ["Entity/地点/景区"],
        },
    )
    _write_json(
        obj / "4.draft/image_work.json",
        {
            "schema": "quwoquan_data.image_work",
            "executionId": EXECUTION_ID,
            "objectRef": TARGET_REF,
            "assetRefs": [ASSET_REF],
            "caption": "西门入口实景。",
        },
    )
    _write_json(
        root / "_shared/receipts/006-4.draft.json",
        {"actor": {"invocation": {"model": "fixture-model"}}},
    )
    target = {
        "name": "西门",
        "entityType": "地点/景区",
        "publishAngle": "建筑",
        "publishTitle": "西门入口",
        "publishSeq": 1,
        "region": "中国/测试区",
    }
    return root, obj, target


def _project(root: Path, obj: Path, target: dict[str, object]) -> dict[str, object]:
    return project_publish_final_surface(
        execution_root=root,
        object_dir=obj,
        target_ref=TARGET_REF,
        target=target,
        carrier="image",
    )



def test_fresh_object_without_manifest_projects_stable_publish_surface(
    tmp_path: Path,
) -> None:
    root, obj, target = _fixture(tmp_path)
    assert not (obj / "manifest.json").exists()

    first = _project(root, obj, target)
    manifest_bytes = (obj / "manifest.json").read_bytes()
    asset_bytes = (obj / "assets/cover.jpg").read_bytes()
    second = _project(root, obj, target)

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert (obj / "manifest.json").read_bytes() == manifest_bytes
    assert (obj / "assets/cover.jpg").read_bytes() == asset_bytes
    manifest = json.loads(manifest_bytes)
    assert_valid(manifest, "content", "post_manifest")
    assert [asset["sourceAssetRef"] for asset in manifest["assets"]] == [ASSET_REF]


def test_final_surface_rejects_selected_asset_set_drift(tmp_path: Path) -> None:
    root, obj, target = _fixture(tmp_path)
    _project(root, obj, target)
    draft_path = obj / "4.draft/image_work.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["assetRefs"] = []
    _write_json(draft_path, draft)

    with pytest.raises(ObjectTransactionError, match="unique selected assets"):
        _project(root, obj, target)


def test_final_surface_rejects_existing_manifest_drift(tmp_path: Path) -> None:
    root, obj, target = _fixture(tmp_path)
    _project(root, obj, target)
    manifest = json.loads((obj / "manifest.json").read_text(encoding="utf-8"))
    manifest["title"] = "drifted"
    _write_json(obj / "manifest.json", manifest)

    with pytest.raises(ObjectTransactionError, match="publish final surface drift"):
        _project(root, obj, target)
