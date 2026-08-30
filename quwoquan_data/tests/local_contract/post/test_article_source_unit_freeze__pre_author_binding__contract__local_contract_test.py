"""Illustrated article author input is frozen before semantic execution."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.controller import content_plan_items
from content.post.article import source_unit_freeze
from content.post.article.source_unit_freeze import (
    ArticleSourceUnitFreezeError,
    validate_article_source_unit_freeze,
    write_article_source_unit_freeze,
)
from content.source import image_download, source_unit_writer
from content.source.fetch_images import PageImageFetchResult, PageImagePayload
from core.io import read_json, write_json
from PIL import Image

EXECUTION_ID = "20260806--travel-article-m3--china--scale-002"
SOURCE_DIGEST = "sha256:" + "a" * 64


def _image(seed: int) -> bytes:
    pixels = bytes((index * 31 + seed) % 256 for index in range(800 * 640 * 3))
    image = Image.frombytes("RGB", (800, 640), pixels)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, list[str]]:
    root = tmp_path / "tasks" / EXECUTION_ID
    source_dir = root / "sources/article-source-001"
    assets_dir = source_dir / "assets"
    assets_dir.mkdir(parents=True)
    manifest_path = root / "execution_manifest.json"
    write_json(
        manifest_path,
        {
            "executionId": EXECUTION_ID,
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": SOURCE_DIGEST,
                "inputs": ["quwoquan_data/scripts"],
            },
        },
    )
    monkeypatch.setattr(
        source_unit_freeze,
        "load_frozen_execution_manifest",
        lambda _execution_id: read_json(manifest_path),
    )
    source_dir.joinpath("source.md").write_text(
        "# 九寨沟同源底稿\n\n覆盖交通、季节与游览顺序。",
        encoding="utf-8",
    )
    rows: list[dict[str, object]] = []
    refs: list[str] = []
    for ordinal in (1, 2):
        name = f"asset-{ordinal}.jpg"
        path = assets_dir / name
        path.write_bytes(_image(ordinal))
        digest = source_unit_freeze.file_sha256(path)
        refs.append(f"sources/article-source-001/assets/{name}")
        rows.append(
            {
                "sourceAssetId": f"asset-{ordinal}",
                "fileName": name,
                "sha256": digest,
                "contentSha256": digest,
                "sourceUrl": f"https://example.com/article/image-{ordinal}.jpg",
                "platform": "专业旅行文章站",
                "creator": "原文摄影作者",
                "capturedAt": "2026-08-06T00:00:00Z",
                "license": "unknown",
                "termsUrl": "https://example.com/terms",
                "authorizationProof": "",
                "authorizationRequired": True,
                "rightsStatus": "unverified",
                "rightsIssues": ["distribution authorization unverified"],
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
            }
        )
    write_json(assets_dir / "index.json", {"assets": rows})
    write_json(
        source_dir / "meta.json",
        {
            "schema": "quwoquan_data.source_unit",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "sourceUnitId": "article-source-001",
            "sourceUnitRef": "sources/article-source-001",
            "sourceRef": "sources/article-source-001/source.md",
            "researchLane": "article",
            "sourceUseMode": "factual_reference_only",
            "rightsMode": "rights_audit_only",
            "assetCount": 2,
        },
    )
    return root, source_dir, refs


def test_freeze_is_create_once_and_revalidated_before_author(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_dir, refs = _fixture(tmp_path, monkeypatch)
    first = write_article_source_unit_freeze(
        execution_id=EXECUTION_ID,
        source_dir=source_dir,
        asset_refs=refs,
        execution_root_path=root,
    )
    second = write_article_source_unit_freeze(
        execution_id=EXECUTION_ID,
        source_dir=source_dir,
        asset_refs=refs,
        execution_root_path=root,
    )
    assert first == second
    receipt = read_json(root / first["receiptRef"])
    assert [row["role"] for row in receipt["assets"]] == ["cover", "body"]
    assert validate_article_source_unit_freeze(
        first,
        execution_id=EXECUTION_ID,
        execution_root_path=root,
    ) == first

    index_path = source_dir / "assets/index.json"
    index = read_json(index_path)
    index["assets"][0]["rightsStatus"] = "verified"
    write_json(index_path, index)
    with pytest.raises(ArticleSourceUnitFreezeError, match="DIGEST_DRIFT"):
        validate_article_source_unit_freeze(
            first,
            execution_id=EXECUTION_ID,
            execution_root_path=root,
        )


def test_semantic_article_plan_is_bound_before_author_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _source_dir, refs = _fixture(tmp_path, monkeypatch)
    packet_path = root / "evidence/content_plan.json"
    packet = {
        "items": [
            {
                "ref": "九寨沟_article",
                "carrier": "article",
                "publishMediaMode": "illustrated",
                "baseSourceRef": "sources/article-source-001/source.md",
                "assetRefs": refs,
            }
        ]
    }
    write_json(packet_path, packet)
    brief = dict(packet["items"][0])

    from content.execution import workspace
    from content.post import content_plan_state, object_index
    from core import paths

    monkeypatch.setattr(paths, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(source_unit_freeze, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        workspace,
        "execution_content_plan_packet_path",
        lambda _execution_id: packet_path,
    )
    monkeypatch.setattr(
        content_plan_state,
        "load_content_plan_packet",
        lambda _execution_id: read_json(packet_path),
    )
    monkeypatch.setattr(
        object_index,
        "read_brief_object",
        lambda _execution_id, _ref: dict(brief),
    )
    written_brief: dict[str, object] = {}
    monkeypatch.setattr(
        content_plan_items,
        "write_brief_object",
        lambda _execution_id, _ref, payload, **_kwargs: written_brief.update(
            payload
        ),
    )

    issues = content_plan_items.bind_article_plan_source_unit_freezes(
        SimpleNamespace(execution_id=EXECUTION_ID)
    )

    assert issues == []
    bound_item = read_json(packet_path)["items"][0]
    assert validate_article_source_unit_freeze(
        bound_item["articleSourceUnitFreeze"],
        execution_id=EXECUTION_ID,
        execution_root_path=root,
    )
    assert written_brief["articleSourceUnitFreeze"] == bound_item[
        "articleSourceUnitFreeze"
    ]


def test_freeze_rejects_text_only_or_one_image_as_illustrated_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_dir, refs = _fixture(tmp_path, monkeypatch)
    with pytest.raises(
        ArticleSourceUnitFreezeError,
        match="ILLUSTRATION_SHORTFALL",
    ):
        write_article_source_unit_freeze(
            execution_id=EXECUTION_ID,
            source_dir=source_dir,
            asset_refs=refs[:1],
            execution_root_path=root,
        )


@pytest.mark.parametrize(
    "field",
    (
        "acquisitionStatus",
        "distributionDecision",
        "authorizationRequired",
        "capturedAt",
    ),
)
def test_freeze_rejects_incomplete_unified_asset_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    root, source_dir, refs = _fixture(tmp_path, monkeypatch)
    index_path = source_dir / "assets/index.json"
    index = read_json(index_path)
    del index["assets"][0][field]
    write_json(index_path, index)

    with pytest.raises(
        ArticleSourceUnitFreezeError,
        match=rf"ADMISSION_INCOMPLETE.*{field}",
    ):
        write_article_source_unit_freeze(
            execution_id=EXECUTION_ID,
            source_dir=source_dir,
            asset_refs=refs,
            execution_root_path=root,
        )


@pytest.mark.parametrize(
    ("entity_name", "source_page"),
    (
        ("西湖", "https://zh.wikipedia.org/wiki/杭州"),
        ("成都大熊猫繁育研究基地", "https://zh.wikipedia.org/wiki/成都"),
    ),
)
def test_wikimedia_same_source_download_writer_freezes_cover_and_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entity_name: str,
    source_page: str,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    root.mkdir(parents=True)
    manifest_path = root / "execution_manifest.json"
    write_json(
        manifest_path,
        {
            "executionId": EXECUTION_ID,
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": SOURCE_DIGEST,
                "inputs": ["quwoquan_data/scripts"],
            },
        },
    )
    monkeypatch.setattr(
        source_unit_freeze,
        "load_frozen_execution_manifest",
        lambda _execution_id: read_json(manifest_path),
    )

    payloads = {
        "cover": _image(31),
        "body": _image(47),
    }

    def _page_payload(url: str, **_kwargs: object) -> PageImageFetchResult:
        key = "cover" if "cover" in url else "body"
        content = payloads[key]
        return PageImageFetchResult(
            requested_url=url,
            resolved_url=url,
            attempt_count=1,
            status_code=200,
            payload=PageImagePayload(
                url=url,
                requested_url=url,
                normalized_from_url="",
                ext=".jpg",
                content=content,
                content_type="image/jpeg",
                sha256=hashlib.sha256(content).hexdigest(),
            ),
        )

    class _Approved:
        blocks_image_publish = False
        status = "approved"
        reasons: tuple[str, ...] = ()

    monkeypatch.setattr(image_download, "_cached_source_image_payload", lambda *_a, **_k: None)
    monkeypatch.setattr(image_download, "fetch_page_image_payload", _page_payload)
    monkeypatch.setattr(image_download, "pixel_size_issue", lambda *_a, **_k: None)
    monkeypatch.setattr(
        image_download,
        "_write_image_check_temp_file",
        lambda *_a, **_k: tmp_path / "image-check.jpg",
    )
    monkeypatch.setattr(image_download, "_assess_source_image", lambda *_a, **_k: _Approved())
    monkeypatch.setattr(image_download, "_cleanup_image_check_temp_file", lambda _path: None)
    monkeypatch.setattr(image_download, "relevance_issue", lambda *_a, **_k: None)
    monkeypatch.setattr(image_download, "dedupe_image_payloads", lambda rows: (rows, []))

    def _candidate(role: str, ordinal: int) -> dict[str, object]:
        file_page = f"https://commons.wikimedia.org/wiki/File:{entity_name}_{role}.jpg"
        return {
            "url": f"https://upload.wikimedia.org/wikipedia/commons/{entity_name}_{role}.jpg",
            "sourceUrl": file_page,
            "platform": "Wikimedia Commons",
            "creator": f"{entity_name} Commons photographer",
            "credit": f"{entity_name} Commons photographer",
            "license": "CC BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": file_page,
            "licenseSnapshot": "Wikimedia Commons file-page rights snapshot",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "caption": f"{entity_name}真实旅行照片 {role}",
            "relevance": f"{entity_name}真实旅行照片 {role}",
            "placementType": "infoboxLead" if role == "cover" else "inline",
            "sourceOrder": ordinal,
            "coverCandidateRank": ordinal - 1,
            "fileTitle": f"{entity_name}_{role}.jpg",
        }

    source = {
        "source_id": f"article_wikipedia_{entity_name}",
        "platform": "Wikipedia",
        "url": source_page,
        "fetchedAt": "2026-08-06T01:02:03Z",
        "imageUrls": [_candidate("cover", 1), _candidate("body", 2)],
        # article lane 的可交付来源单元必须能解析 attribution，站点身份是解析键。
        "articleSiteId": "wikipedia_zh",
        "sourceDiscoveryProfileDigest": "sha256:" + "b" * 64,
        "articleCommercialAdmission": "commercial_release",
    }
    images, issues, funnel = image_download._download_source_unit_images(
        source,
        execution_id=EXECUTION_ID,
        entity_id=entity_name,
        object_dir=root / "entities" / "地点" / "景区" / entity_name,
        ordinal=1,
        vertical="travel",
        research_lane="article",
    )
    assert issues == []
    assert funnel["keptCount"] == 2
    assert {
        (
            row["acquisitionStatus"],
            row["rightsStatus"],
            row["authorizationRequired"],
            row["distributionDecision"],
            row["capturedAt"],
        )
        for row in images
    } == {
        ("acquired", "verified", False, "commercial_allowed", "2026-08-06T01:02:03Z")
    }
    assert all(str(row["contentSha256"]).startswith("sha256:") for row in images)
    assert all(row["rightsIssues"] == [] for row in images)

    object_dir = root / "entities" / "地点" / "景区" / entity_name
    object_dir.mkdir(parents=True)
    monkeypatch.setattr(
        source_unit_writer,
        "execution_source_unit_dir",
        lambda _execution_id, source_unit_id: root / "sources" / source_unit_id,
    )
    monkeypatch.setattr(
        source_unit_writer,
        "relative_execution_ref",
        lambda path, _execution_id: path.resolve().relative_to(root.resolve()).as_posix(),
    )
    monkeypatch.setattr(
        source_unit_writer,
        "stage_execution_context",
        lambda _execution_id: {
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
        },
    )
    monkeypatch.setattr(source_unit_writer, "_record_object_source_ref", lambda *_a, **_k: None)
    source_manifest = source_unit_writer.write_source_unit(
        object_dir,
        ordinal=1,
        source_id=str(source["source_id"]),
        source_md=f"# {entity_name}同页底稿\n\n覆盖交通、季节与现场游览顺序。",
        platform="Wikipedia",
        source_kind="encyclopedia",
        extractor="wikipedia_api",
        policy_revision="article-source-registry-v1",
        source_use_mode="factual_reference_only",
        rights_mode="factual_reference_only",
        publish_media_mode="illustrated",
        source_role="base",
        image_evidence_mode="same_source",
        research_lane="article",
        license_value="CC BY-SA 4.0",
        url=source_page,
        title=f"{entity_name}旅行指南",
        target_ref=f"/entity/地点/景区/{entity_name}",
        relevance=entity_name,
        images=images,
        asset_funnel=funnel,
        execution_id=EXECUTION_ID,
        build_variants=False,
        source=source,
    )
    source_dir = root / "sources" / str(source_manifest["sourceUnitId"])
    asset_index = read_json(source_dir / "assets/index.json")
    rows = asset_index["assets"]
    assert [row["distributionDecision"] for row in rows] == [
        "commercial_allowed",
        "commercial_allowed",
    ]
    assert [row["capturedAt"] for row in rows] == [
        "2026-08-06T01:02:03Z",
        "2026-08-06T01:02:03Z",
    ]
    asset_refs = [
        f"sources/{source_manifest['sourceUnitId']}/assets/{row['fileName']}"
        for row in rows
    ]
    binding = write_article_source_unit_freeze(
        execution_id=EXECUTION_ID,
        source_dir=source_dir,
        asset_refs=asset_refs,
        execution_root_path=root,
    )
    receipt = read_json(root / binding["receiptRef"])
    assert [row["role"] for row in receipt["assets"]] == ["cover", "body"]
    assert all(row["admission"]["sameSourceUnit"] for row in receipt["assets"])


def test_text_only_plan_item_does_not_create_an_image_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[dict[str, object]] = []

    class _Scheduler:
        def assign(self, **_kwargs: object) -> dict[str, str]:
            return {"creatorId": "creator-text-only"}

        def schedule(self, _assignment: object) -> dict[str, str]:
            return {"publishAt": "2026-08-06T00:00:00Z"}

    monkeypatch.setattr(
        content_plan_items,
        "write_article_source_unit_freeze",
        lambda **_kwargs: pytest.fail("text-only article created an image freeze"),
    )
    monkeypatch.setattr(
        content_plan_items,
        "write_brief_object",
        lambda _execution_id, _ref, brief, **_kwargs: written.append(dict(brief)),
    )
    ctx = type("Context", (), {"execution_id": EXECUTION_ID})()
    items: list[dict[str, object]] = []
    content_plan_items.append_article_plan_items(
        ctx=ctx,
        scheduler=_Scheduler(),
        entity_type="place",
        target="九寨沟",
        candidates=[
            {
                "writingIntent": "guide",
                "draftTitle": "九寨沟纯文字指南",
                "sourceId": "article-source-text-only",
                "sourceDir": Path("unused"),
                "sourceRef": "sources/article-source-text-only/source.md",
                "sourceUseMode": "factual_reference_only",
                "publishMediaMode": "text_only",
                "assetRefs": [],
            }
        ],
        items=items,
    )
    assert written[0]["publishMediaMode"] == "text_only"
    assert written[0]["titleHint"] == "九寨沟纯文字指南"
    assert "articleSourceUnitFreeze" not in written[0]
    assert items[0]["publishMediaMode"] == "text_only"
    assert "articleSourceUnitFreeze" not in items[0]


def test_broad_source_title_freezes_exact_article_target_coordinate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[dict[str, object]] = []

    class _Scheduler:
        def assign(self, **_kwargs: object) -> dict[str, str]:
            return {"creatorId": "creator-target-bound"}

        def schedule(self, _assignment: object) -> dict[str, str]:
            return {"publishAt": "2026-08-08T00:00:00Z"}

    monkeypatch.setattr(
        content_plan_items,
        "write_brief_object",
        lambda _execution_id, _ref, brief, **_kwargs: written.append(dict(brief)),
    )
    items: list[dict[str, object]] = []
    content_plan_items.append_article_plan_items(
        ctx=SimpleNamespace(execution_id=EXECUTION_ID),
        scheduler=_Scheduler(),
        entity_type="地点/景区",
        target="杭州西湖",
        candidates=[
            {
                "writingIntent": "planning_consultation",
                "draftTitle": "杭州",
                "sourceId": "article_frontier_wikivoyage_zh_e8cc82203075",
                "sourceDir": Path("unused"),
                "sourceRef": "sources/article/source.md",
                "sourceUseMode": "factual_reference_only",
                "publishMediaMode": "text_only",
                "assetRefs": [],
            }
        ],
        items=items,
    )
    assert written[0]["titleHint"] == "杭州西湖攻略"
    assert items[0]["title"] == "杭州西湖攻略"
