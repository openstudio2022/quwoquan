"""Structured image-work contract tests for materialize and publish."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.content_object import register_content_object  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_root, ensure_batch_layout, ensure_task_layout  # noqa: E402
from _common.provenance import provenance_issues  # noqa: E402
from _common.source_unit import object_image_candidates, write_source_unit  # noqa: E402
from _common.stage_reports import write_stage_result  # noqa: E402
from produce.materialize import _image_source_contract, materialize_posts  # noqa: E402
from publish import assemble as publish_assemble  # noqa: E402
from publish import gate as publish_gate  # noqa: E402


TASK = "image_contract"
BATCH = "pilot"
REF = "空标题图片作品"


def _seed_source_collection() -> list[dict]:
    object_dir = batch_root(TASK, BATCH) / "download" / "objects" / "结构化组图"
    write_source_unit(
        object_dir,
        ordinal=1,
        source_id="alpine_collection",
        source_md="# 结构化组图来源\n\n同一摄影师同一作品集的授权图片。",
        platform="fixture",
        source_category="image_collection",
        source_use_mode="licensed_adaptation",
        source_role="image_base",
        image_evidence_mode="same_collection",
        research_lane="image",
        license_value="CC-BY-4.0",
        url="https://example.com/collections/alpine",
        title="结构化组图来源",
        images=[
            {
                "bytes": b"first-image",
                "slug": "alpine_01",
                "caption": "",
                "sourceCollectionId": "collection-alpine-001",
                "creator": "摄影师甲",
                "collectionPageUrl": "https://example.com/collections/alpine",
                "license": "CC-BY-4.0",
                "termsUrl": "https://example.com/licenses/alpine",
                "authorizationProof": "https://example.com/licenses/alpine",
                "usageScope": "commercial",
            },
            {
                "bytes": b"second-image",
                "slug": "alpine_02",
                "caption": "晨光",
                "sourceCollectionId": "collection-alpine-001",
                "creator": "摄影师甲",
                "collectionPageUrl": "https://example.com/collections/alpine",
                "license": "CC-BY-4.0",
                "termsUrl": "https://example.com/licenses/alpine",
                "authorizationProof": "https://example.com/licenses/alpine",
                "usageScope": "commercial",
            },
        ],
        task_id=TASK,
        batch_id=BATCH,
    )
    return object_image_candidates(object_dir, TASK, BATCH)


def test_object_image_candidates_preserve_sha_and_rights_metadata():
    first, second = _seed_source_collection()
    assert first["sha256"].startswith("sha256:")
    assert second["sha256"].startswith("sha256:")
    assert first["sourceCollectionId"] == "collection-alpine-001"
    assert first["creator"] == "摄影师甲"
    assert first["collectionPageUrl"] == "https://example.com/collections/alpine"
    assert first["license"] == "CC-BY-4.0"


def _seed_image_post() -> None:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "produce")
    register_content_object(TASK, BATCH, REF, content_type="image", angle="画报", title="结构化组图")
    write_stage_result(
        TASK,
        BATCH,
        "produce",
        "review",
        REF,
        {"decision": "approved", "checks": {"rights": {"passed": True, "issues": []}}},
    )
    first, second = _seed_source_collection()
    write_stage_result(
        TASK,
        BATCH,
        "produce",
        "compose",
        REF,
        {
            "topicId": REF,
            "contentType": "image",
            "carrier": "image",
            "generator": "image_evidence_pack",
            "title": "",
            "caption": "",
            "entityRefs": [],
            "tagRefs": ["Topic/摄影", "Format/内容载体/图文/图集"],
            "sourceUrls": ["https://example.com/collections/alpine"],
            "sourcePaths": [first["sourceRef"]],
            "assets": [
                {
                    "assetId": "alpine_01",
                    "fileName": "alpine_01.jpg",
                    "caption": "",
                    "sourcePath": str(first["path"]),
                    "sourceRef": first["sourceRef"],
                    "sourceAssetRef": first["sourceAssetRef"],
                    "sourceCollectionId": "collection-alpine-001",
                    "creator": {"name": "摄影师甲", "profileUrl": "https://example.com/creator/a"},
                    "collectionPageUrl": "https://example.com/collections/alpine",
                    "license": "CC-BY-4.0",
                    "termsUrl": "https://example.com/licenses/alpine",
                    "authorizationProof": "https://example.com/licenses/alpine",
                },
                {
                    "assetId": "alpine_02",
                    "fileName": "alpine_02.jpg",
                    "caption": "晨光",
                    "sourcePath": str(second["path"]),
                    "sourceRef": second["sourceRef"],
                    "sourceAssetRef": second["sourceAssetRef"],
                    "sourceCollectionId": "collection-alpine-001",
                    "creator": {"name": "摄影师甲", "profileUrl": "https://example.com/creator/a"},
                    "collectionPageUrl": "https://example.com/collections/alpine",
                    "license": "CC-BY-4.0",
                    "termsUrl": "https://example.com/licenses/alpine",
                    "authorizationProof": "https://example.com/licenses/alpine",
                },
            ],
            "publishLayout": "gallery",
            "publishTitle": "结构化组图",
            "createdAt": "2026-06-13T00:00:00Z",
            "updatedAt": "2026-06-13T00:00:00Z",
        },
    )


def _materialize_image() -> Path:
    import shutil

    posts = batch_root(TASK, BATCH) / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    shared = batch_root(TASK, BATCH) / "_shared"
    if shared.exists():
        shutil.rmtree(shared)
    _seed_image_post()
    materialized = materialize_posts(TASK, BATCH, "image")
    assert len(materialized) == 1, materialized
    return materialized[0]


def test_image_materialize_is_structured_only():
    post_dir = _materialize_image()
    assert (post_dir / "manifest.json").is_file()
    assert (post_dir / "assets" / "alpine_01.jpg").is_file()
    assert (post_dir / "assets" / "alpine_02.jpg").is_file()
    assert not (post_dir / "article.md").exists()
    assert not (post_dir / "gallery.md").exists()
    assert not (post_dir / "5.review" / "finalization_report.json").exists()

    manifest = read_json(post_dir / "manifest.json")
    assert manifest["contentType"] == "image"
    assert manifest["title"] == ""
    assert manifest["caption"] == ""
    assert len(manifest["assets"]) == 2
    assert manifest["sourceCollectionId"] == "collection-alpine-001"
    assert manifest["creator"]["name"] == "摄影师甲"
    assert manifest["page"] == "https://example.com/collections/alpine"
    assert manifest["sourceCollectionUrl"] == "https://example.com/collections/alpine"
    assert manifest["licenseProof"] == {
        "license": "CC-BY-4.0",
        "termsUrl": "https://example.com/licenses/alpine",
        "proofUrl": "https://example.com/licenses/alpine",
    }
    assert manifest["licenseProofRef"] == "https://example.com/licenses/alpine"
    assert provenance_issues(post_dir, manifest) == []


def test_image_materialize_writes_download_stage_source_refs():
    """图片作品也必须自持 1.download/source_refs.json，阶段树不再缺 1.download。"""
    post_dir = _materialize_image()
    snapshot = post_dir / "1.download" / "source_refs.json"
    assert snapshot.is_file(), "图片作品缺 1.download/source_refs.json"
    data = read_json(snapshot)
    # 单底稿零参考 v2：图片作品的底稿来源单元 = 资产所属同一图集 source unit。
    assert data["schemaVersion"] == "quwoquan_data.source_refs/2"
    assert data["baseSourceRef"], data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["role"] == "base"
    assert "citedSourceRefs" not in data
    assert "sourcePaths" not in data
    assert not (post_dir / "5.review" / "finalization_report.json").exists()


def test_image_source_contract_rejects_mixed_pages():
    try:
        _image_source_contract(
            {
                "sourceCollectionId": "collection-1",
                "creator": "creator-1",
                "license": "CC-BY-4.0",
                "termsUrl": "https://example.com/license",
            },
            [
                {"collectionPageUrl": "https://example.com/page/1"},
                {"collectionPageUrl": "https://example.com/page/2"},
            ],
            ref="mixed",
        )
    except RuntimeError as exc:
        assert "share one collectionPageUrl" in str(exc)
    else:
        raise AssertionError("mixed source pages must be rejected")


def test_release_assembles_image_without_markdown_and_article_with_article_only():
    image_dir = _materialize_image()
    task_dir = Path(tempfile.mkdtemp(prefix="image_contract_task_"))
    batch_posts = task_dir / "batches" / BATCH / "posts"
    image_src = batch_posts / image_dir.relative_to(batch_root(TASK, BATCH) / "posts")
    image_src.parent.mkdir(parents=True, exist_ok=True)

    import shutil

    shutil.copytree(image_dir, image_src)
    (image_src / "article.md").write_text("legacy article", encoding="utf-8")
    (image_src / "gallery.md").write_text("legacy gallery", encoding="utf-8")

    article_src = batch_posts / "article" / "攻略" / "文章作品" / "1"
    article_src.mkdir(parents=True, exist_ok=True)
    (article_src / "article.md").write_text("# 文章作品\n\n正文。", encoding="utf-8")
    (article_src / "gallery.md").write_text("legacy gallery", encoding="utf-8")
    write_json(
        article_src / "manifest.json",
        {
            "topicId": "article",
            "contentType": "article",
            "carrier": "article",
            "entityRefs": [],
            "tagRefs": [],
            "sourceUrls": [],
            "assets": [],
        },
    )

    release_base = Path(tempfile.mkdtemp(prefix="image_contract_release_"))
    # 顶层批次布局：assemble 经 batch_root(task,batch) 定位批次（不再走 task_root/"batches"）。
    old_batch_root = publish_assemble.batch_root
    old_release_root = publish_assemble.release_root
    old_copy_entities = publish_assemble._copy_release_entities
    old_gate_release_root = publish_gate.release_root
    try:
        publish_assemble.batch_root = lambda _task_id, _batch_id: task_dir / "batches" / BATCH
        publish_assemble.release_root = lambda release_id: release_base / release_id
        publish_assemble._copy_release_entities = lambda *_args, **_kwargs: None
        publish_gate.release_root = lambda release_id: release_base / release_id

        release = publish_assemble.assemble_release(TASK, "r1", batch_id=BATCH)
        image_release = release / "posts" / image_src.relative_to(batch_posts)
        article_release = release / "posts" / article_src.relative_to(batch_posts)
        assert (image_release / "manifest.json").is_file()
        assert not (image_release / "article.md").exists()
        assert not (image_release / "gallery.md").exists()
        assert (article_release / "article.md").is_file()
        assert not (article_release / "gallery.md").exists()

        entity_page = release / "entities" / "地点" / "景区" / "占位实体" / "page.md"
        entity_page.parent.mkdir(parents=True, exist_ok=True)
        entity_page.write_text("# 占位实体", encoding="utf-8")
        assert publish_gate._release_surface_issues(release) == []
    finally:
        publish_assemble.batch_root = old_batch_root
        publish_assemble.release_root = old_release_root
        publish_assemble._copy_release_entities = old_copy_entities
        publish_gate.release_root = old_gate_release_root


def test_publish_gate_rejects_image_markdown_and_asset_overflow():
    root = Path(tempfile.mkdtemp(prefix="image_contract_gate_"))
    leaf = root / "posts" / "image" / "画报" / "坏图片作品" / "1"
    leaf.mkdir(parents=True)
    (leaf / "article.md").write_text("forbidden", encoding="utf-8")
    manifest = {
        "contentType": "image",
        "title": "",
        "caption": "",
        "sourceCollectionId": "c",
        "creator": "creator",
        "collectionPageUrl": "https://example.com/page",
        "license": "CC-BY-4.0",
        "termsUrl": "https://example.com/proof",
        "assets": [{"assetId": str(index), "fileName": f"{index}.jpg"} for index in range(21)],
    }
    issues = publish_gate._post_contract_issues(leaf, root, manifest)
    assert any("must not contain article.md or gallery.md" in issue for issue in issues)
    assert any("must contain 1..20 assets" in issue for issue in issues)


def _run_all() -> None:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"image post contract tests passed ({len(tests)})")


if __name__ == "__main__":
    _run_all()
