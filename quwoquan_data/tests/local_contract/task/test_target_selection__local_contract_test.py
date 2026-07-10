"""Target selection and managed batch audit contract tests."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_target_selection_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

from _common.io import read_ndjson, write_json  # noqa: E402
from _common.entity_artifacts import prune_inactive_entity_artifacts  # noqa: E402
from _common.execution_branch import DEFAULT_HOMEPAGE_ONLY_EXECUTION_BRANCH  # noqa: E402
from _common.paths import batch_root, task_catalog  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from task.target_selection import (  # noqa: E402
    DEFAULT_MANDATORY,
    _workflow_failure_items,
    audit_managed_batch,
    build_multimodal_spec,
    handle_audit_batch,
    ineligible_targets_from_batch,
    select_targets,
    write_selected_task,
)
from task import store  # noqa: E402


def _discovery(path: Path) -> None:
    partitions = []
    for region in ("川西", "川北", "川南"):
        leaves = [
            {"name": f"{region}候选{index}", "entityType": "地点/景区"}
            for index in range(1, 30)
        ]
        partitions.append({"key": region, "leaves": leaves})
    partitions[0]["leaves"][:5] = [
        {"name": name, "entityType": "地点/景区"} for name in DEFAULT_MANDATORY
    ]
    write_json(path, {"partitions": partitions})


def test_ineligible_targets_from_managed_state():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b1"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "failedObjects": [
                "巴山大峡谷: image research needs enough rights-cleared collection assets",
                "大千园：image research needs enough rights-cleared collection assets",
                "agent status=error",
            ]
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"巴山大峡谷", "大千园"}


def test_ineligible_targets_do_not_treat_checkpoint_as_entity():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_checkpoint_failure"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "failedObjects": [
                "build_prepare: interrupted; workflow stopped before checkpoint completion",
                "download_plan: repair loop needs more source-ready candidates",
                "阆中古城: homepage baseDraft.text 缺失",
            ]
        },
    )

    assert ineligible_targets_from_batch(task, batch) == {"阆中古城"}


def test_ineligible_targets_keep_content_shortfalls_as_content_level_input():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_abandoned_source"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "abandonedObjects": [
                {"entityId": "光雾山", "stage": "download_fetch", "reason": "source_unavailable"},
            ],
            "abandonedContentObjects": [
                {"ref": "毕棚沟_image", "stage": "content_plan", "reason": "source_unavailable"},
                {"ref": "青城山_seasonal_timing", "stage": "content_plan", "reason": "source_unavailable"},
                {
                    "ref": "都江堰__article_qunar_base_1",
                    "stage": "produce_review",
                    "reason": "produce_review_persistent_failure_after_bounded_retries",
                },
            ],
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"光雾山"}


def test_ineligible_targets_ignore_retrying_content_rows():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_retrying_content"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "abandonedContentObjects": [
                {
                    "ref": "乐山大佛__article_qunar_base_1",
                    "stage": "produce_author",
                    "reason": "agent_infrastructure_unavailable_after_3_managed_retries",
                    "status": "retrying",
                },
                {
                    "ref": "黄龙__article_qunar_base_1",
                    "stage": "publish",
                    "reason": (
                        "publish_content_anchor_unavailable_after_homepage_filter; "
                        "workflowPolicy.best_effort_with_reasoned_rejects"
                    ),
                    "status": "abandoned",
                },
            ],
        },
    )

    assert ineligible_targets_from_batch(task, batch) == {"黄龙"}


def test_ineligible_targets_include_homepage_anchor_failures():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_homepage_anchor_failed"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "abandonedObjects": [
                {
                    "entityId": "阆中古城",
                    "stage": "download_fetch",
                    "abandonScope": "homepage",
                    "reason": "homepage lane sourceScreen retained no primary authority encyclopedia source",
                }
            ],
            "abandonedContentObjects": [
                {
                    "ref": "黄龙__article_qunar_base_1",
                    "stage": "publish",
                    "reason": (
                        "publish_content_anchor_unavailable_after_homepage_filter; "
                        "workflowPolicy.best_effort_with_reasoned_rejects"
                    ),
                },
                {
                    "ref": "剑门关_image",
                    "stage": "publish",
                    "reason": "publish_image_quality_or_known_reject_term",
                },
            ],
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"阆中古城", "黄龙"}


def test_ineligible_targets_merge_audit_failed_lanes():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_audit"
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "managed_batch_audit.json",
        {
            "failedLanes": [
                {"entity": "真佛山", "lane": "image", "issues": ["image supply"]},
                {"entity": "宝箴塞", "lane": "image", "issues": ["image supply"]},
            ]
        },
    )
    write_json(
        shared / "task_workflow_state.json",
        {"failedObjects": ["黄荆老林: image research needs enough rights-cleared collection assets"]},
    )
    assert ineligible_targets_from_batch(task, batch) == {"真佛山", "宝箴塞", "黄荆老林"}


def test_ineligible_targets_read_source_unavailable_report():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_source_unavailable"
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "source_unavailable_targets.json",
        {
            "ineligibleTargets": [
                {
                    "entityId": "墨石公园",
                    "lanes": ["homepage", "article", "image"],
                    "issues": ["no rights-compatible image"],
                }
            ]
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"墨石公园"}


def test_workflow_failure_items_turn_manual_required_into_audit_failure():
    state = {
        "status": "manual_required",
        "failedObjects": [
            "九寨沟: download_repair required: article research needs >= 4 text-qualified base sources",
        ],
    }
    items = _workflow_failure_items(state)
    assert items == [
        {
            "entity": "九寨沟",
            "lane": "article",
            "issues": ["九寨沟: download_repair required: article research needs >= 4 text-qualified base sources"],
        }
    ]


def test_workflow_failure_items_allow_until_stop_state():
    assert _workflow_failure_items({"status": "stopped_at_until", "failedObjects": []}) == []


def test_audit_batch_skips_abandoned_targets():
    spec = build_multimodal_spec(
        name="abandoned审计",
        title="abandoned审计",
        region="测试省",
        category="景区",
        targets=[
            {"name": "可继续景区", "entityType": "地点/景区"},
            {"name": "快速失败景区", "entityType": "地点/景区"},
        ],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_abandoned"
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "task_workflow_state.json",
        {
            "status": "running",
            "abandonedObjects": [
                {
                    "entityId": "快速失败景区",
                    "stage": "download_plan",
                    "reason": "no authorized source after screening",
                    "status": "abandoned",
                }
            ],
        },
    )

    report = audit_managed_batch(task, batch)
    assert report["targetCount"] == 1
    assert report["abandonedCount"] == 1
    assert report["abandonedObjects"][0]["entityId"] == "快速失败景区"
    entity_failures = {
        item["entity"] for item in report["failedLanes"]
        if item.get("entity") != "__batch__"
    }
    assert entity_failures == {"可继续景区"}


def test_audit_batch_counts_only_active_abandoned_content_rows():
    spec = build_multimodal_spec(
        name="retrying内容不算弃稿",
        title="retrying内容不算弃稿",
        region="测试省",
        category="景区",
        targets=[{"name": "乐山大佛", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_retrying_content_audit"
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "task_workflow_state.json",
        {
            "status": "manual_required",
            "waitingCheckpoint": "produce_author",
            "abandonedContentObjects": [
                {
                    "ref": "乐山大佛__article_qunar_base_1",
                    "stage": "produce_author",
                    "reason": "agent_infrastructure_unavailable_after_3_managed_retries",
                    "status": "retrying",
                },
                {
                    "ref": "乐山大佛_article_shortfall_1",
                    "stage": "content_plan",
                    "reason": "article quota shortfall",
                    "status": "abandoned",
                },
            ],
        },
    )

    report = audit_managed_batch(task, batch)
    assert report["abandonedContentCount"] == 1
    assert [row["ref"] for row in report["abandonedContentObjects"]] == [
        "乐山大佛_article_shortfall_1"
    ]


def test_audit_batch_ignores_partial_auto_research_scope():
    spec = build_multimodal_spec(
        name="partial自动检索审计",
        title="partial自动检索审计",
        region="测试省",
        category="景区",
        targets=[
            {"name": "景区甲", "entityType": "地点/景区"},
            {"name": "景区乙", "entityType": "地点/景区"},
            {"name": "景区丙", "entityType": "地点/景区"},
        ],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_partial_auto_report"
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "auto_research_plan.json",
        {
            "sourceAvailability": {
                "readyTargets": ["景区乙"],
                "ineligibleTargets": [],
            }
        },
    )

    report = audit_managed_batch(task, batch)

    assert report["targetCount"] == 3
    assert report["targetScope"] == "task_coverage"


def test_audit_batch_json_strict_exits_nonzero_when_failed():
    spec = build_multimodal_spec(
        name="json严格审计",
        title="json严格审计",
        region="测试省",
        category="景区",
        targets=[{"name": "缺源景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_json_strict_failed"
    store.save_spec(spec)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            handle_audit_batch(
                SimpleNamespace(
                    task=task,
                    batch=batch,
                    write=False,
                    json=True,
                    strict=True,
                )
            )
            assert False, "strict JSON audit should exit non-zero when failed lanes exist"
        except SystemExit as exc:
            assert exc.code == 1
    assert '"failedLaneCount"' in out.getvalue()


def test_audit_batch_reports_homepage_input_issue_after_build_prepare():
    spec = build_multimodal_spec(
        name="主页输入审计",
        title="主页输入审计",
        region="测试省",
        category="景区",
        targets=[{"name": "空底稿景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_homepage_input_issue"
    store.save_spec(spec)
    entity = batch_root(task, batch) / "entities" / "地点" / "景区" / "空底稿景区"
    write_json(
        entity / "1.download" / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_wikipedia",
                        "platform": "维基百科",
                        "category": "encyclopedia",
                        "url": "https://zh.wikipedia.org/wiki/test",
                        "sourceUseMode": "factual_reference_only",
                    },
                    {
                        "source_id": "home_baidu",
                        "platform": "百度百科",
                        "category": "encyclopedia",
                        "url": "https://baike.baidu.com/item/test",
                        "sourceUseMode": "factual_reference_only",
                    },
                ]
            }
        },
    )
    write_json(
        entity / "3.compose" / "entity_page_input.json",
        {"payload": {"name": "空底稿景区", "domain": "地点", "etype": "景区", "baseDraft": {}}},
    )

    report = audit_managed_batch(task, batch)

    homepage_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "空底稿景区" and item.get("lane") == "homepage"
    ]
    assert homepage_failures
    assert any(
        "baseDraft.sourceRef is empty" in issue
        for issue in homepage_failures[0]["issues"]
    ), homepage_failures


def test_audit_batch_blocks_inactive_entity_homepage_artifacts():
    spec = build_multimodal_spec(
        name="失活主页产物审计",
        title="失活主页产物审计",
        region="测试省",
        category="景区",
        targets=[{"name": "有效景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_inactive_homepage_artifacts"
    store.save_spec(spec)
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "auto_research_plan.json",
        {"sourceAvailability": {"readyTargets": ["有效景区"], "ineligibleTargets": []}},
    )
    inactive = resolve_entity_object_dir(task, batch, "失活景区", etype_hint="地点/景区")
    write_json(inactive / "manifest.json", {"entityRef": "/entity/地点/景区/失活景区"})
    (inactive / "page.md").parent.mkdir(parents=True, exist_ok=True)
    (inactive / "page.md").write_text("失活主页", encoding="utf-8")
    (inactive / "assets").mkdir(parents=True, exist_ok=True)

    report = audit_managed_batch(task, batch)

    assert report["inactiveEntityArtifactCount"] == 1
    inactive_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "失活景区" and item.get("lane") == "homepage"
    ]
    assert inactive_failures
    assert "outside active target set" in inactive_failures[0]["issues"][0]


def test_prune_inactive_entity_artifacts_keeps_download_evidence():
    task = "旅行/地域/测试省/景区/失活产物清理"
    batch = "b_prune_inactive"
    inactive = resolve_entity_object_dir(task, batch, "失活景区", etype_hint="地点/景区")
    write_json(inactive / "manifest.json", {"entityRef": "/entity/地点/景区/失活景区"})
    write_json(inactive / "_entity.json", {"name": "失活景区"})
    write_json(inactive / "1.download" / "source.md", {"source": "kept"})
    (inactive / "assets").mkdir(parents=True, exist_ok=True)

    rows = prune_inactive_entity_artifacts(
        task,
        batch,
        active_entity_names=["有效景区"],
    )

    assert [row["entity"] for row in rows] == ["失活景区"]
    assert not (inactive / "manifest.json").exists()
    assert not (inactive / "_entity.json").exists()
    assert not (inactive / "assets").exists()
    assert (inactive / "1.download" / "source.md").exists()


def test_audit_batch_dedupes_workflow_failure_for_same_entity_lane():
    spec = build_multimodal_spec(
        name="重复失败审计",
        title="重复失败审计",
        region="测试省",
        category="景区",
        targets=[{"name": "缺源景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_duplicate_workflow_failure"
    store.save_spec(spec)

    report = audit_managed_batch(
        task,
        batch,
        workflow_state_override={
            "status": "waiting_agent",
            "failedObjects": ["缺源景区: article sources=0 need>=4"],
        },
    )

    # image 为加分项（scoredAngles），图片不足不阻断合格实体、不计入 required failed lane；
    # 缺源实体仅 homepage + article 两条 required lane 失败。article 的 download 缺口与
    # workflow failedObjects 去重合并为同一条，不重复计数。
    assert report["failedLaneCount"] == 2
    article_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "缺源景区" and item.get("lane") == "article"
    ]
    assert len(article_failures) == 1
    assert "缺源景区: article sources=0 need>=4" in article_failures[0]["issues"]


def test_audit_batch_ignores_stale_workflow_failure_when_current_lane_passes():
    spec = build_multimodal_spec(
        name="旧失败容错审计",
        title="旧失败容错审计",
        region="测试省",
        category="景区",
        targets=[{"name": "已修好景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_stale_workflow_failure"
    store.save_spec(spec)
    dl = resolve_entity_object_dir(task, batch, "已修好景区", etype_hint="地点/景区") / "1.download"
    sources = [
        {
            "source_id": f"article_base_{idx}",
            "platform": "去哪儿攻略",
            "url": f"https://example.invalid/youji/{idx}",
            "category": "travelogue",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "entityMatch": "strong",
            "candidateGate": {"passed": True, "issues": []},
        }
        for idx in range(1, 5)
    ]
    write_json(
        dl / "article_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "已修好景区",
                "researchLane": "article",
                "sources": sources,
            },
        },
    )

    report = audit_managed_batch(
        task,
        batch,
        workflow_state_override={
            "status": "waiting_agent",
            "waitingCheckpoint": "download_plan",
            "failedObjects": ["已修好景区: article sources=2 need>=4"],
        },
    )

    assert not any(
        item.get("entity") == "已修好景区" and item.get("lane") == "article"
        for item in report["failedLanes"]
    )


def test_audit_batch_source_precheck_flags_scaled_shortfalls_despite_quota_shortfall():
    spec = build_multimodal_spec(
        name="放量预检查审计",
        title="放量预检查审计",
        region="四川省",
        category="景区",
        targets=[{"name": "预检查景区", "entityType": "地点/景区"}],
        created_by="test",
        image_works_per_target=2,
        target_entity_count=1,
        elastic_overfetch=True,
        allow_quota_shortfall=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )
    task = spec["taskId"]
    batch = "b_source_precheck_scaled_shortfall"
    store.save_spec(spec)
    dl = resolve_entity_object_dir(task, batch, "预检查景区", etype_hint="地点/景区") / "1.download"
    write_json(
        dl / "article_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "预检查景区",
                "researchLane": "article",
                "sources": [
                    {
                        "source_id": f"article_base_{idx}",
                        "platform": platform,
                        "url": f"https://example.invalid/precheck/{idx}",
                        "category": category,
                        "sourceRole": "base",
                        "sourceUseMode": "factual_reference_only",
                        "entityMatch": "strong",
                        "candidateGate": {"passed": True, "issues": []},
                    }
                    for idx, (platform, category) in enumerate(
                        (
                            ("去哪儿攻略", "travelogue"),
                            ("今日头条", "platform_article"),
                            ("微博", "community_post"),
                        ),
                        start=1,
                    )
                ],
            },
        },
    )
    write_json(
        dl / "image_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "预检查景区",
                "researchLane": "image",
                "collections": [
                    {
                        "sourceCollectionId": "tuchong_stock:precheck:one",
                        "creator": "授权摄影师",
                        "credit": "授权摄影师",
                        "collectionPageUrl": "https://stock.tuchong.com/image/one",
                        "license": "photographer_authorized",
                        "termsUrl": "https://stock.tuchong.com/",
                        "authorizationProof": "order:tuchong:one",
                        "usageScope": "app_publish",
                        "platform": "图虫创意",
                        "images": [
                            {
                                "url": "https://stock.tuchong.com/image/one.jpg",
                                "sourceUrl": "https://stock.tuchong.com/image/one",
                                "caption": "预检查景区 山水风光",
                                "width": 1200,
                                "height": 800,
                                "modelReleaseStatus": "not_required",
                            }
                        ],
                    }
                ],
            },
        },
    )

    report = audit_managed_batch(task, batch)

    precheck = report["sourcePrecheck"]
    assert precheck["enabled"] is True
    assert precheck["thresholds"]["minArticleBaseSources"] == 4
    assert precheck["thresholds"]["minImageSourceCollections"] == 2
    assert precheck["failedEntities"] == ["预检查景区"]
    issue_text = "\n".join(
        issue
        for item in report["failedLanes"]
        for issue in (item.get("issues") or [])
        if item.get("entity") == "预检查景区"
    )
    assert "source precheck article base sources=3 need>=4" in issue_text
    assert "source precheck publishable image source collections=1 need>=2" in issue_text
    assert "source precheck homepage baseDraft" in issue_text


def test_source_precheck_image_only_task_does_not_raise_article_gate():
    spec = build_multimodal_spec(
        name="source precheck image only",
        title="source precheck image only",
        region="测试省",
        category="景区",
        targets=[{"entityType": "地点/景区", "name": "图片预检查景区"}],
        created_by="test",
        entity_articles_per_target=0,
        image_works_per_target=1,
        target_entity_count=100,
        allow_quota_shortfall=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )
    task = spec["taskId"]
    batch = "b_source_precheck_image_only"
    store.save_spec(spec)
    dl = resolve_entity_object_dir(task, batch, "图片预检查景区", etype_hint="地点/景区") / "1.download"
    write_json(
        dl / "article_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "图片预检查景区",
                "researchLane": "article",
                "sources": [
                    {
                        "source_id": "weak_article",
                        "platform": "微博",
                        "url": "https://example.invalid/off-topic",
                        "category": "community_post",
                        "sourceRole": "base",
                        "candidateGate": {"passed": False, "issues": ["off_entity_no_anchor"]},
                    }
                ],
            },
        },
    )
    write_json(
        dl / "image_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "图片预检查景区",
                "researchLane": "image",
                "collections": [
                    {
                        "sourceCollectionId": "wikimedia:image:one",
                        "creator": "Commons photographer",
                        "credit": "Commons photographer",
                        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:one.jpg",
                        "license": "CC-BY-SA 4.0",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "authorizationProof": "https://commons.wikimedia.org/wiki/File:one.jpg",
                        "usageScope": "app_publish",
                        "platform": "Wikimedia Commons",
                        "images": [
                            {
                                "url": "https://upload.wikimedia.org/one.jpg",
                                "sourceUrl": "https://commons.wikimedia.org/wiki/File:one.jpg",
                                "caption": "图片预检查景区 山水风光",
                                "width": 1200,
                                "height": 800,
                                "modelReleaseStatus": "not_required",
                            }
                        ],
                    }
                ],
            },
        },
    )

    report = audit_managed_batch(task, batch)

    precheck = report["sourcePrecheck"]
    assert precheck["enabled"] is True
    assert precheck["thresholds"]["minArticleBaseSources"] == 0
    assert precheck["thresholds"]["minSourceCategories"] == 0
    issue_text = "\n".join(
        issue
        for item in report["failedLanes"]
        for issue in (item.get("issues") or [])
        if item.get("entity") == "图片预检查景区"
    )
    assert "source precheck article base sources" not in issue_text
    assert "source precheck major off_entity_no_anchor" not in issue_text
    assert "source precheck source categories" not in issue_text
    assert "source precheck publishable image source collections=1 need>=2" in issue_text


def test_source_precheck_site_supply_dynamic_image_batch_uses_selected_sources():
    spec = build_multimodal_spec(
        name="site supply image precheck",
        title="site supply image precheck",
        region="测试省",
        category="主题",
        targets=[{"entityType": "主题/风光", "name": "风光摄影"}],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=0,
        image_works_per_target=100,
        target_entity_count=100,
        allow_quota_shortfall=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )
    task = spec["taskId"]
    batch = "b_site_supply_dynamic_image_precheck"
    spec.setdefault("content", {}).setdefault("research", {})["lanes"] = ["image"]
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "site_supply_content_plan_report.json",
        {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": "photography",
            "siteId": "pinterest",
            "batchId": "h100_real_pin_4",
            "selectedCount": 100,
            "requestedCount": 100,
            "itemCount": 100,
            "eligibleAvailableCount": 116,
        },
    )

    report = audit_managed_batch(task, batch)

    assert report["failedLaneCount"] == 0
    assert report["lanePassed"]["image"] == 1
    precheck = report["sourcePrecheck"]
    assert precheck["failedEntityCount"] == 0
    assert precheck["entities"][0]["entity"] == "风光摄影"
    assert precheck["entities"][0]["imageSourceCollectionCount"] == 100
    assert precheck["entities"][0]["publishableImageCount"] == 100


def test_source_precheck_ignores_rejected_off_entity_overfetch_noise():
    spec = build_multimodal_spec(
        name="source precheck rejected off entity",
        title="source precheck rejected off entity",
        region="四川省",
        category="景区",
        targets=[{"entityType": "地点/景区", "name": "合格景区"}],
        created_by="test",
        entity_articles_per_target=4,
        image_works_per_target=0,
        target_entity_count=15,
        allow_quota_shortfall=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )
    task = spec["taskId"]
    batch = "b_source_precheck_rejected_off_entity"
    store.save_spec(spec)
    dl = resolve_entity_object_dir(task, batch, "合格景区", etype_hint="地点/景区") / "1.download"
    sources = [
        {
            "source_id": f"article_base_{idx}",
            "platform": platform,
            "url": f"https://example.invalid/qualified/{idx}",
            "category": category,
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "entityMatch": "strong",
            "candidateGate": {"passed": True, "issues": []},
        }
        for idx, (platform, category) in enumerate(
            (
                ("去哪儿攻略", "travelogue"),
                ("今日头条", "platform_article"),
                ("微博", "community_post"),
                ("权威媒体", "media_article"),
            ),
            start=1,
        )
    ]
    sources.append(
        {
            "source_id": "article_rejected_off_entity",
            "platform": "去哪儿攻略",
            "url": "https://example.invalid/rejected/off-entity",
            "category": "travelogue",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "candidateGate": {"passed": False, "issues": ["off_entity_no_anchor"]},
        }
    )
    write_json(
        dl / "article_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "合格景区",
                "researchLane": "article",
                "sources": sources,
            },
        },
    )

    report = audit_managed_batch(task, batch)

    issue_text = "\n".join(
        issue
        for item in report["failedLanes"]
        for issue in (item.get("issues") or [])
        if item.get("entity") == "合格景区" and item.get("lane") == "article"
    )
    assert "source precheck major off_entity_no_anchor" not in issue_text
    assert "source precheck article base sources" not in issue_text
    assert "source precheck source categories" not in issue_text


def test_select_targets_excludes_failed_and_keeps_mandatory():
    discovery = _TMP / "discovery.json"
    _discovery(discovery)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=12,
        mandatory=list(DEFAULT_MANDATORY),
        excluded={"川北候选1", "川南候选1"},
    )
    names = [target["name"] for target in targets]
    assert names[:5] == DEFAULT_MANDATORY
    assert "川北候选1" not in names
    assert "川南候选1" not in names
    assert len(names) == 12
    assert report["excluded"] == ["川北候选1", "川南候选1"]


def test_handle_select_targets_consumes_dedup_ledger_and_exempts_mandatory():
    """跨批去重：dedup_ledger.completedEntities 默认排除；mandatory 点名豁免账本排除。"""
    import argparse as _argparse
    import json as _json

    from _common import dedup
    from task.target_selection import handle_select_targets

    source_task = "旅行/地域/测试省/景区/去重账本源"
    discovery = _TMP / "discovery_dedup_ledger.json"
    _discovery(discovery)
    ledger = dedup.load_manifest(source_task)
    ledger["completedEntities"] = ["川北候选1", DEFAULT_MANDATORY[0]]
    dedup.save_manifest(source_task, ledger)

    args = _argparse.Namespace(
        source_task=source_task,
        discovery=str(discovery),
        exclude="",
        exclude_from_task="",
        exclude_from_batch="",
        exclude_from_run=[],
        mandatory=",".join(DEFAULT_MANDATORY),
        limit=12,
        name="去重账本验证",
        title="去重账本验证",
        region="四川",
        category="景区",
        owner="test",
        write=False,
        force=False,
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        handle_select_targets(args)
    report = _json.loads(buffer.getvalue())
    selected = {target["name"] for target in report["targets"]} if "targets" in report else set()
    ledger_report = report["dedupLedger"]
    assert ledger_report["sourceTaskId"] == source_task
    assert "川北候选1" in ledger_report["excludedByLedger"]
    # mandatory 点名豁免：账本里的 mandatory 不进账本排除。
    assert DEFAULT_MANDATORY[0] not in ledger_report["excludedByLedger"]
    if selected:
        assert "川北候选1" not in selected
        assert DEFAULT_MANDATORY[0] in selected


def test_select_targets_adds_deterministic_reserve_pool():
    discovery = _TMP / "discovery_reserve.json"
    _discovery(discovery)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=10,
        mandatory=list(DEFAULT_MANDATORY[:2]),
        excluded=set(),
        reserve_ratio=0.2,
    )
    selected = {target["name"] for target in targets}
    reserve = report["reserveTargets"]
    assert len(targets) == 10
    assert len(reserve) == 2
    assert not selected & {target["name"] for target in reserve}


def test_select_targets_allows_explicit_elastic_shortfall():
    discovery = _TMP / "discovery_shortfall.json"
    write_json(
        discovery,
        {
            "partitions": [
                {
                    "key": "川西",
                    "leaves": [
                        {"name": "四姑娘山", "entityType": "地点/景区"},
                        {"name": "毕棚沟", "entityType": "地点/景区"},
                    ],
                }
            ]
        },
    )

    targets, report = select_targets(
        discovery_path=discovery,
        limit=5,
        mandatory=["四姑娘山"],
        excluded=set(),
        allow_shortfall=True,
    )

    assert [target["name"] for target in targets] == ["四姑娘山", "毕棚沟"]
    assert report["selectedCount"] == 2
    assert report["selectionShortfall"] == 3
    assert report["allowShortfall"] is True


def test_select_targets_prefers_discovery_canonical_name_and_keeps_source_name():
    discovery = _TMP / "discovery_canonical.json"
    write_json(
        discovery,
        {
            "partitions": [
                {
                    "key": "全国5A",
                    "leaves": [
                        {
                            "name": "承德市承德避暑山庄及周围寺庙景区",
                            "canonicalName": "承德避暑山庄及周围寺庙景区",
                            "entityType": "地点/景区",
                        }
                    ],
                }
            ]
        },
    )

    targets, report = select_targets(
        discovery_path=discovery,
        limit=1,
        mandatory=[],
        excluded=set(),
    )

    assert targets == [
        {
            "name": "承德避暑山庄及周围寺庙景区",
            "entityType": "地点/景区",
            "region": "全国5A",
            "sourceName": "承德市承德避暑山庄及周围寺庙景区",
        }
    ]
    assert report["targets"][0]["sourceName"] == "承德市承德避暑山庄及周围寺庙景区"


def test_select_targets_uses_selection_priority_within_partition():
    discovery = _TMP / "discovery_priority.json"
    write_json(
        discovery,
        {
            "partitions": [
                {
                    "key": "全国5A",
                    "leaves": [
                        {"name": "新晋景区", "entityType": "地点/景区", "selectionPriority": 2024},
                        {"name": "老牌景区", "entityType": "地点/景区", "selectionPriority": 2007},
                    ],
                }
            ]
        },
    )

    targets, report = select_targets(
        discovery_path=discovery,
        limit=1,
        mandatory=[],
        excluded=set(),
    )

    assert [target["name"] for target in targets] == ["老牌景区"]
    assert [target["name"] for target in report["reserveTargets"]] == []


def test_build_multimodal_spec_uses_separated_research_image_contract():
    spec = build_multimodal_spec(
        name="多模态重跑",
        title="多模态重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        reserve_targets=[{"name": "都江堰", "entityType": "地点/景区", "region": "成都"}],
        created_by="test",
    )
    content = spec["content"]
    assert content["modalityContract"] == "separated_research"
    assert content["carriers"] == ["article", "image"]
    assert content["quotas"]["entityArticlesPerTarget"] == 4
    assert content["quotas"]["imageWorksPerTarget"] == 1
    assert spec["acceptance"]["minPostsPerEntity"] == 5
    assert spec["workflowPolicy"]["allowPartialContent"] is True
    assert spec["workflowPolicy"]["deliveryMode"] == "partial_with_replacement_report"
    assert spec["workflowPolicy"]["maxReplacementCandidatesPerWave"] >= 8
    assert spec["workflowPolicy"]["maxReplacementScreenedPerRun"] >= 8
    assert spec["scope"]["reserveCoverageTargets"][0]["name"] == "都江堰"
    assert "galleryPostsPerTarget" not in content["quotas"]


def test_build_multimodal_spec_records_elastic_overfetch_trial_policy():
    targets = [
        {"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"},
        {"name": "都江堰", "entityType": "地点/景区", "region": "成都"},
        {"name": "稻城亚丁", "entityType": "地点/景区", "region": "甘孜"},
        {"name": "海螺沟", "entityType": "地点/景区", "region": "甘孜"},
    ]
    spec = build_multimodal_spec(
        name="弹性百级",
        title="弹性百级",
        region="四川省",
        category="景区",
        targets=targets,
        created_by="test",
        target_entity_count=2,
        elastic_overfetch=True,
        overfetch_multiplier=2.0,
        allow_quota_shortfall=True,
        allow_over_production=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )

    assert len(spec["scope"]["coverageTargets"]) == 4
    assert spec["acceptance"]["minEntities"] == 2
    assert spec["workflowPolicy"]["elasticOverfetch"] is True
    assert spec["workflowPolicy"]["overfetchMultiplier"] == 2.0
    assert spec["workflowPolicy"]["targetEntityCount"] == 2
    assert spec["workflowPolicy"]["targetObjectCount"] == 10
    assert spec["workflowPolicy"]["allowQuotaShortfall"] is True
    assert spec["workflowPolicy"]["allowContentQuotaShortfall"] is True
    assert spec["workflowPolicy"]["allowMinEntityShortfall"] is True
    assert spec["workflowPolicy"]["allowOverProduction"] is True
    assert spec["workflowPolicy"]["minBatchCompletionMode"] == "best_effort_with_reasoned_rejects"


def test_build_multimodal_spec_allows_explicit_image_work_quota():
    spec = build_multimodal_spec(
        name="双图库重跑",
        title="双图库重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        created_by="test",
        image_works_per_target=2,
    )

    assert spec["content"]["quotas"]["imageWorksPerTarget"] == 2
    assert spec["acceptance"]["minPostsPerEntity"] == 6


def test_build_multimodal_spec_supports_image_only_production_contract():
    spec = build_multimodal_spec(
        name="Pinterest图片作品百级",
        title="Pinterest图片作品百级",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=0,
        image_works_per_target=1,
        target_entity_count=1,
        elastic_overfetch=True,
        overfetch_multiplier=1.5,
        allow_quota_shortfall=True,
        allow_over_production=True,
        min_batch_completion_mode="best_effort_with_reasoned_rejects",
    )

    content = spec["content"]
    assert content["carriers"] == ["image"]
    assert content["research"]["lanes"] == ["image"]
    assert content["research"]["laneConcurrency"] == {"image": 4}
    assert content["quotas"]["entityArticlesPerTarget"] == 0
    assert content["quotas"]["entityHomepagesPerTarget"] == 0
    assert content["quotas"]["imageWorksPerTarget"] == 1
    assert spec["acceptance"]["minPostsPerEntity"] == 1
    assert spec["acceptance"].get("requiredAngles", []) == []
    assert spec["workflowPolicy"]["targetObjectCount"] == 1


def test_build_multimodal_spec_freezes_homepage_only_branch_and_object_quota():
    original_branch = os.environ.get("QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH")
    try:
        os.environ["QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH"] = "feature/pinterest-image-commercial-lane"
        spec = build_multimodal_spec(
            name="主页百级",
            title="主页百级",
            region="四川省",
            category="景区",
            targets=[
                {"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"},
                {"name": "都江堰", "entityType": "地点/景区", "region": "成都"},
            ],
            created_by="test",
            entity_articles_per_target=0,
            entity_homepages_per_target=1,
            image_works_per_target=0,
            target_entity_count=2,
            allow_quota_shortfall=True,
        )
    finally:
        if original_branch is None:
            os.environ.pop("QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH", None)
        else:
            os.environ["QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH"] = original_branch

    assert spec["content"]["research"]["lanes"] == ["homepage"]
    assert spec["acceptance"]["minPostsPerEntity"] == 1
    assert spec["workflowPolicy"]["targetObjectCount"] == 2
    assert spec["workflowPolicy"]["executionBranch"] == DEFAULT_HOMEPAGE_ONLY_EXECUTION_BRANCH


def test_build_multimodal_spec_bounds_required_angles_to_article_quota():
    spec = build_multimodal_spec(
        name="两篇文章重跑",
        title="两篇文章重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        created_by="test",
        entity_articles_per_target=2,
        image_works_per_target=1,
    )

    assert spec["content"]["quotas"]["entityArticlesPerTarget"] == 2
    assert spec["acceptance"]["requiredAngles"] == [
        "planning_consultation",
        "decision_experience",
    ]
    assert spec["acceptance"]["minPostsPerEntity"] == 3


def test_write_selected_task_writes_catalog_for_baseline_gate():
    spec = build_multimodal_spec(
        name="可baseline试跑",
        title="可baseline试跑",
        region="四川省",
        category="景区",
        targets=[
            {"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"},
            {"name": "都江堰", "entityType": "地点/景区", "region": "成都"},
        ],
        reserve_targets=[],
        created_by="test",
    )
    write_selected_task(spec, {"targets": []}, force=True)

    rows = read_ndjson(task_catalog(spec["taskId"]))
    assert [row["canonical_name"] for row in rows] == ["四姑娘山", "都江堰"]
    assert {row["topic_id"] for row in rows} == {"地点/景区/四姑娘山", "地点/景区/都江堰"}


_MASTER_LIST_YAML = """\
schemaVersion: quwoquan_data.discovery_seed/2
country: 中国
province: 四川省
city: 成都市
generatedBy: wp3_contract_test
districts:
  - district: 都江堰市
    leaves:
      - name: 都江堰
        canonicalName: 都江堰
        entityType: 地点/景区
        typeTagRefs:
          - Entity/地点/景区/5A景区
          - Entity/地点/景区/世界遗产
        geoTagRef: Topic/地理/行政区/中国/四川省/成都市/都江堰市
        selectionPriority: 1
        sourceReadiness: ready
  - district: 武侯区
    leaves:
      - name: 武侯祠
        canonicalName: 武侯祠
        entityType: 地点/景区
        typeTagRefs:
          - Entity/地点/景区/4A景区
          - Entity/地点/博物馆
        geoTagRef: Topic/地理/行政区/中国/四川省/成都市/武侯区
        geoTagRefs:
          - Topic/地理/行政区/中国/四川省/成都市/武侯区
        aliases:
          - 成都武侯祠博物馆
        selectionPriority: 1
        sourceReadiness: ready
