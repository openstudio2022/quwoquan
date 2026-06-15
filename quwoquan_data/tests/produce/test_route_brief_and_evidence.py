"""Route brief + evidence workflow contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(SCRIPTS_ROOT))

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

from _common.evidence_contract import quality_payload_contract_issues  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import batch_inputs_dir, ensure_batch_layout, ensure_task_layout  # noqa: E402
from _common.content_evidence import extract_source_evidence, public_byline_label  # noqa: E402
from _common.draft_io import read_writing_pack, write_agent_draft, prompt_path, read_draft_meta  # noqa: E402
from _common.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from plan.brief import resolve_compose_brief  # noqa: E402
from produce.route_workflow import analyze_route_ref, build_route_writing_pack, review_route_draft  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402
from template.router import RouteRequest  # noqa: E402
from helpers.agent_draft_kit import route_article  # noqa: E402


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


def test_extract_source_evidence_recognizes_scenic_appreciation_as_like():
    evidence = extract_source_evidence(
        "峨眉山风景秀丽，素有峨眉天下秀的美誉。金顶日出、云海、佛光与圣灯常被并称为可遇不可求的景观。",
        entity_name="峨眉山",
    )

    likes = [entry["sentence"] for entry in evidence["emotionEvidence"] if entry.get("kind") == "like"]
    assert likes
    assert any("风景秀丽" in sentence or "峨眉天下秀" in sentence for sentence in likes)


def test_route_workflow_generates_real_review_green():
    task_id = "route_workflow_test"
    batch_id = "pilot"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    write_batch_manifest(task_id, batch_id, command="produce")

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
    image_root = Path(tempfile.mkdtemp(prefix="route_brief_sources_"))
    for entity in ("九寨沟", "稻城亚丁", "色达", "新都桥"):
        obj = resolve_entity_object_dir(task_id, batch_id, entity, etype_hint="景区")
        image_paths: list[Path] = []
        for k in range(2):
            image_path = image_root / f"{entity}_{k}.jpg"
            _write_clean_image(image_path, seed=hash(entity) % 50 + k + 1)
            image_paths.append(image_path)
        write_source_unit(
            obj,
            ordinal=1,
            source_id="curated_story",
            source_md=source_text.replace("九寨沟", entity),
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

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(task_id, batch_id, ref, brief)
    assert quality_payload["recommendation"] == "proceed"
    assert quality_payload["evidenceBundle"]["coverage"]["coveredEntityCount"] == 4
    assert quality_payload_contract_issues(quality_payload) == []
    for dropped in ("storySpine", "sourceQuality", "relatedSearchPlan"):
        assert dropped not in quality_payload
    assert quality_payload["evidenceBundle"]["storySpine"]["beats"]

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
        agent_run_id="run-route-green",
        agent_id="agent-route-green",
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


def test_agent_draft_time_facts_are_stable_and_monotonic():
    task_id = "route_workflow_time_facts"
    batch_id = "pilot"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    write_batch_manifest(task_id, batch_id, command="produce")

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
        title="时间事实校验线路",
        entity_refs=["地点/景区/九寨沟"],
    )
    ref = "时间事实校验线路"
    write_json(batch_inputs_dir(task_id, batch_id, "produce", "compose") / f"{ref}.json", brief)
    obj = resolve_entity_object_dir(task_id, batch_id, "九寨沟", etype_hint="景区")
    source_text = """---
url: https://example.com/jzg
platform: curated
license: internal-curated
allowedUse: internal_reference
title: sample
entity: 九寨沟
retained: true
---

