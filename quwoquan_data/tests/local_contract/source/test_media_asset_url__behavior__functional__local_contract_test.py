# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-002
"""Canonical CAS → immutable release media manifest 契约。"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import read_json, write_json  # noqa: E402
from core.media_asset_url import (  # noqa: E402
    IMAGE_VARIANT_POLICY_VERSION,
    IMAGE_VARIANT_PROFILES,
    build_public_media_slice_key,
    build_release_media_manifest,
    is_cas_media_object_key,
    is_public_media_slice_key,
    materialize_release_media,
    sha256_file,
)
from core.release_media_binding import bind_release_object_media_assets  # noqa: E402


def _seed_canonical() -> tuple[Path, str, str]:
    root = Path(tempfile.mkdtemp(prefix="media_asset_url_"))
    payload = b"canonical-cas-asset"
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.png"
    physical = root / object_key
    physical.parent.mkdir(parents=True)
    physical.write_bytes(payload)
    post_ref = "posts/article/攻略/毕棚沟攻略/1"
    post = root / post_ref
    write_json(
        post / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": object_key,
                    "sha256": "sha256:" + digest,
                }
            ]
        },
    )
    write_json(
        post / "rights_snapshots" / "cover.json",
        {
            "assetId": "cover",
            "manifestAsset": {
                "assetId": "cover",
                "sha256": "sha256:" + digest,
            },
        },
    )
    return root, post_ref, object_key


def test_materialize_release_media_reads_closed_cas_only() -> None:
    canonical, post_ref, object_key = _seed_canonical()
    release_root = Path(tempfile.mkdtemp(prefix="release_media_"))
    report = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert report["issues"] == []
    asset = report["assets"][0]
    assert "objectKey" not in asset
    assert asset["assetId"] == "cover"
    assert asset["kind"] == "image"
    assert asset["sha256"] == "sha256:" + object_key.split("/")[-1].split(".")[0]
    assert asset["rightsSnapshotRefs"] == [
        "objects/posts/article/攻略/毕棚沟攻略/1/rights_snapshots/cover.json"
    ]
    assert is_public_media_slice_key(asset["publicSliceKey"])
    path = release_root / "release-a/payload/media_manifest.json"
    assert read_json(path)["assets"] == report["assets"]
    assert (
        release_root / "release-a/payload" / asset["publicSliceKey"]
    ).read_bytes() == b"canonical-cas-asset"
    assert (canonical / object_key).read_bytes() == b"canonical-cas-asset"
    assert not (canonical / post_ref / "manifest.json").exists()


def test_release_media_manifest_is_create_once() -> None:
    canonical, post_ref, _ = _seed_canonical()
    release_root = Path(tempfile.mkdtemp(prefix="release_media_once_"))
    first = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    second = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert first == second


def test_invalid_or_dangling_asset_ref_fails_closed() -> None:
    canonical, post_ref, _ = _seed_canonical()
    write_json(
        canonical / post_ref / "asset.refs.json",
        {"assets": [{"objectKey": "../escape.png", "sha256": "sha256:" + "0" * 64}]},
    )
    release_root = Path(tempfile.mkdtemp(prefix="release_media_bad_"))
    report = materialize_release_media(
        release_id="release-bad",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert report["issues"]
    assert not (release_root / "release-bad/payload/media_manifest.json").exists()


def test_cas_key_and_hash_contract() -> None:
    canonical, _, object_key = _seed_canonical()
    assert is_cas_media_object_key(object_key)
    assert not is_cas_media_object_key("../escape.png")
    assert sha256_file(canonical / object_key) == "sha256:" + object_key.split("/")[-1].split(".")[0]


def test_public_slice_is_kind_scoped_and_accepts_historical_unicode_asset_identity() -> None:
    image_key = build_public_media_slice_key(
        asset_id="杭州西湖_cover_三潭印月",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )
    video_key = build_public_media_slice_key(
        asset_id="杭州西湖_video_北山街",
        kind="video",
        version=1,
        content_type="video/mp4",
    )
    avatar_key = build_public_media_slice_key(
        asset_id="creator_avatar_001",
        kind="avatar",
        version=1,
        content_type="image/png",
    )
    assert image_key.startswith("media/image/s/asset/unicode-")
    assert video_key.startswith("media/video/s/asset/unicode-")
    assert avatar_key == "media/avatar/s/asset/creator_avatar_001/v1/source.png"
    assert len({image_key, video_key, avatar_key}) == 3
    assert not build_public_media_slice_key(
        asset_id="bad identity",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )


def test_release_manifest_unifies_avatar_image_video_identity_and_rights() -> None:
    canonical = Path(tempfile.mkdtemp(prefix="release_media_kinds_"))

    def seed(
        *,
        object_kind: str,
        object_ref: str,
        asset_id: str,
        asset_kind: str,
        suffix: str,
        content_type: str,
    ) -> None:
        payload = f"{asset_kind}:{asset_id}".encode()
        digest = hashlib.sha256(payload).hexdigest()
        object_key = (
            f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"
        )
        physical = canonical / object_key
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_bytes(payload)
        root = canonical / object_kind / object_ref
        write_json(
            root / "asset.refs.json",
            {
                "assets": [
                    {
                        "assetId": asset_id,
                        "objectKey": object_key,
                        "sha256": f"sha256:{digest}",
                        "bytes": len(payload),
                    }
                ]
            },
        )
        if object_kind != "creators":
            write_json(
                root / "manifest.json",
                {
                    "assets": [
                        {
                            "assetId": asset_id,
                            "kind": asset_kind,
                            "mimeType": content_type,
                            "objectKey": object_key,
                            "sha256": f"sha256:{digest}",
                        }
                    ]
                },
            )
        write_json(
            root / "rights_snapshots" / f"{asset_kind}.json",
            {
                "assetId": asset_id,
                "manifestAsset": {
                    "assetId": asset_id,
                    "sha256": f"sha256:{digest}",
                },
            },
        )

    seed(
        object_kind="creators",
        object_ref="creator-a",
        asset_id="creator-avatar",
        asset_kind="avatar",
        suffix=".png",
        content_type="image/png",
    )
    seed(
        object_kind="posts",
        object_ref="image/gallery-a",
        asset_id="gallery-image",
        asset_kind="image",
        suffix=".jpg",
        content_type="image/jpeg",
    )
    seed(
        object_kind="posts",
        object_ref="video/clip-a",
        asset_id="clip-video",
        asset_kind="video",
        suffix=".mp4",
        content_type="video/mp4",
    )

    manifest = build_release_media_manifest(
        release_id="release-kinds",
        creator_refs=["creator-a"],
        post_refs=["image/gallery-a", "video/clip-a"],
        entity_refs=[],
        publish_root=canonical,
    )

    assert manifest["issues"] == []
    assert {asset["kind"] for asset in manifest["assets"]} == {
        "avatar",
        "image",
        "video",
    }
    for asset in manifest["assets"]:
        assert "objectKey" not in asset
        assert asset["publicSliceKey"].startswith(f"media/{asset['kind']}/s/")
        assert asset["rightsSnapshotRefs"]
        assert asset["sha256"].startswith("sha256:")


def test_release_object_media_binding_removes_private_cas_and_environment_urls() -> None:
    objects = Path(tempfile.mkdtemp(prefix="release_object_media_")) / "objects"
    manifest_path = objects / "entities/地点/景区/示例/manifest.json"
    asset_refs_path = objects / "entities/地点/景区/示例/asset.refs.json"
    rights_snapshot_path = (
        objects / "entities/地点/景区/示例/rights_snapshots/cover.json"
    )
    write_json(
        manifest_path,
        {
            "assets": [
                {
                    "assetId": "cover",
                    "role": "cover",
                    "objectKey": "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg",
                    "cdnUrl": "https://private.invalid/object",
                }
            ]
        },
    )
    write_json(
        asset_refs_path,
        {
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg",
                }
            ]
        },
    )
    write_json(
        rights_snapshot_path,
        {
            "assetId": "cover",
            "manifestAsset": {
                "assetId": "cover",
                "objectKey": "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg",
            },
        },
    )
    bind_release_object_media_assets(
        objects_root=objects,
        manifest={
            "assets": [
                {
                    "assetId": "cover",
                    "kind": "image",
                    "sha256": "sha256:" + "a" * 64,
                }
            ]
        },
    )
    asset = read_json(manifest_path)["assets"][0]
    assert asset == {
        "assetId": "cover",
        "role": "cover",
        "kind": "image",
        "sha256": "sha256:" + "a" * 64,
    }
    assert "objectKey" not in asset_refs_path.read_text(encoding="utf-8")
    assert "objectKey" not in rights_snapshot_path.read_text(encoding="utf-8")


def test_release_object_media_binding_preserves_frozen_asset_review_bytes() -> None:
    objects = Path(tempfile.mkdtemp(prefix="release_review_binding_")) / "objects"
    receipt_path = (
        objects
        / "posts/video/example/asset_reviews/receipts/frozen-review.json"
    )
    write_json(
        receipt_path,
        {
            "schema": "quwoquan_data.independent_asset_review_receipt",
            "assetSnapshot": {
                "assetId": "video-asset",
                "contentSha256": "sha256:" + "a" * 64,
            },
            "receiptDigest": "sha256:" + "b" * 64,
        },
    )
    frozen = receipt_path.read_bytes()

    bind_release_object_media_assets(
        objects_root=objects,
        manifest={
            "assets": [
                {
                    "assetId": "video-asset",
                    "kind": "video",
                    "sha256": "sha256:" + "a" * 64,
                }
            ]
        },
    )

    assert receipt_path.read_bytes() == frozen


def test_image_variant_profiles_are_loaded_from_canonical_metadata() -> None:
    assert IMAGE_VARIANT_POLICY_VERSION == 1
    assert IMAGE_VARIANT_PROFILES == {
        "thumbnail": {
            "width": 320,
            "format": "webp",
            "quality": 80,
            "scene": "feed_grid",
            "processing": "image/resize,w_320/format,webp/quality,q_80",
        },
        "display": {
            "width": 960,
            "format": "webp",
            "quality": 82,
            "scene": "article_body",
            "processing": "image/resize,w_960/format,webp/quality,q_82",
        },
        "cover": {
            "width": 1280,
            "format": "webp",
            "quality": 85,
            "scene": "feed_cover",
            "processing": "image/resize,w_1280/format,webp/quality,q_85",
        },
        "full": {
            "width": 2048,
            "format": "webp",
            "quality": 90,
            "scene": "immersive_viewer",
            "processing": "image/resize,w_2048/format,webp/quality,q_90",
        },
    }
