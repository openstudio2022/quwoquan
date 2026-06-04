"""Route brief + evidence workflow contract tests."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import os

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402


def _write_clean_image(path: Path, seed: int) -> None:
    img = np.zeros((220, 300, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (150 + seed, 110), 30 + seed * 4, (int(seed * 41) % 255, 70, 160), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.io import write_json  # noqa: E402
from _common.paths import batch_inputs_dir, batch_sources_dir, ensure_batch_layout, ensure_task_layout  # noqa: E402
from _common.content_evidence import public_byline_label  # noqa: E402
from _common.draft_io import read_writing_pack, write_agent_draft, prompt_path, read_draft_meta  # noqa: E402
from plan.brief import resolve_compose_brief  # noqa: E402
from produce.route_workflow import analyze_route_ref, build_route_writing_pack, review_route_draft  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402
from template.router import RouteRequest  # noqa: E402
from agent_draft_kit import route_article  # noqa: E402


def test_route_brief_includes_narrative_contract():
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
        entity_refs=[
            "地点/景区/九寨沟",
            "地点/景区/稻城亚丁",
            "地点/景区/色达",
            "地点/景区/新都桥",
        ],
    )
    assert brief["templateId"] == "线路_跟团攻略"
    assert brief["narrativeMode"]["kind"] == "route_decision"
    assert brief["evidenceRequirements"]["emotion"]["required"] is True
    assert brief["continuityExpectations"]["requireProgression"] is True
    assert brief["routeCoverageExpectations"]["minCoveredEntityRefs"] == 3
    assert len(brief["narrativePlan"]["routeNodes"]) == 4


def test_route_workflow_generates_real_review_green():
    task_id = "route_workflow_test"
    batch_id = "pilot"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")

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
        entity_refs=[
            "地点/景区/九寨沟",
            "地点/景区/稻城亚丁",
            "地点/景区/色达",
            "地点/景区/新都桥",
        ],
    )
    write_json(batch_inputs_dir(task_id, batch_id, "produce", "compose") / "川西大环线慢游_跟团_夏.json", brief)

    source_text = """---
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
    for entity in ("九寨沟", "稻城亚丁", "色达", "新都桥"):
        src_dir = batch_sources_dir(task_id, batch_id, entity) / "curated_story"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "source.md").write_text(source_text.replace("九寨沟", entity), encoding="utf-8")
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
        images_dir = batch_sources_dir(task_id, batch_id, entity) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        for k in range(2):
            _write_clean_image(images_dir / f"{entity}_{k}.jpg", seed=hash(entity) % 50 + k + 1)

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(task_id, batch_id, ref, brief)
    assert quality_payload["recommendation"] == "proceed"
    assert quality_payload["evidenceBundle"]["coverage"]["coveredEntityCount"] == 4

    # prepare：CLI 只产写作契约 + prompt + 占位草稿（不拼正文）。
    pack = build_route_writing_pack(task_id, batch_id, ref, brief, quality_payload)
    assert pack["kind"] == "route"
    assert pack["assets"], "writing pack must select assets"
    assert prompt_path(task_id, batch_id, ref).exists()
    assert read_writing_pack(task_id, batch_id, ref) is not None
    # 占位阶段：generator=pending，review 必须判 revision（出处门拦截脚本/占位）。
    placeholder_review = review_route_draft(task_id, batch_id, ref, brief, quality_payload)
    assert placeholder_review["decision"] == "revision_needed"
    assert not placeholder_review["checks"]["generatorProvenance"]["passed"]

    # 会话模型创作正文写回草稿（generator=agent）。
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    node_names = ["九寨沟", "稻城亚丁", "色达", "新都桥"]
    article = route_article(brief["titleHint"], byline, node_names, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        task_id,
        batch_id,
        ref,
        article,
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
    )
    assert read_draft_meta(task_id, batch_id, ref)["generator"] == "agent"

    review_payload = review_route_draft(task_id, batch_id, ref, brief, quality_payload)
    assert review_payload["decision"] == "approved", review_payload["issues"]
    assert review_payload["checks"]["routeCoverage"]["passed"] is True
    assert review_payload["checks"]["narrativeContinuity"]["passed"] is True
    assert review_payload["checks"]["travelogueDensity"]["passed"] is True, review_payload["checks"]["travelogueDensity"]["issues"]
    assert review_payload["checks"]["imageGate"]["passed"] is True, review_payload["checks"]["imageGate"]["issues"]
    assert review_payload["checks"]["carrierConsistency"]["passed"] is True
    assert review_payload["checks"]["generatorProvenance"]["passed"] is True
    assert review_payload["checks"]["factTraceability"]["passed"] is True, review_payload["checks"]["factTraceability"]["issues"]
    assert review_payload["humanReviewRequired"] is False
    assert review_payload["generator"] == "agent"


if __name__ == "__main__":
    test_route_brief_includes_narrative_contract()
    test_route_workflow_generates_real_review_green()
    print("route brief and evidence tests passed")
