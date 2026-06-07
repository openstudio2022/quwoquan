"""环境数据 release contract 与一致性扫描契约。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import write_json  # noqa: E402
from ship.consistency import scan_release_contract  # noqa: E402
from ship.release_contract import build_release_contract  # noqa: E402
from ship.sampler import build_sample_bundle  # noqa: E402


MANIFEST = {
    "salt": "release-test",
    "defaults": {"sampleRatio": 1.0, "postCapPerBucket": 0, "entityCapPerBucket": 0, "maxPosts": 0, "maxEntities": 0},
    "environments": {"gamma": {}, "prod": {"sampleRatio": 1.0}},
}


def _publish_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="data_release_"))
    write_json(root / "tags" / "Topic" / "旅行" / "_definition.json", {"label": "旅行"})
    write_json(root / "entities" / "地点" / "景区" / "甲居藏寨" / "_entity.json", {"label": "甲居藏寨"})
    (root / "entities" / "地点" / "景区" / "甲居藏寨" / "page.md").write_text("# 甲居藏寨\n", encoding="utf-8")
    return root


def test_sample_bundle_closes_selected_post_entities():
    posts = [
        {
            "postRef": "posts/article/体验/甲居藏寨体验/1",
            "contentType": "article",
            "angle": "体验",
            "entityRefs": ["地点/景区/甲居藏寨"],
        }
    ]
    entities = [{"entityRef": "地点/景区/甲居藏寨", "domain": "地点", "etype": "景区"}]
    bundle = build_sample_bundle("gamma", MANIFEST, posts, entities)
    assert "地点/景区/甲居藏寨" in bundle["entities"], "post 入选时引用 entity 必须同批入选"


def test_release_contract_and_consistency_pass_for_closed_refs():
    root = _publish_root()
    posts = [
        {
            "postRef": "posts/article/体验/甲居藏寨体验/1",
            "contentType": "article",
            "angle": "体验",
            "entityRefs": ["地点/景区/甲居藏寨"],
            "tagRefs": ["Topic/旅行"],
        }
    ]
    entities = [{"entityRef": "地点/景区/甲居藏寨", "domain": "地点", "etype": "景区"}]
    bundle = build_sample_bundle("gamma", MANIFEST, posts, entities)
    contract = build_release_contract(
        env="gamma",
        bundle=bundle,
        posts=posts,
        entities=entities,
        release_id="rel_gamma_001",
    )
    report = scan_release_contract(contract, publish_root=root)
    assert report["status"] == "passed", report
    assert contract["releaseId"] == "rel_gamma_001"
    assert contract["counts"]["actions"] == 2


def test_release_consistency_blocks_media_manifest_issues():
    root = _publish_root()
    write_json(
        root / "media" / "releases" / "rel_media_bad" / "gamma.json",
        {
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "releaseId": "rel_media_bad",
            "environment": "gamma",
            "assets": [],
            "issues": ["地点/景区/甲居藏寨: asset file missing on disk"],
            "counts": {"assets": 0, "issues": 1},
        },
    )
    contract = build_release_contract(
        env="gamma",
        bundle={
            "environment": "gamma",
            "posts": [],
            "entities": ["地点/景区/甲居藏寨"],
            "counts": {},
        },
        posts=[],
        entities=[{"entityRef": "地点/景区/甲居藏寨", "domain": "地点", "etype": "景区"}],
        release_id="rel_media_bad",
        media_manifest={
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "path": "media/releases/rel_media_bad/gamma.json",
            "counts": {"assets": 0, "issues": 1},
        },
    )

    report = scan_release_contract(contract, publish_root=root)

    assert report["status"] == "failed"
    assert any(i["code"] == "media_manifest_issue" for i in report["blockingIssues"])


def test_release_consistency_blocks_invalid_media_url():
    root = _publish_root()
    object_key = "media/objects/sha256/aa/aa/" + ("a" * 64) + ".png"
    media_file = root / "media" / "library" / object_key
    media_file.parent.mkdir(parents=True, exist_ok=True)
    media_file.write_bytes(b"asset")
    write_json(
        root / "media" / "releases" / "rel_media_url_bad" / "gamma.json",
        {
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "releaseId": "rel_media_url_bad",
            "environment": "gamma",
            "assets": [
                {
                    "assetId": "cover",
                    "kind": "image",
                    "objectKey": object_key,
                    "cdnUrl": "http://cdn.example.com/" + object_key,
                    "sha256": "sha256:" + "a" * 64,
                    "libraryPath": "media/library/" + object_key,
                }
            ],
            "issues": [],
            "counts": {"assets": 1, "issues": 0},
        },
    )
    contract = build_release_contract(
        env="gamma",
        bundle={"environment": "gamma", "posts": [], "entities": [], "counts": {}},
        posts=[],
        entities=[],
        release_id="rel_media_url_bad",
        media_manifest={
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "path": "media/releases/rel_media_url_bad/gamma.json",
            "counts": {"assets": 1, "issues": 0},
        },
    )

    report = scan_release_contract(contract, publish_root=root)

    assert report["status"] == "failed"
    assert any(i["code"] == "media_asset_invalid_cdn_url" for i in report["blockingIssues"])


def test_release_consistency_blocks_duplicate_sha_with_different_object_key():
    root = _publish_root()
    object_key_a = "media/objects/sha256/aa/aa/" + ("a" * 64) + ".png"
    object_key_b = "media/objects/sha256/bb/bb/" + ("b" * 64) + ".png"
    media_file_a = root / "media" / "library" / object_key_a
    media_file_b = root / "media" / "library" / object_key_b
    media_file_a.parent.mkdir(parents=True, exist_ok=True)
    media_file_b.parent.mkdir(parents=True, exist_ok=True)
    payload = b"same-asset"
    media_file_a.write_bytes(payload)
    media_file_b.write_bytes(payload)
    digest = "sha256:" + __import__("hashlib").sha256(payload).hexdigest()
    write_json(
        root / "media" / "releases" / "rel_media_dup_sha" / "gamma.json",
        {
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "releaseId": "rel_media_dup_sha",
            "environment": "gamma",
            "assets": [
                {
                    "assetId": "cover",
                    "kind": "image",
                    "objectKey": object_key_a,
                    "cdnUrl": "https://cdn.example.com/" + object_key_a,
                    "sha256": digest,
                    "libraryPath": "media/library/" + object_key_a,
                },
                {
                    "assetId": "cover2",
                    "kind": "image",
                    "objectKey": object_key_b,
                    "cdnUrl": "https://cdn.example.com/" + object_key_b,
                    "sha256": digest,
                    "libraryPath": "media/library/" + object_key_b,
                },
            ],
            "issues": [],
            "counts": {"assets": 2, "issues": 0},
        },
    )
    contract = build_release_contract(
        env="gamma",
        bundle={"environment": "gamma", "posts": [], "entities": [], "counts": {}},
        posts=[],
        entities=[],
        release_id="rel_media_dup_sha",
        media_manifest={
            "schemaVersion": "quwoquan.media_asset_manifest.v1",
            "path": "media/releases/rel_media_dup_sha/gamma.json",
            "counts": {"assets": 2, "issues": 0},
        },
    )
    report = scan_release_contract(contract, publish_root=root)
    assert report["status"] == "failed"
    assert any(i["code"] == "media_asset_duplicate_sha_object_key" for i in report["blockingIssues"])


def test_consistency_blocks_dangling_post_entity_ref():
    root = _publish_root()
    posts = [
        {
            "postRef": "posts/article/体验/孤儿内容/1",
            "contentType": "article",
            "angle": "体验",
            "entityRefs": ["地点/景区/不存在"],
            "tagRefs": ["Topic/旅行"],
        }
    ]
    bundle = {
        "schemaVersion": "quwoquan.content_sample_bundle",
        "environment": "gamma",
        "sampleRatio": 1.0,
        "salt": "release-test",
        "posts": ["posts/article/体验/孤儿内容/1"],
        "entities": [],
        "counts": {},
    }
    contract = build_release_contract(
        env="gamma",
        bundle=bundle,
        posts=posts,
        entities=[],
        release_id="rel_bad_001",
    )
    report = scan_release_contract(contract, publish_root=root)
    assert report["status"] == "failed"
    assert any(i["code"] == "dangling_post_entity_ref" for i in report["blockingIssues"])


def test_consistency_blocks_missing_fixture_author():
    root = _publish_root()
    metadata = root.parent / "metadata"
    write_json(metadata / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json", {
        "seedSets": {"core": {"profiles": [{"userId": "fixture_user_current"}]}}
    })
    posts = [
        {
            "postRef": "posts/article/体验/作者缺失/1",
            "contentType": "article",
            "angle": "体验",
            "entityRefs": ["地点/景区/甲居藏寨"],
            "tagRefs": ["Topic/旅行"],
            "authorId": "fixture_user_missing",
        }
    ]
    entities = [{"entityRef": "地点/景区/甲居藏寨", "domain": "地点", "etype": "景区"}]
    bundle = build_sample_bundle("gamma", MANIFEST, posts, entities)
    contract = build_release_contract(env="gamma", bundle=bundle, posts=posts, entities=entities, release_id="rel_bad_author")
    report = scan_release_contract(contract, publish_root=root, metadata_root=metadata)
    assert report["status"] == "failed"
    assert any(i["code"] == "dangling_post_fixture_author" for i in report["blockingIssues"])


def test_prod_hard_delete_requires_approval():
    try:
        build_release_contract(
            env="prod",
            bundle={"environment": "prod", "posts": [], "entities": [], "counts": {}},
            posts=[],
            entities=[],
            release_id="rel_prod_001",
            delete_policy="hard-delete",
        )
    except ValueError as exc:
        assert "approved_by" in str(exc)
    else:
        raise AssertionError("prod hard-delete without approval must fail")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"data release consistency tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
