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
from _common.content_evidence import (  # noqa: E402
    extract_source_evidence,
    gate_route_evidence_bundle,
    public_byline_label,
)
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
    旧逻辑会把整批 produce_compose 判 `missing emotion evidence` 转人工。图片作品的把关由
    许可(rights)/资产落盘/相关性/works_gate 负责，不应受线路证据门约束。
    """
    empty_bundle: dict = {
        "coverage": {"coveredEntityCount": 0},
        "routeNodes": [],
        "emotionSignals": {"likes": [], "painPoints": []},
        "storySpine": {},
    }
    for carrier in ("image", "gallery", "Image", "GALLERY"):
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


def test_article_prompt_preserves_whole_base_draft_no_irrelevant_city_trim():
    """根因：多目的地路书底稿被框成单实体 guide 并被指示「删除无关城市段落」，

    agent 为聚焦单一实体而丢弃其它站点章节 → baseDraftFidelity 崩到 18-49% < 55% 全挂。
    1:1 源中心：底稿写到的所有目的地/行程段落都是正文内容，必须整篇保留，实体只是标签不是
    裁剪边界；prompt 只允许删平台/广告/隐私噪声，不得以「与本篇实体无关」为由删其它城市段落。
    """
    from _common.writing_pack import render_prompt_md

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
    # 旧裁剪许可必须消失（这是 fidelity 崩塌根因）。
    assert "无关城市段落" not in prompt, "prompt 仍保留「无关城市段落」裁剪许可，会诱导 agent 丢站点脱稿"
    # 新的整篇保真指令必须在场。
    assert "整篇保留" in prompt, prompt[:400]
    assert ("多目的地" in prompt) or ("全部站点" in prompt), prompt[:400]
    assert "实体只是标签" in prompt, prompt[:400]


def test_article_section_intents_do_not_force_single_entity_focus():
    """章节意图不得把多目的地底稿框成「关于某实体的那篇」诱导裁剪。"""
    from produce.entity_workflow import _entity_section_intents

    intents = _entity_section_intents({"subject": {"type": "地点/景区"}}, "都江堰")
    joined = "\n".join(intents)
    assert "关于 都江堰 的那篇" not in joined, joined
    assert ("全部站点" in joined) or ("多目的地" in joined), joined


if __name__ == "__main__":
    test_route_brief_includes_narrative_contract()
    test_gate_route_evidence_skips_narrative_requirements_for_image_carrier()
    test_gate_route_evidence_still_gates_narrative_carriers()
    test_route_workflow_generates_real_review_green()
    test_route_skip_does_not_prepare_writing_pack()
    test_route_review_blocks_intra_doc_repetition_padding()
    test_article_prompt_preserves_whole_base_draft_no_irrelevant_city_trim()
    test_article_section_intents_do_not_force_single_entity_focus()
    print("route brief and evidence tests passed")
