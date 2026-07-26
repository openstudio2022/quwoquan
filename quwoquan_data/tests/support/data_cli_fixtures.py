"""Shared fixtures for data CLI contract tests."""



from __future__ import annotations

import sys

from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

TESTS_ROOT = DATA_ROOT / "tests"

SCRIPTS_ROOT = DATA_ROOT / "scripts"

for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse

import json

import os

import shutil

import subprocess

import sys

import tempfile

from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="data_cli_"))




for _readonly_dir in ("schema",):
    _src = DATA_ROOT / _readonly_dir
    _dst = _TMP / _readonly_dir
    if _dst.exists():
        continue
    try:
        _dst.symlink_to(_src, target_is_directory=True)
    except OSError:
        shutil.copytree(_src, _dst)

sys.path.insert(0, str(SCRIPTS_ROOT))

from core.command_packet import build_packet, write_packet

from core.article_package import compute_document_sha256, sha256_text

from content.execution.runtime_state import write_execution_runtime_state

from core.io import read_json, read_ndjson, write_json

from core.paths import (  # noqa: E402
    execution_audit_markdown_path,
    execution_audit_summary_path,
    execution_entity_object_dir,
    execution_state_path,
    ensure_execution_command_layout,
    ensure_execution_layout,
    execution_spec_path,
    execution_progress_path,
    execution_baseline_freeze_packet_path,
    execution_catalog,
    execution_explore_packet_path,
    execution_shared_dir,
)

from content.execution.baseline import handle_baseline

from content.source.discovery.handler import handle_explore


from content.source.source_unit import write_source_unit

from content import handler as task_handler_mod

from content.execution import store


CLI = SCRIPTS_ROOT / "cli.py"

def _make_task(
    execution_id: str = "20260722--travel-homepage-contract--test-region-a--pilot-001",
    *,
    with_baseline: bool = True,
) -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="test-region",
        key="test-region-a",
        name="测试实体丙ollection",
        category="景区",
        scope={
            "region": "test-region-a",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "测试实体甲"},
                {"entityType": "地点/景区", "name": "测试实体乙"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {"lanes": ["homepage"]},
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 0,
            },
        },
        created_by="test",
    )
    spec["executionId"] = execution_id
    spec["title"] = "test-entity collection"
    spec["executionPolicy"] = {
        "selectionPolicy": "frozen",
        "targetEntityCount": 2,
        "targetObjectCount": 2,
    }
    store.save_spec(spec)
    store.save_progress(
        store.init_progress(
            execution_id,
            remaining=["地点/景区/测试实体甲", "地点/景区/测试实体乙"],
        )
    )
    if with_baseline:
        _seed_baseline(execution_id)
    else:
        baseline_packet = execution_baseline_freeze_packet_path(execution_id)
        if baseline_packet.exists():
            baseline_packet.unlink()
    return execution_id

def _seed_baseline(execution_id: str) -> None:
    packet = build_packet(
        execution_id=execution_id,
        command="data baseline",
        object_kind="task",
        object_ref=execution_id,
        stage="baseline",
        read_policy=["content.yaml", "progress.json", "catalog.ndjson"],
        stop_if=["executionId mismatch"],
        output_policy=["write task/_shared/baseline_freeze_packet.json"],
        inputs={
            "taskSpecPath": str(execution_spec_path(execution_id)),
            "progressPath": str(execution_progress_path(execution_id)),
            "catalogPath": str(execution_catalog(execution_id)),
        },
        outputs={"packetPath": str(execution_baseline_freeze_packet_path(execution_id))},
        handoff_to="task execute",
        evidence={"required": ["baseline_freeze_packet.json"]},
        summary={"coverageTargetCount": 2, "catalogRowCount": 2},
    )
    write_packet(execution_baseline_freeze_packet_path(execution_id), packet)

def _audit_entity_source_refs(execution_id: str, name: str) -> tuple[str, str]:
    ent = execution_entity_object_dir(execution_id, "地点", "景区", name)
    refs = read_json(ent / "1.download" / "source_refs.json")
    row = (refs.get("sources") or [])[0]
    source_ref = str(row["sourceRef"])
    return source_ref, source_ref.rsplit("/", 1)[0]

