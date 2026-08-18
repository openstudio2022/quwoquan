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

from core.evidence_contract import quality_payload_contract_issues  # noqa: E402
from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.io import write_json  # noqa: E402
from core.paths import execution_inputs_dir, ensure_execution_command_layout, ensure_execution_layout  # noqa: E402
from content.post.article.evidence_bundle import (  # noqa: E402
    extract_source_evidence,
    gate_route_evidence_bundle,
    public_byline_label,
)
from content.post.article.draft_io import read_writing_pack, write_agent_draft, prompt_path, read_draft_meta  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from content.execution.planning.brief import resolve_compose_brief  # noqa: E402
from content.post.article.route_analysis import analyze_route_ref  # noqa: E402
from content.post.article.route_compose import build_route_writing_pack  # noqa: E402
from content.post.article.route_review import review_route_draft  # noqa: E402
from content.templates.registry import TemplateRegistry  # noqa: E402
from content.templates.router import RouteRequest  # noqa: E402
from support.helpers.agent_draft_kit import route_article  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402


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


def test_extract_source_evidence_recognizes_travelogue_emotion_phrases():
    evidence = extract_source_evidence(
        "吃上了心心念念的雅鱼，真的很幸运。那一口太美味了，是这趟路上一大幸福。过桥时全程腿抖，确实害怕。",
        entity_name="测试实体丙",
    )

    likes = [entry["sentence"] for entry in evidence["emotionEvidence"] if entry.get("kind") == "like"]
    pains = [entry["sentence"] for entry in evidence["emotionEvidence"] if entry.get("kind") == "pain"]
    assert any("心心念念" in sentence or "太美味" in sentence for sentence in likes)
    assert any("腿抖" in sentence for sentence in pains)


def test_extract_source_evidence_uses_scenic_alias_for_mainline():
    evidence = extract_source_evidence(
        "五台山国家公园位于忻州五台县东北隅。五台山属有华北屋脊之称的太行山系北端山峰群。",
        entity_name="五台山风景名胜区",
    )

    assert evidence["mainlineEvidence"]
    assert any("五台山国家公园" in sentence for sentence in evidence["mainlineEvidence"])


def test_extract_source_evidence_folds_common_zh_variants_for_mainline():
    evidence = extract_source_evidence(
        "雲台山位於河南焦作修武，地處太行山南麓，是以峽谷地貌與水體景觀為特色的景區。",
        entity_name="云台山－神农山－青天河风景区",
    )

    assert evidence["mainlineEvidence"]
    assert any("雲台山" in sentence for sentence in evidence["mainlineEvidence"])


def test_gate_route_evidence_skips_narrative_requirements_for_image_carrier():
    """载体错配根因：image/gallery 画报曾被线路叙事门（情感/storySpine/路线覆盖）误门控。

    开放许可图集（Wikimedia/CC）只有事实性 caption、无 UGC 互动信号，必然缺 emotion evidence，
    旧逻辑会把整批 post_compose 判 `missing emotion evidence` 转人工。图片作品的把关由
    许可(rights)/资产落盘/相关性/works_gate 负责，不应受线路证据门约束。
    """
    empty_bundle: dict = {
        "coverage": {"coveredEntityCount": 0},
        "routeNodes": [],
        "emotionSignals": {"likes": [], "painPoints": []},
        "storySpine": {},
    }
    for carrier in ("image", "Image"):
        brief = {
            "carrier": carrier,
            "evidenceRequirements": {"emotion": {"required": True}},
            "mustIncludeFacts": ["九寨沟五花海"],
        }
        assert gate_route_evidence_bundle(brief, empty_bundle) == [], carrier


def test_gate_route_evidence_still_gates_narrative_carriers():
    """回归护栏：article/route 等叙事载体在空证据下仍必须被拦截，禁止载体感知误伤叙事门。"""
    empty_bundle: dict = {
        "coverage": {"coveredEntityCount": 0},
        "routeNodes": [],
        "emotionSignals": {"likes": [], "painPoints": []},
        "storySpine": {},
    }
    for carrier in ("article", "route", ""):
        brief = {
            "carrier": carrier,
            "evidenceRequirements": {"emotion": {"required": True}},
        }
        issues = gate_route_evidence_bundle(brief, empty_bundle)
        assert any("missing emotion evidence" in issue for issue in issues), (carrier, issues)
        assert any("route progression spine" in issue for issue in issues), (carrier, issues)


