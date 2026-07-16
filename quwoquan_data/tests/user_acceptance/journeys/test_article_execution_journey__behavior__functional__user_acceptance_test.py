"""用户验收：article execution 端到端（analyze->compose->review->materialize->verify）应全绿。

可直接运行：python3 quwoquan_data/tests/user_acceptance/journeys/test_verify_pilot_gwt__behavior__functional__user_acceptance_test.py
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

_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="verify_pilot_rt_"))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.io import write_json  # noqa: E402
from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.paths import (  # noqa: E402
    execution_inputs_dir,
    ensure_execution_command_layout,
    ensure_execution_layout,
)
import core.paths as _paths_mod  # noqa: E402
from content.post.evidence_bundle import public_byline_label  # noqa: E402
from content.post.draft_io import write_agent_draft  # noqa: E402
from verify.post_verify import verify_scope  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from content.execution.planning.brief import resolve_compose_brief  # noqa: E402
from content.post.route_analysis import analyze_route_ref  # noqa: E402
from content.post.route_compose import build_route_writing_pack  # noqa: E402
from content.post.route_review import review_route_draft  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402
from content.templates.registry import TemplateRegistry  # noqa: E402
from content.templates.router import RouteRequest  # noqa: E402
from support.helpers.agent_draft_kit import route_article  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

EXECUTION_ID = "20260711--travel-article-pilot-uat--cn-sichuan--canary-001"
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


def _retarget_runtime() -> None:
    os.environ["QWQ_OUTPUT_ROOT"] = str(_RUNTIME_ROOT)
    _paths_mod.RUNTIME_ROOT = _RUNTIME_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _RUNTIME_ROOT / "tasks"


def _clean_image(path: Path, seed: int) -> None:
    img = np.zeros((220, 300, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (150 + seed, 110), 28 + seed * 4, (int(seed * 41) % 255, 70, 160), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def test_article_execution_journey_is_green():
    _retarget_runtime()
    build_execution_fixture(EXECUTION_ID)
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "source")
    ensure_execution_command_layout(EXECUTION_ID, "post")
    write_execution_runtime_state(EXECUTION_ID, command="post")
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
    write_json(execution_inputs_dir(EXECUTION_ID, "post", "compose") / f"{REF}.json", brief)
    image_root = Path(tempfile.mkdtemp(prefix="verify_pilot_sources_"))
    for idx, entity in enumerate(ENTITIES):
        obj = resolve_entity_object_dir(EXECUTION_ID, entity, etype_hint="景区")
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

    quality = analyze_route_ref(EXECUTION_ID, REF, brief)
    pack = build_route_writing_pack(EXECUTION_ID, REF, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    article = route_article(brief["titleHint"], byline, ENTITIES, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        EXECUTION_ID,
        REF,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-verify-pilot",
        agent_id="agent-verify-pilot",
    )
    review = review_route_draft(EXECUTION_ID, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]

    posts = materialize_posts(EXECUTION_ID, "article")
    assert posts, "materialize produced no posts"

    roots, issues = verify_scope(execution_id=EXECUTION_ID, scope="current")
    assert roots, "verify found no posts root for the pilot execution"
    assert not issues, "pilot verify must be green:\n" + "\n".join(issues[:40])


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"verify pilot GWT passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
