from __future__ import annotations

import argparse

from support.data_cli_fixtures import *  # noqa: F401,F403

import verify.handler as verify_handler_mod
import verify.sdk_monitoring as sdk_monitor_mod
from _common.paths import OUTPUT_ARTIFACTS_ROOT


def test_sdk_monitoring_discovery_root_uses_output_artifacts_root():
    assert sdk_monitor_mod._ARTIFACTS_ROOT == OUTPUT_ARTIFACTS_ROOT
    retired_root = ".qwq_output/" + "runs/"
    assert retired_root not in str(sdk_monitor_mod._ARTIFACTS_ROOT)
    assert sdk_monitor_mod._ARTIFACTS_ROOT.parts[-2:] == ("data", "runs")


def _seed_sdk_monitor_batch(task_id: str, batch_id: str, *, plan_id: str) -> tuple[Path, Path]:
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "produce")
    shared = batch_workflow_state_path(task_id, batch_id).parent
    write_json(
        batch_workflow_state_path(task_id, batch_id),
        {
            "schemaVersion": "quwoquan.task.workflow_state",
            "taskId": task_id,
            "batchId": batch_id,
            "status": "succeeded",
            "waitingCheckpoint": None,
            "nextAction": "",
            "completed": [
                "download_plan",
                "content_plan",
                "produce_compose",
                "produce_author",
                "review",
                "release",
            ],
            "throughput": {
                "objectsPerHour": 18.5,
                "elapsedSeconds": 1200.0,
                "postCount": 6,
                "maxWorkers": 2,
                "agentActive": False,
            },
            "quality": {
                "firstPassRate": 0.833,
                "reviewedRefs": 6,
                "repairedRefs": 1,
            },
            "lastAgentRun": {
                "startupFailedJobs": 0,
                "infrastructureFailures": 0,
            },
        },
    )
    write_json(
        shared / "token_ledger.json",
        {
            "schemaVersion": "quwoquan_data.token_ledger/1",
            "measurementMode": "cursor_sdk_result_usage",
            "summary": {
                "entryCount": 6,
                "usedTokens": 12345,
                "averageUsedTokens": 2057.5,
                "unitPassedCostUsd": 0.0345,
            },
        },
    )
    write_json(
        shared / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "taskId": task_id,
            "batchId": batch_id,
            "agentProvider": "cursor_sdk",
            "model": "composer",
            "ready": True,
            "preflight": {
                "issues": [],
                "cursorStartup": {
                    "checked": True,
                    "ready": True,
                    "status": "finished",
                    "runtime": "local",
                    "model": "composer",
                    "attempts": 1,
                    "successCount": 1,
                    "authFailures": 0,
                    "true5xxCount": 0,
                    "startupTimeoutCount": 0,
                    "bridgeDisconnectCount": 0,
                    "timeoutSeconds": 240.0,
                    "issues": [],
                },
            },
            "cursorStartup": {
                "checked": True,
                "ready": True,
                "status": "finished",
                "runtime": "local",
                "model": "composer",
                "attempts": 1,
                "successCount": 1,
                "authFailures": 0,
                "true5xxCount": 0,
                "startupTimeoutCount": 0,
                "bridgeDisconnectCount": 0,
                "timeoutSeconds": 240.0,
                "issues": [],
            },
            "startupTimeoutSeconds": 240.0,
            "credentialIngress": {
                "source": "QWQ_CURSOR_API_KEY_FILE",
                "keyFile": "/tmp/cursor.key",
            },
            "runtimeRoots": {
                "workspace": "/tmp/workspace",
                "dataRoot": "/tmp/data",
                "runtimeRoot": "/tmp/runtime",
                "publishRoot": "/tmp/publish",
            },
        },
    )
    write_json(
        shared / "managed_batch_audit.json",
        {
            "schemaVersion": "quwoquan_data.managed_batch_audit/1",
            "failedLaneCount": 0,
            "lanePassed": {"image": 6},
            "inactiveEntityArtifactCount": 0,
            "replacementCount": 0,
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "workflowState": {"status": "succeeded"},
            "lastAgentRun": {"startupFailedJobs": 0, "infrastructureFailures": 0},
        },
    )
    queue_dir = shared / "object_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        queue_dir / "job_succeeded.json",
        {
            "jobId": "job_succeeded",
            "stage": "author",
            "state": "succeeded",
            "startupFailureCount": 0,
            "timings": [{"event": "leased"}],
        },
    )
    write_json(
        fanout_run_matrix_path(plan_id),
        {
            "schemaVersion": "quwoquan_data.fanout_run_matrix",
            "planId": plan_id,
            "executionBranch": "ops-commercialization",
            "orchestrators": [
                {
                    "taskId": task_id,
                    "batchId": batch_id,
                    "worker": "part::四川省",
                    "reached": True,
                    "missing": [],
                    "error": None,
                }
            ],
            "workers": [
                {
                    "worker": "worker-1",
                    "leased": 6,
                    "completed": 6,
                    "failed": 0,
                    "startupFailures": 0,
                    "attemptFailures": 0,
                    "orchestrated": 1,
                    "orchestrationFailed": 0,
                    "prewarmed": True,
                    "coldStartWaitSeconds": 0.0,
                }
            ],
            "summary": {
                "assignments": 1,
                "leased": 6,
                "completed": 6,
                "failed": 0,
                "attemptFailures": 0,
                "startupFailures": 0,
                "orchestrationFailed": 0,
                "connectionRefused": 0,
                "throughput": {"elapsedSeconds": 1200.0, "completedPerMinute": 0.3},
                "credentialIngress": {
                    "source": "QWQ_CURSOR_API_KEY_FILE",
                    "keyFile": "/tmp/cursor.key",
                },
            },
        },
    )
    return shared, queue_dir