"""


def _master_list_dir(name: str) -> Path:
    root = _TMP / name / "中国"
    (root / "四川省").mkdir(parents=True, exist_ok=True)
    (root / "四川省" / "成都市.yaml").write_text(_MASTER_LIST_YAML, encoding="utf-8")
    return root


def test_select_targets_walks_master_list_directory_and_carries_contract_fields():
    """WP3-1：--discovery 指向主清单目录时 walk yaml，leaf 契约字段透传进目标行。"""
    root = _master_list_dir("master_list_walk")

    targets, report = select_targets(
        discovery_path=root,
        limit=2,
        mandatory=[],
        excluded=set(),
    )

    by_name = {target["name"]: target for target in targets}
    assert set(by_name) == {"都江堰", "武侯祠"}
    assert by_name["都江堰"]["geoTagRef"] == "Topic/地理/行政区/中国/四川省/成都市/都江堰市"
    assert by_name["都江堰"]["typeTagRefs"] == [
        "Entity/地点/景区/5A景区",
        "Entity/地点/景区/世界遗产",
    ]
    assert by_name["武侯祠"]["geoTagRefs"] == ["Topic/地理/行政区/中国/四川省/成都市/武侯区"]
    assert by_name["武侯祠"]["aliases"] == ["成都武侯祠博物馆"]
    assert report["selectedCount"] == 2


_MASTER_LIST_MIXED_READINESS_YAML = """\
schemaVersion: quwoquan_data.discovery_seed/2
country: 中国
province: 浙江省
city: 舟山市
generatedBy: wp5_contract_test
districts:
  - district: 普陀区
    leaves:
      - name: 普陀山
        canonicalName: 普陀山
        entityType: 地点/景区
        geoTagRef: Topic/地理/行政区/中国/浙江省/舟山市/普陀区
        selectionPriority: 1
        sourceReadiness: ready
      - name: 朱家尖
        canonicalName: 朱家尖
        entityType: 地点/景区
        geoTagRef: Topic/地理/行政区/中国/浙江省/舟山市/普陀区
        selectionPriority: 2
        sourceReadiness: pending
  - district: 嵊泗县
    leaves:
      - name: 嵊泗列岛
        canonicalName: 嵊泗列岛
        entityType: 地点/景区
        geoTagRef: Topic/地理/行政区/中国/浙江省/舟山市/嵊泗县
        selectionPriority: 1
        sourceReadiness: pending
