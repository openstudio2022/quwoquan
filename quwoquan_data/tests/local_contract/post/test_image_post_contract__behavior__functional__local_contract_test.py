"""Structured image-work contract tests for materialize and content.release.canonical."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from content.execution.stage_reports import write_stage_result  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402
from content.post.materialize_contract import _image_source_contract  # noqa: E402
from content.post.object_index import register_content_object  # noqa: E402
from content.release.canonical import assemble as publish_assemble  # noqa: E402
from content.release.canonical import gate as publish_gate  # noqa: E402
from content.source.source_assets import object_image_candidates  # noqa: E402
from content.source.source_unit import write_source_unit  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.paths import (  # noqa: E402
    ensure_execution_command_layout,
    ensure_execution_layout,
    execution_root,
)
from core.provenance import provenance_issues  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402
from support.image_fixture import jpeg_bytes  # noqa: E402

EXECUTION_ID = "20260711--travel-image-post-contract--test-region-a--pilot-001"
REF = "空标题图片作品"
SOURCE_ATTRIBUTION = {
    "isOriginal": False,
    "originalCreatorId": None,
    "originalCreatorName": "摄影师甲",
    "originalCreatorProfileUrl": "https://example.com/creator/a",
    "platform": "fixture",
    "sourcePostUrl": "https://example.com/collections/alpine",
    "originalAssetUrl": "https://example.com/collections/alpine/original.jpg",
    "attributionText": "摄影师甲 / CC-BY-4.0",
    "rightsBasis": "CC-BY-4.0",
    "commercialAuthorizationStatus": "verified",
    "publicationAdmission": "commercial_release",
    "authorizationProofUrl": "https://example.com/licenses/alpine",
    "termsUrl": "https://example.com/licenses/alpine",
    "riskAcceptanceId": None,
    "watermarkStatus": "absent",
    "audioRightsStatus": "no_audio",
    "modelReleaseStatus": "not_required",
    "propertyReleaseStatus": "not_required",
    "collectedAt": "2026-06-13T00:00:00Z",
    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
}


def _seed_source_collection() -> list[dict]:
    build_execution_fixture(EXECUTION_ID)
    object_dir = execution_root(EXECUTION_ID) / "download" / "objects" / "结构化组图"
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
                "bytes": jpeg_bytes(seed=1),
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
                "bytes": jpeg_bytes(seed=2),
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
        execution_id=EXECUTION_ID,
        source={"sourceAttribution": SOURCE_ATTRIBUTION},
    )
    return object_image_candidates(object_dir, EXECUTION_ID)


def test_object_image_candidates_preserve_sha_and_rights_metadata():
    first, second = _seed_source_collection()
    assert first["sha256"].startswith("sha256:")
    assert second["sha256"].startswith("sha256:")
    assert first["sourceCollectionId"] == "collection-alpine-001"
    assert first["creator"] == "摄影师甲"
    assert first["collectionPageUrl"] == "https://example.com/collections/alpine"
    assert first["license"] == "CC-BY-4.0"


def _seed_image_post(*, public_title: str = "结构化组图") -> None:
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "post")
    register_content_object(EXECUTION_ID, REF, content_type="image", angle="画报", title="结构化组图")
    write_stage_result(
        EXECUTION_ID,
        "post",
        "review",
        REF,
        {"decision": "approved", "checks": {"rights": {"passed": True, "issues": []}}},
    )
    first, second = _seed_source_collection()
    write_stage_result(
        EXECUTION_ID,
        "post",
        "compose",
        REF,
        {
            "topicId": REF,
            "contentType": "image",
            "carrier": "image",
            "vertical": "travel",
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
                    "rightsAuditStatus": "verified",
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
                    "rightsAuditStatus": "verified",
                },
            ],
            "publishLayout": "gallery",
            "publishTitle": public_title,
            "createdAt": "2026-06-13T00:00:00Z",
            "updatedAt": "2026-06-13T00:00:00Z",
        },
    )


def _materialize_image(*, public_title: str = "结构化组图") -> Path:
    import shutil

    posts = execution_root(EXECUTION_ID) / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    shared = execution_root(EXECUTION_ID) / "_shared"
    if shared.exists():
        shutil.rmtree(shared)
    build_execution_fixture(EXECUTION_ID)
    _seed_image_post(public_title=public_title)
    materialized = materialize_posts(EXECUTION_ID, "image")
    assert len(materialized) == 1, materialized
    return materialized[0]


def test_image_materialize_is_structured_only():
    post_dir = _materialize_image()
    assert (post_dir / "manifest.json").is_file()
    assert (post_dir / "assets" / "alpine_01.jpg").is_file()
    assert (post_dir / "assets" / "alpine_02.jpg").is_file()
    assert not (post_dir / "article.md").exists()
    assert not (post_dir / "gallery.md").exists()
    # 资产型作品同样必须保留终态证据，避免发布面只有素材却无 review 闭环。
    finalization = read_json(post_dir / "5.review" / "finalization_report.json")
    assert finalization["articleSource"] == "4.draft/draft_meta.json"
    assert finalization["normalizationActions"] == ["asset_only_finalization"]

    manifest = read_json(post_dir / "manifest.json")
    assert manifest["contentType"] == "image"
    assert manifest["contentIdentity"] == "work"
    assert manifest["title"] == ""
    assert manifest["caption"] == ""
    assert len(manifest["assets"]) == 2
    assert manifest["sourceCollectionId"] == "collection-alpine-001"
    assert manifest["creator"]["name"] == "摄影师甲"
    assert manifest["collectionPageUrl"] == "https://example.com/collections/alpine"
    assert manifest["license"] == "CC-BY-4.0"
    assert manifest["termsUrl"] == "https://example.com/licenses/alpine"
    assert manifest["authorizationProof"] == "https://example.com/licenses/alpine"
    assert manifest["sourceAttribution"] == SOURCE_ATTRIBUTION
    assert "licenseProof" not in manifest
    assert provenance_issues(post_dir, manifest) == []


def test_image_materialize_does_not_backfill_publish_title_from_object_coords():
    post_dir = _materialize_image(public_title="")
    manifest = read_json(post_dir / "manifest.json")
    assert manifest["title"] == ""
    assert manifest["publishTitle"] == ""


def test_image_materialize_writes_download_stage_source_refs():
    """图片作品也必须自持 1.download/source_refs.json，阶段树不再缺 1.download。"""
    post_dir = _materialize_image()
    snapshot = post_dir / "1.download" / "source_refs.json"
    assert snapshot.is_file(), "图片作品缺 1.download/source_refs.json"
    data = read_json(snapshot)
    # 图片作品的底稿来源单元 = 资产所属同一图集 source unit。
    assert data["schema"] == "quwoquan_data.source_refs"
    assert data["baseSourceRef"], data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["role"] == "base"
    assert "citedSourceRefs" not in data
    assert "sourcePaths" not in data
    assert (post_dir / "5.review" / "finalization_report.json").is_file()


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
            vertical="travel",
        )
    except RuntimeError as exc:
        assert "share one collectionPageUrl" in str(exc)
    else:
        raise AssertionError("mixed source pages must be rejected")


def test_image_source_contract_rejects_retired_alias_keys():
    try:
        _image_source_contract(
            {
                "collectionId": "collection-1",
                "credit": "creator-1",
                "page": "https://example.com/page",
                "license": "CC-BY-4.0",
                "licenseProof": {
                    "termsUrl": "https://example.com/license",
                    "proofUrl": "https://example.com/proof",
                },
            },
            [],
            ref="retired-aliases",
            vertical="travel",
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "retired image source aliases" in message
        assert "collectionId->sourceCollectionId" in message
        assert "licenseProof->termsUrl/authorizationProof" in message
    else:
        raise AssertionError("retired image source aliases must be rejected")


def test_release_assembles_image_without_markdown_and_article_with_article_only():
    image_dir = _materialize_image()
    execution_dir = Path(tempfile.mkdtemp(prefix="image_contract_execution_"))
    execution_posts = execution_dir / "posts"
    image_src = execution_posts / image_dir.relative_to(execution_root(EXECUTION_ID) / "posts")
    image_src.parent.mkdir(parents=True, exist_ok=True)

    import shutil

    shutil.copytree(image_dir, image_src)

    article_src = execution_posts / "article" / "攻略" / "文章作品" / "1"
    article_src.mkdir(parents=True, exist_ok=True)
    (article_src / "article.md").write_text("# 文章作品\n\n正文。", encoding="utf-8")
    write_json(article_src / "5.review" / "attestation.json", {"decision": "approved"})
    write_json(
        article_src / "5.review" / "evidence_index.json",
        {"schema": "quwoquan_data.evidence_index", "evidence": []},
    )
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
    old_execution_root = publish_assemble.execution_root
    old_release_root = publish_assemble.release_root
    old_copy_entities = publish_assemble._copy_release_entities
    old_gate_release_root = publish_gate.release_root
    try:
        publish_assemble.execution_root = lambda _execution_id: execution_dir
        publish_assemble.release_root = lambda release_id: release_base / release_id
        publish_assemble._copy_release_entities = lambda *_args, **_kwargs: None
        publish_gate.release_root = lambda release_id: release_base / release_id

        release = publish_assemble.assemble_release(EXECUTION_ID, "r1")
        image_release = release / "posts" / image_src.relative_to(execution_posts)
        article_release = release / "posts" / article_src.relative_to(execution_posts)
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
        publish_assemble.execution_root = old_execution_root
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
