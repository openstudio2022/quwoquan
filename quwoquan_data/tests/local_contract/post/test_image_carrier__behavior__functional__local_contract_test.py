"""画报载体 contract tests：载体路由 + gallery compose + 载体感知门。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_image_carrier__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="image_carrier_rt_"))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paths import (  # noqa: E402
    execution_inputs_dir,
    ensure_execution_command_layout,
    ensure_execution_layout,
)
import core.paths as _paths_mod  # noqa: E402
from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from content.post.article.evidence_bundle import public_byline_label  # noqa: E402
from content.post.article.draft_io import draft_article_path, draft_meta_path, read_draft_meta, read_writing_pack, write_agent_draft  # noqa: E402
from content.post.article.draft_io import prompt_path  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from content.post.article.writing_pack import build_writing_pack as build_generic_writing_pack  # noqa: E402
from content.post.article import route_compose as RC  # noqa: E402
from content.post.article import route_assets as route_assets  # noqa: E402
from content.post.article import route_core as route_core  # noqa: E402
from content.post.article import route_assets as route_assets_mod  # noqa: E402
from content.post.article.route_analysis import analyze_route_ref  # noqa: E402
from content.post.article.route_compose import build_route_writing_pack  # noqa: E402
from content.post.article.route_review import review_route_draft  # noqa: E402
from support.helpers.agent_draft_kit import gallery_article  # noqa: E402


EXECUTION_ID = "20260711--travel-image-image-carrier--cn-zhejiang--canary-001"
ENTITIES = ["雅拉雪山", "黑石城", "莲花湖", "墨石公园"]


def _retarget_runtime() -> None:
    os.environ["QWQ_OUTPUT_ROOT"] = str(_RUNTIME_ROOT)
    _paths_mod.RUNTIME_ROOT = _RUNTIME_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _RUNTIME_ROOT / "tasks"


def _distinct_image(seed: int) -> np.ndarray:
    img = np.zeros((240, 320, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=(240, 320, 3), dtype=np.uint8)
    cv2.circle(img, (40 + seed * 17 % 220, 60 + seed * 19 % 120), 20 + seed * 3, (int(seed * 31) % 255, 60, 180), -1)
    cv2.rectangle(img, (seed * 11 % 180, seed * 7 % 120), (220, 190), (30, int(seed * 47) % 255, 210), 3)
    cv2.putText(img, f"{seed}", (20 + seed * 9 % 160, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return img


_SOURCE_PATHS: list[str] = []


def _seed():
    _retarget_runtime()
    from support.execution_manifest_fixture import build_execution_fixture

    build_execution_fixture(EXECUTION_ID)
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "source")
    ensure_execution_command_layout(EXECUTION_ID, "post")
    write_execution_runtime_state(EXECUTION_ID, command="post")
    _SOURCE_PATHS.clear()
    image_root = Path(tempfile.mkdtemp(prefix="gallery_sources_"))
    for idx, name in enumerate(ENTITIES):
        obj = resolve_entity_object_dir(EXECUTION_ID, name, etype_hint="景区")
        image_paths: list[Path] = []
        for k in range(2):
            image_path = image_root / f"{name}_{k}.jpg"
            cv2.imwrite(str(image_path), _distinct_image(idx * 5 + k + 1))
            image_paths.append(image_path)
        write_source_unit(
            obj,
            ordinal=1,
            source_id="curated_image_collection",
            source_md=f"{name} 的光影与现场氛围记录，仅作内部参考。\n",
            platform="curated",
            source_category="image_collection",
            research_lane="image",
            license_value="CC-BY-SA 4.0",
            url=f"https://example.com/{name}",
            title=name,
            target_ref=f"/entity/地点/景区/{name}",
            relevance=f"{name} 的图文证据",
            images=[
                {
                    "sourcePath": str(path),
                    "caption": f"{name} 图{k}",
                    "relevance": f"{name} 图{k}",
                    "sourceCollectionId": "fixture:gallery:gongga-west",
                    "creator": "测试摄影师",
                    "collectionPageUrl": "https://example.com/gallery",
                    "license": "CC-BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "authorizationProof": "fixture rights proof",
                    "usageScope": "app_publish",
                }
                for k, path in enumerate(image_paths)
            ],
            execution_id=EXECUTION_ID,
        )
        _SOURCE_PATHS.append(str(obj / "1.download" / "sources" / "01.curated_image_collection" / "source.md"))


def _image_brief() -> dict:
    return {
        "carrier": "image",
        "sourceCollectionId": "fixture:gallery:gongga-west",
        "imagePolicy": {"minImages": 4, "captionMaxChars": 20},
        "titleHint": "贡嘎西坡光影图集",
        "templateId": "主题_图文画报",
        "entityRefs": ENTITIES,
        "tagRefs": ["Topic/旅行/主题/风光"],
        "render": {"articleTemplate": "gallery", "fontPreset": "clean"},
        "imagePlan": [
            {"slot": "封面", "imageLayout": "fullWidth"},
            {"slot": "光影图集", "gallery": "masonry"},
        ],
    }


def _low_narrative_quality_payload() -> dict:
    nodes = [{"entityName": n, "entityRef": f"地点/景区/{n}", "mainlineEvidence": [], "emotionEvidence": {}} for n in ENTITIES]
    return {
        "evidenceBundle": {"routeNodes": nodes},
        "storySpine": {},
        "sourceUrls": ["https://example.com/gallery"],
        "sourcePaths": list(_SOURCE_PATHS),
    }


def test_declared_image_stays_image_when_asset_is_text_heavy():
    assets = [{"isTextHeavy": True, "imageStatus": "text_heavy"}] + [{"imageStatus": "safe"} for _ in range(4)]
    assert route_core.resolve_carrier({"carrier": "image"}, {"routeNodes": []}, assets) == "image"


def test_undeclared_text_heavy_routes_article():
    assets = [{"isTextHeavy": True, "imageStatus": "text_heavy"}] + [{"imageStatus": "safe"} for _ in range(4)]
    assert route_core.resolve_carrier({}, {"routeNodes": []}, assets) == "article"


def test_declared_article_stays_article():
    assets = [{"imageStatus": "safe"} for _ in range(6)]
    assert route_core.resolve_carrier({"carrier": "article"}, {"routeNodes": []}, assets) == "article"


def test_image_heavy_low_narrative_routes_image():
    assets = [{"imageStatus": "safe"} for _ in range(5)]
    assert route_core.resolve_carrier({}, {"routeNodes": []}, assets) == "image"


REF = "贡嘎画报"


def test_image_compose_brief_uses_structural_image_contract():
    _seed()
    brief = _image_brief()
    write_json(execution_inputs_dir(EXECUTION_ID, "post", "compose") / f"{REF}.json", brief)
    quality = _low_narrative_quality_payload()

    # prepare：写作契约解析为 image 载体 + 结构化图片草稿元数据。
    pack = build_route_writing_pack(EXECUTION_ID, REF, brief, quality)
    assert pack["carrier"] == "image", pack.get("carrier")
    assert pack["publishLayout"] == "image"
    assert pack["evidencePoints"] == []
    assert pack["sectionIntents"] == []
    assert pack["captionPolicy"]["captionMaxChars"] == 300
    assert "sourceCollectionId" in pack
    image_prompt = prompt_path(EXECUTION_ID, REF).read_text(encoding="utf-8")
    assert "# 图片作品任务" in image_prompt
    assert "## 证据点" not in image_prompt
    assert len(image_prompt) < 4500
    assert read_writing_pack(EXECUTION_ID, REF) is not None
    assert not draft_article_path(EXECUTION_ID, REF).exists()
    meta = read_draft_meta(EXECUTION_ID, REF)
    assert meta is not None
    assert meta["generator"] == "image_evidence_pack"
    assert meta["articleContract"] == "structured_image_only"
    stale_article = draft_article_path(EXECUTION_ID, REF)
    stale_article.write_text("# 旧错误正文\n\n这不应出现在图片作品里。", encoding="utf-8")
    build_route_writing_pack(EXECUTION_ID, REF, brief, quality)
    assert not stale_article.exists()
    # 图片作品是结构化图片集合 + 可选短配文，不生成 article/gallery markdown。
    review = review_route_draft(EXECUTION_ID, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    assert review["checks"]["carrierConsistency"]["passed"]
    assert review["checks"]["imageGate"]["passed"]
    assert review["checks"]["imageFidelity"]["passed"], review["checks"]["imageFidelity"]["issues"]
    assert review["checks"]["galleryCaption"]["passed"], review["checks"]["galleryCaption"]["issues"]
    assert "travelogueDensity" not in review["checks"], "画报载体不应套长文叙事门"
    assert review["generator"] == "image_evidence_pack"


def test_image_writing_pack_trims_asset_caption_to_publish_limit():
    long_caption = "山川湖海 " * 80
    pack = build_generic_writing_pack(
        ref="图片作品",
        kind="entity",
        brief={
            "titleHint": "雪山湖泊",
            "caption": long_caption,
            "sourceCollectionId": "fixture:gallery",
            "templateId": "travel.entity.image",
        },
        evidence_bundle={},
        assets=[
            {
                "assetId": "asset_1",
                "fileName": "asset_1.jpg",
                "caption": long_caption,
                "kind": "image",
                "role": "cover",
            }
        ],
        carrier="image",
        byline="内容编辑",
        publish_layout="image",
        section_intents=[],
        source_urls=[],
        source_paths=[],
        execution_id=EXECUTION_ID,
    )

    assert len(pack["caption"]) <= 300
    assert len(pack["assets"][0]["caption"]) <= 300


def test_image_compose_payload_prefers_agent_meta_title_and_caption():
    _seed()
    brief = _image_brief()
    write_json(execution_inputs_dir(EXECUTION_ID, "post", "compose") / f"{REF}.json", brief)
    quality = _low_narrative_quality_payload()

    build_route_writing_pack(EXECUTION_ID, REF, brief, quality)
    pack = read_writing_pack(EXECUTION_ID, REF)
    meta = read_draft_meta(EXECUTION_ID, REF)
    assert pack is not None
    assert meta is not None
    meta.update(
        {
            "title": "Agent 轻润色标题",
            "caption": "Agent 轻润色配文，只保留图片本身已经能支持的事实。",
        }
    )
    write_json(draft_meta_path(EXECUTION_ID, REF), meta)

    payload = RC._compose_payload_from_pack(REF, brief, quality, pack, "", meta)

    assert payload["title"] == "Agent 轻润色标题"
    assert payload["publishTitle"] == "Agent 轻润色标题"
    assert payload["caption"] == "Agent 轻润色配文，只保留图片本身已经能支持的事实。"
    assert payload["summary"] == "Agent 轻润色配文，只保留图片本身已经能支持的事实。"


def test_image_compose_payload_keeps_public_title_empty_when_source_title_absent():
    _seed()
    brief = _image_brief()
    brief["titleHint"] = ""
    write_json(execution_inputs_dir(EXECUTION_ID, "post", "compose") / f"{REF}.json", brief)
    quality = _low_narrative_quality_payload()

    build_route_writing_pack(EXECUTION_ID, REF, brief, quality)
    pack = read_writing_pack(EXECUTION_ID, REF)
    meta = read_draft_meta(EXECUTION_ID, REF)
    assert pack is not None
    assert meta is not None

    payload = RC._compose_payload_from_pack(REF, brief, quality, pack, "", meta)

    assert payload["title"] == ""
    assert payload["publishTitle"] == ""


def test_declared_image_asset_ref_reports_safety_block_separately_from_missing_asset():
    global EXECUTION_ID
    old_task = EXECUTION_ID
    EXECUTION_ID = "20260711--travel-image-image-carrier--cn-zhejiang--canary-002"
    try:
        _seed()
        target = ENTITIES[0]
        candidate = route_assets._entity_image_candidates(EXECUTION_ID, target, f"/entity/地点/景区/{target}")[0]
        brief = {
            **_image_brief(),
            "carrier": "image",
            "entityRefs": [f"/entity/地点/景区/{target}"],
            "sourceCollectionId": candidate["sourceCollectionId"],
            "assetRefs": [candidate["sourceAssetRef"]],
        }
        quality = {
            "routeNodes": [],
            "evidenceBundle": {
                "routeNodes": [
                    {"entityName": target, "entityRef": f"/entity/地点/景区/{target}"}
                ]
            },
        }

        class _UnsafeVerdict:
            status = route_assets.STATUS_UNSAFE
            reasons = ("watermark_or_platform_text",)
            text_area_ratio = 0.0
            is_text_heavy = False

        original = route_assets_mod.assess_image
        try:
            route_assets_mod.assess_image = lambda _path: _UnsafeVerdict()
            try:
                route_assets._build_route_assets(EXECUTION_ID, "安全门归因测试", brief, quality["evidenceBundle"])
            except RuntimeError as exc:
                message = str(exc)
            else:  # pragma: no cover - explicit assertion keeps direct script runner useful
                raise AssertionError("expected image safety gate failure")
        finally:
            route_assets_mod.assess_image = original
    finally:
        EXECUTION_ID = old_task

    assert "blocked by image safety gate" in message
    assert candidate["sourceAssetRef"] in message


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"image carrier tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
