"""Media asset URL materialization and collision contract tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.io import read_json, write_json  # noqa: E402
from _common.media_asset_url import (  # noqa: E402
    build_object_key,
    is_cas_media_object_key,
    materialize_release_media,
    sha256_file,
)


def _seed_publish_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="media_asset_url_"))
    entity_dir = root / "entities" / "地点" / "景区" / "毕棚沟"
    entity_assets = entity_dir / "assets"
    entity_assets.mkdir(parents=True, exist_ok=True)
    (entity_assets / "毕棚沟_homepage_detail.png").write_bytes(b"fake-png-detail")
    (entity_dir / "page.md").write_text(
        "# 毕棚沟\n\n{asset://毕棚沟_homepage_detail|wrapRight|毕棚沟细节图|width=45%}\n",
        encoding="utf-8",
    )
    write_json(entity_dir / "_entity.json", {"label": "毕棚沟", "domain": "地点", "type": "景区"})
    write_json(
        entity_dir / "manifest.json",
        {
            "entityRef": "地点/景区/毕棚沟",
            "assets": [
                {
                    "assetId": "毕棚沟_homepage_detail",
                    "fileName": "毕棚沟_homepage_detail.png",
                    "caption": "毕棚沟细节图",
                    "role": "detail",
                }
            ],
        },
    )

    post_dir = root / "posts" / "article" / "攻略" / "毕棚沟攻略" / "1"
    post_assets = post_dir / "assets"
    post_assets.mkdir(parents=True, exist_ok=True)
    (post_assets / "cover.jpg").write_bytes(b"fake-jpg-cover")
    (post_dir / "article.md").write_text(
        "# 毕棚沟攻略\n\n![封面](asset://cover)\n",
        encoding="utf-8",
    )
    write_json(
        post_dir / "manifest.json",
        {
            "contentType": "article",
            "assets": [
                {
                    "assetId": "cover",
                    "fileName": "cover.jpg",
                    "caption": "封面",
                    "kind": "image",
                }
            ],
            "articleAssetManifest": {"assets": [{"assetId": "cover"}]},
        },
    )
    return root


def test_materialize_release_media_updates_manifests_and_library():
    root = _seed_publish_root()
    manifest = materialize_release_media(
        env="prod",
        release_id="rel_media",
        post_refs=["posts/article/攻略/毕棚沟攻略/1"],
        entity_refs=["地点/景区/毕棚沟"],
        publish_root=root,
        image_cdn_base_url="https://img.example.com",
    )

    assert manifest["counts"]["assets"] == 2
    assert manifest["counts"]["imageAssets"] == 2
    assert manifest["counts"]["variants"] == 10
    assert manifest["counts"]["issues"] == 0
    assert manifest["operationalTargets"]["dailyVisits"] == 100000
    assert (root / manifest["path"]).is_file()

    entity_manifest = read_json(root / "entities" / "地点" / "景区" / "毕棚沟" / "manifest.json")
    entity_asset = entity_manifest["assets"][0]
    assert is_cas_media_object_key(entity_asset["objectKey"])
    assert entity_asset["cdnUrl"].startswith("https://img.example.com/media/objects/sha256/")
    assert "x-oss-process=" in entity_asset["cdnUrl"]
    assert entity_asset["sha256"] == sha256_file(root / "entities" / "地点" / "景区" / "毕棚沟" / "assets" / "毕棚沟_homepage_detail.png")
    assert (root / "media" / "library" / entity_asset["objectKey"]).is_file()
    assert set(entity_asset["variants"]) >= {"thumbnail", "display", "cover", "full", "original"}
    assert entity_asset["variants"]["display"]["profile"] == "display"
    assert entity_asset["variants"]["display"]["cdnUrl"].startswith("https://img.example.com/")
    assert entity_asset["variants"]["display"]["sourceSha256"] == entity_asset["sha256"]
    assert entity_asset["variants"]["original"]["cdnUrl"] == ""
    assert entity_asset["variants"]["original"]["requiresAccess"] is True

    post_manifest = read_json(root / "posts" / "article" / "攻略" / "毕棚沟攻略" / "1" / "manifest.json")
    article_asset = post_manifest["articleAssetManifest"]["assets"][0]
    assert is_cas_media_object_key(article_asset["objectKey"])
    assert article_asset["cdnUrl"].startswith("https://img.example.com/media/objects/sha256/")
    assert article_asset["variants"]["thumbnail"]["width"] == 320
    assert article_asset["variants"]["full"]["width"] == 2048


def test_object_key_uses_content_hash_only():
    old_key = build_object_key(
        source_owner="qwq_data",
        env="prod",
        scope="cold_start",
        object_type="entity_homepage",
        stable_object_ref="地点/景区/同名",
        asset_id="cover",
        sha256="sha256:" + "a" * 64,
        ext=".jpg",
        kind="image",
    )
    changed_content_key = build_object_key(
        source_owner="qwq_data",
        env="prod",
        scope="cold_start",
        object_type="entity_homepage",
        stable_object_ref="地点/景区/同名",
        asset_id="cover",
        sha256="sha256:" + "b" * 64,
        ext=".jpg",
        kind="image",
    )
    other_entity_key = build_object_key(
        source_owner="qwq_data",
        env="prod",
        scope="cold_start",
        object_type="entity_homepage",
        stable_object_ref="地点/景区/另一个同名",
        asset_id="cover",
        sha256="sha256:" + "a" * 64,
        ext=".jpg",
        kind="image",
    )

    assert old_key != changed_content_key
    assert old_key == other_entity_key
    assert old_key == "media/objects/sha256/aa/aa/" + ("a" * 64) + ".jpg"


def test_materialize_release_media_records_video_stage_one_variants():
    root = Path(tempfile.mkdtemp(prefix="media_video_asset_url_"))
    post_dir = root / "posts" / "video" / "旅行" / "雪山视频" / "1"
    post_assets = post_dir / "assets"
    post_assets.mkdir(parents=True, exist_ok=True)
    (post_assets / "clip.mp4").write_bytes(b"fake-mp4")
    write_json(
        post_dir / "manifest.json",
        {
            "contentType": "video",
            "assets": [
                {
                    "assetId": "clip",
                    "fileName": "clip.mp4",
                    "kind": "video",
                    "durationMs": 12000,
                }
            ],
        },
    )

    manifest = materialize_release_media(
        env="gamma",
        release_id="rel_video",
        post_refs=["posts/video/旅行/雪山视频/1"],
        entity_refs=[],
        publish_root=root,
        video_cdn_base_url="https://video.example.com",
    )

    assert manifest["counts"]["videoAssets"] == 1
    video_asset = manifest["assets"][0]
    assert set(video_asset["variants"]) >= {"adaptive", "original"}
    assert video_asset["variants"]["adaptive"]["cdnUrl"].startswith("https://video.example.com/")
    assert video_asset["variants"]["original"]["cdnUrl"] == ""
    assert video_asset["variants"]["original"]["requiresAccess"] is True


def test_collision_ledger_blocks_same_object_key_with_different_sha():
    root = _seed_publish_root()
    source = root / "entities" / "地点" / "景区" / "毕棚沟" / "assets" / "毕棚沟_homepage_detail.png"
    digest = sha256_file(source)
    key = build_object_key(
        source_owner="qwq_data",
        env="prod",
        scope="cold_start",
        object_type="entity_homepage",
        stable_object_ref="地点/景区/毕棚沟",
        asset_id="毕棚沟_homepage_detail",
        sha256=digest,
        ext=".png",
        kind="image",
    )
    write_json(
        root / "media" / "collision_ledger.json",
        {
            "schemaVersion": "quwoquan.media_collision_ledger.v1",
            "objects": {
                digest: {
                    "sha256": digest,
                    "objectKey": "media/objects/sha256/00/00/" + ("0" * 64) + ".png",
                    "refs": [
                        {
                            "sourceRef": "old",
                            "releaseId": "old",
                        }
                    ],
                }
            },
        },
    )

    manifest = materialize_release_media(
        env="prod",
        release_id="rel_media",
        post_refs=[],
        entity_refs=["地点/景区/毕棚沟"],
        publish_root=root,
        image_cdn_base_url="https://img.example.com",
    )

    assert manifest["counts"]["issues"] == 1
    assert "multiple objectKeys" in manifest["issues"][0]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"media asset url tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