"""


def test_select_targets_accepts_city_level_master_list_single_file():
    """WP5：--discovery 可指向市州级主清单单文件（批次精确圈定一个市州）。"""
    path = _TMP / "master_list_city_file" / "舟山市.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_MASTER_LIST_MIXED_READINESS_YAML, encoding="utf-8")

    targets, report = select_targets(
        discovery_path=path,
        limit=3,
        mandatory=[],
        excluded=set(),
    )

    assert {target["name"] for target in targets} == {"普陀山", "朱家尖", "嵊泗列岛"}
    assert report["selectedCount"] == 3


def test_select_targets_filters_by_source_readiness():
    """WP5：sourceReadiness 圈选门——只跑 ready，pending/缺字段一律排除。"""
    path = _TMP / "master_list_readiness" / "舟山市.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_MASTER_LIST_MIXED_READINESS_YAML, encoding="utf-8")

    targets, report = select_targets(
        discovery_path=path,
        limit=3,
        mandatory=[],
        excluded=set(),
        allow_shortfall=True,
        source_readiness=["ready"],
    )

    assert [target["name"] for target in targets] == ["普陀山"]
    assert report["sourceReadinessFilter"] == ["ready"]

    # 无字段 leaf（非主清单 discovery）在启用过滤时视为不命中。
    discovery = _TMP / "discovery_no_readiness.json"
    _discovery(discovery)
    try:
        select_targets(
            discovery_path=discovery,
            limit=3,
            mandatory=[],
            excluded=set(),
            source_readiness=["ready"],
        )
        raise AssertionError("缺 sourceReadiness 字段的 discovery 启用过滤后应报无可选叶子")
    except ValueError as exc:
        assert "无可选叶子" in str(exc)


def test_build_multimodal_spec_carries_master_list_fields_into_coverage_targets():
    """WP3-1：coverageTargets/reserveCoverageTargets 透传主清单契约字段（schema 同口径）。"""
    spec = build_multimodal_spec(
        name="打标透传",
        title="打标透传",
        region="四川省",
        category="景区",
        targets=[
            {
                "name": "武侯祠",
                "entityType": "地点/景区",
                "region": "武侯区",
                "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/武侯区",
                "geoTagRefs": ["Topic/地理/行政区/中国/四川省/成都市/武侯区"],
                "typeTagRefs": ["Entity/地点/景区/4A景区", "Entity/地点/博物馆"],
                "aliases": ["成都武侯祠博物馆"],
            },
            {"name": "无契约字段景区", "entityType": "地点/景区", "region": "测试区"},
        ],
        reserve_targets=[
            {
                "name": "青城山",
                "entityType": "地点/景区",
                "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            }
        ],
        created_by="test",
    )

    covered = {row["name"]: row for row in spec["scope"]["coverageTargets"]}
    assert covered["武侯祠"]["geoTagRef"] == "Topic/地理/行政区/中国/四川省/成都市/武侯区"
    assert covered["武侯祠"]["typeTagRefs"] == ["Entity/地点/景区/4A景区", "Entity/地点/博物馆"]
    assert covered["武侯祠"]["aliases"] == ["成都武侯祠博物馆"]
    # 主清单没有的字段不编造（连键都不写）。
    assert "geoTagRef" not in covered["无契约字段景区"]
    assert "typeTagRefs" not in covered["无契约字段景区"]
    reserve = spec["scope"]["reserveCoverageTargets"][0]
    assert reserve["geoTagRef"] == "Topic/地理/行政区/中国/四川省/成都市/都江堰市"


def test_write_selected_task_catalog_geo_ref_uses_admin_region_path():
    """收债 7：catalog geo_tag_ref 统一为行政区树路径制，禁止 /tag/地域/{region} 回归。"""
    spec = build_multimodal_spec(
        name="行政区geo催收",
        title="行政区geo催收",
        region="四川省",
        category="景区",
        targets=[
            {
                "name": "都江堰",
                "entityType": "地点/景区",
                "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            },
            {"name": "无geo景区", "entityType": "地点/景区"},
        ],
        reserve_targets=[],
        created_by="test",
    )
    write_selected_task(spec, {"targets": []}, force=True)

    rows = {row["canonical_name"]: row for row in read_ndjson(task_catalog(spec["taskId"]))}
    assert rows["都江堰"]["geo_tag_ref"] == "Topic/地理/行政区/中国/四川省/成都市/都江堰市"
    assert rows["无geo景区"]["geo_tag_ref"] == ""
    assert not any(str(row.get("geo_tag_ref") or "").startswith("/tag/") for row in rows.values())


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