九寨沟的清晨让人愿意慢下来。"""
    image_path = Path(tempfile.mkdtemp(prefix="route_time_facts_")) / "九寨沟_0.jpg"
    _write_clean_image(image_path, seed=7)
    write_source_unit(
        obj,
        ordinal=1,
        source_id="curated_story",
        source_md=source_text,
        quality={
            "sourceId": "curated_story",
            "quality": "A-story",
            "score": 8,
            "reasons": ["length_ok"],
            "excerpt": "九寨沟清晨体验",
            "url": "https://example.com/jzg",
        },
        platform="curated",
        source_category="internal-curated",
        url="https://example.com/jzg",
        title="sample",
        target_ref="/entity/地点/景区/九寨沟",
        relevance="九寨沟路线证据",
        images=[{"sourcePath": str(image_path), "caption": "九寨沟", "relevance": "九寨沟"}],
    )
    quality_payload = analyze_route_ref(task_id, batch_id, ref, brief)
    pack = build_route_writing_pack(task_id, batch_id, ref, brief, quality_payload)
    write_agent_draft(
        task_id,
        batch_id,
        ref,
        route_article(brief["titleHint"], public_byline_label(str(brief.get("templateId")), brief.get("creator") or {}), ["九寨沟"], pack.get("mustIncludeFacts") or []),
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-route-time-1",
        agent_id="agent-route-time",
    )
    first_meta = read_draft_meta(task_id, batch_id, ref)
    assert first_meta is not None
    assert first_meta["createdAt"] == first_meta["updatedAt"]

    write_agent_draft(
        task_id,
        batch_id,
        ref,
        route_article(brief["titleHint"], public_byline_label(str(brief.get("templateId")), brief.get("creator") or {}), ["九寨沟"], ["新增事实"]),
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=["新增事实"],
        agent_run_id="run-route-time-2",
        agent_id="agent-route-time",
    )
    second_meta = read_draft_meta(task_id, batch_id, ref)
    assert second_meta is not None
    assert second_meta["createdAt"] == first_meta["createdAt"]
    assert second_meta["updatedAt"] >= first_meta["updatedAt"]


def test_route_skip_does_not_prepare_writing_pack():
    task_id = "route_workflow_skip_test"
    batch_id = "pilot"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    write_batch_manifest(task_id, batch_id, command="produce")

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

    reject_text = """---
url: https://example.com/probe
platform: mafengwo
license: fetch-required
allowedUse: internal_reference
entity: 九寨沟
retained: false
taskProvidedBody: true
---

manual_source_plan_note: 探针页，正文抓取失败。
"""
    for entity in ("九寨沟", "稻城亚丁", "色达", "新都桥"):
        obj = resolve_entity_object_dir(task_id, batch_id, entity, etype_hint="景区")
        write_source_unit(
            obj,
            ordinal=1,
            source_id="failed_probe",
            source_md=reject_text.replace("九寨沟", entity),
            quality={
                "sourceId": "failed_probe",
                "quality": "Reject",
                "score": 0,
                "reasons": ["fetch_failed"],
                "excerpt": "",
                "url": f"https://example.com/{entity}",
                "fetchSucceeded": False,
            },
            platform="mafengwo",
            source_category="travelogue",
            url=f"https://example.com/{entity}",
            title="probe",
            target_ref=f"/entity/地点/景区/{entity}",
            relevance=f"{entity} 探针页",
        )

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(task_id, batch_id, ref, brief)
    assert quality_payload["recommendation"] == "skip", quality_payload
    assert read_writing_pack(task_id, batch_id, ref) is None


def test_route_review_blocks_intra_doc_repetition_padding():
    task_id = "route_workflow_repeat_test"
    batch_id = "pilot"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    write_batch_manifest(task_id, batch_id, command="produce")

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
    image_root = Path(tempfile.mkdtemp(prefix="route_brief_repeat_sources_"))
    for entity in ("九寨沟", "稻城亚丁", "色达", "新都桥"):
        obj = resolve_entity_object_dir(task_id, batch_id, entity, etype_hint="景区")
        image_path = image_root / f"{entity}.jpg"
        _write_clean_image(image_path, seed=hash(entity) % 50 + 1)
        write_source_unit(
            obj,
            ordinal=1,
            source_id="curated_story",
            source_md=source_text.replace("九寨沟", entity),
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
            images=[{"sourcePath": str(image_path), "caption": f"{entity} 图", "relevance": f"{entity} 图"}],
        )

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(task_id, batch_id, ref, brief)
    pack = build_route_writing_pack(task_id, batch_id, ref, brief, quality_payload)
    repeated = "另外，九寨沟在这篇里强调慢看与错峰，别用赶场心态压缩体验。"
    article = (
        f"# {brief['titleHint']}\n\n"
        f"> {public_byline_label(str(brief.get('templateId')), brief.get('creator') or {})}\n\n"
        "先把正常开头写清楚。\n\n"
        "再补一段正常行程判断。\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n"
    )
    write_agent_draft(
        task_id,
        batch_id,
        ref,
        article,
        model="test-agent/repetition",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-route-repeat",
        agent_id="agent-route-repeat",
    )
    review_payload = review_route_draft(task_id, batch_id, ref, brief, quality_payload)
    assert review_payload["decision"] == "revision_needed"
    assert any("intraDocRepetition" in issue for issue in review_payload["checks"]["provenanceRewrite"]["issues"]), review_payload


if __name__ == "__main__":
    test_route_brief_includes_narrative_contract()
    test_route_workflow_generates_real_review_green()
    test_route_skip_does_not_prepare_writing_pack()
    test_route_review_blocks_intra_doc_repetition_padding()
    print("route brief and evidence tests passed")