def test_route_review_generates_real_review_green():
    execution_id = "20260711--travel-article-route--test-region-b--pilot-001"
    build_execution_fixture(execution_id)
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    ensure_execution_command_layout(execution_id, "post")
    write_execution_runtime_state(execution_id, command="post")

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
    write_json(execution_inputs_dir(execution_id, "post", "compose") / "川西大环线慢游_跟团_夏.json", brief)

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
    base_source_ref = ""
    for entity_index, entity in enumerate(
        ("九寨沟", "稻城亚丁", "色达", "新都桥")
    ):
        obj = resolve_entity_object_dir(execution_id, entity, etype_hint="景区")
        image_paths: list[Path] = []
        for k in range(2):
            image_path = image_root / f"{entity}_{k}.jpg"
            _write_clean_image(image_path, seed=7 + entity_index * 2 + k)
            image_paths.append(image_path)
        source_manifest = write_source_unit(
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
        if entity == "九寨沟":
            base_source_ref = str(source_manifest["sourceRef"])

    brief["baseSourceRef"] = base_source_ref
    write_json(
        execution_inputs_dir(execution_id, "post", "compose")
        / "川西大环线慢游_跟团_夏.json",
        brief,
    )

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(execution_id, ref, brief)
    assert quality_payload["recommendation"] == "proceed"
    assert quality_payload["evidenceBundle"]["coverage"]["coveredEntityCount"] == 4
    assert quality_payload_contract_issues(quality_payload) == []
    for dropped in ("storySpine", "sourceQuality", "relatedSearchPlan"):
        assert dropped not in quality_payload
    assert quality_payload["evidenceBundle"]["storySpine"]["beats"]

    # prepare：CLI 只产写作契约 + prompt + 占位草稿（不拼正文）。
    pack = build_route_writing_pack(execution_id, ref, brief, quality_payload)
    assert pack["kind"] == "route"
    assert pack["assets"], "writing pack must select assets"
    assert prompt_path(execution_id, ref).exists()
    assert read_writing_pack(execution_id, ref) is not None
    # 占位阶段：generator=pending，review 必须判 revision（出处门拦截脚本/占位）。
    placeholder_review = review_route_draft(execution_id, ref, brief, quality_payload)
    assert placeholder_review["decision"] == "revision_needed"
    assert not placeholder_review["checks"]["generatorProvenance"]["passed"]

    # 会话模型创作正文写回草稿（generator=agent）。
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    node_names = ["九寨沟", "稻城亚丁", "色达", "新都桥"]
    article = route_article(brief["titleHint"], byline, node_names, pack.get("mustIncludeFacts") or [])
    write_agent_draft(
        execution_id,
        ref,
        article,
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-route-green",
        agent_id="agent-route-green",
    )
    assert read_draft_meta(execution_id, ref)["generator"] == "agent"

    review_payload = review_route_draft(execution_id, ref, brief, quality_payload)
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
    execution_id = "20260711--travel-article-route-time--test-region-b--pilot-002"
    build_execution_fixture(execution_id)
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    ensure_execution_command_layout(execution_id, "post")
    write_execution_runtime_state(execution_id, command="post")

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
    write_json(execution_inputs_dir(execution_id, "post", "compose") / f"{ref}.json", brief)
    obj = resolve_entity_object_dir(execution_id, "九寨沟", etype_hint="景区")
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
    image_root = Path(tempfile.mkdtemp(prefix="route_time_facts_"))
    image_paths = [image_root / "九寨沟_0.jpg", image_root / "九寨沟_1.jpg"]
    for seed, image_path in enumerate(image_paths, start=7):
        _write_clean_image(image_path, seed=seed)
    source_manifest = write_source_unit(
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
        images=[
            {
                "sourcePath": str(image_path),
                "caption": f"九寨沟图{index}",
                "relevance": f"九寨沟图{index}",
            }
            for index, image_path in enumerate(image_paths)
        ],
    )
    brief["baseSourceRef"] = source_manifest["sourceRef"]
    write_json(
        execution_inputs_dir(execution_id, "post", "compose") / f"{ref}.json",
        brief,
    )
    quality_payload = analyze_route_ref(execution_id, ref, brief)
    pack = build_route_writing_pack(execution_id, ref, brief, quality_payload)
    write_agent_draft(
        execution_id,
        ref,
        route_article(brief["titleHint"], public_byline_label(str(brief.get("templateId")), brief.get("creator") or {}), ["九寨沟"], pack.get("mustIncludeFacts") or []),
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-route-time-1",
        agent_id="agent-route-time",
    )
    first_meta = read_draft_meta(execution_id, ref)
    assert first_meta is not None
    assert first_meta["createdAt"] == first_meta["updatedAt"]

    write_agent_draft(
        execution_id,
        ref,
        route_article(brief["titleHint"], public_byline_label(str(brief.get("templateId")), brief.get("creator") or {}), ["九寨沟"], ["新增事实"]),
        model="test-agent/contract",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=["新增事实"],
        agent_run_id="run-route-time-2",
        agent_id="agent-route-time",
    )
    second_meta = read_draft_meta(execution_id, ref)
    assert second_meta is not None
    assert second_meta["createdAt"] == first_meta["createdAt"]
    assert second_meta["updatedAt"] >= first_meta["updatedAt"]


def test_route_skip_does_not_prepare_writing_pack():
    execution_id = "20260711--travel-article-route-skip--test-region-b--pilot-003"
    build_execution_fixture(execution_id)
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    ensure_execution_command_layout(execution_id, "post")
    write_execution_runtime_state(execution_id, command="post")

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
    write_json(execution_inputs_dir(execution_id, "post", "compose") / "川西大环线慢游_跟团_夏.json", brief)

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
        obj = resolve_entity_object_dir(execution_id, entity, etype_hint="景区")
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
    quality_payload = analyze_route_ref(execution_id, ref, brief)
    assert quality_payload["recommendation"] == "skip", quality_payload
    assert read_writing_pack(execution_id, ref) is None


def test_route_review_blocks_intra_doc_repetition_padding():
    execution_id = "20260711--travel-article-route-repeat--test-region-b--pilot-004"
    build_execution_fixture(execution_id)
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    ensure_execution_command_layout(execution_id, "post")
    write_execution_runtime_state(execution_id, command="post")

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
    write_json(execution_inputs_dir(execution_id, "post", "compose") / "川西大环线慢游_跟团_夏.json", brief)

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
    base_source_ref = ""
    for entity_index, entity in enumerate(
        ("九寨沟", "稻城亚丁", "色达", "新都桥")
    ):
        obj = resolve_entity_object_dir(execution_id, entity, etype_hint="景区")
        image_paths = [image_root / f"{entity}_0.jpg"]
        if entity == "九寨沟":
            image_paths.append(image_root / f"{entity}_1.jpg")
        for index, image_path in enumerate(image_paths):
            _write_clean_image(image_path, seed=7 + entity_index * 2 + index)
        source_manifest = write_source_unit(
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
            images=[
                {
                    "sourcePath": str(image_path),
                    "caption": f"{entity} 图{index}",
                    "relevance": f"{entity} 图{index}",
                }
                for index, image_path in enumerate(image_paths)
            ],
        )
        if entity == "九寨沟":
            base_source_ref = str(source_manifest["sourceRef"])

    brief["baseSourceRef"] = base_source_ref
    write_json(
        execution_inputs_dir(execution_id, "post", "compose")
        / "川西大环线慢游_跟团_夏.json",
        brief,
    )

    ref = "川西大环线慢游_跟团_夏"
    quality_payload = analyze_route_ref(execution_id, ref, brief)
    pack = build_route_writing_pack(execution_id, ref, brief, quality_payload)
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
        execution_id,
        ref,
        article,
        model="test-agent/repetition",
        cited_source_paths=quality_payload.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id="run-route-repeat",
        agent_id="agent-route-repeat",
    )
    review_payload = review_route_draft(execution_id, ref, brief, quality_payload)
    assert review_payload["decision"] == "revision_needed"
    assert any("intraDocRepetition" in issue for issue in review_payload["checks"]["provenanceRewrite"]["issues"]), review_payload


