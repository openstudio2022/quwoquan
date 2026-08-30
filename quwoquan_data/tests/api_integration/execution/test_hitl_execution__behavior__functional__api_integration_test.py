"""HITL 主线契约：manifest 最小化 + 账本 sidecar + 实体候选治理。

可直接运行：python3 quwoquan_data/tests/api_integration/execution/test_hitl_execution__behavior__functional__api_integration_test.py
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
_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="hitl_execution_rt_"))

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core.paths as _paths_mod
from content.execution.planning.brief import resolve_compose_brief
from content.execution.runtime_state import write_execution_runtime_state
from content.post.article.draft_io import write_agent_draft
from content.post.article.evidence_bundle import public_byline_label
from content.post.article.route_analysis import analyze_route_ref
from content.post.article.route_compose import build_route_writing_pack
from content.post.article.route_review import review_route_draft
from content.post.materialize_apply import materialize_posts
from content.review.ledger import load_ledger
from content.source.source_unit import (
    resolve_entity_object_dir,
    write_source_unit,
)
from content.templates.registry import TemplateRegistry
from content.templates.router import RouteRequest
from core.control_types import ReviewItemKind
from core.entity_object import find_entity_object_dir
from core.evidence_contract import (
    post_manifest_contract_issues,
    quality_payload_contract_issues,
)
from core.io import read_json, write_json
from core.paths import (
    ensure_execution_command_layout,
    ensure_execution_layout,
    execution_inputs_dir,
)
from governance.coverage.entity_extract import _governance_root
from governance.creators.candidates.store import CandidateRepository
from support.article_source_registry_fixture import (
    ARTICLE_SOURCE_UNIT_IDENTITY,
    article_source_registry_binding,
)
from support.execution_manifest_fixture import build_execution_fixture
from support.helpers.agent_draft_kit import route_article

TASK = "20260711--travel-article-hitl-execution--test-region-b--pilot-001"
REF = "川西大环线慢游_跟团_夏"
# Article fixtures bind one work to one base source unit. Additional named
# places discovered by the draft continue through the governed entity sidecar.
ENTITIES = ["九寨沟"]
MINED = "洛绒牛场"
TAG_LABEL = "晨雾"
TAG_DIMENSION = "摄影"
_CONTROLLER_RESULT: Path | None = None


def _retarget_runtime() -> None:
    os.environ["QWQ_OUTPUT_ROOT"] = str(_RUNTIME_ROOT)
    _paths_mod.RUNTIME_ROOT = _RUNTIME_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _RUNTIME_ROOT / "tasks"

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


def _run_controller() -> Path:
    global _CONTROLLER_RESULT
    _retarget_runtime()
    if _CONTROLLER_RESULT is not None:
        return _CONTROLLER_RESULT
    build_execution_fixture(TASK)
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "source")
    ensure_execution_command_layout(TASK, "post")
    write_execution_runtime_state(TASK, command="execution")
    registry = TemplateRegistry.load()
    brief = resolve_compose_brief(
        registry,
        RouteRequest(
            vertical="travel",
            subject_kind="entity",
            subject_type="地点/景区",
            intent="体验",
            audience="groupTourTraveler",
            region="高原",
            season="夏",
        ),
        title="九寨沟清晨慢游体验（夏季）",
        entity_refs=[f"地点/景区/{n}" for n in ENTITIES],
    )
    image_root = Path(tempfile.mkdtemp(prefix="hitl_execution_sources_"))
    base_source_ref = ""
    for idx, entity in enumerate(ENTITIES):
        obj = resolve_entity_object_dir(TASK, entity, etype_hint="景区")
        image_paths: list[Path] = []
        for k in range(2):
            image_path = image_root / f"{entity}_{k}.jpg"
            _clean_image(image_path, seed=idx * 7 + k + 1)
            image_paths.append(image_path)
        source_manifest = write_source_unit(
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
            platform="去哪儿",
            publish_media_mode="illustrated",
            source_role="base",
            research_lane="article",
            url=f"https://example.com/{entity}",
            title="sample",
            target_ref=f"/entity/地点/景区/{entity}",
            relevance=f"{entity} 线路证据",
            **ARTICLE_SOURCE_UNIT_IDENTITY,
            source=article_source_registry_binding(
                platform="去哪儿",
                url=f"https://example.com/{entity}",
            ),
            images=[{"sourcePath": str(path), "caption": f"{entity} 图{k}", "relevance": f"{entity} 图{k}"} for k, path in enumerate(image_paths)],
        )
        if idx == 0:
            base_source_ref = str(source_manifest.get("sourceRef") or "")

    assert base_source_ref.endswith("/source.md")
    brief["baseSourceRef"] = base_source_ref
    brief["sourceUseMode"] = "factual_reference_only"
    brief["publishMediaMode"] = "illustrated"
    write_json(execution_inputs_dir(TASK, "post", "compose") / f"{REF}.json", brief)

    quality = analyze_route_ref(TASK, REF, brief)
    assert quality_payload_contract_issues(quality) == []
    pack = build_route_writing_pack(TASK, REF, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    article = route_article(brief["titleHint"], byline, ENTITIES, pack.get("mustIncludeFacts") or [])
    article += (
        "\n\n如果把清晨留给湖水和雪山，行程就要从票务与观光车时间倒推。"
        "进门后先确认当天的换乘节奏，不把每一站都塞满，遇到排队也能保留停留空间。\n"
        "\n午后天气变化快，返程缓冲比多赶一个点更重要。"
        "连续坐车时要观察体力和高原反应，出现不适就缩短停留；"
        "雨势增大时优先回到明确的接驳节点，不临时增加陌生支线。\n"
    )
    article += f"\n\n返程前经过{MINED}，这里作为沿途自然景观只做短暂停留。\n"
    article += f"\n清晨适合拍{TAG_LABEL}，光线柔和层次分明。\n"
    write_agent_draft(
        TASK,
        REF,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        extracted_entities=[{"name": MINED, "type": "自然景观", "evidenceRef": "curated_story"}],
        extracted_tags=[{"label": TAG_LABEL, "dimensionId": TAG_DIMENSION}],
        agent_run_id="run-hitl",
        agent_id="agent-hitl",
    )
    review = review_route_draft(TASK, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    posts = materialize_posts(TASK, "article")
    assert posts, "materialize produced no posts"
    _CONTROLLER_RESULT = posts[0]
    return _CONTROLLER_RESULT


def test_manifest_is_minimal_and_trace_offloaded():
    post_dir = _run_controller()
    manifest = read_json(post_dir / "manifest.json")
    assert post_manifest_contract_issues(manifest) == []
    assert manifest["createdAt"]
    assert manifest["updatedAt"]
    assert "publishedAt" not in manifest
    for dropped in ("sourceQuality", "relatedSearchPlan", "evidenceBundle", "sourcePaths"):
        assert dropped not in manifest, f"manifest 不应再含中间态 {dropped}"
    assert "articleMarkdownDigest" not in manifest
    assert manifest["topicId"] == REF
    assert manifest["generator"] == "agent"
    provenance = read_json(post_dir / "5.review" / "provenance.json")
    assert provenance["agentInput"]["writingPack"].endswith("3.compose/writing_pack.json")
    assert provenance["originalSources"]


def test_ledger_written_and_copied():
    post_dir = _run_controller()
    ledger = load_ledger(TASK, REF)
    assert ledger is not None, "review 必须落账本"
    assert ledger.article is not None
    assert ledger.images, "应有逐图 agent 判定项"
    # 账本落内容对象 5.review（与成品同处对象根，promote 发布门据此过滤）
    copied = read_json(post_dir / "5.review" / "review_ledger.json")
    assert copied["ref"] == REF
    assert any(i["kind"] == ReviewItemKind.IMAGE.value for i in copied["images"])


def test_mined_entity_enters_review_without_placeholder_homepage():
    post_dir = _run_controller()
    sidecar = read_json(post_dir / "5.review" / "review_entities.json")
    names = {e["name"]: e for e in sidecar["entities"]}
    assert MINED in names, "应挖掘出专有实体"
    ent = names[MINED]
    assert ent["hasHomepage"] is False
    assert ent["generated"] is False
    assert ent["governanceStatus"] == "pending_review"
    assert ent["candidateId"]
    mentions = [
        row for row in sidecar["semanticMentions"]
        if row["targetRef"] == ent["ref"]
    ]
    assert mentions and mentions[0]["status"] == "pending_review"
    assert mentions[0]["mentionId"] in ent["mentionIds"]

    candidate = CandidateRepository(_governance_root()).get(ent["candidateId"])
    assert candidate is not None
    assert candidate["status"] == "pending_review"
    assert candidate["mentionIds"] == ent["mentionIds"]

    # 未经人审不得在 execution 实体对象根生成占位主页。
    obj = find_entity_object_dir(TASK, ent["domain"], ent["type"], MINED)
    assert obj is None or not (obj / "page.md").is_file()


def test_manifest_backfills_entity_and_tag_semantic_mentions_from_sidecar():
    """端到端：sidecar 的实体/标签 semanticMentions 全链路回填 manifest（生产侧 draft → review sidecar → materialize）。"""
    post_dir = _run_controller()
    manifest = read_json(post_dir / "manifest.json")
    sidecar = read_json(post_dir / "5.review" / "review_entities.json")

    manifest_mentions = manifest.get("semanticMentions") or []
    assert manifest_mentions, "manifest 必须回填 semanticMentions（实体/标签 grounding 源头）"

    # sidecar 是治理真相源；manifest 必须包含 sidecar 的全部 mentionId（不丢失）。
    sidecar_ids = {row["mentionId"] for row in (sidecar.get("semanticMentions") or [])}
    manifest_ids = {row["mentionId"] for row in manifest_mentions}
    assert sidecar_ids, "sidecar 应产出 semanticMentions"
    assert sidecar_ids <= manifest_ids, "sidecar mention 必须全部进入 manifest"

    # 实体 mention（挖掘出的专有实体，pending_review）。
    entity_mentions = [m for m in manifest_mentions if m.get("kind") == "entity"]
    assert any(m.get("surface") == MINED for m in entity_mentions), "应回填实体 mention"

    # 标签 mention（生产侧 extractedTags → review sidecar → manifest，端到端打通）。
    tag_mentions = [m for m in manifest_mentions if m.get("kind") == "tag"]
    assert tag_mentions, "extractedTags 必须端到端产出 tag semantic mention"
    tag = next(m for m in tag_mentions if m.get("surface") == TAG_LABEL)
    assert tag["targetRef"].endswith(TAG_LABEL)
    assert tag["status"] in {"published", "pending_review"}
    assert tag["startUtf16"] >= 0 and tag["endUtf16"] > tag["startUtf16"]

    # sidecar.tags 结构体同源记录该标签及其 mentionIds。
    sidecar_tags = {t["label"]: t for t in (sidecar.get("tags") or [])}
    assert TAG_LABEL in sidecar_tags, "sidecar 应记录结构化 tag 条目"
    assert tag["mentionId"] in sidecar_tags[TAG_LABEL]["mentionIds"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"hitl execution tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
