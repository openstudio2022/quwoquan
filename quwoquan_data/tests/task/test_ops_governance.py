"""ops_governance contract tests：controller lease / batch report 硬门。

可直接运行：python3 quwoquan_data/tests/task/test_ops_governance.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_ops_governance_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import ops_governance as og  # noqa: E402
from _common.io import read_json  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区精选"


def test_startup_internal_error_is_infra_retry():
    assert og.classify_failure("startup: internal error") == og.FAILURE_INFRA_RETRY
    assert og.classify_failure("Cursor SDK bridge startup failed") == og.FAILURE_INFRA_RETRY


def test_same_batch_second_controller_is_gate_blocked():
    batch = "controller_singleton"
    with og.controller_lease(TASK, batch) as first:
        issue = og.active_controller_issue(TASK, batch)
        assert issue and first["controllerRunId"] in issue
        try:
            with og.controller_lease(TASK, batch):
                pass
        except RuntimeError as exc:
            assert "GATE_BLOCK controller lease active" in str(exc)
        else:
            raise AssertionError("same task+batch must not allow a second active controller")

    assert og.active_controller_issue(TASK, batch) is None
    released = og.read_controller_lease(TASK, batch)
    assert released and released["status"] == "released"


def test_quality_target_report_aggregates_ledgers_and_scale_decision():
    batch = "quality_report_rollup"
    og.append_failure(
        TASK,
        batch,
        ref="九寨沟_图片作品",
        stage="source_gate",
        reason="rights blocked",
        category=og.FAILURE_ABANDON,
        owner="image_subagent",
    )
    og.append_failure(
        TASK,
        batch,
        ref="峨眉山_文章",
        stage="author",
        reason="template quality repair",
        category=og.FAILURE_QUALITY_REPAIR,
        owner="author_subagent",
    )
    og.append_conflict(
        TASK,
        batch,
        conflict_type="source_unit_atomicity",
        subject="1.download/sources/01.article_base/source.md",
        refs=["峨眉山_文章"],
        reason="article asset came from another URL snapshot",
    )

    report = og.write_quality_target_report(
        TASK,
        batch,
        target_goal=100,
        quality_passed_count=82,
    )

    assert report["targetSatisfactionRate"] == 0.82
    assert report["scaleDecision"] == "rerun_same_scale_optimize_sources"
    assert report["failureSummary"]["byCategory"][og.FAILURE_ABANDON] == 1
    assert report["abandonedByReason"]["rights blocked"] == 1
    assert report["conflictSummary"]["byType"]["source_unit_atomicity"] == 1
    assert report["conflictsByType"]["source_unit_atomicity"] == 1


def test_assignment_upsert_state_is_idempotent_and_events_are_deduped():
    batch = "assignment_upsert"
    assignment = og.build_assignment(
        task_id=TASK,
        batch_id=batch,
        controller_run_id="ctrl-upsert",
        assignment_path=["四川省", "阿坝藏族羌族自治州"],
        role="partition_agent",
        parent_assignment_id="batch-root",
        scope={"sliceType": "city", "name": "阿坝藏族羌族自治州"},
        allowed_read_roots=["_shared"],
        allowed_write_roots=["entities/地点/景区"],
        budget={"maxObjects": 25},
        deadline_epoch=1_800_000_000,
    )
    og.append_assignment(TASK, batch, assignment)
    duplicated = dict(assignment)
    duplicated["deadlineEpoch"] = 1_900_000_000
    og.append_assignment(TASK, batch, duplicated)

    state = read_json(og.assignment_state_path(TASK, batch))
    events = og.read_jsonl(og.assignment_events_path(TASK, batch))
    legacy_events = og.read_jsonl(og.assignment_ledger_path(TASK, batch))

    assert list(state["assignments"]) == [assignment["assignmentId"]]
    assert len(events) == 1
    assert events[0]["eventType"] == "created"
    assert len(legacy_events) == 1


def test_delegated_assignment_requires_parent_deadline_heartbeat_and_budget():
    assignment = og.build_assignment(
        task_id=TASK,
        batch_id="assignment_validation",
        controller_run_id="ctrl-validate",
        assignment_path=["四川省", "成都市", "都江堰"],
        role="author_subagent",
        parent_assignment_id="partition-parent",
        scope={"sliceType": "content_ref", "ref": "都江堰_article_1"},
        allowed_read_roots=["_shared"],
        allowed_write_roots=["posts/article"],
        budget={"maxAttempts": 2},
    )
    assert og.validate_assignment_payload(assignment) == []

    missing = dict(assignment)
    missing["parentAssignmentId"] = None
    missing["deadlineEpoch"] = 0
    missing["heartbeatAt"] = ""
    missing["budget"] = {}
    issues = og.validate_assignment_payload(missing)
    assert "parentAssignmentId required for delegated assignment" in issues
    assert "deadlineEpoch required" in issues
    assert "heartbeatAt required" in issues
    assert "budget required" in issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"ops_governance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
