"""task run 编排器回归（目标① 无人值守 DAG）：

验证编排器在 Agent checkpoint 正确暂停/推进、workflow_state 可 resume：
1. 首跑停在 download_plan checkpoint（无 source_plan）。
2. 预置 source_plan(含 body 离线兜底) 后 resume → 过 download_plan/download_fetch/
   build_prepare，停在下一个 checkpoint build_homepage（主页未物化）。
3. workflow_state.completed 正确累积、幂等。

隔离 QWQ_DATA_ROOT，造最小单实体 task，不依赖联网/真实 committed 任务。
可直接运行 python3 quwoquan_data/tests/workflow/test_task_run_pipeline.py
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

import argparse
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="task_run_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.draft_io import draft_article_path, write_placeholder_draft  # noqa: E402
from _common.command_packet import build_packet, write_packet  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common import content_object  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_posts_root,
    committed_task_spec,
    STAGE_DOWNLOAD,
    batch_command_root,
    batch_inputs_dir,
    ensure_batch_layout,
    release_root,
    task_baseline_freeze_packet_path,
    task_data,
    task_entities,
    task_tags,
    task_entity_pages,
    task_graph,
)
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from task import run as run_mod  # noqa: E402
from task import store  # noqa: E402

_EID = "测试景区甲"


def _make_task() -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="景区全覆盖",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": _EID}],
        },
        created_by="test",
    )
    store.save_spec(spec)
    store.save_progress(store.init_progress(spec["taskId"], remaining=[f"地点/景区/{_EID}"]))
    _seed_baseline(spec["taskId"])
    return spec["taskId"]


def _seed_baseline(task_id: str) -> None:
    packet = build_packet(
        task_id=task_id,
        command="data baseline",
        object_kind="task",
        object_ref=task_id,
        stage="baseline",
        read_policy=["task.yaml", "progress.json"],
        stop_if=["taskId mismatch"],
        output_policy=["write task/_shared/baseline_freeze_packet.json"],
        inputs={"taskSpecPath": str(committed_task_spec(task_id))},
        outputs={"packetPath": str(task_baseline_freeze_packet_path(task_id))},
        handoff_to="data workflow run",
        evidence={"required": ["baseline_freeze_packet.json"]},
        summary={"coverageTargetCount": 1, "catalogRowCount": 1},
    )
    write_packet(task_baseline_freeze_packet_path(task_id), packet)


def _ctx(task_id: str, batch_id: str) -> run_mod.PipelineContext:
    spec = store.load_spec(task_id)
    baseline_packet = read_json(task_baseline_freeze_packet_path(task_id))
    return run_mod.PipelineContext(
        task_id=task_id, batch_id=batch_id,
        entity_ids=run_mod._coverage_entity_ids(spec), spec=spec,
        baseline_packet=baseline_packet, baseline_packet_path=task_baseline_freeze_packet_path(task_id),
    )


def _seed_source_plan(task_id: str, batch_id: str) -> None:
    # 对象优先（M2 规范路径）：Agent 把 source_plan 填到实体对象 1.download/source_plan.json。
    ensure_batch_layout(task_id, batch_id, "download")
    obj = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    write_json(obj / STAGE_DOWNLOAD / "source_plan.json", {
        "sources": [
            {
                "source_id": "s1",
                "platform": "baike",
                "url": "https://x.invalid/a",
                "body": "离线兜底正文：测试景区甲简介与门票海拔。",
            },
            {
                "source_id": "s2",
                "platform": "mafengwo",
                "url": "https://x.invalid/b",
                "body": "离线兜底正文：测试景区甲游记与避坑。",
            },
            {
                "source_id": "s3",
                "platform": "官网",
                "url": "https://x.invalid/c",
                "body": "离线兜底正文：测试景区甲官方开放与预约信息。",
            },
        ],
    })


def _seed_publish_inputs(task_id: str, batch_id: str) -> None:
    entities_dir = task_data(task_id).entities_dir()
    entity_dir = entities_dir / "地点" / "景区" / _EID
    entity_dir.mkdir(parents=True, exist_ok=True)
    write_json(entity_dir / "_entity.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "label": _EID,
        "tagRefs": ["四川省", "景区"],
        "geoTagRef": "四川省",
        "sourceTaskId": task_id,
    })
    (entity_dir / "page.md").write_text(f"# {_EID}\n\n这是用于 publish 回归的实体主页。", encoding="utf-8")
    write_json(entity_dir / "manifest.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "sourceTaskId": task_id,
        "tagRefs": ["四川省", "景区"],
    })

    post_dir = batch_posts_root(task_id, batch_id) / "article" / "攻略" / _EID / "001"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "article.md").write_text(f"# {_EID} 攻略\n\n这是用于 publish 的真实成品正文。", encoding="utf-8")
    write_json(post_dir / "manifest.json", {
        "contentType": "article",
        "publishTitle": f"{_EID} 攻略",
        "title": f"{_EID} 攻略",
        "sourceTaskId": task_id,
        "sourceBatchId": batch_id,
        "entityRefs": [f"/entity/地点/景区/{_EID}"],
        "tagRefs": ["四川省", "景区"],
    })
    review_dir = post_dir / "5.review"
    review_dir.mkdir(parents=True, exist_ok=True)
    write_json(review_dir / "review_ledger.json", {
        "schemaVersion": "quwoquan_data.review_ledger",
        "taskId": task_id,
        "batchId": batch_id,
        "ref": f"{_EID} 攻略",
        "policy": {
            "autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True, "autoDiscardScoreAtMost": 1},
            "reprocess": {"maxAttempts": 3},
        },
        "article": {
            "kind": "article",
            "target": f"{_EID} 攻略",
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
    })
    write_json(review_dir / "review_entities.json", {
        "schemaVersion": "quwoquan_data.review_entities",
        "ref": f"{_EID} 攻略",
        "entities": [
            {
                "name": _EID,
                "domain": "地点",
                "type": "景区",
                "ref": f"/entity/地点/景区/{_EID}",
                "hasHomepage": True,
                "generated": False,
                "evidenceRef": "",
            }
        ],
    })


def test_first_run_pauses_at_download_plan():
    task_id = _make_task()
    code = run_mod.run_pipeline(_ctx(task_id, "b1"))
    assert code == 10, f"expected pause(10), got {code}"
    state = run_mod.load_workflow_state(task_id, "b1")
    assert state["waitingCheckpoint"] == "download_plan"
    assert "download_fetch" not in state["completed"]


def test_resume_advances_after_source_plan():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b2"))  # pause at download_plan
    _seed_source_plan(task_id, "b2")
    code = run_mod.run_pipeline(_ctx(task_id, "b2"))  # resume
    assert code == 10, f"expected next-checkpoint pause(10), got {code}"
    state = run_mod.load_workflow_state(task_id, "b2")
    # download_plan/fetch/build_prepare 应已完成，停在 build_homepage
    assert "download_plan" in state["completed"]
    assert "download_fetch" in state["completed"]
    assert "build_prepare" in state["completed"]
    assert state["waitingCheckpoint"] == "build_homepage"


def test_rewind_drops_target_and_subsequent():
    """ReAct 回退：rewind 到 produce_compose 应清掉它及之后所有 stage，保留之前。"""
    completed = set(run_mod.STAGE_NAMES)  # 全完成
    kept = run_mod._rewind_to(completed, "produce_compose")
    assert "produce_compose" not in kept
    assert "produce_review" not in kept
    assert "publish" not in kept
    assert "download_fetch" in kept and "build_validate" in kept


def test_react_rewind_respects_max_and_writes_repair():
    """ReAct 回退计数到上限后不再回退；回退时写 repair_report。"""
    task_id = _make_task()
    state = run_mod.load_workflow_state(task_id, "rw1")
    ctx = _ctx(task_id, "rw1")
    completed = set(run_mod.STAGE_NAMES)
    fail = run_mod.StageResult("produce_review", run_mod.AUTO, "failed",
                               "发布门未过", fallback_stage="download", issues=["x"])
    # 前 MAX 次应成功回退
    for i in range(run_mod.MAX_REACT_REWINDS):
        completed, ok = run_mod._react_rewind(ctx, state, completed, fail)
        assert ok, f"rewind {i} should succeed"
        assert "download_plan" not in completed  # download→download_plan 已回退
        completed = set(run_mod.STAGE_NAMES)  # 模拟重跑后再次失败
    # 超限后不再回退
    _, ok = run_mod._react_rewind(ctx, state, completed, fail)
    assert ok is False
    # repair_report 已落盘
    from _common.paths import batch_results_dir
    repair_dir = batch_results_dir(task_id, "rw1", "workflow_run", "repair_report")
    assert repair_dir.is_dir() and any(repair_dir.glob("*.json"))


def test_until_stops_early():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b3"))
    _seed_source_plan(task_id, "b3")
    ctx = _ctx(task_id, "b3")
    ctx.until = "download_fetch"
    code = run_mod.run_pipeline(ctx)
    assert code == 0, f"expected clean stop(0) at --until, got {code}"
    state = run_mod.load_workflow_state(task_id, "b3")
    assert "download_fetch" in state["completed"]
    assert "build_homepage" not in state["completed"]


def test_author_checkpoint_only_reads_packaged_drafts():
    task_id = _make_task()
    batch_id = "drafts1"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    legacy = batch_command_root(task_id, batch_id, "produce") / "drafts" / "旧.article.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# 旧平铺正文\n\n这不应被新 checkpoint 识别。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False
    assert pending == ["(no article drafts; run compose-brief first)"]

    content_object.register_content_object(task_id, batch_id, "新", content_type="article", angle="体验", title="新")
    write_placeholder_draft(task_id, batch_id, "新")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False and pending == ["新"]
    draft_article_path(task_id, batch_id, "新").write_text("# 新正文\n\n这是 Agent 完成的正文。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []


def test_publish_stage_materializes_task_inputs_and_release():
    task_id = _make_task()
    batch_id = "publish1"
    _seed_publish_inputs(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)
    assert result.status == "done", result.message
    assert task_entities(task_id).exists()
    assert task_tags(task_id).exists()
    assert task_entity_pages(task_id).is_dir()
    assert (task_graph(task_id) / "relations.ndjson").exists()
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    assert (release_root_dir / "release_manifest.json").exists()
    assert (release_root_dir / "entities" / "entities.ndjson").exists()
    assert (release_root_dir / "tags" / "tags.ndjson").exists()
    assert (release_root_dir / "entity_pages").is_dir()
    assert (release_root_dir / "graph" / "relations.ndjson").exists()
    assert (release_root_dir / "posts" / "article" / "攻略" / _EID / "001" / "5.review" / "review_ledger.json").exists()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"task run pipeline tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
