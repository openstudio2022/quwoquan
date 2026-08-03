"""Aggregate homepage releases use one immutable payload tree."""
from __future__ import annotations

import json
import hashlib
import shutil
import sys
from argparse import Namespace
from pathlib import Path



ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import payload_digest, payload_file  # noqa: E402
from core.source_digest import current_source_digest  # noqa: E402
from content.release.canonical import handler  # noqa: E402
from content.release.canonical import integrity  # noqa: E402
from content.release.canonical.aggregate_release import build_aggregate_release  # noqa: E402


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--scale-901"
RELEASE_ID = "20260713--travel-homepage-coverage--test-release-a--scale-901"
TAG_REF = "Topic/旅行"


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
        },
    )
    (entity_root / "page.md").write_text("# 测试实体甲\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(entity_root / "rights.json", {"assets": []})
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
    shutil.rmtree(execution_root)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
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
    assert aggregate["sourceDigests"] == [current_source_digest().to_document()]
    assert aggregate["postCount"] == 0
    assert aggregate["creatorCount"] == 0
    header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert header["sourceDigests"] == [current_source_digest().to_document()]
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
    )
    assert rerun["idempotent"] is True


def test_release_aggregate_handler__execution_ids__contract__local_contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    execution_ids = [
        "20260715--travel-homepage-coverage--test-region-a--pilot-001",
        "20260715--travel-homepage-coverage--test-region-b--pilot-001",
    ]
    captured: dict[str, object] = {}

    def _build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"releaseId": RELEASE_ID, "idempotent": False}

    monkeypatch.setattr(handler, "build_aggregate_release", _build)
    handler.handle_aggregate_release(
        Namespace(
            execution_ids=",".join(execution_ids),
            publish_root=str(tmp_path / "publish"),
            release_root=str(tmp_path / "releases"),
            release_id=RELEASE_ID,
        )
    )

    assert captured["execution_ids"] == execution_ids
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
        },
    )
    (entity_root / "page.md").write_text("# test entity\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(entity_root / "rights.json", {"assets": []})
    _write_json(entity_root / "creator.refs.json", {"creatorRefs": []})
    _write_json(entity_root / "tag.refs.json", {"tagRefs": []})
    _write_json(entity_root / "asset.refs.json", {"assets": []})
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

    def add_execution(
        execution_id: str,
        *,
        entities: list[str],
        posts: list[str],
        source_digest: dict[str, object] | None = None,
    ) -> None:
        source_digest = source_digest or current_source_digest().to_document()
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
    alternate_source_digest = current_source_digest().to_document()
    alternate_source_digest["digest"] = "sha256:" + "c" * 64
    for content_type, suffix in (("article", "guide"), ("image", "gallery"), ("video", "short")):
        post_ref = f"{content_type}/测试实体甲/{suffix}"
        post_root = publish_root / "posts" / post_ref
        object_keys: list[str] = []
        if content_type == "article":
            cover_key, cover = _write_cas(publish_root, b"article-cover")
            body_key, body = _write_cas(publish_root, b"article-body")
            cover.update(
                role="cover",
                sourceUnitRef="sources/article-source-unit/source.md",
            )
            body.update(
                role="embedded",
                sourceUnitRef="sources/article-source-unit/source.md",
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
        _write_json(post_root / "rights.json", {"assets": []})
        _write_json(post_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(post_root / "tag.refs.json", {"tagRefs": []})
        _write_json(post_root / "asset.refs.json", {"assets": assets})
        for asset in assets:
            _write_rights_snapshot(post_root, asset)
        add_execution(
            f"20260718--travel-{content_type}-supply--test-region-a--scale-90{len(executions) + 1}",
            entities=[],
            posts=[post_ref],
            source_digest=(
                alternate_source_digest if content_type == "article" else None
            ),
        )
        assert all((publish_root / object_key).is_file() for object_key in object_keys)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-multi-carrier--test-release-b--001",
        execution_ids=executions,
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
    assert release_header["sourceDigests"] == sorted(
        [current_source_digest().to_document(), alternate_source_digest],
        key=lambda item: item["digest"],
    )
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