def _seed_entity_object_for_audit(execution_id: str, *, name: str) -> None:
    from content.execution.asset_registry import ExecutionAssetRegistry, allocate_post_asset_id
    from content.execution.runtime_state import load_execution_runtime_state

    ent = execution_entity_object_dir(execution_id, "地点", "景区", name)
    manifest = write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md=f"# {name}\n\n概述",
        clean_md=f"# {name}\n\n概述",
        platform="baike",
        source_category="overview_baike",
        url=f"https://example.com/{name}",
        title=f"{name}百科",
        target_ref=f"/entity/地点/景区/{name}",
        execution_id=execution_id,
    )
    source_ref = str(manifest["sourceRef"])
    write_json(
        ent / "_entity.json",
        {
            "label": name,
            "domain": "地点",
            "type": "景区",
            "originTaskId": execution_id,
        },
    )
    runtime_state = load_execution_runtime_state(execution_id)
    assert runtime_state is not None
    global_seq = runtime_state.execution_sequence
    registry = ExecutionAssetRegistry(execution_id=execution_id, execution_sequence=global_seq)
    asset_id = allocate_post_asset_id(
        entity_name=name,
        role="cover",
        ref=f"{name}_主页",
        execution_sequence=global_seq,
        registry=registry,
    )
    (ent / "page.md").write_text(
        f"# {name}\n\n"
        + (name * 460)
        + f"\n\n{{asset://{asset_id}|wrapRight|{name}配图|width=45%}}\n",
        encoding="utf-8",
    )
    (ent / "assets").mkdir(parents=True, exist_ok=True)
    (ent / "assets" / f"{asset_id}.jpg").write_bytes(b"cover")
    write_json(
        ent / "manifest.json",
        {"assets": [{"assetId": asset_id, "fileName": f"{asset_id}.jpg", "caption": f"{name}配图"}]},
    )
    write_json(
        ent / "2.quality" / "quality_analysis.json",
        {
            "entityRef": f"/entity/地点/景区/{name}",
            "baseDraft": {"sourceRef": source_ref},
            "candidateCount": 1,
            "candidates": [{"sourceRef": source_ref, "score": 0.9, "length": 100}],
            "recommendation": "proceed",
            "issues": [],
            "sourcePaths": [source_ref],
        },
    )
    write_json(ent / "3.compose" / "entity_page_input.json", {"payload": {"name": name}})
    (ent / "4.draft").mkdir(parents=True, exist_ok=True)
    (ent / "4.draft" / "page.md").write_text((ent / "page.md").read_text(encoding="utf-8"), encoding="utf-8")
    (ent / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(
        ent / "5.review" / "review.json",
        {
            "decision": "approved",
            "issues": [],
            "fallbackStage": None,
            "checks": {
                "entityPageQuality": {"passed": True, "issues": []},
                "sourceQualification": {"passed": True, "issues": []},
            },
        },
    )
    write_json(
        ent / "5.review" / "provenance.json",
        {
            "schema": "quwoquan_data.provenance",
            "ref": f"/entity/地点/景区/{name}",
            "final": {"generator": "agent", "agentRunId": f"run-{name}", "entityRefs": [f"/entity/地点/景区/{name}"], "articleDigest": None},
            "agentInput": {"writingPack": f"entities/地点/景区/{name}/3.compose/entity_page_input.json"},
            "originalSources": [{"path": source_ref, "url": f"https://example.com/{name}"}],
            "gateResults": {"decision": "approved", "checks": {"entityPageQuality": True, "sourceQualification": True}},
            "citedSourcePaths": [source_ref],
        },
    )
    write_json(
        ent / "5.review" / "finalization_report.json",
        {
            "schema": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
            "draftSha256": compute_document_sha256((ent / "4.draft" / "page.md").read_text(encoding="utf-8")),
            "finalSha256": compute_document_sha256((ent / "page.md").read_text(encoding="utf-8")),
        },
    )

def _seed_verified_post_for_audit(execution_id: str, *, ref: str, title: str, name: str) -> None:
    from content.post.object_index import register_content_object

    register_content_object(execution_id, ref, content_type="article", angle="攻略", title=title)
    from content.post.object_index import content_object_dir
    obj = content_object_dir(execution_id, ref)
    article = (
        f"# {title}\n\n"
        f"第一次去[{name}](/entity/地点/景区/{name})，更适合把行程当成“先看主线工程、再看城内转场、最后处理返程”的顺序题，而不是临场想到哪走到哪。\n\n"
        "## 先定游览顺序\n\n"
        "先去离堆公园一线看鱼嘴、飞沙堰和宝瓶口的关系，再根据体力决定是否补城内步行段，这样路线会更稳，也方便把最重要的视角放在前半天。\n\n"
        "## 交通怎么去\n\n"
        "如果你从成都主城出发，交通上更省心的做法通常是高铁加短驳；自驾也可以，但停车、进出城和景区周边排队都要额外算时间。怎么去并不是小事，它直接决定你上午能不能把核心段走完。\n\n"
        "## 预约与排队怎么取舍\n\n"
        "旺季和节假日一定要先看预约与开放时间，热门时段排队会明显拉长。如果你只想抓住第一次到访的重点，我会建议宁可压缩外围闲逛，也别赶在中午最挤的时候硬冲完整大圈。\n\n"
        "## 什么情况值得调整\n\n"
        "如果你同行里有人更在意拍照，就把河道和城门一线留到光线更稳定的时段；如果更在意工程理解，建议把讲解或导览放在最前面。真正的取舍不是多看一个点，而是避免来回折返，把注意力留给最能解释都江堰价值的那一段。\n\n"
        "## 返程前最后提醒\n\n"
        "返程不要只看景区出口距离，交通切换、停车取车和高铁进站都要留余量。我的建议是把最不确定的一段放在下午后半程之前解决，别赶、别赌临场空窗，这样第一次去都江堰也能把核心体验和返程节奏都兼顾好。\n\n"
        "## 带老人或孩子时怎么改\n\n"
        "如果你是带老人或孩子同行，我会建议把步行最密集的一段缩短，把休息点和补给点放进路线规划里。与其追求一次性走完所有名称最响的点位，不如先保证交通衔接、排队耐受和休整节奏，这样体验反而更完整，也更容易判断哪些段落值得下次再来补足。\n\n"
        "## 为什么这条攻略值得照着执行\n\n"
        "这条写法的重点不是替你做唯一答案，而是帮你先完成第一轮取舍：先后顺序怎么排、交通怎么去、预约与排队要不要避开、返程窗口留多少余量。只要这四件事先想清楚，第一次去都江堰通常就不会因为局部犹豫而把整天节奏拖乱。"
    )
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "article.md").write_text(article, encoding="utf-8")
    (obj / "2.quality").mkdir(parents=True, exist_ok=True)
    (obj / "3.compose").mkdir(parents=True, exist_ok=True)
    (obj / "4.draft").mkdir(parents=True, exist_ok=True)
    (obj / "4.draft" / "draft.article.md").write_text(article, encoding="utf-8")
    (obj / "1.download").mkdir(parents=True, exist_ok=True)
    (obj / "5.review").mkdir(parents=True, exist_ok=True)
    source_ref, source_unit_ref = _audit_entity_source_refs(execution_id, name)
    source_md = f"# {name}\n\n概述"
    article_digest = compute_document_sha256(article)
    write_json(
        obj / "2.quality" / "quality_analysis.json",
        {
            "schema": "quwoquan_data.stage_envelope",
            "executionId": execution_id,
            "executionId": execution_id,
            "step": "quality_analysis",
            "ref": ref,
            "payload": {
                "topicId": ref,
                "qualityScore": 90,
                "recommendation": "proceed",
                "templateId": "travel.route.guide",
                "title": title,
                "sourceUrls": [f"https://example.com/{name}"],
                "sourcePaths": [source_ref],
                "evidenceBundle": {
                    "storySpine": {
                        "mustIncludeFacts": [],
                        "routeEntities": [name],
                    }
                },
            },
        },
    )
    write_json(
        obj / "manifest.json",
        {
            "topicId": ref,
            "contentType": "article",
            "entityRefs": [f"/entity/地点/景区/{name}"],
            "normalizedEntityRefs": [f"entity:景区:{name}"],
            "tagRefs": ["Topic/旅行/景区攻略", "Format/内容角度/攻略"],
            "sourceUrls": [f"https://example.com/{name}"],
            "assets": [],
            "carrier": "article",
            "generator": "agent",
            "generatorModel": "test-agent/audit",
            "citedSourceRefs": [source_ref],
            "reviewDecision": "approved",
            "publishLayout": "article",
            "publishAngle": "攻略",
            "publishTitle": title,
            "publishSeq": 1,
            "createdAt": "2026-06-12T00:00:00Z",
            "updatedAt": "2026-06-12T00:00:00Z",
            "originTaskId": execution_id,
            "sourceBatchId": execution_id,
            "writingIntent": "planning_consultation",
            "baseSourceRef": source_ref,
            "intersectionHints": [
                {
                    "dimension": "content",
                    "source": "entityRef",
                    "tagRefs": [],
                    "actionType": "view_object",
                    "actionTargetId": f"entity:景区:{name}",
                },
                {
                    "dimension": "interest",
                    "source": "tagRef",
                    "tagRefs": ["Topic/旅行/景区攻略"],
                    "actionType": "join",
                    "actionTargetId": "Topic/旅行/景区攻略",
                },
                {
                    "dimension": "location",
                    "source": "geoTagRef",
                    "tagRefs": [],
                    "actionType": "view_object",
                    "actionTargetId": "test-region-b",
                },
            ],
        },
    )
    # 单底稿零参考宪法：source_refs.json 仅保留 baseSourceRef + sources（只留 sha256），
    # 禁止 citedSourceRefs / sourcePaths（第二来源/全量索引）与内联 sourceMarkdown 原文镜像。
    write_json(
        obj / "1.download" / "source_refs.json",
        {
            "schema": "quwoquan_data.source_refs",
            "baseSourceRef": source_ref,
            "sources": [
                {
                    "sourceRef": source_ref,
                    "sourceUnitRef": source_unit_ref,
                    "sourceMarkdownSha256": sha256_text(source_md),
                }
            ],
        },
    )
    write_json(
        obj / "5.review" / "review.json",
        {
            "topicId": ref,
            "decision": "approved",
            "issues": [],
            "humanReviewRequired": False,
            "generator": "agent",
            "checks": {
                "generatorProvenance": {"passed": True},
                "factTraceability": {"passed": True},
                "baseDraftFidelity": {"passed": True},
                "writingIntentConsistency": {"passed": True},
            },
        },
    )
    write_json(
        obj / "5.review" / "review_gate.json",
        {
            "schema": "quwoquan_data.stage_envelope",
            "payload": {
                "passed": True,
                "issues": [],
                "status": "green",
            },
        },
    )
    write_json(
        obj / "5.review" / "review_ledger.json",
        {
            "schema": "quwoquan_data.review_ledger",
            "executionId": execution_id,
            "executionId": execution_id,
            "ref": ref,
            "policy": {
                "autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True, "autoDiscardScoreAtMost": 1},
                "reprocess": {"maxAttempts": 3},
            },
            "article": {
                "kind": "article",
                "target": ref,
                "agentJudgment": "credible",
                "agentScore": 4,
                "humanJudgment": "unjudged",
                "humanScore": None,
                "humanOverride": None,
                "reprocessCount": 0,
                "reasons": [],
                "notes": "",
            },
            "images": [],
            "facts": [],
        },
    )
    write_json(
        obj / "5.review" / "review_entities.json",
        {
            "schema": "quwoquan_data.review_entities",
            "ref": ref,
            "entities": [
                {
                    "name": name,
                    "domain": "地点",
                    "type": "景区",
                    "ref": f"/entity/地点/景区/{name}",
                    "hasHomepage": True,
                    "generated": False,
                    "evidenceRef": "overview_baike",
                }
            ],
        },
    )
    write_json(
        obj / "5.review" / "provenance.json",
        {
            "schema": "quwoquan_data.provenance",
            "ref": ref,
            "final": {
                "publishTitle": title,
                "publishSeq": 1,
                "generator": "agent",
                "model": "test-agent/audit",
                "agentRunId": f"run-{ref}",
                "agentId": "agent-audit",
                "sessionTrace": "audit-session",
                "styleFamily": "route-guide",
                "openingStrategy": "scene_immersion",
                "articleDigest": article_digest,
                "entityRefs": [f"/entity/地点/景区/{name}"],
            },
            "agentInput": {
                "writingPack": "3.compose/writing_pack.json",
                "prompt": "4.draft/prompt.md",
                "title": title,
                "styleFamily": "route-guide",
                "promptSha256": "sha256:a",
                "writingPackSha256": "sha256:b",
                "sourceBundleSha256": "sha256:c",
                "draftSha256": "sha256:d",
            },
            "originalSources": [{"path": source_ref, "url": f"https://example.com/{name}"}],
            "gateResults": {"decision": "approved", "checks": {"generatorProvenance": True, "factTraceability": True}},
            "citedSourcePaths": [source_ref],
        },
    )
    write_json(
        obj / "5.review" / "finalization_report.json",
        {
            "schema": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/draft.article.md",
            "finalArticleRef": "article.md",
            "draftSha256": article_digest,
            "finalSha256": article_digest,
            "composeSnapshotMatchesDraft": True,
            "bodyChanged": False,
            "frontmatterOnlyChange": False,
        },
    )



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
