"""Aggregate homepage releases use one immutable payload tree."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import (
    aggregate_release_pool_closure,
    aggregate_release_result,
    handler,
    integrity,
)
from content.release.canonical.aggregate_release import (
    build_aggregate_release,
    build_pool_release,
)
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core import paths as core_paths
from core.release_layout import payload_digest, payload_file
from core.source_digest import (
    content_source_revision,
    current_source_digest,
)
from governance.coverage import distribution
from tests.support.release_admission_fixture import (
    article_render_profile,
    bind_publishable_video_review,
)

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


def test_aggregate_release__payload_layout__contract__local_contract(tmp_path: Path) -> None:
    publish_root, execution_root, release_root, selected_key, unrelated_key = _fixture(tmp_path)
    frozen_source_digest = json.loads(
        (
            publish_root / "entities/地点/景区/测试实体甲/manifest.json"
        ).read_text(encoding="utf-8")
    )["sourceDigest"]
    identity = _release_source_identity(str(frozen_source_digest["digest"]))
    shutil.rmtree(execution_root)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        **identity,
    )

    release = release_root / RELEASE_ID
    assert result["idempotent"] is False
    assert payload_file(release, "release.json").is_file()
    assert payload_file(release, "desired_state.json").is_file()
    assert payload_file(release, "objects/entities/地点/景区/测试实体甲/manifest.json").is_file()
    assert payload_file(release, "objects/tags/Topic/旅行/_definition.json").is_file()
    desired = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    assert desired["desiredRefs"]["tags"] == [TAG_REF]
    media = json.loads(payload_file(release, "media_manifest.json").read_text(encoding="utf-8"))
    assert len(media["assets"]) == 1
    release_asset = media["assets"][0]
    assert "objectKey" not in release_asset
    assert release_asset["publicSliceKey"].startswith("media/image/s/asset/")
    assert payload_file(release, release_asset["publicSliceKey"]).is_file()
    release_objects_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(payload_file(release, "objects").rglob("*.json"))
    )
    assert '"objectKey"' not in release_objects_text
    assert "media/objects/sha256/" not in release_objects_text
    assert unrelated_key != selected_key
    assert all(unrelated_key not in str(item) for item in media["assets"])
    aggregate = json.loads((release / "attestations/release.json").read_text(encoding="utf-8"))
    assert aggregate["payloadSha256"] == payload_digest(release)
    assert aggregate["sourceDigests"] == [frozen_source_digest]
    assert aggregate["sourceDigest"] == frozen_source_digest["digest"]
    assert aggregate["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    assert aggregate["sourceRevision"] == identity["source_revision"]
    assert aggregate["postCount"] == 0
    assert aggregate["creatorCount"] == 0
    header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert header["sourceDigests"] == [frozen_source_digest]
    assert header["sourceDigest"] == frozen_source_digest["digest"]
    assert header["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    assert header["sourceRevision"] == identity["source_revision"]
    assert not (release / "release.json").exists()
    assert not (release / "desired_state.json").exists()

    later = publish_root / "entities/地点/景区/后续对象"
    _write_json(later / "manifest.json", {"schema": "quwoquan_data.entity_manifest"})
    _write_json(later / "creator.refs.json", {"creatorRefs": []})
    _write_json(later / "tag.refs.json", {"tagRefs": []})
    _write_json(later / "asset.refs.json", {"assets": []})

    rerun = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        **identity,
    )
    assert rerun["idempotent"] is True


def test_existing_release__self_consistent_rights_tamper__rejects_idempotent(
    tmp_path: Path,
) -> None:
    publish_root, execution_root, release_root, _selected_key, _unrelated_key = (
        _fixture(tmp_path)
    )
    frozen_source_digest = json.loads(
        (
            publish_root / "entities/地点/景区/测试实体甲/manifest.json"
        ).read_text(encoding="utf-8")
    )["sourceDigest"]
    identity = _release_source_identity(str(frozen_source_digest["digest"]))
    shutil.rmtree(execution_root)
    build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        **identity,
    )

    release = release_root / RELEASE_ID
    header_path = payload_file(release, "release.json")
    attestation_path = release / "attestations/release.json"
    admission = json.loads(
        payload_file(release, "asset_admission.json").read_text(encoding="utf-8")
    )
    assert admission["containsUnverifiedAssets"] is True
    assert admission["rightsStatusCounts"]["unverified"] == 1

    tampered_rights = {
        "verified": 1,
        "unverified": 0,
        "restricted": 0,
        "unknown": 0,
    }
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.update(
        {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": tampered_rights,
            "authorizationRequiredAssetIds": [],
            "commercialAcceptedCount": header["researchAcceptedCount"],
        }
    )
    _write_json(header_path, header)
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation.update(
        {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": tampered_rights,
            "authorizationRequiredAssetIds": [],
            "commercialAcceptedCount": attestation["researchAcceptedCount"],
            "payloadSha256": payload_digest(release),
        }
    )
    _write_json(attestation_path, attestation)
    assert attestation["payloadSha256"] == payload_digest(release)

    with pytest.raises(
        ObjectTransactionError,
        match="aggregate release create-once conflict",
    ):
        build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=RELEASE_ID,
            execution_ids=[EXECUTION_ID],
            **identity,
        )


def test_copy_tag_snapshot__excludes_nested_child_tags__local_contract(tmp_path: Path) -> None:
    from content.release.canonical.aggregate_release_closure import copy_tag_snapshot

    source = tmp_path / "Topic" / "旅行"
    nested = source / "玩法" / "观光游览"
    nested.mkdir(parents=True)
    (source / "_definition.json").write_text('{"label":"旅行"}\n', encoding="utf-8")
    (nested / "_definition.json").write_text('{"label":"观光游览"}\n', encoding="utf-8")
    target = tmp_path / "out" / "Topic" / "旅行"
    copy_tag_snapshot(source, target)
    assert (target / "_definition.json").is_file()
    assert not (target / "玩法" / "观光游览" / "_definition.json").is_file()


def test_release_campaign_aggregate_handler__derives_execution_ids__contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root_execution_id = (
        "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    )
    captured: dict[str, object] = {}

    def _build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"releaseId": RELEASE_ID, "idempotent": False}

    monkeypatch.setattr(handler, "build_campaign_release", _build)
    monkeypatch.setattr(handler, "PUBLISH_ROOT", tmp_path / "publish")
    handler.handle_campaign_aggregate_release(
        Namespace(
            root_execution_id=root_execution_id,
            output_root=str(tmp_path / "output"),
            release_id=RELEASE_ID,
        )
    )

    assert captured["root_execution_id"] == root_execution_id
    assert "execution_ids" not in captured
    assert json.loads(capsys.readouterr().out)["releaseId"] == RELEASE_ID


def test_release__multi_carrier_object_closure__contract__local_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "releases"
    entity_ref = "地点/景区/测试实体甲"
    creator_ref = "test_creator_a"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish_root / relative).mkdir(parents=True, exist_ok=True)
    entity_root = publish_root / "entities" / entity_ref
    _entity_key, entity_asset = _write_cas(publish_root, b"entity-homepage-hero")
    entity_asset["role"] = "cover"
    _write_json(
        entity_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": entity_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "homepage-admission.json",
                "evidenceDigest": "sha256:" + "c" * 64,
            },
            "status": "active",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [entity_asset],
        },
    )
    (entity_root / "page.md").write_text("# test entity\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(
        entity_root / "rights.json",
        {"assets": [_research_rights(entity_asset)]},
    )
    _write_json(entity_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
    _write_json(entity_root / "tag.refs.json", {"tagRefs": []})
    _write_json(entity_root / "asset.refs.json", {"assets": [entity_asset]})
    _write_rights_snapshot(entity_root, entity_asset)
    creator_root = publish_root / "creators" / creator_ref
    _avatar_key, avatar_asset = _write_cas(publish_root, b"creator-avatar")
    avatar_asset["kind"] = "avatar"
    _write_json(
        creator_root / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": creator_ref,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [],
            "entityRefs": [],
        },
    )
    _write_json(
        creator_root / "profile.json",
        {
            "authorId": creator_ref,
            "userId": creator_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "author-admission.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
            "status": "active",
            "avatarAsset": {
                "assetId": avatar_asset["assetId"],
                "kind": "avatar",
                "sha256": avatar_asset["sha256"],
            },
        },
    )
    avatar_asset["bytes"] = (
        publish_root / str(avatar_asset["objectKey"])
    ).stat().st_size
    _write_json(creator_root / "assets.refs.json", {"assets": [avatar_asset]})
    _write_avatar_rights_snapshot(creator_root, avatar_asset)
    (creator_root / "works.refs.ndjson").write_text("", encoding="utf-8")

    executions: list[str] = []
    frozen_source_digest = current_source_digest().to_document()

    def add_execution(
        execution_id: str,
        *,
        entities: list[str],
        posts: list[str],
        source_digest: dict[str, object] | None = None,
        record_execution: bool = True,
    ) -> None:
        source_digest = source_digest or frozen_source_digest
        for kind, refs in (("entities", entities), ("posts", posts)):
            for ref in refs:
                manifest_path = publish_root / kind / ref / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["executionId"] = execution_id
                manifest["sourceDigest"] = source_digest
                source_identity = {
                    "executionId": execution_id,
                    "sourceRevision": content_source_revision(
                        source_digest=str(source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
                manifest["sourceIdentity"] = {
                    **source_identity,
                    "identityDigest": source_identity_digest(source_identity),
                }
                if kind == "entities":
                    manifest["sourceAttribution"] = _source_attribution(
                        "homepage"
                    )
                admission = manifest.get("admission")
                if isinstance(admission, dict):
                    evidence_path = manifest_path.parent / str(
                        admission["evidenceRef"]
                    )
                    if not evidence_path.is_file():
                        _write_json(
                            evidence_path,
                            {
                                "schema": "quwoquan_data.test_release_admission_evidence",
                                "executionId": execution_id,
                                "result": "passed",
                            },
                        )
                    admission["evidenceDigest"] = (
                        "sha256:"
                        + hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                    )
                _write_json(manifest_path, manifest)
                if kind in {"entities", "posts"}:
                    append_pool_record(
                        object_root=manifest_path.parent,
                        record=build_canonical_pool_record(
                            object_root=manifest_path.parent,
                            object_type=(
                                "homepage" if kind == "entities" else "content"
                            ),
                            object_ref=ref,
                        ),
                    )
        if record_execution:
            executions.append(execution_id)

    add_execution(
        "20260718--travel-homepage-coverage--test-region-a--scale-901",
        entities=[entity_ref],
        posts=[],
    )
    alternate_source_digest = {**frozen_source_digest}
    alternate_source_digest["digest"] = "sha256:" + "c" * 64
    for content_type, suffix in (("article", "guide"), ("image", "gallery"), ("video", "short")):
        post_ref = f"{content_type}/测试实体甲/{suffix}"
        post_root = publish_root / "posts" / post_ref
        object_keys: list[str] = []
        if content_type == "article":
            cover_key, cover = _write_cas(publish_root, b"article-cover")
            body_key, body = _write_cas(publish_root, b"article-body")
            article_source_ref = "sources/article-source-unit/source.md"
            cover.update(
                role="cover",
                sourceRef=article_source_ref,
            )
            body.update(
                role="embedded",
                sourceRef=article_source_ref,
            )
            assets = [cover, body]
            object_keys.extend((cover_key, body_key))
        elif content_type == "video":
            video_key, video = _write_cas(
                publish_root,
                b"video-asset",
                suffix=".mp4",
                kind="video",
                mime_type="video/mp4",
            )
            poster_key, poster = _write_cas(publish_root, b"video-poster")
            poster["role"] = "cover"
            video["posterAssetId"] = poster["assetId"]
            assets = [video, poster]
            object_keys.extend((video_key, poster_key))
        else:
            image_key, image = _write_cas(publish_root, b"image-asset")
            image["role"] = "cover"
            assets = [image]
            object_keys.append(image_key)
        _write_json(
            post_root / "manifest.json",
            {
                "schema": "quwoquan_data.post_manifest",
                "contentIdentity": "work",
                "vertical": "travel",
                "contentType": content_type,
                "contentId": f"content-{content_type}",
                "version": 1,
                "sourceType": "data",
                "creatorProfileId": creator_ref,
                "authorId": creator_ref,
                "reviewDecision": "approved",
                    "entityRefs": [f"/entity/{entity_ref}"],
                    "sourceAttribution": _source_attribution(content_type),
                "variantPurpose": "original",
                "admission": {
                    "processResult": "completed",
                    "qualityResult": "passed",
                    "usageScope": "research",
                    "evidenceRef": "attestation.json",
                    "evidenceDigest": "sha256:" + "b" * 64,
                },
                "status": "active",
                "finalContentRef": "content.md",
                "sourceCatalogRef": "source_catalog.json",
                "rightsRef": "rights.json",
                "creatorRefsRef": "creator.refs.json",
                "tagRefsRef": "tag.refs.json",
                "assetRefsRef": "asset.refs.json",
                "assets": assets,
                **(
                    {
                        "publishMediaMode": "same_source_illustrated",
                        "articleRenderProfile": article_render_profile(
                            mode="illustrated",
                            source_ref=article_source_ref,
                            cover_asset_id=str(assets[0]["assetId"]),
                            body_asset_ids=[str(assets[1]["assetId"])],
                        ),
                        "imageBindings": [
                            {"assetId": str(asset["assetId"])} for asset in assets
                        ],
                    }
                    if content_type == "article"
                    else {}
                ),
            },
        )
        (post_root / "content.md").write_text(f"# {content_type}\n", encoding="utf-8")
        _write_json(post_root / "source_catalog.json", {"sources": []})
        _write_json(
            post_root / "rights.json",
            {"assets": [_research_rights(asset) for asset in assets]},
        )
        if content_type == "video":
            video_asset = next(
                asset for asset in assets if asset.get("kind") == "video"
            )
            bind_publishable_video_review(
                object_root=post_root,
                output_root=core_paths.OUTPUT_ROOT,
                asset_id=str(video_asset["assetId"]),
                content_sha256=str(video_asset["sha256"]),
                object_ref=post_ref,
                source_digest=str(frozen_source_digest["digest"]),
                entity_catalog_digest=ENTITY_CATALOG_DIGEST,
            )
        _write_json(post_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(post_root / "tag.refs.json", {"tagRefs": []})
        _write_json(post_root / "asset.refs.json", {"assets": assets})
        for asset in assets:
            _write_rights_snapshot(post_root, asset)
        add_execution(
            f"20260718--travel-{content_type}-supply--test-region-a--scale-90{len(executions) + 1}",
            entities=[],
            posts=[post_ref],
        )
        assert all((publish_root / object_key).is_file() for object_key in object_keys)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-multi-carrier--test-release-b--001",
        execution_ids=executions,
        target_environment="alpha",
        **_release_source_identity(str(frozen_source_digest["digest"])),
    )

    release = release_root / result["releaseId"]
    desired = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    assert desired["desiredRefs"] == {
        "creators": [creator_ref],
        "entities": [entity_ref],
        "posts": [
            "article/测试实体甲/guide",
            "image/测试实体甲/gallery",
            "video/测试实体甲/short",
        ],
        "tags": [],
    }
    assert payload_file(release, f"objects/creators/{creator_ref}/_creator.json").is_file()
    assert result["postCount"] == 3
    assert result["creatorCount"] == 1
    release_header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert release_header["sourceOwner"] == "qwq_data"
    assert release_header["sourceDigests"] == [frozen_source_digest]
    assert release_header["targetEnvironment"] == "alpha"
    assert release_header["releaseMode"] == "research"
    assert release_header["counts"] == {
        "article": 1,
        "image": 1,
        "video": 1,
        "total": 3,
    }
    assert result["poolEligibleCount"] == 3
    monkeypatch.setattr(integrity.paths, "PUBLISH_ROOT", publish_root)
    integrity_report = integrity._release_integrity(result["releaseId"], release)
    stats = integrity_report["stats"]
    assert stats["postCount"] == 3
    assert stats["articleCount"] == 1
    assert stats["imageCount"] == 1
    assert stats["videoCount"] == 1
    assert (
        stats["articleCount"] + stats["imageCount"] + stats["videoCount"]
        == stats["postCount"]
    )

    article_manifest_path = (
        publish_root / "posts/article/测试实体甲/guide/manifest.json"
    )
    article_manifest = json.loads(article_manifest_path.read_text(encoding="utf-8"))
    original_article_manifest = json.loads(json.dumps(article_manifest))
    article_manifest["sourceDigest"] = alternate_source_digest
    _write_json(article_manifest_path, article_manifest)
    with pytest.raises(ObjectTransactionError, match="one frozen sourceDigest"):
        build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id="20260718--travel-multi-carrier--mixed-source--001",
            execution_ids=executions,
            **_release_source_identity(str(frozen_source_digest["digest"])),
        )
    article_manifest = original_article_manifest
    _write_json(article_manifest_path, article_manifest)

    standalone_entity_ref = "地点/景区/独立实体乙"
    standalone_execution = (
        "20260718--travel-homepage-coverage--test-region-b--scale-902"
    )
    standalone_root = publish_root / "entities" / standalone_entity_ref
    _standalone_key, standalone_asset = _write_cas(
        publish_root, b"standalone-entity-homepage-hero"
    )
    standalone_asset["role"] = "cover"
    _write_json(
        standalone_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": standalone_entity_ref,
            "version": 1,
            "executionId": standalone_execution,
            "sourceDigest": frozen_source_digest,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "homepage-admission.json",
                "evidenceDigest": "sha256:" + "d" * 64,
            },
            "status": "active",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [standalone_asset],
        },
    )
    (standalone_root / "page.md").write_text("# standalone entity\n", encoding="utf-8")
    _write_json(standalone_root / "source_catalog.json", {"sources": []})
    _write_json(
        standalone_root / "rights.json",
        {"assets": [_research_rights(standalone_asset)]},
    )
    _write_json(
        standalone_root / "creator.refs.json", {"creatorRefs": [creator_ref]}
    )
    _write_json(standalone_root / "tag.refs.json", {"tagRefs": []})
    _write_json(standalone_root / "asset.refs.json", {"assets": [standalone_asset]})
    _write_rights_snapshot(standalone_root, standalone_asset)
    add_execution(
        standalone_execution,
        entities=[standalone_entity_ref],
        posts=[],
        source_digest=alternate_source_digest,
        record_execution=False,
    )

    independent_creator_ref = "test_creator_independent"
    independent_tag_ref = "Topic/旅行/独立作者"
    independent_creator_root = publish_root / "creators" / independent_creator_ref
    _write_json(
        independent_creator_root / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": independent_creator_ref,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [independent_tag_ref],
            "entityRefs": [],
        },
    )
    _write_json(
        independent_creator_root / "profile.json",
        {
            "authorId": independent_creator_ref,
            "userId": independent_creator_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "author-admission.json",
                "evidenceDigest": "sha256:" + "e" * 64,
            },
            "status": "active",
        },
    )
    _write_json(independent_creator_root / "assets.refs.json", {"assets": []})
    (independent_creator_root / "works.refs.ndjson").write_text(
        "", encoding="utf-8"
    )
    _write_json(
        publish_root / "tags" / independent_tag_ref / "_definition.json",
        {"label": "独立作者", "labelEn": "independent-author"},
    )

    pool_result = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha--001",
        target_environment="alpha",
    )
    assert pool_result["postCount"] == 3
    assert pool_result["entityCount"] == 2
    assert pool_result["counts"] == {
        "article": 1,
        "image": 1,
        "video": 1,
        "total": 3,
    }
    assert pool_result["targetEnvironment"] == "alpha"
    pool_header = json.loads(
        payload_file(
            release_root / pool_result["releaseId"],
            "release.json",
        ).read_text(encoding="utf-8")
    )
    assert pool_header["poolDigest"] == pool_result["poolDigest"]
    assert pool_header["executionIds"] == sorted([*executions, standalone_execution])
    expected_source_identities, expected_source_identity_set_digest = (
        source_identity_set(
            [
                {
                    "executionId": execution_id,
                    "sourceRevision": content_source_revision(
                        source_digest=str(frozen_source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(frozen_source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
                for execution_id in executions
            ]
            + [
                {
                    "executionId": standalone_execution,
                    "sourceRevision": content_source_revision(
                        source_digest=str(alternate_source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(alternate_source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
            ]
        )
    )
    assert pool_header["sourceIdentities"] == expected_source_identities
    assert (
        pool_header["sourceIdentitySetDigest"]
        == expected_source_identity_set_digest
    )
    assert {
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    }.isdisjoint(pool_header)
    pool_attestation = json.loads(
        (
            release_root
            / pool_result["releaseId"]
            / "attestations/release.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        "sourceIdentities",
        "sourceIdentitySetDigest",
    }.issubset(pool_attestation)
    assert pool_attestation["sourceIdentities"] == expected_source_identities
    assert (
        pool_attestation["sourceIdentitySetDigest"]
        == expected_source_identity_set_digest
    )
    assert {
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    }.isdisjoint(pool_attestation)
    assert pool_header["authors"] == [
        {"authorId": creator_ref, "version": 1, "creatorRef": creator_ref},
        {
            "authorId": independent_creator_ref,
            "version": 1,
            "creatorRef": independent_creator_ref,
        },
    ]
    pool_desired = json.loads(
        payload_file(
            release_root / pool_result["releaseId"],
            "desired_state.json",
        ).read_text(encoding="utf-8")
    )
    assert pool_desired["desiredRefs"]["tags"] == [independent_tag_ref]
    assert {
        (item["contentId"], item["version"], item["postRef"])
        for item in pool_header["contents"]
    } == {
        (
            f"content-{ref.split('/', 1)[0]}",
            1,
            ref,
        )
        for ref in (
            "article/测试实体甲/guide",
            "image/测试实体甲/gallery",
            "video/测试实体甲/short",
        )
    }
    assert build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=pool_result["releaseId"],
        target_environment="alpha",
    )["idempotent"] is True

    invalid_article = json.loads(
        article_manifest_path.read_text(encoding="utf-8")
    )
    invalid_article.pop("mediaClosure", None)
    invalid_article.pop("articleRenderProfile", None)
    _write_json(article_manifest_path, invalid_article)
    media_partial = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha-media-partial--001",
        target_environment="alpha",
    )
    assert media_partial["postCount"] == 2
    assert media_partial["excludedCount"] == 1
    assert media_partial["excluded"][0]["postRef"] == "article/测试实体甲/guide"
    _write_json(article_manifest_path, article_manifest)

    invalid_manifest_path = (
        publish_root / "posts/video/测试实体甲/short/manifest.json"
    )
    invalid_manifest = json.loads(
        invalid_manifest_path.read_text(encoding="utf-8")
    )
    invalid_manifest["admission"]["qualityResult"] = "failed"
    _write_json(invalid_manifest_path, invalid_manifest)
    append_pool_record(
        object_root=invalid_manifest_path.parent,
        record=build_canonical_pool_record(
            object_root=invalid_manifest_path.parent,
            object_type="content",
            object_ref="video/测试实体甲/short",
        ),
    )
    partial_result = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha-partial--001",
        target_environment="alpha",
    )
    assert partial_result["postCount"] == 2
    assert partial_result["excludedCount"] == 1
    assert partial_result["excluded"] == [
        {
            "postRef": "video/测试实体甲/short",
            "category": "quality",
            "code": "DATA.POOL.QUALITY_FAILED",
            "message": "DATA.POOL.QUALITY_FAILED: postRef=video/测试实体甲/short",
        }
    ]
    partial_header = json.loads(
        payload_file(
            release_root / partial_result["releaseId"],
            "release.json",
        ).read_text(encoding="utf-8")
    )
    assert partial_header["counts"] == {
        "article": 1,
        "image": 1,
        "video": 0,
        "total": 2,
    }
