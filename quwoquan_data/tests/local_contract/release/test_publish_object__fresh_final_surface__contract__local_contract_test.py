# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from content.release.canonical.final_surface_projection import (
    project_publish_final_surface,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.schema import assert_valid

EXECUTION_ID = "20260906--travel-image-final-surface--test-region-a--pilot-001"
TARGET_REF = "posts/image/建筑/西门入口/1"
SOURCE_REF = "sources/commons/source.md"
ASSET_REF = "sources/commons/assets/cover.jpg"
CREATOR_PROFILE = "qwq_creator_landscape_photographer_001"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / EXECUTION_ID
    obj = root / TARGET_REF
    source = root / SOURCE_REF
    source.parent.mkdir(parents=True)
    source.write_text("# Commons source\n", encoding="utf-8")
    asset = root / ASSET_REF
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"reviewed-image-bytes")
    _write_json(
        root / "sources/commons/meta.json",
        {
            "sourceId": "commons",
            "canonicalUrl": "https://commons.example.test/file",
            "sourceUseMode": "licensed_adaptation",
            "sourceClass": "open_license_media",
            "fetchedAt": "2026-09-06T00:00:00Z",
            "rightsClue": "作者 Fixture Photographer，CC BY 4.0。",
        },
    )
    _write_json(
        root / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "fileName": "cover.jpg",
                    "sourceAssetId": "cover",
                    "assetRole": "image",
                    "mimeType": "image/jpeg",
                    "sourceUrl": "https://commons.example.test/file",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0",
                    "authorizationProof": "https://commons.example.test/file",
                    "rightsStatus": "verified",
                    "rightsIssues": [],
                    "distributionDecision": "commercial_allowed",
                    "acquisitionReceiptRef": "receipts/acquired.json",
                }
            ]
        },
    )
    _write_json(
        obj / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceId": "commons",
                    "sourceRef": SOURCE_REF,
                    "metaRef": "sources/commons/meta.json",
                    "sourceUrl": "https://commons.example.test/file",
                }
            ]
        },
    )
    _write_json(
        obj / "3.compose/writing_pack.json",
        {
            "vertical": "travel",
            "title": "西门入口",
            "publishLayout": "image",
            "creatorProfileRef": CREATOR_PROFILE,
            "selectedSourceRefs": [SOURCE_REF],
            "tagRefs": ["Entity/地点/景区"],
        },
    )
    _write_json(
        obj / "4.draft/image_work.json",
        {
            "schema": "quwoquan_data.image_work",
            "executionId": EXECUTION_ID,
            "objectRef": TARGET_REF,
            "assetRefs": [ASSET_REF],
            "caption": "西门入口实景。",
        },
    )
    _write_json(
        root / "_shared/receipts/006-4.draft.json",
        {"actor": {"invocation": {"model": "fixture-model"}}},
    )
    target = {
        "name": "西门",
        "entityType": "地点/景区",
        "publishAngle": "建筑",
        "publishTitle": "西门入口",
        "publishSeq": 1,
        "region": "中国/测试区",
    }
    return root, obj, target


def _project(root: Path, obj: Path, target: dict[str, object]) -> dict[str, object]:
    return project_publish_final_surface(
        execution_root=root,
        object_dir=obj,
        target_ref=TARGET_REF,
        target=target,
        carrier="image",
    )



def test_fresh_object_without_manifest_projects_stable_publish_surface(
    tmp_path: Path,
) -> None:
    root, obj, target = _fixture(tmp_path)
    assert not (obj / "manifest.json").exists()

    first = _project(root, obj, target)
    manifest_bytes = (obj / "manifest.json").read_bytes()
    asset_bytes = (obj / "assets/cover.jpg").read_bytes()
    second = _project(root, obj, target)

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert (obj / "manifest.json").read_bytes() == manifest_bytes
    assert (obj / "assets/cover.jpg").read_bytes() == asset_bytes
    manifest = json.loads(manifest_bytes)
    assert_valid(manifest, "content", "post_manifest")
    assert [asset["sourceAssetRef"] for asset in manifest["assets"]] == [ASSET_REF]


def test_final_surface_rejects_selected_asset_set_drift(tmp_path: Path) -> None:
    root, obj, target = _fixture(tmp_path)
    _project(root, obj, target)
    draft_path = obj / "4.draft/image_work.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["assetRefs"] = []
    _write_json(draft_path, draft)

    with pytest.raises(ObjectTransactionError, match="unique selected assets"):
        _project(root, obj, target)


def test_final_surface_rejects_existing_manifest_drift(tmp_path: Path) -> None:
    root, obj, target = _fixture(tmp_path)
    _project(root, obj, target)
    manifest = json.loads((obj / "manifest.json").read_text(encoding="utf-8"))
    manifest["title"] = "drifted"
    _write_json(obj / "manifest.json", manifest)

    with pytest.raises(ObjectTransactionError, match="publish final surface drift"):
        _project(root, obj, target)


