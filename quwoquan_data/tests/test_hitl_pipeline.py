"""HITL 主线契约：manifest 最小化 + 账本 sidecar + 实体挖掘 + 关联实体主页自动生成。

可直接运行：python3 quwoquan_data/tests/test_hitl_pipeline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_inputs_dir,
    batch_sources_dir,
    ensure_batch_layout,
    ensure_task_layout,
    task_data,
)
from _common.content_evidence import public_byline_label  # noqa: E402
from _common.draft_io import write_agent_draft  # noqa: E402
from _common.review_ledger import load_ledger, KIND_IMAGE  # noqa: E402
from plan.brief import resolve_compose_brief  # noqa: E402
from produce.route_workflow import analyze_route_ref, build_route_writing_pack, review_route_draft  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402
from template.router import RouteRequest  # noqa: E402
from agent_draft_kit import route_article  # noqa: E402

TASK = "hitl_task"
BATCH = "b1"
REF = "川西大环线慢游_跟团_夏"
ENTITIES = ["九寨沟", "稻城亚丁", "色达", "新都桥"]
MINED = "洛绒牛场"

SOURCE_TEXT = """---
url: https://example.com/a
platform: curated
license: internal-curated
allowedUse: internal_reference
title: sample
entity: 九寨沟
retained: true
---

清晨从成都集合出发，先到九寨沟，真正让人愿意慢下来的不是打卡，而是一路进入景区之后雪山和湖水的层次。

门票和观光车都要提前确认，午后雷阵雨容易把转场节奏打乱，排队和返程都要留缓冲。

很多人喜欢九寨沟的清晨光线，但也会抱怨暑期排队、高反和连续坐车太累。
"""


def _clean_image(path: Path, seed: int) -> None:
    img = np.zeros((220, 300, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (150 + seed, 110), 28 + seed * 4, (int(seed * 41) % 255, 70, 160), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def _run_pipeline() -> Path:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    ensure_batch_layout(TASK, BATCH, "produce")
    registry = TemplateRegistry.load()
    brief = resolve_compose_brief(
        registry,
        RouteRequest(
            vertical="travel",
            subject_kind="topic",
            subject_type="旅行/线路",
            intent="跟团指南",
            audience="groupTourTraveler",
            region="高原",
            season="夏",
        ),
        title="川西大环线慢游跟团深度攻略（夏季）",
        entity_refs=[f"地点/景区/{n}" for n in ENTITIES],
    )
    write_json(batch_inputs_dir(TASK, BATCH, "produce", "compose") / f"{REF}.json", brief)
    for idx, entity in enumerate(ENTITIES):
        src_dir = batch_sources_dir(TASK, BATCH, entity) / "curated_story"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "source.md").write_text(SOURCE_TEXT.replace("九寨沟", entity), encoding="utf-8")
        write_json(
            src_dir / "source.quality.json",
            {
                "sourceId": "curated_story",
                "quality": "A-story",
                "score": 8,
                "reasons": ["length_ok", "scene_rich"],
                "excerpt": f"{entity} 这一段真正影响体验的是转场和停留的平衡。",
                "url": f"https://example.com/{entity}",
            },
        )
        images_dir = batch_sources_dir(TASK, BATCH, entity) / "images"
        for k in range(2):
            _clean_image(images_dir / f"{entity}_{k}.jpg", seed=idx * 7 + k + 1)

    quality = analyze_route_ref(TASK, BATCH, REF, brief)
    pack = build_route_writing_pack(TASK, BATCH, REF, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    node_names = [str(n) for n in (pack.get("routeEntities") or []) if n] or ENTITIES
    article = route_article(brief["titleHint"], byline, node_names, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        TASK,
        BATCH,
        REF,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        extracted_entities=[{"name": MINED, "type": "自然景观", "evidenceRef": "curated_story"}],
    )
    review = review_route_draft(TASK, BATCH, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    posts = materialize_posts(TASK, BATCH, "article")
    assert posts, "materialize produced no posts"
    return posts[0]


def test_manifest_is_minimal_and_trace_offloaded():
    post_dir = _run_pipeline()
    manifest = read_json(post_dir / "manifest.json")
    for dropped in ("storySpine", "sourceQuality", "relatedSearchPlan", "evidenceBundle", "sourcePaths"):
        assert dropped not in manifest, f"manifest 不应再含中间态 {dropped}"
    assert manifest["topicId"] == REF
    assert manifest["generator"] == "agent"
    trace = read_json(post_dir / "produce_trace.json")
    assert "evidenceBundle" in trace and "sourcePaths" in trace


def test_ledger_written_and_copied():
    post_dir = _run_pipeline()
    ledger = load_ledger(TASK, BATCH, REF)
    assert ledger is not None, "review 必须落账本"
    assert ledger.article is not None
    assert ledger.images, "应有逐图 agent 判定项"
    # 账本随 post 流转
    copied = read_json(post_dir / "review" / "ledger.json")
    assert copied["ref"] == REF
    assert any(i["kind"] == KIND_IMAGE for i in copied["images"])


def test_mined_entity_homepage_generated():
    post_dir = _run_pipeline()
    sidecar = read_json(post_dir / "review" / "entities.json")
    names = {e["name"]: e for e in sidecar["entities"]}
    assert MINED in names, "应挖掘出专有实体"
    ent = names[MINED]
    assert ent["hasHomepage"] is True
    # 关联实体主页 page.md 真实生成在 task entities 下（无主页的抽取实体会被自动建主页）
    page = task_data(TASK).entity_page(ent["domain"], ent["type"], MINED)
    assert page.is_file(), "无主页的抽取实体应自动生成关联实体主页"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"hitl pipeline tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
