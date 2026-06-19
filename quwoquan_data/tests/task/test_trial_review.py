"""Managed trial review diagnostics."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_trial_review_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
for _readonly_dir in ("schema", "sop"):
    src = DATA_ROOT / _readonly_dir
    dst = _TMP / _readonly_dir
    if dst.exists():
        continue
    try:
        dst.symlink_to(src, target_is_directory=True)
    except OSError:
        shutil.copytree(src, dst)

from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_shared_dir,
    release_manifest,
    task_baseline_freeze_packet_path,
    task_catalog,
    task_shared_dir,
)
from task import store  # noqa: E402
from task.trial_review import build_trial_review  # noqa: E402


def _make_task(name: str = "试跑复盘") -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name=name,
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "景区甲"},
                {"entityType": "地点/景区", "name": "景区乙"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
            },
        },
        created_by="test",
    )
    spec["status"] = "active"
    store.save_spec(spec)
    store.save_progress(store.init_progress(spec["taskId"]))
    write_json(task_baseline_freeze_packet_path(spec["taskId"]), {"status": "frozen"})
    write_json(task_shared_dir(spec["taskId"]) / "baseline_report.json", {"status": "passed"})
    catalog = task_catalog(spec["taskId"])
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text('{"name":"景区甲"}\n{"name":"景区乙"}\n', encoding="utf-8")
    return spec["taskId"]


def test_trial_review_blocks_when_runtime_never_started():
    task_id = _make_task("只有baseline")

    report = build_trial_review(task_id, "run_1", env={})

    assert report["convergence"]["status"] == "not_started"
    assert report["qualityAndScaleGate"]["passed"] is False
    assert "managed batch runtime missing; no end-to-end trial evidence" in report["qualityAndScaleGate"]["blockers"]
    assert "CURSOR_API_KEY missing; real managed Cursor SDK trial cannot run" in report["qualityAndScaleGate"]["blockers"]
    assert report["terminalCause"]["category"] == "environment_blocker"
    assert report["nextTrialStrategy"]["mode"] == "deterministic_until_content_plan"
    assert report["scaleLadder"]["levels"][0]["go"] is False
    assert report["decision"]["canScale"] is False


def test_trial_review_classifies_cursor_infra_failure_and_efficiency_risk():
    task_id = _make_task("基础设施失败")
    shared = batch_shared_dir(task_id, "run_infra")
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "repairing",
            "waitingCheckpoint": "produce_author",
            "failedObjects": ["produce_author: agent subprocess timed out"],
            "lastAgentRun": {
                "stage": "produce_author",
                "plannedJobCount": 2,
                "jobCount": 2,
                "startedCount": 1,
                "finishedCount": 1,
                "infrastructureFailures": 1,
            },
        },
    )

    report = build_trial_review(task_id, "run_infra", env={"CURSOR_API_KEY": "present"})

    blockers = report["qualityAndScaleGate"]["blockers"]
    assert "Cursor SDK infrastructure failures=1" in blockers
    assert "workflow stuck at checkpoint produce_author" in blockers
    assert report["terminalCause"]["category"] == "cursor_sdk_infra_failure"
    assert report["nextTrialStrategy"]["mode"] == "managed_author_retry_after_infra_recovery"
    assert report["efficiency"]["estimatedAuthorJobs"] == 12
    assert any(
        "subprocess startup overhead" in issue
        for issue in report["efficiency"]["issues"]
    )


def test_trial_review_uses_batch_scheduler_worker_cap_before_shell_default():
    task_id = _make_task("批次并发证据")
    shared = batch_shared_dir(task_id, "run_workers")
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 100},
            "quality": {"firstPassRate": 0.9},
            "lastAgentRun": {
                "stage": "produce_author",
                "plannedJobCount": 12,
                "jobCount": 12,
                "startedCount": 12,
                "finishedCount": 12,
                "infrastructureFailures": 0,
                "scheduler": {
                    "promptCount": 12,
                    "requestedMaxWorkers": 4,
                    "effectiveWorkerCount": 4,
                    "localCursorMaxWorkers": 4,
                    "elapsedSeconds": 180,
                    "startedAt": "s1",
                },
                "finishedAt": "t1",
            },
            "agentRunHistory": [
                {
                    "stage": "produce_author",
                    "plannedJobCount": 12,
                    "jobCount": 12,
                    "startedCount": 12,
                    "finishedCount": 12,
                    "infrastructureFailures": 0,
                    "scheduler": {
                        "promptCount": 12,
                        "requestedMaxWorkers": 4,
                        "effectiveWorkerCount": 4,
                        "localCursorMaxWorkers": 4,
                        "elapsedSeconds": 180,
                        "startedAt": "s1",
                    },
                    "finishedAt": "t1",
                }
            ],
        },
    )

    report = build_trial_review(task_id, "run_workers", env={"CURSOR_API_KEY": "present"})

    assert report["efficiency"]["agentRunHistoryCount"] == 1
    assert not any("worker cap is 1" in issue for issue in report["efficiency"]["issues"])


def test_trial_review_classifies_source_sufficiency_blocker():
    task_id = _make_task("来源不足")
    shared = batch_shared_dir(task_id, "run_source")
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "running",
            "waitingCheckpoint": "download_plan",
            "failedObjects": [],
        },
    )
    write_json(
        shared / "managed_batch_audit.json",
        {
            "targetCount": 2,
            "lanePassed": {"homepage": 1, "article": 0, "image": 1},
            "failedLaneCount": 3,
            "failedLanes": [
                {"entity": "景区甲", "lane": "article", "issues": ["article sources=0 need>=4"]},
                {"entity": "景区乙", "lane": "article", "issues": ["article sources=0 need>=4"]},
                {"entity": "景区乙", "lane": "image", "issues": ["image collection missing"]},
            ],
            "abandonedCount": 0,
        },
    )

    report = build_trial_review(task_id, "run_source", env={"CURSOR_API_KEY": "present"})

    assert report["terminalCause"]["category"] == "source_sufficiency_blocker"
    assert report["nextTrialStrategy"]["mode"] == "source_ready_repair_or_replace"
    assert "task audit-batch" in report["nextTrialStrategy"]["commands"][0]
    assert "task select-targets" in report["nextTrialStrategy"]["commands"][1]
    assert report["evidence"]["sourceReadiness"]["status"] == "blocked"
    assert report["evidence"]["sourceReadiness"]["allLaneReadyTargetCount"] == 0
    assert report["evidence"]["sourceReadiness"]["laneCoverage"]["article"]["passed"] == 0
    assert any(
        "managed batch failed lanes=3" in item
        for item in report["scaleLadder"]["levels"][0]["requiredBeforeGo"]
    )
    assert report["terminalCause"]["stage"] == "download_plan"


def test_trial_review_prefers_auto_research_availability_over_stale_audit():
    task_id = _make_task("来源可用性优先")
    shared = batch_shared_dir(task_id, "run_auto_availability")
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "download_plan",
            "failedObjects": ["景区乙: article sources=1 need>=4"],
        },
    )
    write_json(
        shared / "managed_batch_audit.json",
        {
            "targetCount": 2,
            "lanePassed": {"homepage": 2, "article": 2, "image": 2},
            "failedLaneCount": 0,
            "failedLanes": [],
        },
    )
    write_json(
        shared / "auto_research_plan.json",
        {
            "sourceAvailability": {
                "readyTargets": ["景区甲"],
                "ineligibleTargets": [
                    {
                        "entityId": "景区乙",
                        "lanes": ["article"],
                        "issues": ["article sources=1 need>=4"],
                    }
                ],
            },
            "sourceUnavailable": [{"entityId": "景区乙", "lane": "article"}],
        },
    )

    report = build_trial_review(task_id, "run_auto_availability", env={"CURSOR_API_KEY": "present"})

    readiness = report["evidence"]["sourceReadiness"]
    assert readiness["status"] == "blocked"
    assert readiness["allLaneReadyTargetCount"] == 1
    assert readiness["laneCoverage"]["article"]["passed"] == 1
    assert readiness["laneCoverage"]["homepage"]["passed"] == 2
    blockers = report["qualityAndScaleGate"]["blockers"]
    assert "source-ready targets 1/2" in blockers
    assert "source-ready targets 2/2" not in blockers
    assert report["terminalCause"]["reason"].startswith("source availability ready 1/2")


def test_trial_review_uses_active_scheduler_when_interrupted_before_last_agent_record():
    task_id = _make_task("中断并发证据")
    shared = batch_shared_dir(task_id, "run_interrupted")
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "manual_required",
            "waitingCheckpoint": "download_plan",
            "failedObjects": ["download_plan: interrupted; cancelled queued managed agent jobs"],
            "activeAgentScheduler": {
                "stage": "download_plan",
                "requestedMaxWorkers": 8,
                "effectiveWorkerCount": 8,
                "localCursorMaxWorkers": 8,
                "runtime": "local",
                "promptCount": 171,
                "estimatedMinWaves": 22,
                "startedAt": "s1",
            },
        },
    )

    report = build_trial_review(task_id, "run_interrupted", env={"CURSOR_API_KEY": "present"})

    assert report["workflow"]["activeAgentScheduler"]["effectiveWorkerCount"] == 8
    assert report["efficiency"]["batchScheduler"]["promptCount"] == 171
    assert report["efficiency"]["batchScheduler"]["effectiveWorkerCount"] == 8
    assert not any("worker cap is 1" in issue for issue in report["efficiency"]["issues"])
    assert any("171 prompts" in issue for issue in report["efficiency"]["issues"])


def test_trial_review_prefers_batch_env_ready_evidence_over_current_shell():
    task_id = _make_task("环境证据优先")
    shared = batch_shared_dir(task_id, "run_env_ready")
    write_json(shared / "env_ready_report.json", {"ready": True, "issues": []})
    write_json(
        shared / "task_workflow_state.json",
        {
            "status": "manual_required",
            "failedObjects": [
                "景区甲_seasonal_timing: source_unavailable: usable article base sources 3 < 4"
            ],
            "nextAction": "content_plan 存在确定性 source-unavailable",
        },
    )

    report = build_trial_review(task_id, "run_env_ready", env={})

    blockers = report["qualityAndScaleGate"]["blockers"]
    assert "CURSOR_API_KEY missing; real managed Cursor SDK trial cannot run" not in blockers
    assert report["terminalCause"]["category"] == "source_sufficiency_blocker"
    assert report["scaleLadder"]["currentObjectCount"] == 14
    assert report["scaleLadder"]["entityBatchLevels"][0]["entityCount"] == 10
    assert report["scaleLadder"]["entityBatchLevels"][0]["articlesPerEntity"] == 4
    assert report["scaleLadder"]["entityBatchLevels"][0]["imageWorksPerEntity"] == 2


def test_trial_review_infers_isolated_release_evidence():
    task_id = _make_task("发布证据")
    batch_id = "run_release"
    shared = batch_shared_dir(task_id, batch_id)
    write_json(shared / "env_ready_report.json", {"ready": True, "issues": []})
    write_json(shared / "task_workflow_state.json", {"status": "succeeded", "failedObjects": []})
    inferred_release = f"{task_id.replace('/', '__')}__{batch_id}"
    write_json(release_manifest(inferred_release), {"releaseId": inferred_release})

    report = build_trial_review(task_id, batch_id, env={})

    assert report["evidence"]["releaseEvidenceExists"] is True
    assert report["evidence"]["releaseId"] == inferred_release


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
