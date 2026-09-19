# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-002
"""Canonical CAS → immutable release media manifest 契约。"""
from __future__ import annotations

import hashlib
import stat
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.content_library import MEDIA_KIND, admit_library_bytes  # noqa: E402
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
    """Seed one canonical post whose body the content library owns.

    A canonical object names its media body by digest instead of carrying it, so
    packaging resolves the bytes from the library. The body is still written under
    the canonical root as well, because create-once and byte-identity assertions
    read it back from there.
    """

    root = Path(tempfile.mkdtemp(prefix="media_asset_url_"))
    payload = b"canonical-cas-asset"
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.png"
    physical = root / "posts" / "article/攻略/p0001/毕棚沟攻略/1/media/cover.png"
    physical.parent.mkdir(parents=True)
    physical.write_bytes(payload)
    admit_library_bytes(payload, kind=MEDIA_KIND)
    post_ref = "posts/article/攻略/毕棚沟攻略/1"
    post = root / "posts" / "article/攻略/p0001/毕棚沟攻略/1"
    physical = post / "media/cover.png"
    physical.parent.mkdir(parents=True, exist_ok=True)
    physical.write_bytes(payload)
    source_body = b"fixture source evidence"
    source_root = post / "sources/s001"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "evidence.txt").write_bytes(source_body)
    source_ref = "sources/s001/source.json"
    write_json(source_root / "source.json", {
        "schema": "quwoquan_data.publish_source", "sourceId": "s001",
        "sourceUrl": "https://example.test/media/cover", "sourceUseMode": "licensed_adaptation",
        "fetchedAt": "2026-09-16T00:00:00Z", "metadata": {},
        "assets": [{"assetId": "cover", "sourceAssetRef": "sources/s001/assets/cover.png", "sourceAsset": {"rightsAuditStatus": "verified"}}],
        "evidence": [{"path": "evidence.txt", "sha256": "sha256:" + hashlib.sha256(source_body).hexdigest(), "bytes": len(source_body), "kind": "source_snapshot"}],
    })
    write_json(post / "manifest.json", {
        "objectRef": post_ref.removeprefix("posts/"), "contentType": "article", "contentId": "post-media-fixture", "version": 1,
        "assets": [{"assetId": "cover", "path": "media/cover.png", "sha256": "sha256:" + digest, "bytes": len(payload), "sourceRefs": [source_ref]}],
    })
    return root, post_ref, object_key


def test_materialize_release_media_reads_closed_cas_only() -> None:
    canonical, post_ref, object_key = _seed_canonical()
    release_root = Path(tempfile.mkdtemp(prefix="release_media_"))
    import shutil
    shutil.copytree(canonical / "posts/article/攻略/p0001/毕棚沟攻略/1", release_root / "release-a/payload/objects/posts/article/攻略/毕棚沟攻略/1")
    copied = release_root / "release-a/payload/objects/posts/article/攻略/毕棚沟攻略/1"
    assert (copied / "media/cover.png").is_file()
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
        "objects/posts/article/攻略/毕棚沟攻略/1/sources/s001/source.json"
    ]
    assert is_public_media_slice_key(asset["publicSliceKey"])
    path = release_root / "release-a/payload/media_manifest.json"
    assert read_json(path)["assets"] == report["assets"]
    assert (
        release_root / "release-a/payload" / asset["publicSliceKey"]
    ).read_bytes() == b"canonical-cas-asset"
    assert (canonical / "posts" / "article/攻略/p0001/毕棚沟攻略/1/media/cover.png").read_bytes() == b"canonical-cas-asset"
    assert (canonical / "posts" / "article/攻略/p0001/毕棚沟攻略/1/manifest.json").is_file()


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
        canonical / "posts" / "article/攻略/p0001/毕棚沟攻略/1/manifest.json",
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
    carried = canonical / "posts/article/攻略/p0001/毕棚沟攻略/1/media/cover.png"
    assert sha256_file(carried) == "sha256:" + object_key.split("/")[-1].split(".")[0]


def test_public_slice_is_kind_scoped_and_derives_ascii_from_canonical_asset_identity() -> None:
    """A non-ASCII assetId keeps its role and sequence readable in the URL path.

    The display text cannot enter a URL path, but the role and execution sequence
    of a canonical post assetId already are ASCII, so only the parts that are not
    get hashed. An identity that is not a canonical post assetId yields no slice
    key at all: there is nothing to derive a stable, collision-free segment from.
    """

    image_key = build_public_media_slice_key(
        asset_id="杭州西湖_cover_三潭印月_1_a1b2c3d4",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )
    video_key = build_public_media_slice_key(
        asset_id="杭州西湖_detail_北山街骑行_2_b2c3d4e5",
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
    assert image_key.startswith("media/image/s/asset/cover-1-")
    assert image_key.split("/")[-2:] == ["v1", "source.jpg"]
    assert video_key.startswith("media/video/s/asset/detail-2-")
    assert avatar_key == "media/avatar/s/asset/creator_avatar_001/v1/source.png"
    assert len({image_key, video_key, avatar_key}) == 3
    for refused in ("bad identity", "杭州西湖_cover_三潭印月"):
        assert not build_public_media_slice_key(
            asset_id=refused,
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
        root = canonical / object_kind / object_ref
        physical = root / f"media/source{suffix}"
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_bytes(payload)
        admit_library_bytes(payload, kind=MEDIA_KIND)
        evidence = f"source:{asset_id}".encode()
        source_root = root / "sources/s001"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / "evidence.txt").write_bytes(evidence)
        source_ref = "sources/s001/source.json"
        write_json(source_root / "source.json", {
            "schema": "quwoquan_data.publish_source", "sourceId": "s001",
            "sourceUrl": f"https://example.test/{asset_id}", "sourceUseMode": "licensed_adaptation",
            "fetchedAt": "2026-09-16T00:00:00Z", "metadata": {},
            "assets": [{"assetId": asset_id}],
            "evidence": [{"path": "evidence.txt", "sha256": "sha256:" + hashlib.sha256(evidence).hexdigest(), "bytes": len(evidence), "kind": "source_snapshot"}],
        })
        write_json(root / ("profile.json" if object_kind == "creators" else "manifest.json"), {
            "assets": [{"assetId": asset_id, "kind": asset_kind, "mimeType": content_type,
                        "path": f"media/source{suffix}", "sha256": f"sha256:{digest}",
                        "bytes": len(payload), "sourceRefs": [source_ref]}]
        })

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
                    "kind": "image",
                    "sha256": "sha256:" + "a" * 64,
                    "objectKey": "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg",
                    "cdnUrl": "https://private.invalid/object",
                }
            ]
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
                    "ownerRefs": ["entities/地点/景区/示例"],
                    "publicSliceKey": "media/image/s/asset/cover/v1/source.jpg",
                    "deliveryField": "cdnUrl",
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
    assert "objectKey" not in manifest_path.read_text(encoding="utf-8")
    assert not rights_snapshot_path.exists()


def test_release_object_media_binding_preserves_read_only_unrelated_json(
    tmp_path: Path,
) -> None:
    objects = tmp_path / "objects"
    definition_path = objects / "tags/Topic/地理/_definition.json"
    write_json(
        definition_path,
        {
            "schema": "quwoquan_data.tag_definition",
            "tagRef": "Topic/地理",
        },
    )
    definition_path.chmod(0o444)
    frozen = definition_path.read_bytes()

    bind_release_object_media_assets(
        objects_root=objects,
        manifest={"assets": []},
    )

    assert definition_path.read_bytes() == frozen
    assert stat.S_IMODE(definition_path.stat().st_mode) == 0o444


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