def test_factual_article_prompt_uses_source_as_facts_not_expression_draft():
    """factual_reference_only 不得再以保真为由要求保留跨城原段落。"""
    from content.post.article.prompt_renderer import render_prompt_md

    pack = {
        "ref": "都江堰__article_qunar_base_1",
        "kind": "entity",
        "carrier": "article",
        "title": "彭水.成都.都江堰.乐山.赤水.遵义 渝蜀贵自驾穷游漫记",
        "templateId": "travel.entity.guide",
        "byline": "虚拟创作者",
        "writingIntent": "planning_consultation",
        "sourceUseMode": "factual_reference_only",
        "baseSourceRef": "sources/su_demo/source.md",
        "baseDraftText": "彭水乌江画廊碧波，成都青石板烟火，都江堰千年石堤，乐山大佛慈悲。" * 20,
        "wordCount": {"min": 600, "max": 2000},
    }
    prompt = render_prompt_md(pack)
    assert "事实参考材料" in prompt
    assert "只取事实，不保留表达" in prompt
    assert "禁止保留来源连续长句" in prompt
    assert "整篇保留" not in prompt
    assert "实体只是标签" not in prompt


def test_article_section_intents_do_not_force_single_entity_focus():
    """章节意图不得把多目的地底稿框成「关于某实体的那篇」诱导裁剪。"""
    from content.post.article.entity_composition import _entity_section_intents

    intents = _entity_section_intents({"subject": {"type": "地点/景区"}}, "都江堰")
    joined = "\n".join(intents)
    assert "关于 都江堰 的那篇" not in joined, joined
    assert ("全部站点" in joined) or ("多目的地" in joined), joined


