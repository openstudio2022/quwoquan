"""aggregate release payload_layout 合约测试共享常量、fixture 与 helper。

Aggregate homepage releases use one immutable payload tree.

由 test_aggregate_release__payload_layout_* 场景组测试文件共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
``_use_research_distribution`` 是模块级 autouse fixture，场景测试文件
必须显式 import 它以保持 autouse 语义。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from content.release.canonical import (
    aggregate_release_pool_closure,
    aggregate_release_result,
)
from core import paths as core_paths
from core.source_digest import (
    content_source_revision,
    current_source_digest,
)
from governance.coverage import distribution


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--scale-901"
RELEASE_ID = "20260713--travel-homepage-coverage--test-release-a--scale-901"
TAG_REF = "Topic/旅行"
ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


@pytest.fixture(autouse=True)
def _use_research_distribution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    policy = distribution.load_content_distribution_policy()
    research_policy = replace(
        policy,
        product_lifecycle_state=distribution.ProductLifecycleState.RESEARCH,
        release_class=distribution.ReleaseClass.RESEARCH,
    )
    monkeypatch.setattr(
        aggregate_release_pool_closure,
        "load_content_distribution_policy",
        lambda: research_policy,
    )
    monkeypatch.setattr(
        aggregate_release_result,
        "load_content_distribution_policy",
        lambda: research_policy,
    )
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path / "output")


def _release_source_identity(source_digest: str | None = None) -> dict[str, str]:
    source_digest = source_digest or current_source_digest().digest
    return {
        "source_revision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        ),
        "entity_catalog_digest": ENTITY_CATALOG_DIGEST,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_cas(
    publish_root: Path,
    payload: bytes,
    *,
    suffix: str = ".jpg",
    kind: str = "image",
    mime_type: str = "image/jpeg",
) -> tuple[str, dict[str, object]]:
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"
    path = publish_root / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return object_key, {
        "assetId": f"asset-{digest[:16]}",
        "kind": kind,
        "mimeType": mime_type,
        "objectKey": object_key,
        "sha256": f"sha256:{digest}",
    }


def _write_rights_snapshot(object_root: Path, asset: dict[str, object]) -> None:
    _write_json(
        object_root / "rights_snapshots" / f"{asset['assetId']}.json",
        {
            "assetId": asset["assetId"],
            "manifestAsset": {
                "assetId": asset["assetId"],
                "sha256": asset["sha256"],
            },
        },
    )


def _research_rights(asset: dict[str, object]) -> dict[str, object]:
    return {
        "assetId": asset["assetId"],
        "asset": {
            "sha256": asset["sha256"],
            "bytes": 128,
        },
        "sourceUrl": f"https://media.example/{asset['assetId']}",
        "platform": "Research Media",
        "creator": "Research Creator",
        "capturedAt": "2026-08-05T00:00:00Z",
        "license": "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": "",
        "rightsAuditStatus": "unverified",
        "rightsAuditIssues": ["commercial authorization pending"],
    }


def _source_attribution(content_type: str) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "Research Creator",
        "platform": "Research Media",
        "sourcePostUrl": f"https://media.example/{content_type}",
        "originalAssetUrl": f"https://media.example/{content_type}/asset",
        "attributionText": "Research Creator / Research Media",
        "rightsBasis": "unknown",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "unverified" if content_type == "video" else "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-05T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _write_avatar_rights_snapshot(
    object_root: Path,
    asset: dict[str, object],
) -> None:
    object_key = str(asset["objectKey"])
    physical = object_root.parents[1] / object_key
    byte_count = physical.stat().st_size
    asset_id = str(asset["assetId"])
    digest = str(asset["sha256"])
    _write_json(
        object_root / "rights_snapshots" / f"{asset_id}.json",
        {
            "schema": "quwoquan_data.creator_avatar_rights_snapshot",
            "assetId": asset_id,
            "depictsIdentifiablePerson": False,
            "manifestAsset": {"assetId": asset_id, "sha256": digest},
            "commercialRights": {
                "assetId": asset_id,
                "sourceKind": "licensed_creator_avatar",
                "sourceUseMode": "licensed_adaptation",
                "canonicalFilePage": "https://rights.example/avatar-a",
                "snapshotUrl": "https://rights.example/avatar-a",
                "pageRevision": "sha256:" + "b" * 64,
                "originalAssetUrl": "https://rights.example/avatar-a.jpg",
                "author": "Avatar Author",
                "source": "https://rights.example/avatar-a",
                "licenseName": "CC BY 4.0",
                "licenseShortName": "CC BY 4.0",
                "licenseUrl": "https://creativecommons.org/licenses/by/4.0",
                "usageScope": "app_publish",
                "attribution": "Avatar Author, CC BY 4.0",
                "caption": "Creator avatar",
                "captionSource": "rights owner metadata",
                "modifications": "square crop",
                "fetchedAt": "2026-07-28T00:00:00Z",
                "snapshot": {
                    "ref": "evidence/avatar-a.json",
                    "sha256": "sha256:" + "c" * 64,
                    "bytes": 128,
                },
                "asset": {
                    "ref": f"cas/{digest.removeprefix('sha256:')}.jpg",
                    "sha256": digest,
                    "bytes": byte_count,
                    "mimeType": str(asset["mimeType"]),
                    "width": 64,
                    "height": 64,
                },
                "authorizationProof": "https://rights.example/avatar-a/license",
                "modelReleaseStatus": "not_required",
                "rightsAuditStatus": "verified",
                "rightsAuditIssues": [],
            },
        },
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    publish_root = tmp_path / "publish"
    execution_root = tmp_path / EXECUTION_ID
    release_root = tmp_path / "releases"
    source_digest = current_source_digest().to_document()
    _write_json(
        execution_root / "execution_manifest.json",
        {
            "executionId": EXECUTION_ID,
            "sourceDigest": source_digest,
        },
    )
    _write_json(
        execution_root / "publish_ref.json",
        {
            "schema": "quwoquan_data.execution_publish_ref",
            "executionId": EXECUTION_ID,
            "canonicalPublishRoot": "quwoquan_data/publish",
            "publishedRefs": {"entities": ["地点/景区/测试实体甲"], "posts": []},
        },
    )
    _write_json(
        execution_root / "entities/地点/景区/测试实体甲/5.review/attestation.json",
        {
            "decision": "approved",
            "objectRef": "/entity/地点/景区/测试实体甲",
            "independentReviewer": {"status": "passed"},
        },
    )
    selected_key, selected_asset = _write_cas(publish_root, b"putuo-release-asset")
    unrelated_key, unrelated_asset = _write_cas(publish_root, b"unrelated-canonical-asset")
    entity_root = publish_root / "entities/地点/景区/测试实体甲"
    _write_json(
        entity_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_object",
            "executionId": EXECUTION_ID,
            "sourceDigest": source_digest,
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [{**selected_asset, "role": "cover"}],
        },
    )
    (entity_root / "page.md").write_text("# 测试实体甲\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(entity_root / "rights.json", {"assets": [_research_rights(selected_asset)]})
    _write_json(
        entity_root / "creator.refs.json",
        {"creatorRefs": []},
    )
    _write_json(
        entity_root / "tag.refs.json",
        {"tagRefs": [TAG_REF]},
    )
    _write_json(
        publish_root / "tags/Topic/旅行/_definition.json",
        {
            "label": "旅行",
            "labelEn": "travel",
            "createdAt": "2026-07-13T00:00:00Z",
            "updatedAt": "2026-07-13T00:00:00Z",
        },
    )
    _write_json(
        entity_root / "asset.refs.json",
        {"assets": [selected_asset]},
    )
    _write_rights_snapshot(entity_root, selected_asset)
    _write_json(publish_root / "entities/地点/景区/其他/manifest.json", {"assets": []})
    _write_json(
        publish_root / "entities/地点/景区/其他/creator.refs.json",
        {"creatorRefs": []},
    )
    _write_json(
        publish_root / "entities/地点/景区/其他/tag.refs.json",
        {"tagRefs": [TAG_REF]},
    )
    _write_json(
        publish_root / "entities/地点/景区/其他/asset.refs.json",
        {"assets": [unrelated_asset]},
    )
    return publish_root, execution_root, release_root, selected_key, unrelated_key