def _text_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    execution_id = "20260906--travel-article-final-surface--test-region-a--pilot-001"
    target_ref = "posts/article/攻略/西门入园/1"
    root = tmp_path / execution_id
    obj = root / target_ref
    source_ref = "sources/official/source.md"
    source = root / source_ref
    source.parent.mkdir(parents=True)
    source.write_text("# 官方预约事实\n", encoding="utf-8")
    _write_json(
        root / "sources/official/meta.json",
        {
            "sourceId": "official",
            "canonicalUrl": "https://example.test/official-guide",
            "sourceUseMode": "factual_reference_only",
            "sourceClass": "official_primary",
            "fetchedAt": "2026-09-06T00:00:00Z",
        },
    )
    _write_json(
        obj / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceId": "official",
                    "sourceRef": source_ref,
                    "metaRef": "sources/official/meta.json",
                    "sourceUrl": "https://example.test/official-guide",
                }
            ]
        },
    )
    _write_json(
        obj / "3.compose/writing_pack.json",
        {
            "vertical": "travel",
            "title": "西门入园攻略",
            "publishLayout": "article",
            "creatorProfileRef": "qwq_creator_landscape_photographer_001",
            "selectedSourceRefs": [source_ref],
            "tagRefs": ["Entity/地点/景区"],
        },
    )
    draft = obj / "4.draft/draft.article.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# 西门入园攻略\n\n按预约时段入园。\n", encoding="utf-8")
    _write_json(
        root / "_shared/receipts/006-4.draft.json",
        {"actor": {"invocation": {"model": "fixture-model"}}},
    )
    target = {
        "name": "西门",
        "entityType": "地点/景区",
        "publishAngle": "攻略",
        "publishTitle": "西门入园攻略",
        "publishSeq": 1,
        "region": "中国/测试区",
    }
    return root, obj, target


def test_article_projects_text_only_final_from_draft(tmp_path: Path) -> None:
    root, obj, target = _text_fixture(tmp_path)

    result = project_publish_final_surface(
        execution_root=root,
        object_dir=obj,
        target_ref="posts/article/攻略/西门入园/1",
        target=target,
        carrier="article",
    )

    manifest = json.loads((obj / "manifest.json").read_text(encoding="utf-8"))
    assert result["finalFiles"] == ["article.md", "manifest.json"]
    assert (obj / "article.md").read_bytes() == (
        obj / "4.draft/draft.article.md"
    ).read_bytes()
    assert manifest["publishMediaMode"] == "text_only"
    assert manifest["assets"] == []
    assert_valid(manifest, "content", "post_manifest")


def _homepage_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    execution_id = "20260906--travel-homepage-final-surface--test-region-a--pilot-001"
    target_ref = "entities/地点/景区/西门"
    root = tmp_path / execution_id
    obj = root / target_ref
    source_ref = "sources/wikipedia/source.md"
    source = root / source_ref
    source.parent.mkdir(parents=True)
    source.write_text("# 西门百科事实\n", encoding="utf-8")
    _write_json(
        root / "sources/wikipedia/meta.json",
        {
            "sourceId": "wikipedia",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/Test",
            "sourceUseMode": "licensed_adaptation",
            "sourceKind": "wikipedia",
            "title": "西门",
            "fetchedAt": "2026-09-06T00:00:00Z",
            "rawSha256": _digest(source),
        },
    )
    _write_json(
        obj / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceId": "wikipedia",
                    "sourceRef": source_ref,
                    "metaRef": "sources/wikipedia/meta.json",
                    "sourceUrl": "https://zh.wikipedia.org/wiki/Test",
                }
            ]
        },
    )
    _write_json(
        obj / "3.compose/entity_page_input.json",
        {
            "schema": "quwoquan_data.stage_envelope",
            "stage": "3.compose",
            "executionId": execution_id,
            "step": "entity_page",
            "ref": target_ref,
            "qualityRef": "2.quality/quality_analysis.json",
            "qualityDigest": "sha256:" + "1" * 64,
            "selectedSourceUrls": ["https://zh.wikipedia.org/wiki/Test"],
            "selectedSourceRefs": [source_ref],
            "payload": {
                "name": "西门",
                "entityRef": "/entity/地点/景区/西门",
                "baseDraft": {},
                "draftPage": "4.draft/page.md",
                "minChars": 1,
                "minSectionChars": 1,
            },
        },
    )
    page = obj / "4.draft/page.md"
    page.parent.mkdir(parents=True)
    page.write_text("# 西门\n\n百科主页正文。\n", encoding="utf-8")
    target = {
        "name": "西门",
        "entityType": "地点/景区",
        "region": "中国/测试区",
    }
    return root, obj, target


def test_homepage_projects_entity_page_manifest_and_source_catalog(
    tmp_path: Path,
) -> None:
    root, obj, target = _homepage_fixture(tmp_path)

    result = project_publish_final_surface(
        execution_root=root,
        object_dir=obj,
        target_ref="entities/地点/景区/西门",
        target=target,
        carrier="homepage",
    )

    assert result["finalFiles"] == [
        "_entity.json",
        "evidence/source_catalog.json",
        "manifest.json",
        "page.md",
    ]
    assert (obj / "page.md").read_bytes() == (obj / "4.draft/page.md").read_bytes()
    entity = json.loads((obj / "_entity.json").read_text(encoding="utf-8"))
    catalog = json.loads(
        (obj / "evidence/source_catalog.json").read_text(encoding="utf-8")
    )
    assert entity["entityRef"] == "/entity/地点/景区/西门"
    assert entity["creatorProfileId"] == "qwq_creator_geo_editor_001"
    assert catalog["primarySource"]["sourceKind"] == "wikipedia"
    assert_valid(catalog, "publish", "source_catalog")