def test_build_sdk_monitoring_report_aggregates_runtime_evidence(tmp_path):
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_ok")
    batch_id = "sdk_monitor_ok_batch"
    plan_id = "sdk_monitor_ok_plan"
    shared, _queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)

    startup_probe = tmp_path / "startup_probe.json"
    write_json(
        startup_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": True,
            "attempts": 6,
            "successCount": 6,
            "authFailures": 0,
            "true5xxCount": 0,
            "startupTimeoutCount": 0,
            "bridgeDisconnectCount": 0,
            "startupLatencyP95": 8.2,
            "issues": [],
        },
    )
    watchdog_log = tmp_path / "watchdog.log"
    watchdog_log.write_text("", encoding="utf-8")

    report = sdk_monitor_mod.build_sdk_monitoring_report(
        task_id,
        batch_id,
        plan_id=plan_id,
        startup_probe_path=startup_probe,
        watchdog_log_path=watchdog_log,
    )

    assert report["schemaVersion"] == sdk_monitor_mod.SDK_MONITORING_SCHEMA
    assert report["passed"] is True
    assert report["throughput"]["objectsPerHour"] == 18.5
    assert report["quality"]["firstPassRate"] == 0.833
    assert report["tokenLedger"]["usedTokens"] == 12345
    assert report["tokenLedger"]["measurementMode"] == "cursor_sdk_result_usage"
    assert report["managedBatchAudit"]["lanePassed"] == {"image": 6}
    assert report["objectQueue"]["counts"] == {"succeeded": 1}
    assert report["envReady"]["ready"] is True
    assert report["startupProbe"]["ready"] is True
    assert report["startupProbe"]["derivedFromEnvReady"] is True
    assert report["externalStartupProbe"]["exists"] is True
    assert report["runMatrix"]["summary"]["completed"] == 6
    assert report["runMatrix"]["credentialIngress"]["source"] == "QWQ_CURSOR_API_KEY_FILE"
    assert report["watchdog"]["eventCount"] == 0
    assert report["tokenLedger"]["path"] == str(shared / "token_ledger.json")


