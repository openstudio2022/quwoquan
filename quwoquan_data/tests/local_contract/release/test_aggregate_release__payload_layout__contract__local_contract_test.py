"""Aggregate homepage releases use one immutable payload tree."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import (
    handler,
    integrity,
)
from content.release.canonical.aggregate_release import (
    build_aggregate_release,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.release_layout import payload_digest, payload_file
from core.source_digest import (
    content_source_revision,
    current_source_digest,
)
from tests.support.release_admission_fixture import (
    article_render_profile,
    bind_publishable_video_review,
)

EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--scale-901"
RELEASE_ID = "20260713--travel-homepage-coverage--test-release-a--scale-901"
TAG_REF = "Topic/旅行"
ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


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
            "userId": creator_ref,
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
    ) -> None:
        source_digest = source_digest or frozen_source_digest
        for kind, refs in (("entities", entities), ("posts", posts)):
            for ref in refs:
                manifest_path = publish_root / kind / ref / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["executionId"] = execution_id
                manifest["sourceDigest"] = source_digest
                _write_json(manifest_path, manifest)
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
                "creatorProfileId": creator_ref,
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
