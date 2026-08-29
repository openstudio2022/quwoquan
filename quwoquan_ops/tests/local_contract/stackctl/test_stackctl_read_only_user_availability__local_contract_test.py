"""stackctl 只读用户可用性聚合的代际与低基数负例。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import read_only_user_availability as subject

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64
TRAIN_DIGEST = "sha256:" + "c" * 64


def _blocked_report(first_blocker_class: str = "startup_identity") -> dict[str, object]:
    layers = [
        {
            "name": name,
            "status": "blocked",
            "issues": [f"{name} blocked"],
        }
        for name in subject.LAYERS
    ]
    return {
        "schema": subject.SCHEMA,
        "target": "gamma-local",
        "environment": "gamma",
        "observedAt": "2026-08-18T00:00:00Z",
        "status": "failed",
        "firstBlockerClass": first_blocker_class,
        "firstBlocker": layers[0]["issues"][0],
        "userAvailability": layers,
        "metrics": subject._metrics(
            target_name="gamma-local",
            layers=layers,
            overall_status="failed",
            first_blocker_class=first_blocker_class,
        ),
        "evidence": {},
    }


def test_report_schema_accepts_bounded_status_and_metric_vocabulary() -> None:
    schema = json.loads(
        Path(
            "quwoquan_ops/environments/read_only_user_availability_report.schema.json"
        ).read_text(encoding="utf-8")
    )
    report = _blocked_report()

    Draft202012Validator(schema).validate(report)
    assert {metric["name"] for metric in report["metrics"]} == {
        "stackctl_user_availability",
        "stackctl_first_blocker",
    }


def test_report_schema_rejects_high_cardinality_metric_labels() -> None:
    report = _blocked_report()
    metrics = report["metrics"]
    assert isinstance(metrics, list)
    first_metric = metrics[0]
    assert isinstance(first_metric, dict)
    labels = first_metric["labels"]
    assert isinstance(labels, dict)
    labels["receiptDigest"] = DIGEST

    try:
        subject.validate_read_only_user_availability_report(report)
    except ValueError as error:
        assert "low-cardinality" in str(error)
    else:
        raise AssertionError("receipt digest must never become an observability label")


def test_startup_identity_blocker_does_not_stop_independent_collection(
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        subject,
        "_candidate_report",
        lambda _target: (
            calls.append("candidate")
            or {"status": "validated", "providerRuntime": {}, "issues": []}
        ),
    )
    monkeypatch.setattr(
        subject,
        "_startup_report",
        lambda **kwargs: (
            calls.append(str(kwargs["mode"]))
            or {"mode": kwargs["mode"], "status": "stopped"}
        ),
    )
    monkeypatch.setattr(
        subject,
        "_provider_report",
        lambda **_kwargs: (
            calls.append("provider")
            or {
                "ready": False,
                "runtimeCompositionDigest": DIGEST,
                "bindingCount": 2,
                "workloadRoles": ["sms-provider-substitute"],
                "issues": ["generation mismatch"],
            }
        ),
    )
    monkeypatch.setattr(
        subject,
        "_content_report",
        lambda **_kwargs: (
            calls.append("content")
            or {
                "releaseActive": True,
                "exactQueriesReady": True,
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessPhase": "research",
                "readinessReceiptRef": "env/gamma/runs/readiness.json",
                "readinessReceiptDigest": DIGEST,
                "exactQueryReceiptAgeSeconds": 42,
                "generationMatch": True,
                "startupAttemptId": "attempt-current",
                "issues": [],
            }
        ),
    )
    monkeypatch.setattr(
        subject,
        "_consumer_lease_report",
        lambda *_args, **_kwargs: (
            calls.append("lease")
            or {"ready": False, "leases": [], "issues": ["missing"]}
        ),
    )
    monkeypatch.setattr(
        subject,
        "_device_trust_report",
        lambda *_args, **_kwargs: (
            calls.append("trust")
            or {"ready": False, "receipts": [], "issues": ["missing"]}
        ),
    )
    monkeypatch.setattr(
        subject,
        "_distribution_report",
        lambda _target: (
            calls.append("distribution")
            or {"status": "ready", "ready": True, "issues": []}
        ),
    )
    monkeypatch.setattr(
        subject,
        "_content_live_report",
        lambda **_kwargs: (
            calls.append("content-live")
            or {"passed": False, "matches": [], "issues": ["missing"]}
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "load_environment_topology",
        lambda: {"targets": {"gamma-local": {"env": "gamma"}}},
    )
    monkeypatch.setattr(
        stackctl,
        "get_target",
        lambda _topology, _target: {"env": "gamma"},
    )

    report = subject.read_only_user_availability_report("gamma-local")

    assert report["status"] == "failed"
    assert report["firstBlockerClass"] == "startup_identity"
    assert report["evidence"]["content"]["exactQueryReceiptAgeSeconds"] == 42
    assert report["evidence"]["distribution"]["ready"] is True
    assert calls == [
        "candidate",
        "test_live",
        "immutable_candidate",
        "provider",
        "content",
        "lease",
        "trust",
        "distribution",
        "content-live",
    ]


def test_old_or_mismatched_consumer_lease_cannot_promote_device(monkeypatch) -> None:
    monkeypatch.setattr(
        stackctl,
        "inspect_consumer_leases",
        lambda _target: [
            {
                "leaseId": DIGEST,
                "device": "emulator-5554",
                "platform": "android",
                "state": "active",
                "releaseId": "old-release",
                "manifestDigest": OTHER_DIGEST,
                "readinessReceiptDigest": OTHER_DIGEST,
            },
            {
                "leaseId": OTHER_DIGEST,
                "device": "sim-1",
                "platform": "ios-simulator",
                "state": "stale",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigest": DIGEST,
            },
        ],
    )

    report = subject._consumer_lease_report(
        "gamma-local",
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
    )

    assert report["ready"] is False
    assert all(lease["generationMatch"] is False for lease in report["leases"])
    assert "another release generation" in report["issues"][0]


def test_released_lease_of_the_same_generation_promotes_device(monkeypatch) -> None:
    """UAT 结束会交回 lease，交回后仍必须能证明本代际绑定。

    lease 交回与 device_bound 判定是两个先后发生的事实：若交回等于销毁证据，
    device_bound 永远只能在 App 仍在前台时成立，一次完整 UAT 跑完就自相矛盾。
    """
    monkeypatch.setattr(
        stackctl,
        "inspect_consumer_leases",
        lambda _target: [
            {
                "leaseId": DIGEST,
                "device": "sim-1",
                "platform": "ios-simulator",
                "state": "released",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigest": DIGEST,
            }
        ],
    )

    report = subject._consumer_lease_report(
        "gamma-local",
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
    )

    assert report["ready"] is True
    assert report["leases"][0]["generationMatch"] is True
    assert report["issues"] == []


def test_released_lease_from_another_generation_cannot_promote_device(
    monkeypatch,
) -> None:
    """接受 released 只放宽状态，不放宽代际：摘要必须仍由三个 digest 决定。"""
    monkeypatch.setattr(
        stackctl,
        "inspect_consumer_leases",
        lambda _target: [
            {
                "leaseId": DIGEST,
                "device": "sim-1",
                "platform": "ios-simulator",
                "state": "released",
                "releaseId": "release-1",
                "manifestDigest": OTHER_DIGEST,
                "readinessReceiptDigest": DIGEST,
            }
        ],
    )

    report = subject._consumer_lease_report(
        "gamma-local",
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
    )

    assert report["ready"] is False
    assert report["leases"][0]["generationMatch"] is False
    assert "another release generation" in report["issues"][0]


def test_old_content_live_receipt_cannot_promote_new_startup(
    monkeypatch, tmp_path
) -> None:
    report_path = tmp_path / "env/gamma/runs/old-uat/report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_ops.app_content_uat_receipt",
                "status": "passed",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigests": [DIGEST],
                "consumerLeaseIds": [OTHER_DIGEST],
                "releaseTrainId": TRAIN_DIGEST,
                "packageBaselines": {"gamma-local": DIGEST},
                "runtimeBindings": {
                    "gamma-local": {
                        "startupAttemptId": "attempt-old",
                        "candidateDigest": DIGEST,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        stackctl, "env_runs_root", lambda _env: tmp_path / "env/gamma/runs"
    )
    monkeypatch.setattr(stackctl, "repo_runs_root", lambda: tmp_path / "env/repo/runs")
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))

    report = subject._content_live_report(
        target_name="gamma-local",
        candidate={"baselineId": DIGEST, "releaseTrainId": TRAIN_DIGEST},
        startup={
            "attemptId": "attempt-new",
            "candidateDigest": DIGEST,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        },
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
        leases={
            "leases": [
                {
                    "leaseId": OTHER_DIGEST,
                    "generationMatch": True,
                }
            ]
        },
        observed_at=datetime.now(timezone.utc),
    )

    assert report["passed"] is False
    assert report["matches"][0]["generationMatch"] is False
    assert "runtime generation" in report["issues"][0]


def test_content_live_finds_the_aggregate_receipt_in_the_repo_runs_root(
    monkeypatch,
    tmp_path,
) -> None:
    """一次 UAT 可绑定多个 target，其聚合回执落在 repo 级 runs 根。

    只扫环境根时该层永远读不到回执，content_live 在结构上不可达；代际判据仍由
    回执内的 runtimeBindings 与 startupAttemptId 决定，不因扫描范围放宽而松动。
    """
    report_path = tmp_path / "env/repo/runs/current-uat/report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_ops.app_content_uat_receipt",
                "status": "passed",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigests": [DIGEST],
                "consumerLeaseIds": [OTHER_DIGEST],
                "releaseTrainId": TRAIN_DIGEST,
                "packageBaselines": {"gamma-local": DIGEST},
                "runtimeBindings": {
                    "gamma-local": {
                        "startupAttemptId": "attempt-new",
                        "candidateDigest": DIGEST,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        stackctl, "env_runs_root", lambda _env: tmp_path / "env/gamma/runs"
    )
    monkeypatch.setattr(stackctl, "repo_runs_root", lambda: tmp_path / "env/repo/runs")
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))

    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    report = subject._content_live_report(
        target_name="gamma-local",
        candidate={"baselineId": DIGEST, "releaseTrainId": TRAIN_DIGEST},
        startup={
            "attemptId": "attempt-new",
            "candidateDigest": DIGEST,
            "startedAt": started_at.isoformat(),
        },
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
        leases={"leases": [{"leaseId": OTHER_DIGEST, "generationMatch": True}]},
        observed_at=datetime.now(timezone.utc),
    )

    assert report["passed"] is True
    assert report["issues"] == []


def test_content_live_rejects_target_baseline_or_startup_candidate_drift(
    monkeypatch,
    tmp_path,
) -> None:
    report_path = tmp_path / "env/repo/runs/current-uat/report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_ops.app_content_uat_receipt",
                "status": "passed",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigests": [DIGEST],
                "consumerLeaseIds": [OTHER_DIGEST],
                "releaseTrainId": TRAIN_DIGEST,
                "packageBaselines": {"gamma-local": DIGEST},
                "runtimeBindings": {
                    "gamma-local": {
                        "startupAttemptId": "attempt-new",
                        "candidateDigest": DIGEST,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        stackctl, "env_runs_root", lambda _env: tmp_path / "env/gamma/runs"
    )
    monkeypatch.setattr(stackctl, "repo_runs_root", lambda: tmp_path / "env/repo/runs")
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))
    common = {
        "target_name": "gamma-local",
        "content": {
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
        "leases": {"leases": [{"leaseId": OTHER_DIGEST, "generationMatch": True}]},
        "observed_at": datetime.now(timezone.utc),
    }
    started_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    wrong_target_baseline = subject._content_live_report(
        candidate={"baselineId": OTHER_DIGEST, "releaseTrainId": TRAIN_DIGEST},
        startup={
            "attemptId": "attempt-new",
            "candidateDigest": OTHER_DIGEST,
            "startedAt": started_at,
        },
        **common,
    )
    stale_startup = subject._content_live_report(
        candidate={"baselineId": DIGEST, "releaseTrainId": TRAIN_DIGEST},
        startup={
            "attemptId": "attempt-new",
            "candidateDigest": OTHER_DIGEST,
            "startedAt": started_at,
        },
        **common,
    )

    assert wrong_target_baseline["passed"] is False
    assert stale_startup["passed"] is False
    assert all(
        report["matches"][0]["generationMatch"] is False
        for report in (wrong_target_baseline, stale_startup)
    )


def test_content_live_still_rejects_a_repo_receipt_from_another_generation(
    monkeypatch,
    tmp_path,
) -> None:
    """扫描范围放宽只解决「找不到」，代际不符仍必须判否。"""
    report_path = tmp_path / "env/repo/runs/other-uat/report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_ops.app_content_uat_receipt",
                "status": "passed",
                "releaseId": "release-1",
                "manifestDigest": DIGEST,
                "readinessReceiptDigests": [DIGEST],
                "consumerLeaseIds": [OTHER_DIGEST],
                "releaseTrainId": TRAIN_DIGEST,
                "packageBaselines": {"gamma-local": DIGEST},
                "runtimeBindings": {
                    "gamma-local": {
                        "startupAttemptId": "attempt-old",
                        "candidateDigest": DIGEST,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        stackctl, "env_runs_root", lambda _env: tmp_path / "env/gamma/runs"
    )
    monkeypatch.setattr(stackctl, "repo_runs_root", lambda: tmp_path / "env/repo/runs")
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))

    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    report = subject._content_live_report(
        target_name="gamma-local",
        candidate={"baselineId": DIGEST, "releaseTrainId": TRAIN_DIGEST},
        startup={
            "attemptId": "attempt-new",
            "candidateDigest": DIGEST,
            "startedAt": started_at.isoformat(),
        },
        content={
            "releaseId": "release-1",
            "manifestDigest": DIGEST,
            "readinessReceiptDigest": DIGEST,
        },
        leases={"leases": [{"leaseId": OTHER_DIGEST, "generationMatch": True}]},
        observed_at=datetime.now(timezone.utc),
    )

    assert report["passed"] is False
    assert report["matches"][0]["generationMatch"] is False


def test_inspect_aggregates_user_availability_and_fails_on_first_blocker(
    monkeypatch,
    tmp_path,
) -> None:
    report_dir = tmp_path / "inspect"
    monkeypatch.setattr(
        stackctl,
        "load_environment_topology",
        lambda: {"targets": {"gamma-local": {"env": "gamma"}}},
    )
    monkeypatch.setattr(
        stackctl,
        "get_target",
        lambda _topology, _target: {"env": "gamma"},
    )
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda *_args: report_dir)
    monkeypatch.setattr(stackctl, "_local_log_report", lambda _target: {"paths": []})
    monkeypatch.setattr(
        stackctl,
        "_read_only_user_availability_report",
        lambda _target: _blocked_report("startup_identity"),
    )

    result = stackctl.command_inspect(
        argparse.Namespace(
            target="gamma-local",
            scope="logs",
            output_format="json",
            report_dir=str(report_dir),
            ssh_host="",
            host_id="",
            deployment_instance="prod",
        )
    )

    assert result["exitCode"] == 1
    assert result["firstBlockerClass"] == "startup_identity"
    persisted = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert persisted["inspection"]["userAvailability"]["status"] == "failed"