def test_build_sdk_monitoring_report_flags_auth_watchdog_and_dead_jobs(tmp_path):
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_bad")
    batch_id = "sdk_monitor_bad_batch"
    plan_id = "sdk_monitor_bad_plan"
    shared, queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)

    write_json(
        queue_dir / "job_dead.json",
        {
            "jobId": "job_dead",
            "stage": "author",
            "state": "dead",
            "startupFailureCount": 2,
            "timings": [{"event": "reconciled", "reason": "artifact_completed"}],
        },
    )
    write_json(
        shared / "managed_batch_audit.json",
        {
            "schemaVersion": "quwoquan_data.managed_batch_audit/1",
            "failedLaneCount": 1,
            "lanePassed": {"image": 5},
            "inactiveEntityArtifactCount": 0,
            "replacementCount": 0,
            "abandonedCount": 1,
            "abandonedContentCount": 0,
            "workflowState": {"status": "failed"},
            "lastAgentRun": {"startupFailedJobs": 1, "infrastructureFailures": 3},
        },
    )
    write_json(
        batch_workflow_state_path(task_id, batch_id),
        {
            "schemaVersion": "quwoquan.task.workflow_state",
            "taskId": task_id,
            "batchId": batch_id,
            "status": "failed",
            "waitingCheckpoint": "produce_author",
            "completed": ["download_plan", "content_plan"],
            "throughput": {"objectsPerHour": 0.0, "elapsedSeconds": 300.0, "postCount": 0, "maxWorkers": 2},
            "quality": {"firstPassRate": 0.0, "reviewedRefs": 0, "repairedRefs": 0},
            "lastAgentRun": {"startupFailedJobs": 1, "infrastructureFailures": 2},
        },
    )
    write_json(
        fanout_run_matrix_path(plan_id),
        {
            "schemaVersion": "quwoquan_data.fanout_run_matrix",
            "planId": plan_id,
            "orchestrators": [
                {
                    "taskId": task_id,
                    "batchId": batch_id,
                    "worker": "part::四川省",
                    "reached": False,
                    "missing": ["release"],
                    "error": "startup failed",
                }
            ],
            "workers": [],
            "summary": {
                "assignments": 1,
                "leased": 0,
                "completed": 0,
                "failed": 1,
                "attemptFailures": 1,
                "startupFailures": 1,
                "orchestrationFailed": 1,
                "connectionRefused": 2,
                "throughput": {"elapsedSeconds": 300.0, "completedPerMinute": 0.0},
                "credentialIngress": {"source": "QWQ_CURSOR_API_KEY_FILE", "keyFile": "/tmp/cursor.key"},
            },
        },
    )
    write_json(
        shared / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "taskId": task_id,
            "batchId": batch_id,
            "agentProvider": "cursor_sdk",
            "model": "composer",
            "ready": False,
            "preflight": {
                "issues": ["401 unauthorized"],
                "cursorStartup": {
                    "checked": True,
                    "ready": False,
                    "status": "auth_failed",
                    "runtime": "local",
                    "model": "composer",
                    "attempts": 4,
                    "successCount": 0,
                    "authFailures": 1,
                    "true5xxCount": 0,
                    "startupTimeoutCount": 1,
                    "bridgeDisconnectCount": 2,
                    "timeoutSeconds": 240.0,
                    "issues": ["401 unauthorized"],
                },
            },
            "cursorStartup": {
                "checked": True,
                "ready": False,
                "status": "auth_failed",
                "runtime": "local",
                "model": "composer",
                "attempts": 4,
                "successCount": 0,
                "authFailures": 1,
                "true5xxCount": 0,
                "startupTimeoutCount": 1,
                "bridgeDisconnectCount": 2,
                "timeoutSeconds": 240.0,
                "issues": ["401 unauthorized"],
            },
            "startupTimeoutSeconds": 240.0,
            "credentialIngress": {"source": "QWQ_CURSOR_API_KEY_FILE", "keyFile": "/tmp/cursor.key"},
            "runtimeRoots": {
                "workspace": "/tmp/workspace",
                "dataRoot": "/tmp/data",
                "runtimeRoot": "/tmp/runtime",
                "publishRoot": "/tmp/publish",
            },
        },
    )

    startup_probe = tmp_path / "startup_probe_bad.json"
    write_json(
        startup_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": False,
            "attempts": 4,
            "successCount": 0,
            "authFailures": 1,
            "true5xxCount": 0,
            "startupTimeoutCount": 1,
            "bridgeDisconnectCount": 2,
            "startupLatencyP95": 21.5,
            "issues": ["401 unauthorized"],
        },
    )
    watchdog_log = tmp_path / "watchdog_bad.log"
    watchdog_log.write_text(
        "2026-07-08T10:00:00Z,WARN,kill,matched,pid=11\n"
        "2026-07-08T10:00:01Z,WARN,kill,matched,pid=12\n",
        encoding="utf-8",
    )

    report = sdk_monitor_mod.build_sdk_monitoring_report(
        task_id,
        batch_id,
        plan_id=plan_id,
        startup_probe_path=startup_probe,
        watchdog_log_path=watchdog_log,
    )

    assert report["passed"] is False
    assert report["objectQueue"]["deadJobs"] == 1
    assert report["objectQueue"]["staleRecoveryCount"] == 1
    assert report["watchdog"]["eventCount"] == 2
    assert report["authVsInfra"]["startupProbeAuthFailures"] == 1
    assert report["startupProbe"]["derivedFromEnvReady"] is True
    assert report["externalStartupProbe"]["exists"] is True
    assert report["authVsInfra"]["managedAuditInfrastructureFailures"] == 3
    joined = "\n".join(report["issues"])
    assert "startupProbe.authFailures=1" in joined
    assert "startupProbe.bridgeDisconnectCount=2" in joined
    assert "objectQueue.deadJobs=1" in joined
    assert "watchdog.eventCount=2" in joined
    assert "runMatrix.startupFailures=1" in joined
    assert "managedBatchAudit.failedLaneCount=1" in joined


