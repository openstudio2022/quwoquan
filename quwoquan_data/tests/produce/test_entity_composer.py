"""实体（非线路）内容 composer 红绿契约 + 端到端 GWT。

覆盖：is_entity_brief 分类、单实体成稿（开篇动机/亮点/不足/实用提醒就地融入）、
图片门、体裁一致、来源痕迹清洗、materialize + verify 全绿。

可直接运行：python3 quwoquan_data/tests/produce/test_entity_composer.py
"""
from __future__ import annotations

import argparse
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

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.io import write_json  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_inputs_dir,
    batch_root,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.content_evidence import public_byline_label  # noqa: E402
from _common.content_object import read_brief_object, write_brief_object  # noqa: E402
from _common.base_draft import save_base_draft_ledger  # noqa: E402
from _common.draft_io import read_writing_pack, write_agent_draft  # noqa: E402
from _common.post_verify import verify_scope  # noqa: E402
from _common.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from produce.route_workflow import analyze_route_ref  # noqa: E402
from produce.entity_workflow import (  # noqa: E402
    build_entity_writing_pack,
    is_entity_brief,
    review_entity_draft,
)
from produce.route_workflow import load_compose_brief  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from produce.handler import handle_produce  # noqa: E402
from helpers.agent_draft_kit import entity_article  # noqa: E402


