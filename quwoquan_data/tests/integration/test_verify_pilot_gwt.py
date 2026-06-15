"""GWT：川西 pilot 端到端（analyze->compose->review->materialize->verify）应全绿。

可直接运行：python3 quwoquan_data/tests/integration/test_verify_pilot_gwt.py
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

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.io import write_json  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_inputs_dir,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.content_evidence import public_byline_label  # noqa: E402
from _common.draft_io import write_agent_draft  # noqa: E402
from _common.post_verify import verify_scope  # noqa: E402
from _common.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from plan.brief import resolve_compose_brief  # noqa: E402
from produce.route_workflow import analyze_route_ref, build_route_writing_pack, review_route_draft  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402
from template.router import RouteRequest  # noqa: E402
from helpers.agent_draft_kit import route_article  # noqa: E402

TASK = "川西冷启动_gwt"
BATCH = "pilot"
REF = "川西大环线慢游_跟团_夏"
ENTITIES = ["九寨沟", "稻城亚丁", "色达", "新都桥"]

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


def test_pilot_e2e_verify_green():
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    ensure_batch_layout(TASK, BATCH, "produce")
    write_batch_manifest(TASK, BATCH, command="produce")
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
    image_root = Path(tempfile.mkdtemp(prefix="verify_pilot_sources_"))
    for idx, entity in enumerate(ENTITIES):
        obj = resolve_entity_object_dir(TASK, BATCH, entity, etype_hint="景区")
        image_paths: list[Path] = []
        for k in range(2):
            image_path = image_root / f"{entity}_{k}.jpg"
            _clean_image(image_path, seed=idx * 7 + k + 1)
            image_paths.append(image_path)
        write_source_unit(
            obj,
            ordinal=1,
            source_id="curated_story",
            source_md=SOURCE_TEXT.replace("九寨沟", entity),
            quality={
                "sourceId": "curated_story",
                "quality": "A-story",
                "score": 8,
                "reasons": ["length_ok", "scene_rich"],
                "excerpt": f"{entity} 这一段真正影响体验的是转场和停留的平衡。",
                "url": f"https://example.com/{entity}",
            },
            platform="curated",
            source_category="internal-curated",
            url=f"https://example.com/{entity}",
            title="sample",
            target_ref=f"/entity/地点/景区/{entity}",
            relevance=f"{entity} 路线证据",
            images=[{"sourcePath": str(path), "caption": f"{entity} 图{k}", "relevance": f"{entity} 图{k}"} for k, path in enumerate(image_paths)],
        )

    quality = analyze_route_ref(TASK, BATCH, REF, brief)
    pack = build_route_writing_pack(TASK, BATCH, REF, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    article = route_article(brief["titleHint"], byline, ENTITIES, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        TASK,
        BATCH,
        REF,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-verify-pilot",
        agent_id="agent-verify-pilot",
    )
    review = review_route_draft(TASK, BATCH, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]

    posts = materialize_posts(TASK, BATCH, "article")
    assert posts, "materialize produced no posts"

    roots, issues = verify_scope(task=TASK, batch=BATCH, scope="current")
    assert roots, "verify found no posts root for the pilot batch"
    assert not issues, "pilot verify must be green:\n" + "\n".join(issues[:40])


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"verify pilot GWT passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