def test_build_sdk_monitoring_report_rejects_estimated_token_ledger(tmp_path):
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_estimated")
    batch_id = "sdk_monitor_estimated_batch"
    plan_id = "sdk_monitor_estimated_plan"
    shared, _queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)
    write_json(
        shared / "token_ledger.json",
        {
            "schemaVersion": "quwoquan_data.token_ledger/1",
            "measurementMode": "estimated_from_artifacts",
            "summary": {
                "entryCount": 1,
                "usedTokens": 999,
                "averageUsedTokens": 999.0,
                "unitPassedCostUsd": 0.0,
            },
        },
    )
    startup_probe = tmp_path / "startup_probe_estimated.json"
    write_json(
        startup_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": True,
            "attempts": 1,
            "successCount": 1,
            "authFailures": 0,
            "true5xxCount": 0,
            "startupTimeoutCount": 0,
            "bridgeDisconnectCount": 0,
            "startupLatencyP95": 3.0,
            "issues": [],
        },
    )
    watchdog_log = tmp_path / "watchdog_estimated.log"
    watchdog_log.write_text("", encoding="utf-8")

    report = sdk_monitor_mod.build_sdk_monitoring_report(
        task_id,
        batch_id,
        plan_id=plan_id,
        startup_probe_path=startup_probe,
        watchdog_log_path=watchdog_log,
    )

    assert report["passed"] is False
    assert "tokenLedger.measurementMode=estimated_from_artifacts" in "\n".join(report["issues"])


def test_build_sdk_monitoring_report_accepts_estimated_token_ledger_with_explicit_flag(tmp_path):
    """H100 口径（2026-07-06 裁定）：estimated 账本仅在显式传参时不计 issue，转入 acceptedDeviations。"""
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_estimated_accept")
    batch_id = "sdk_monitor_estimated_accept_batch"
    plan_id = "sdk_monitor_estimated_accept_plan"
    shared, _queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)
    write_json(
        shared / "token_ledger.json",
        {
            "schemaVersion": "quwoquan_data.token_ledger/1",
            "measurementMode": "estimated_from_artifacts",
            "summary": {
                "entryCount": 6,
                "usedTokens": 999,
                "averageUsedTokens": 166.5,
                "unitPassedCostUsd": 0.01,
            },
        },
    )
    startup_probe = tmp_path / "startup_probe_estimated_accept.json"
    write_json(
        startup_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": True,
            "attempts": 1,
            "successCount": 1,
            "authFailures": 0,
            "true5xxCount": 0,
            "startupTimeoutCount": 0,
            "bridgeDisconnectCount": 0,
            "startupLatencyP95": 3.0,
            "issues": [],
        },
    )
    watchdog_log = tmp_path / "watchdog_estimated_accept.log"
    watchdog_log.write_text("", encoding="utf-8")

    report = sdk_monitor_mod.build_sdk_monitoring_report(
        task_id,
        batch_id,
        plan_id=plan_id,
        startup_probe_path=startup_probe,
        watchdog_log_path=watchdog_log,
        accept_estimated_token_ledger=True,
    )

    assert report["passed"] is True, report["issues"]
    assert "tokenLedger.measurementMode=estimated_from_artifacts" not in "\n".join(report["issues"])
    assert any(
        "estimated_from_artifacts" in item and "explicitly accepted" in item
        for item in report["acceptedDeviations"]
    )
    assert report["tokenLedger"]["measurementMode"] == "estimated_from_artifacts"


