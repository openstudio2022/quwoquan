"""content_plan 证据准入门 contract test：source_screen=reject 来源不得进入 content_plan。

可直接运行：python3 quwoquan_data/tests/common/test_content_plan_source_reject.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import struct
import zlib
from io import BytesIO
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_content_plan_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import content_object, content_plan as cp  # noqa: E402
from _common.base_draft import assign_base_draft, base_draft_candidates, base_draft_fidelity_issues, load_base_draft_text  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import STAGE_COMPOSE, batch_content_plan_packet_path, batch_results_dir, batch_root  # noqa: E402
from _common.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区精选"
BATCH = "test_batch_reject"


def _real_jpeg(seed: int = 0) -> bytes:
    from PIL import Image

    width, height = 320, 220
    img = Image.new("RGB", (width, height))
    for y in range(height):
        for x in range(width):
            img.putpixel(
                (x, y),
                (
                    (x * 5 + seed * 17) % 256,
                    (y * 7 + seed * 29) % 256,
                    ((x + y) * 3 + seed * 11) % 256,
                ),
            )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _oversized_png_header(width: int = 9000, height: int = 6000) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )


def _write_article_source_asset(source_dir: Path, *, label: str) -> Path:
    asset_dir = source_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_file = asset_dir / f"{label}.jpg"
    asset_file.write_bytes(_real_jpeg(len(label)))
    write_json(
        asset_dir / "index.json",
        {
            "assets": [
                {
                    "fileName": asset_file.name,
                    "sourceAssetId": f"asset_{label}",
                    "sha256": f"sha256:{label}",
                    "sourceCollectionId": f"article:{label}",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "usageScope": "commercial_editorial",
                    "caption": "与正文底稿同源的配图",
                    "relevance": "与景区正文段落同源相关",
                }
            ]
        },
    )
    return asset_file


def _seed():
    reject_dir = batch_results_dir(TASK, BATCH, "download", "source_screen")
    write_json(reject_dir / "reject1.json", {"sourceId": "reject1", "decision": "reject"})
    write_json(reject_dir / "keep1.json", {"sourceId": "keep1", "decision": "retain"})
    packet = {
        "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
        "items": [
            {
                "ref": "x",
                "kind": "entity",
                "title": "样例",
                "entityRefs": ["e1"],
                "evidenceRefs": ["1.download/sources/reject1.md"],
                "rationale": "r",
                "writingIntent": "planning_consultation",
                "baseSourceRef": "1.download/sources/reject1.md",
            }
        ],
    }
    write_json(batch_content_plan_packet_path(TASK, BATCH), packet)


def test_reject_source_ids_collects_only_rejects():
    _seed()
    rejects = cp.reject_source_ids(TASK, BATCH)
    assert rejects == {"reject1"}


def test_content_plan_blocks_rejected_source():
    _seed()
    issues = cp.validate_content_plan(TASK, BATCH, {})
    assert any("cites rejected source" in i and "reject1" in i for i in issues), issues


def test_content_plan_quotas_required_includes_image_works():
    spec = {"content": {"modalityContract": "separated_research", "quotas": {"imageWorksPerTarget": 2}}}
    assert cp.content_plan_quotas_required(spec) is True


def test_content_plan_blocks_base_source_reuse_policy_in_strict_mode():
    batch = "base_source_reuse_policy_disallowed"
    entity = "九寨沟"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.shared_article"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，包含行前交通、沟内动线、旺季预约、季节差异、"
            "拍摄视角和游览节奏判断。"
        )
        * 80,
        encoding="utf-8",
    )
    article_asset = _write_article_source_asset(source_dir, label="jiuzhaigou_shared")
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "shared_article",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    items = []
    for index, intent in enumerate(("planning_consultation", "seasonal_timing"), start=1):
        ref = f"{entity}_{intent}"
        title = f"九寨沟{intent}"
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type="article",
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": intent})
        item = {
            "ref": ref,
            "kind": "entity",
            "carrier": "article",
            "researchLane": "article",
            "title": title,
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [source_ref],
            "rationale": f"{intent} 主线证据",
            "writingIntent": intent,
            "baseSourceRef": source_ref,
            "assetRefs": [article_asset.relative_to(batch_root(TASK, batch)).as_posix()],
            "sourceUseMode": "factual_reference_only",
        }
        if index == 2:
            item["baseSourceReusePolicy"] = "multi_intent_source_bundle"
        items.append(item)
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("baseSourceReusePolicy is not allowed" in issue for issue in issues), issues
    assert any("baseSourceRef reused by" in issue for issue in issues), issues


def test_content_plan_allows_text_only_article_base_source_without_source_assets():
    batch = "article_base_without_source_assets_text_only"
    entity = "九寨沟"
    ref = f"{entity}_planning_consultation"
    title = "九寨沟行前怎么安排"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.no_image_article"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，覆盖交通方式、沟内换乘、开放时间、季节差异、"
            "拍照点、亲子老人同行和雨雪天气替代安排。"
        )
        * 80,
        encoding="utf-8",
    )
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "no_image_article",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    content_object.register_content_object(
        TASK,
        batch,
        ref,
        content_type="article",
        angle="攻略",
        title=title,
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": "planning_consultation"})
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_ref],
                    "rationale": "优质文字底稿可无源图发布",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": source_ref,
                    "sourceUseMode": "factual_reference_only",
                    "publishMediaMode": "text_only",
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert issues == []


def test_content_plan_blocks_declared_article_asset_missing_rights_fields():
    batch = "article_declared_asset_missing_rights"
    entity = "九寨沟"
    ref = f"{entity}_planning_consultation"
    title = "九寨沟行前怎么安排"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.article_with_unlicensed_asset"
    )
    asset_dir = source_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，覆盖交通方式、沟内换乘、开放时间、季节差异、"
            "拍照点、亲子老人同行和雨雪天气替代安排。"
        )
        * 80,
        encoding="utf-8",
    )
    asset_path = asset_dir / "source.jpg"
    asset_path.write_bytes(b"fake-image")
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "article_with_unlicensed_asset",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_path.name, "sha256": "sha256:test"}]},
    )
    content_object.register_content_object(
        TASK,
        batch,
        ref,
        content_type="article",
        angle="攻略",
        title=title,
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": "planning_consultation"})
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    asset_ref = asset_path.relative_to(batch_root(TASK, batch)).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_ref],
                    "rationale": "声明源图必须权利完整",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": source_ref,
                    "assetRefs": [asset_ref],
                    "sourceUseMode": "factual_reference_only",
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("missing rights fields" in issue for issue in issues), issues


def test_content_plan_enforces_per_target_2_plus_2_distribution():
    batch = "per_target_quotas"
    entity = "四姑娘山"
    items = []
    for index, (carrier, intent) in enumerate(
        [
            ("article", "planning_consultation"),
            ("article", "decision_experience"),
            ("image", "decision_experience"),
            ("image", "decision_experience"),
        ],
        start=1,
    ):
        ref = f"siguniang_{index}"
        title = f"四姑娘山作品{index}"
        source_dir = (
            batch_root(TASK, batch)
            / "entities/地点/景区/四姑娘山/1.download/sources"
            / f"{index:02d}.source_{index}"
        )
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "source.md"
        source_path.write_text(
            (f"四姑娘山来源证据 {index}，这是一段包含交通、季节、游览动线和体验判断的图文底稿。" * 45),
            encoding="utf-8",
        )
        article_asset = None
        if carrier != "image":
            article_asset = _write_article_source_asset(source_dir, label=f"article_{index}")
        write_json(
            source_dir / "meta.json",
            {
                "sourceUseMode": "factual_reference_only",
                "researchLane": "article",
                "sourceRole": "base",
                "category": "travelogue",
            },
        )
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type="image" if carrier == "image" else "article",
            angle="画报" if carrier == "image" else "攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
        rel = source_path.relative_to(batch_root(TASK, batch)).as_posix()
        item = {
            "ref": ref,
            "kind": "entity",
            "carrier": carrier,
            "title": title,
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [rel],
            "rationale": f"证据驱动主题 {index}",
            "writingIntent": intent,
            "baseSourceRef": rel,
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
        }
        if carrier == "image":
            asset_dir = batch_root(TASK, batch) / "entities/地点/景区/四姑娘山/1.download/sources" / f"image_{index}" / "assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            asset_file = asset_dir / f"asset_{index}.jpg"
            asset_file.write_bytes(_real_jpeg(index))
            write_json(
                asset_dir / "index.json",
                {
                    "assets": [
                        {
                            "fileName": asset_file.name,
                            "sourceCollectionId": f"collection_{index}",
                        }
                    ]
                },
            )
            write_json(
                asset_dir.parent / "meta.json",
                {"researchLane": "image", "sourceCollectionId": f"collection_{index}"},
            )
            item.update(
                {
                    "researchLane": "image",
                    "sourceCollectionId": f"collection_{index}",
                    "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
                    "baseSourceRef": "",
                    "sourceUseMode": "",
                }
            )
        elif article_asset is not None:
            item["assetRefs"] = [article_asset.relative_to(batch_root(TASK, batch)).as_posix()]
        items.append(item)
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    spec = {
        "scope": {
            "coverageTargets": [{"entityType": "地点/景区", "name": entity}],
        },
        "content": {
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
            "modalityContract": "separated_research",
            "research": {"imageCountPolicy": "hard_quota"},
        },
    }
    assert cp.validate_content_plan(TASK, batch, spec) == []
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": "quwoquan_data.content_plan_packet/1", "items": items},
    )
    schema_issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("content_plan_packet.schemaVersion" in issue for issue in schema_issues), schema_issues
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items[:-1]},
    )
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("imageWorksPerTarget quota 2" in issue for issue in issues), issues


def test_content_plan_enforces_required_angles_for_4_plus_1_distribution():
    batch = "per_target_4_plus_1"
    entity = "九寨沟"
    article_intents = [
        "planning_consultation",
        "decision_experience",
        "route_transport",
        "seasonal_timing",
    ]
    items = []
    for index, intent in enumerate(article_intents, start=1):
        ref = f"{entity}_{intent}"
        title = f"九寨沟{intent}"
        source_dir = (
            batch_root(TASK, batch)
            / "entities/地点/景区/九寨沟/1.download/sources"
            / f"{index:02d}.{intent}"
        )
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "source.md"
        source_path.write_text(
            (f"九寨沟 {intent} 来源证据，含图文混合底稿 {index}，补充路线、季节、停留时长和风险提示。" * 45),
            encoding="utf-8",
        )
        article_asset = _write_article_source_asset(source_dir, label=f"jiuzhaigou_{index}")
        write_json(
            source_dir / "meta.json",
            {
                "sourceUseMode": "factual_reference_only",
                "researchLane": "article",
                "sourceRole": "base",
                "category": "travelogue",
            },
        )
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type="article",
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": intent})
        rel = source_path.relative_to(batch_root(TASK, batch)).as_posix()
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "article",
                "researchLane": "article",
                "title": title,
                "entityRefs": [f"/entity/地点/景区/{entity}"],
                "evidenceRefs": [rel],
                "rationale": f"{intent} 主线证据",
                    "writingIntent": intent,
                    "baseSourceRef": rel,
                    "assetRefs": [article_asset.relative_to(batch_root(TASK, batch)).as_posix()],
                    "sourceUseMode": "factual_reference_only",
                }
            )

    image_source = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/05.image_collection"
    )
    asset_dir = image_source / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = image_source / "source.md"
    source_path.write_text("九寨沟同一摄影集合，图片底稿。", encoding="utf-8")
    asset_file = asset_dir / "asset_1.jpg"
    asset_file.write_bytes(_real_jpeg(41))
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_file.name, "sourceCollectionId": "jiuzhaigou:image:one"}]},
    )
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    ref = f"{entity}_image"
    content_object.register_content_object(
        TASK,
        batch,
        ref,
        content_type="image",
        angle="画报",
        title="九寨沟图片作品",
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": "九寨沟图片作品"})
    items.append(
        {
            "ref": ref,
            "kind": "entity",
            "carrier": "image",
            "researchLane": "image",
            "title": "九寨沟图片作品",
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [source_path.relative_to(batch_root(TASK, batch)).as_posix()],
            "rationale": "同一图片集合证据",
            "sourceCollectionId": "jiuzhaigou:image:one",
            "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
        }
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {
            "requiredAngles": [*article_intents, "image"],
        },
    }
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    assert cp.validate_content_plan(TASK, batch, spec) == []
    write_json(
        image_source / "meta.json",
        {"researchLane": "article", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    lane_issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("image asset must come from researchLane=image" in issue for issue in lane_issues), lane_issues
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items[:2] + [items[-1]]},
    )
    state_dir = batch_root(TASK, batch) / "_shared"
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        state_dir / "task_workflow_state.json",
        {
            "abandonedContentObjects": [
                {
                    "ref": f"{entity}_route_transport",
                    "status": "abandoned",
                    "reason": "fixture partial article source unavailable",
                },
                {
                    "ref": f"{entity}_seasonal_timing",
                    "status": "abandoned",
                    "reason": "fixture partial article source unavailable",
                },
            ]
        },
    )
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("acceptance.requiredAngles" in issue for issue in issues), issues
    partial_spec = {**spec, "workflowPolicy": {"allowContentQuotaShortfall": True}}
    assert cp.validate_content_plan(TASK, batch, partial_spec) == []


def test_content_plan_blocks_oversized_image_asset_refs():
    batch = "image_asset_safety_gate"
    entity = "九寨沟"
    image_source = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.image_collection"
    )
    asset_dir = image_source / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = image_source / "source.md"
    source_path.write_text("九寨沟同一摄影集合，图片底稿。", encoding="utf-8")
    asset_file = asset_dir / "oversized.png"
    asset_file.write_bytes(_oversized_png_header())
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_file.name, "sourceCollectionId": "jiuzhaigou:image:huge"}]},
    )
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:huge"},
    )
    ref = f"{entity}_image"
    content_object.register_content_object(
        TASK,
        batch,
        ref,
        content_type="image",
        angle="画报",
        title="九寨沟图片作品",
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": "九寨沟图片作品"})
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "九寨沟图片作品",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_path.relative_to(batch_root(TASK, batch)).as_posix()],
                    "rationale": "同一图片集合证据",
                    "sourceCollectionId": "jiuzhaigou:image:huge",
                    "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {"requiredAngles": ["image"]},
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("image asset blocked by image safety gate" in issue for issue in issues), issues
    assert any("image_pixels_too_large" in issue for issue in issues), issues


def test_content_plan_blocks_image_work_reusing_article_base_asset():
    batch = "article_image_asset_reuse_gate"
    entity = "九寨沟"
    root = batch_root(TASK, batch)
    article_source = root / "entities/地点/景区/九寨沟/1.download/sources/01.article_base"
    image_source = root / "entities/地点/景区/九寨沟/1.download/sources/02.image_collection"
    shared_bytes = _real_jpeg(91)
    shared_digest = __import__("hashlib").sha256(shared_bytes).hexdigest()
    for source_dir, lane, file_name in [
        (article_source, "article", "article.jpg"),
        (image_source, "image", "image.jpg"),
    ]:
        asset_dir = source_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "source.md").write_text("九寨沟图文底稿。" * 120, encoding="utf-8")
        (asset_dir / file_name).write_bytes(shared_bytes)
        write_json(
            source_dir / "meta.json",
            {
                "researchLane": lane,
                "sourceRole": "base" if lane == "article" else "",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue" if lane == "article" else "image_collection",
                "sourceCollectionId": "shared:collection",
            },
        )
        write_json(
            asset_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": file_name,
                        "sha256": f"sha256:{shared_digest}",
                        "sourceCollectionId": "shared:collection",
                        "caption": "九寨沟共享图",
                        "license": "CC-BY-SA 4.0",
                        "credit": "测试摄影师",
                        "sourceUrl": "https://example.test/shared",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )
    article_ref = f"{entity}_planning_consultation"
    image_ref = f"{entity}_image"
    for ref, content_type, title in [
        (article_ref, "article", "九寨沟文章"),
        (image_ref, "image", "九寨沟图片"),
    ]:
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type=content_type,
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
    article_source_ref = (article_source / "source.md").relative_to(root).as_posix()
    article_asset_ref = (article_source / "assets" / "article.jpg").relative_to(root).as_posix()
    image_source_ref = (image_source / "source.md").relative_to(root).as_posix()
    image_asset_ref = (image_source / "assets" / "image.jpg").relative_to(root).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": article_ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": "九寨沟文章",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [article_source_ref],
                    "rationale": "文章底稿",
                        "writingIntent": "planning_consultation",
                        "baseSourceRef": article_source_ref,
                        "assetRefs": [article_asset_ref],
                        "sourceUseMode": "factual_reference_only",
                    },
                {
                    "ref": image_ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "九寨沟图片",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [image_source_ref],
                    "rationale": "图片作品",
                    "sourceCollectionId": "shared:collection",
                    "assetRefs": [image_asset_ref],
                },
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {"requiredAngles": ["planning_consultation", "image"]},
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("image sha256" in issue and "reused" in issue for issue in issues), issues
    assert any("sourceCollectionId" in issue and "reused" in issue for issue in issues), issues


def test_base_draft_candidates_exclude_reject_sources():
    obj = resolve_entity_object_dir(TASK, BATCH, "九寨沟", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r",
        title="探针页",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 九寨沟\n\n真实正文，含开放时间与体验判断。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 8},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g",
        title="可用正文",
        target_ref="/entity/地点/景区/九寨沟",
    )
    brief = {"entityRefs": ["地点/景区/九寨沟"]}
    candidates = base_draft_candidates(TASK, BATCH, brief)
    refs = [row["sourceRef"] for row in candidates]
    assert any("good_story" in ref for ref in refs), refs
    assert not any("reject_probe" in ref for ref in refs), refs


def test_assign_base_draft_rejects_declared_reject_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "黄龙", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页",
        target_ref="/entity/地点/景区/黄龙",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 黄龙\n\n真实正文，含体验判断与出行信息。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 9},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g2",
        title="可用正文",
        target_ref="/entity/地点/景区/黄龙",
    )
    chosen = assign_base_draft(
        TASK,
        BATCH,
        "post://黄龙",
        {
            "entityRefs": ["地点/景区/黄龙"],
            "baseSourceRef": "entities/地点/景区/黄龙/1.download/sources/01.reject_probe/source.md",
        },
    )
    assert chosen and "good_story" in chosen, chosen


def test_assign_base_draft_reassigns_when_declared_source_taken_by_peer():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_dujiangyan",
        source_md="# 都江堰\n\n概述底稿，含基础事实。",
        quality={"sourceId": "wiki_dujiangyan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/wiki",
        title="都江堰概述",
        target_ref="/entity/地点/景区/都江堰",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_dujiangyan",
        source_md="# 都江堰游记\n\n长篇游记底稿，保留现场叙事。",
        quality={"sourceId": "ctrip_dujiangyan", "quality": "A-story", "score": 8},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip",
        title="都江堰游记",
        target_ref="/entity/地点/景区/都江堰",
    )
    first = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_画报",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    second = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_攻略",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    assert first and "wiki_dujiangyan" in first, first
    assert second and "ctrip_dujiangyan" in second, second
    assert first != second


def test_load_base_draft_text_prefers_source_clean():
    obj = resolve_entity_object_dir(TASK, BATCH, "峨眉山", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_emeishan",
        source_md="raw source with frontmatter-ish noise\nmanual_source_plan_note: 不该优先命中",
        clean_md="clean source body only",
        quality={"sourceId": "wiki_emeishan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/emeishan",
        title="峨眉山概述",
        target_ref="/entity/地点/景区/峨眉山",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/峨眉山/1.download/sources/01.wiki_emeishan/source.md",
    )
    assert text == "clean source body only"


def test_load_base_draft_text_extracts_signal_body_from_noisy_clean_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_noisy",
        source_md="raw fallback",
        clean_md=(
            "登录\n注册\n我的订单\n"
            "都江堰景区，位于都江堰市城西岷江干流上，由秦国蜀郡太守李冰及其子于西元前256年左右修建，是目前中国保存完整的古代水利工程。\n"
            "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程和百丈堤、人字堤等附属工程构成，把岷江分隔成外江和内江。\n"
            "用户点评\n"
            "附近景点\n"
            "都江堰真的很值得一看，古人的智慧太了不起了。\n"
        ),
        quality={"sourceId": "ctrip_noisy", "quality": "B-fact", "score": 4},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip-noisy",
        title="都江堰 noisy",
        target_ref="/entity/地点/景区/都江堰",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/都江堰/1.download/sources/02.ctrip_noisy/source.md",
    )
    assert "登录" not in text
    assert "附近景点" not in text
    assert "都江堰景区，位于都江堰市城西岷江干流上" in text
    assert "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程" in text


def test_base_draft_fidelity_gallery_uses_leading_excerpt_window():
    tail = "\\n\\n".join(
        f"尾段延伸事实{i:03d}：这一段只用于拉长底稿窗口，不应要求画报全文覆盖。"
        for i in range(120)
    )
    base = (
        "第一段先写景区概况与主景。\\n\\n"
        "第二段继续写最核心的观看顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n\\n"
        + tail
    )
    article = (
        "# 图集\\n\\n"
        "第一段先写景区概况与主景。\\n\\n"
        "第二段继续写最核心的观看顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n"
    )
    assert base_draft_fidelity_issues(
        article, base, source_use_mode="licensed_adaptation"
    )  # 授权改编的 article 口径仍会被长尾底稿拉低
    assert base_draft_fidelity_issues(
        article,
        base,
        carrier="gallery",
        source_use_mode="licensed_adaptation",
    ) == []


def test_factual_reference_only_uses_unified_fidelity_gate():
    """版权风险全面放开：fidelity 门对所有来源统一生效，不再因 factual_reference_only 跳过。

    未授权普通网页同样要求「以底稿为基础适度润色」，脱离底稿从零另写会被同一道下限门拦截。
    """
    off_base = base_draft_fidelity_issues(
        "完全独立组织的正文，只复述可核验事实。",
        "普通网页的原始叙述和作者表达。",
        source_use_mode="factual_reference_only",
    )
    assert off_base, "factual 来源脱离底稿应被统一 fidelity 门拦截"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content_plan source-reject tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