def test_article_prompt_first_pass_hardening_contract():
    """0704a 弃稿主因修复（cs100 可靠性 S1）：同实体多篇骨架/开篇趋同、底稿重复段落轻改保留、
    平台词泄漏、单章节吞篇/时间线回跳，都必须在 prompt 合同中有明确针对性指令。"""
    from content.post.article.prompt_renderer import _preferred_opening_index, render_prompt_md

    def _pack(ref: str) -> dict:
        return {
            "ref": ref,
            "kind": "entity",
            "carrier": "article",
            "title": "青城山两日慢游记",
            "templateId": "travel.entity.guide",
            "byline": "虚拟创作者",
            "writingIntent": "planning_consultation",
            "sourceUseMode": "factual_reference_only",
            "styleFamily": "旅途随笔风",
            "baseSourceRef": "sources/su_demo/source.md",
            "baseDraftText": "青城山的清晨，山门薄雾。\n**住宿**：成都东站附近公寓。\n" * 30,
            "wordCount": {"min": 600, "max": 2000},
        }

    prompt = render_prompt_md(_pack("青城山__article_qunar_base_12"))
    # ① 同实体差异化：确定性优先开篇策略 + 禁通用模板骨架。
    assert "本篇优先" in prompt, prompt[:600]
    assert "同实体差异化" in prompt
    assert "禁止与其它文章共用同一套开场白或标题序列" in prompt
    # ② 底稿内重复段落去重（治 intraDocRepetition）。
    assert "禁止保留来源连续长句" in prompt
    # ③ 平台词点名（治 provenanceRewrite 泄漏「大众点评」等）。
    assert "大众点评" in prompt
    assert "去哪儿" in prompt
    # ④ 章节结构合同（治 carrierConsistency/sectionBalance/timelineOrder）。
    assert "章节结构合同" in prompt
    assert "60%" in prompt
    assert "单一时间顺序" in prompt

    # 确定性轮转：同一 ref 稳定；不同 sibling ref 在候选数 >1 时应可分散（crc32 轮转）。
    n = 3
    idx_a = _preferred_opening_index("青城山__article_qunar_base_12", n)
    assert idx_a == _preferred_opening_index("青城山__article_qunar_base_12", n)
    spread = {
        _preferred_opening_index(f"青城山__article_qunar_base_{i}", n) for i in range(8)
    }
    assert len(spread) > 1, spread


def test_base_aware_word_count_tracks_long_base_draft():
    """根因：wordCount 固定上限(1600)远小于长底稿(~8900字)时，baseDraftFidelity>=55% 数学不可达
    （成稿最多覆盖底稿 ~18% 三连）。light-edit 文章字数目标必须按清洗底稿长度派生。"""
    from content.post.article.base_draft_analysis import base_aware_word_count, clean_base_draft_length

    long_base = "都江堰的清晨薄雾未散，我们沿着秦堰楼一路下行，江风裹着水汽扑面而来。\n" * 200
    clean_len = clean_base_draft_length(long_base)
    assert clean_len > 5000, clean_len
    wc = base_aware_word_count(long_base, carrier="article", source_use_mode="licensed_adaptation")
    assert wc is not None
    # 上限跟随底稿，不再被固定 1600 钉死。
    assert wc["max"] > 1600 and wc["max"] >= clean_len, wc
    assert wc["min"] >= 600, wc
    # 数学可行：成稿达到 min 且逐句沿用底稿即可覆盖 >=55% 三连。
    assert wc["min"] >= int(clean_len * 0.55), (wc, clean_len)
    # image/gallery（短配文）与非改编源不设底稿字数门。
    assert base_aware_word_count(long_base, carrier="article", source_use_mode="factual_reference_only") is None
    assert base_aware_word_count(long_base, carrier="image", source_use_mode="licensed_adaptation") is None
    assert base_aware_word_count(long_base, carrier="article", source_use_mode="blocked") is None
    # 短底稿（< 文章下限）不强行抬高字数门。
    assert base_aware_word_count("一句话。", carrier="article", source_use_mode="licensed_adaptation") is None


if __name__ == "__main__":
    test_route_brief_includes_narrative_contract()
    test_gate_route_evidence_skips_narrative_requirements_for_image_carrier()
    test_gate_route_evidence_still_gates_narrative_carriers()
    test_route_review_generates_real_review_green()
    test_route_skip_does_not_prepare_writing_pack()
    test_route_review_blocks_intra_doc_repetition_padding()
    test_article_prompt_preserves_whole_base_draft_no_irrelevant_city_trim()
    test_article_section_intents_do_not_force_single_entity_focus()
    test_article_prompt_first_pass_hardening_contract()
    test_base_aware_word_count_tracks_long_base_draft()
    print("route brief and evidence tests passed")