def test_build_sdk_monitoring_report_uses_batch_env_ready_when_probe_not_passed(tmp_path, monkeypatch):
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_no_global_fallback")
    batch_id = "sdk_monitor_no_global_fallback_batch"
    plan_id = "sdk_monitor_no_global_fallback_plan"
    _shared, _queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)

    unrelated_probe = tmp_path / "startup_probe.json"
    write_json(
        unrelated_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": True,
            "attempts": 6,
            "successCount": 6,
            "authFailures": 0,
            "true5xxCount": 0,
            "startupTimeoutCount": 0,
            "bridgeDisconnectCount": 0,
            "startupLatencyP95": 8.2,
            "issues": [],
        },
    )
    unrelated_watchdog = tmp_path / "watchdog.log"
    unrelated_watchdog.write_text("2026-07-06T00:00:00Z,INFO,watchdog,ok,noop\n", encoding="utf-8")
    monkeypatch.setattr(sdk_monitor_mod, "_discover_startup_probe_path", lambda: unrelated_probe)
    monkeypatch.setattr(sdk_monitor_mod, "_discover_watchdog_log_path", lambda: unrelated_watchdog)

    report = sdk_monitor_mod.build_sdk_monitoring_report(
        task_id,
        batch_id,
        plan_id=plan_id,
    )

    assert report["startupProbe"]["exists"] is True
    assert report["startupProbe"]["derivedFromEnvReady"] is True
    assert report["startupProbe"]["path"].endswith("env_ready_report.json")
    assert report["startupProbe"]["ready"] is True
    assert report["watchdog"]["exists"] is False
    assert "startup probe report missing" not in report["issues"]


def test_handle_verify_sdk_monitoring_writes_report(tmp_path):
    task_id = _make_task("旅行/地域/四川省/景区/sdk_monitor_handler")
    batch_id = "sdk_monitor_handler_batch"
    plan_id = "sdk_monitor_handler_plan"
    _shared, _queue_dir = _seed_sdk_monitor_batch(task_id, batch_id, plan_id=plan_id)

    startup_probe = tmp_path / "startup_probe_handler.json"
    write_json(
        startup_probe,
        {
            "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
            "ready": True,
            "attempts": 3,
            "successCount": 3,
            "authFailures": 0,
            "true5xxCount": 0,
            "startupTimeoutCount": 0,
            "bridgeDisconnectCount": 0,
            "startupLatencyP95": 5.0,
            "issues": [],
        },
    )
    watchdog_log = tmp_path / "watchdog_handler.log"
    watchdog_log.write_text("", encoding="utf-8")
    report_out = tmp_path / "sdk_monitoring_report.json"

    verify_handler_mod.handle_verify(
        argparse.Namespace(
            verify_command="sdk-monitoring",
            task=task_id,
            batch=batch_id,
            plan=plan_id,
            startup_probe_file=str(startup_probe),
            watchdog_log=str(watchdog_log),
            run_matrix=None,
            report_out=str(report_out),
            strict=True,
            release=None,
            scope="current",
            data_release_file=None,
            publish_root=None,
            metadata_root=None,
            phase="preflight",
            report=None,
        )
    )

    report = read_json(report_out)
    assert report["schemaVersion"] == sdk_monitor_mod.SDK_MONITORING_SCHEMA
    assert report["passed"] is True
    assert report["runMatrix"]["exists"] is True