def _compose_entity_agent_draft(task: str, batch: str, ref: str, brief: dict):
    """共享：prepare 写作契约 → 模拟会话模型创作 entity 正文写回草稿。返回 (quality, pack)。"""
    quality = analyze_route_ref(task, batch, ref, brief)
    pack = build_entity_writing_pack(task, batch, ref, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    article = entity_article(brief["titleHint"], byline, ENTITY, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        task,
        batch,
        ref,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id=f"run-{ref}",
        agent_id=f"agent-{ref}",
    )
    return quality, pack

TASK = "实体冷启动_gwt"
BATCH = "pilot"
REF = "三星堆博物馆_体验"
ENTITY = "三星堆博物馆"

SOURCE_TEXT = """---
url: https://example.com/sanxingdui
platform: curated
license: internal-curated
allowedUse: internal_reference
title: sample
entity: 三星堆博物馆
retained: true
---

出发前我其实有点犹豫，怕三星堆博物馆只是网红打卡，真正走进去之后才发现展陈的清晨光线让人愿意慢下来。

参观时间建议留出大半天，开馆后先按推荐动线走青铜大立人和黄金面具所在的停留展厅，人少时最能看清细节。

最打动我的是那种安静看展的节奏；让我不太舒服的是午后排队和讲解人多，连续看展也会有点累。

实地走过后我会建议：把停留展厅和参观时间排进当天计划，避开午后高峰，比追求把所有展厅都看完更值得。
"""


def _clean_image(path: Path, seed: int) -> None:
    img = np.zeros((220, 300, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (140 + seed * 6, 110), 30 + seed * 5, (int(seed * 53) % 255, 90, 150), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def _entity_brief() -> dict:
    return {
        "templateId": "博物馆_体验",
        "titleHint": "三星堆博物馆体验指南",
        "subject": {"kind": "entity", "type": "地点/博物馆"},
        "entityRefs": [f"地点/博物馆/{ENTITY}"],
        "vertical": "travel",
        "carrier": "article",
        "creator": {
            "creatorProfileId": "qwq_creator_travel_blogger_001",
            "authorId": "builtin_travel_blogger",
            "creatorArchetype": "travel_blogger",
        },
        "render": {"articleTemplate": "journal", "fontPreset": "handwritten"},
        "structure": {"required": ["进馆第一印象", "最停留的展厅", "参观动线", "离开后的感受"]},
        "hooks": ["在{name}，我停留最久的是这个展柜"],
        "mustIncludeFacts": ["参观时间", "推荐动线", "停留展厅"],
        "wordCount": {"min": 700, "max": 1600},
        "imagePlan": [{"slot": "外观", "imageLayout": "fullWidth"}, {"slot": "展陈细节", "imageLayout": "wrapRight"}],
        "tagRefs": ["Format/内容角度/体验/亲身体验", "Format/内容载体/文章/长文", "Topic/旅行/玩法/博物馆展览"],
        "conditionContext": {},
    }


def _seed_sources() -> None:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    ensure_batch_layout(TASK, BATCH, "produce")
    write_batch_manifest(TASK, BATCH, command="task_run")
    import shutil

    d = batch_root(TASK, BATCH) / "drafts"
    if d.exists():
        shutil.rmtree(d)
    # 对象优先：草稿已迁到 batch posts 对象目录，需连同路由索引一并重置，避免跨用例残留 agent 草稿。
    posts_root = batch_root(TASK, BATCH) / "posts"
    if posts_root.exists():
        shutil.rmtree(posts_root)
    index_file = batch_root(TASK, BATCH) / "_shared" / "content_object_index.json"
    if index_file.exists():
        index_file.unlink()
    write_json(batch_inputs_dir(TASK, BATCH, "produce", "compose") / f"{REF}.json", _entity_brief())
    obj = resolve_entity_object_dir(TASK, BATCH, ENTITY, etype_hint="地点/博物馆")
    image_root = Path(tempfile.mkdtemp(prefix="entity_composer_sources_"))
    image_paths: list[Path] = []
    for k in range(3):
        image_path = image_root / f"{ENTITY}_{k}.jpg"
        _clean_image(image_path, seed=k + 1)
        image_paths.append(image_path)
    write_source_unit(
        obj,
        ordinal=1,
        source_id="curated_story",
        source_md=SOURCE_TEXT,
        quality={
            "sourceId": "curated_story",
            "quality": "A-story",
            "score": 8,
            "reasons": ["length_ok", "scene_rich"],
            "excerpt": f"{ENTITY} 真正影响体验的是参观时间和停留展厅的取舍。",
            "url": "https://example.com/sanxingdui",
        },
        platform="curated",
        source_category="internal-curated",
        url="https://example.com/sanxingdui",
        title="sample",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
        relevance=f"{ENTITY} 的参观与展陈体验",
        images=[{"sourcePath": str(path), "caption": f"{ENTITY} 图{k}", "relevance": f"{ENTITY} 图{k}"} for k, path in enumerate(image_paths)],
    )


def test_is_entity_brief_classification():
    assert is_entity_brief(_entity_brief()) is True
    route_like = {"subject": {"kind": "topic", "type": "旅行/线路"}, "templateId": "线路_环线攻略", "entityRefs": ["a"]}
    assert is_entity_brief(route_like) is False


def test_normalize_entity_refs_full_path():
    """回归：主实体引用必须补全为发布门可识别的全路径 /entity/{domain}/{type}/{name}。

    历史 bug：composer 仅拼 /entity/{name}，publish_filter._parse_entity_ref 需 domain/type/name
    三段，导致主实体被误判「无主页」过滤，post 失去实体关联。
    """
    from _common.entity_extract import normalize_entity_refs
    from _common.publish_filter import _parse_entity_ref

    # 短名 + subject.type 补全
    assert normalize_entity_refs(["稻城亚丁"], "地点/景区") == ["/entity/地点/景区/稻城亚丁"]
    # 已是 domain/type/name（无 /entity/ 前缀）
    assert normalize_entity_refs(["地点/博物馆/三星堆博物馆"], "地点/博物馆") == [
        "/entity/地点/博物馆/三星堆博物馆"
    ]
    # 已带 /entity/ 前缀的全路径，原样规范化
    assert normalize_entity_refs(["/entity/地点/景区/四姑娘山"], "地点/景区") == [
        "/entity/地点/景区/四姑娘山"
    ]
    # 输出必须被 publish_filter 解析为完整三段（修复前会解析失败 → 过滤）
    domain, etype, name = _parse_entity_ref(normalize_entity_refs(["稻城亚丁"], "地点/景区")[0])
    assert (domain, etype, name) == ("地点", "景区", "稻城亚丁")


def test_load_compose_brief_hydrates_entity_condition_context_from_profile():
    _seed_sources()
    task_root = Path(os.environ["QWQ_RUNTIME_ROOT"]) / "tasks" / TASK / "entities" / "地点" / "博物馆" / ENTITY
    task_root.mkdir(parents=True, exist_ok=True)
    write_json(
        task_root / "_entity.json",
        {
            "label": ENTITY,
            "conditionProfile": {
                "regions": ["平原都市"],
                "seasons": ["秋"],
                "altitudeMeters": 500,
                "notes": "城市平原展馆，无高反风险",
            },
        },
    )
    brief = _entity_brief()
    brief.pop("conditionContext", None)
    write_brief_object(TASK, BATCH, REF, brief, content_type="article")
    hydrated = load_compose_brief(TASK, BATCH, REF)
    context = hydrated.get("conditionContext") or {}
    assert context["region"]["name"] == "平原都市"
    assert context["season"]["name"] == "秋"
    assert context["entityProfile"]["altitudeMeters"] == 500


def test_entity_placeholder_blocks_then_agent_draft_green():
    _seed_sources()
    brief = _entity_brief()
    # prepare：写作契约 + 占位草稿；占位阶段出处门必须拦截。
    quality = analyze_route_ref(TASK, BATCH, REF, brief)
    build_entity_writing_pack(TASK, BATCH, REF, brief, quality)
    assert read_writing_pack(TASK, BATCH, REF) is not None
    placeholder = review_entity_draft(TASK, BATCH, REF, brief, quality)
    assert placeholder["decision"] == "revision_needed"
    assert not placeholder["checks"]["generatorProvenance"]["passed"]

    # 会话模型创作 → review 全绿。
    quality, pack = _compose_entity_agent_draft(TASK, BATCH, REF, brief)
    review = review_entity_draft(TASK, BATCH, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    assert "travelogueDensity" in review["checks"]
    assert review["checks"]["entityCoverage"]["passed"]
    assert review["checks"]["imageGate"]["passed"]
    assert review["checks"]["generatorProvenance"]["passed"]
    assert review["checks"]["factTraceability"]["passed"], review["checks"]["factTraceability"]["issues"]
    assert review["generator"] == "agent"


def test_entity_e2e_materialize_verify_green():
    _seed_sources()
    brief = _entity_brief()
    quality, _pack = _compose_entity_agent_draft(TASK, BATCH, REF, brief)
    review = review_entity_draft(TASK, BATCH, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    posts = materialize_posts(TASK, BATCH, "article")
    assert posts, "materialize produced no entity post"
    # 回归：materialized manifest 的 entityRefs 必须是发布门可识别的全路径。
    import json as _json
    from _common.publish_filter import _parse_entity_ref

    mani = _json.loads((Path(str(posts[0])) / "manifest.json").read_text(encoding="utf-8"))
    assert mani["entityRefs"] == [f"/entity/地点/博物馆/{ENTITY}"], mani["entityRefs"]
    assert _parse_entity_ref(mani["entityRefs"][0]) == ("地点", "博物馆", ENTITY)
    roots, issues = verify_scope(task=TASK, batch=BATCH, scope="current")
    assert roots, "verify found no posts root"
    assert not issues, "entity pilot verify must be green:\n" + "\n".join(issues[:40])


def test_compose_brief_persists_reassigned_base_source_ref():
    _seed_sources()
    brief = _entity_brief()
    write_brief_object(TASK, BATCH, REF, brief, content_type="article")
    initial_ref = "entities/地点/博物馆/三星堆博物馆/1.download/sources/01.curated_story/source.md"
    save_base_draft_ledger(
        TASK,
        BATCH,
        {
            "schemaVersion": "quwoquan_data.base_draft_ledger/1",
            "assignments": {initial_ref: "三星堆博物馆_图集"},
        },
    )

    obj = resolve_entity_object_dir(TASK, BATCH, ENTITY, etype_hint="博物馆")
    write_source_unit(
        obj,
        ordinal=2,
        source_id="museum_story",
        source_md="# 三星堆博物馆\n\n这是一条可写底稿，保留现场叙事。",
        clean_md="# 三星堆博物馆\n\n这是一条可写底稿，保留现场叙事。",
        quality={"sourceId": "museum_story", "quality": "A-story", "score": 8},
        platform="curated",
        source_category="travelogue",
        url="https://example.com/story",
        title="museum story",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
    )

    handle_produce(
        argparse.Namespace(
            task=TASK,
            batch=BATCH,
            type="article",
            stage="compose-brief",
            refs=REF,
            batch_size=1,
            materialize=False,
            allow_partial=False,
        )
    )
    persisted = read_brief_object(TASK, BATCH, REF)
    assert persisted is not None
    assert persisted["baseSourceRef"].endswith("02.museum_story/source.md"), persisted["baseSourceRef"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"entity composer tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