def _video_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object], str, str]:
    execution_id = "20260906--travel-video-final-surface--test-region-a--pilot-001"
    target_ref = "posts/video/建筑/西门入口/1"
    root = tmp_path / execution_id
    obj = root / target_ref
    source_ref = "sources/video/source.md"
    video_ref = "sources/video/assets/source.mp4"
    poster_ref = "sources/video/assets/poster.jpg"
    source = root / source_ref
    source.parent.mkdir(parents=True)
    source.write_text("# 视频来源\n", encoding="utf-8")
    video = root / video_ref
    video.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.04",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-y",
            str(video),
        ],
        check=True,
        timeout=30,
    )
    poster = root / poster_ref
    poster.write_bytes(b"reviewed-poster-bytes")
    _write_json(
        root / "sources/video/meta.json",
        {
            "sourceId": "video",
            "canonicalUrl": "https://example.test/video",
            "sourceUseMode": "licensed_adaptation",
            "sourceClass": "open_license_media",
            "fetchedAt": "2026-09-06T00:00:00Z",
            "rightsClue": "作者 Fixture Filmmaker，CC BY 4.0。",
            "acquisition": {"posterAssetRef": "assets/poster.jpg"},
        },
    )
    common = {
        "sourceUrl": "https://example.test/video",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0",
        "authorizationProof": "https://example.test/video",
        "rightsStatus": "verified",
        "rightsIssues": [],
        "distributionDecision": "commercial_allowed",
        "acquisitionReceiptRef": "receipts/acquired.json",
    }
    _write_json(
        root / "sources/video/assets/index.json",
        {
            "assets": [
                {
                    **common,
                    "fileName": "source.mp4",
                    "sourceAssetId": "video-source",
                    "assetRole": "video",
                    "mimeType": "video/mp4",
                },
                {
                    **common,
                    "fileName": "poster.jpg",
                    "sourceAssetId": "video-poster",
                    "assetRole": "poster",
                    "mimeType": "image/jpeg",
                },
            ]
        },
    )
    _write_json(
        obj / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceId": "video",
                    "sourceRef": source_ref,
                    "metaRef": "sources/video/meta.json",
                    "sourceUrl": "https://example.test/video",
                }
            ]
        },
    )
    _write_json(
        obj / "3.compose/writing_pack.json",
        {
            "vertical": "travel",
            "title": "西门入口实景",
            "publishLayout": "video",
            "creatorProfileRef": "qwq_creator_landscape_photographer_001",
            "selectedSourceRefs": [source_ref],
            "sourceVideo": {"assetRef": video_ref},
            "tagRefs": ["Entity/地点/景区"],
        },
    )
    _write_json(
        obj / "4.draft/video_script.json",
        {
            "schema": "quwoquan_data.video_script",
            "executionId": execution_id,
            "objectRef": target_ref,
            "title": "西门入口实景",
            "caption": "西门入口短视频。",
            "scriptLines": ["看清入口动线。"],
        },
    )
    _write_json(
        root / "_shared/receipts/006-4.draft.json",
        {"actor": {"invocation": {"model": "fixture-model"}}},
    )
    target = {
        "name": "西门",
        "entityType": "地点/景区",
        "publishAngle": "建筑",
        "publishTitle": "西门入口实景",
        "publishSeq": 1,
        "region": "中国/测试区",
    }
    return root, obj, target, video_ref, poster_ref


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe required")
def test_video_projects_exact_source_video_and_bound_poster(tmp_path: Path) -> None:
    root, obj, target, video_ref, poster_ref = _video_fixture(tmp_path)
    source_video_digest = _digest(root / video_ref)
    source_poster_digest = _digest(root / poster_ref)

    project_publish_final_surface(
        execution_root=root,
        object_dir=obj,
        target_ref="posts/video/建筑/西门入口/1",
        target=target,
        carrier="video",
    )

    manifest = json.loads((obj / "manifest.json").read_text(encoding="utf-8"))
    assets = {asset["kind"]: asset for asset in manifest["assets"]}
    assert sorted(
        ref
        for asset in manifest["assets"]
        for ref in asset.get("sourceAssetRefs") or [asset.get("sourceAssetRef")]
    ) == sorted([video_ref, poster_ref])
    assert assets["video"]["sha256"] == source_video_digest
    assert assets["video"]["posterSha256"] == source_poster_digest
    assert (obj / assets["video"]["fileName"]).read_bytes() == (
        root / video_ref
    ).read_bytes()
    assert (obj / assets["image"]["fileName"]).read_bytes() == (
        root / poster_ref
    ).read_bytes()
    assert_valid(manifest, "content", "post_manifest")
