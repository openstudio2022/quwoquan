"""stackctl 只读用户可用性聚合的代际与低基数负例。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import json
import subprocess
from types import SimpleNamespace

import pytest
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
                "status": "complete",
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
                "status": "complete",
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
                "status": "complete",
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
                "status": "complete",
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


@pytest.fixture
def hosted_runtime(monkeypatch):
    """只模拟 SSH 边界；身份匹配与分层判定执行真实实现。"""
    from quwoquan_ops.cli.commands import hosted_read_only as hosted
    from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.constants import PROD_CADDY_IMAGE

    access = stackctl.load_prod_hosted_access_manifest()
    plan = stackctl.resolve_prod_hosted_plan(access, instance="prevalidate")
    runtime_by_plane = {}
    material_by_plane = {}
    images = {}
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.prod_hosted_rehearsal import compose_service_image_owner
    for placement in plan:
        required = access["prevalidation"]["planes"][placement.plane]["startupServices"]
        containers, inspected, configs = [], [], {}
        for service in required:
            images[compose_service_image_owner(service)] = {"imageDigest": DIGEST}
            containers.append({"id": service, "composeService": service, "imageId": DIGEST, "running": True, "health": "healthy"})
            inspected.append({
                "Id": service, "Image": DIGEST,
                "Config": {
                    "Env": ["APP_ENV=prod", f"IMAGE_VERSION={DIGEST.removeprefix('sha256:')}", f"CONFIG_VERSION={OTHER_DIGEST}", "QWQ_NONPROMOTABLE_PREVALIDATION=first-party", "SECRET_TOKEN=do-not-expose"],
                    "Labels": {"com.docker.compose.project": placement.project, "com.docker.compose.service": service},
                },
                "Mounts": [
                    {"Destination": "/etc/qwq-config", "Source": placement.remote_root + "/runtime/config-root", "RW": False},
                    {"Destination": "/etc/quwoquan/artifact-identity.json", "Source": placement.remote_root + "/runtime/artifact-identity.json", "RW": False},
                ],
            })
            configs[service] = {"version": OTHER_DIGEST, "digest": TRAIN_DIGEST, "expectedDigest": TRAIN_DIGEST}
        for service in placement.support_services:
            containers.append({"id": service, "composeService": service, "image": PROD_CADDY_IMAGE, "imageId": DIGEST, "running": True, "health": "healthy"})
            inspected.append({
                "Id": service, "Image": DIGEST,
                "Config": {"Image": PROD_CADDY_IMAGE, "Labels": {
                    "com.docker.compose.project": placement.project,
                    "com.docker.compose.service": service,
                }},
            })
        runtime_by_plane[placement.plane] = {
            "instance": placement.instance, "plane": placement.plane,
            "hostId": placement.host_id, "host": placement.ssh_host,
            "replicaId": placement.replica_id, "project": placement.project,
            "account": placement.account, "composeRoot": placement.remote_root,
            "composeFileExists": True, "envFileExists": True,
            "unit": {"name": placement.systemd_unit, "enabled": True, "active": True},
            "containers": containers, "inspect": inspected,
        }
        material_by_plane[placement.plane] = {
            "candidateDigest": DIGEST, "instance": "prevalidate", "plane": placement.plane,
            "dataMode": "external", "configs": configs,
            "artifactIdentity": {"schema": "qwq.environment-artifact-identity", "environment": "prod", "configDigest": DIGEST},
        }
    monkeypatch.setattr(hosted, "_hosted_candidate", lambda *_: ({"baselineId": DIGEST}, {"materialSource": "local-build", "legalStaticPlaceholder": True, "images": images}))
    material_reader = hosted._hosted_material_readback
    monkeypatch.setattr(hosted, "_hosted_material_readback", lambda placement: material_by_plane[placement.plane])
    calls = []
    def runtime(plane, **kwargs):
        calls.append((plane, kwargs))
        return runtime_by_plane[plane]
    monkeypatch.setattr(stackctl, "_prod_plane_runtime_report", runtime)
    return SimpleNamespace(runtime=runtime_by_plane, material=material_by_plane, calls=calls, plan=plan, material_reader=material_reader, access=access)


def _hosted_report():
    return subject.read_only_user_availability_report(
        "prod-hosted", deployment_instance="prevalidate", candidate_digest=DIGEST,
    )


def test_hosted_never_consumes_local_receipts_and_keeps_axes_separate(monkeypatch, hosted_runtime):
    # spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t2
    def forbidden(*args, **kwargs):
        pytest.fail("hosted must not consume any local receipt")
    for name in ("load_test_live_startup_attempt", "read_startup_attempt", "active_deployment_candidate_snapshot", "load_test_live_content_binding", "inspect_consumer_leases"):
        monkeypatch.setattr(stackctl, name, forbidden)
    report = _hosted_report()
    Draft202012Validator(json.loads(Path("quwoquan_ops/environments/read_only_user_availability_report.schema.json").read_text())).validate(report)
    evidence = report["evidence"]
    assert evidence["runtime"]["selectedMode"] == "hosted"
    assert evidence["containerRuntime"]["status"] == "ready"
    assert evidence["firstPartyReadiness"]["status"] == "ready"
    assert evidence["providerReadiness"]["status"] == "unavailable"
    assert evidence["contentUAT"]["status"] == "unavailable"
    assert evidence["releaseEligibility"]["status"] == "GATE_BLOCK"
    assert evidence["rehearsal"]["validated"] is True
    assert report["status"] == "failed"
    assert "SECRET_TOKEN" not in json.dumps(report)
    assert "startupReceipt" not in evidence["runtime"]
    assert all(kwargs["instance"] == "prevalidate" and kwargs["host_id"] and kwargs["host"] for _, kwargs in hosted_runtime.calls)


@pytest.mark.parametrize("drift", ["host", "instance", "image", "config", "mount", "material", "label", "missing-container"])
def test_hosted_identity_drift_never_validates_rehearsal(hosted_runtime, drift):
    # spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t1
    runtime = hosted_runtime.runtime["service"]
    if drift in {"host", "instance"}:
        runtime[drift] = "other"
    elif drift == "image":
        runtime["containers"][0]["imageId"] = OTHER_DIGEST
    elif drift == "config":
        hosted_runtime.material["service"]["configs"][runtime["containers"][0]["composeService"]]["digest"] = DIGEST
    elif drift == "mount":
        runtime["inspect"][0]["Mounts"][0]["RW"] = True
    elif drift == "material":
        hosted_runtime.material["service"]["artifactIdentity"]["configDigest"] = OTHER_DIGEST
    elif drift == "label":
        runtime["inspect"][0]["Config"]["Labels"]["com.docker.compose.project"] = "local-project"
    else:
        runtime["containers"] = []
    evidence = _hosted_report()["evidence"]
    assert evidence["runtime"]["identity"]["status"] == "blocked"
    assert evidence["rehearsal"]["validated"] is False
    assert evidence["containerRuntime"]["status"] == "blocked"


def test_unknown_hosted_instance_is_blocked_before_ssh(hosted_runtime):
    report = subject.read_only_user_availability_report("prod-hosted", deployment_instance="unknown", candidate_digest=DIGEST)
    assert report["status"] == "failed"
    assert "unsupported deployment instance" in report["firstBlocker"]
    assert hosted_runtime.calls == []


def test_provider_unhealthy_does_not_claim_container_exit(hosted_runtime):
    product_ops = next(item for item in hosted_runtime.runtime["service"]["containers"] if item["composeService"] == "product-ops-service")
    product_ops["health"] = "unhealthy"
    evidence = _hosted_report()["evidence"]
    assert evidence["containerRuntime"]["status"] == "ready"
    assert evidence["firstPartyReadiness"]["status"] == "ready"
    assert evidence["providerReadiness"]["status"] == "unavailable"
    product_ops["running"] = False
    assert _hosted_report()["evidence"]["containerRuntime"]["status"] == "blocked"


@pytest.mark.parametrize("instance,legal_issue,drift,expected_exit", [
    ("prevalidate", "owner.name contains placeholder text", False, 0),
    ("prod", "owner.name contains placeholder text", False, 1),
    ("prevalidate", "owner.name contains placeholder text", True, 1),
    ("prevalidate", "source checksum mismatch", False, 1),
])
def test_doctor_legal_exception_requires_exact_rehearsal(monkeypatch, tmp_path, hosted_runtime, instance, legal_issue, drift, expected_exit):
    # spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t3
    if drift:
        hosted_runtime.runtime["service"]["hostId"] = "other-host"
    availability = _hosted_report()
    diagnostics = availability["evidence"]
    diagnostics["httpProbes"] = {"status": "failed", "endpointBinding": "public-target-only"}
    captured = []
    monkeypatch.setattr(stackctl, "command_health", lambda args: captured.append(args) or {"exitCode": 1, "runtimeDiagnostics": diagnostics, "details": ["public target HTTP probe failed"]})
    monkeypatch.setattr(stackctl, "_legal_static_command", lambda *args, **kwargs: (subprocess.CompletedProcess([], 1), {"issues": [legal_issue]}))
    monkeypatch.setattr(stackctl, "local_runtime_capacity_evidence", lambda target: {"issues": [], "warnings": [], "evidence": {}, "reclaimCommands": []})
    monkeypatch.setattr(stackctl, "_load_release_state", lambda *_: {})
    result = stackctl.command_doctor(argparse.Namespace(target="prod-hosted", deployment_instance=instance, candidate_digest=DIGEST, ssh_host="", host_id="", report_dir=str(tmp_path)))
    assert result["exitCode"] == expected_exit
    assert captured[0].candidate_digest == DIGEST
    assert captured[0].deployment_instance == instance
    assert captured[0].read_only is True
    assert result["releaseEligibility"]["status"] == "GATE_BLOCK"
    if expected_exit == 0:
        assert result["nonPromotable"] is True
        assert result["releaseEligibility"]["legalStatic"]["status"] == "GATE_BLOCK"


def test_hosted_candidate_requires_explicit_digest_and_rejects_formal_local_build(monkeypatch, tmp_path):
    from quwoquan_ops.cli.commands import hosted_read_only as hosted
    with pytest.raises(ValueError, match="explicit exact"):
        hosted._hosted_candidate("", "prevalidate")
    oci_path = tmp_path / "packages/runtime-shared/oci-images.json"
    oci_path.parent.mkdir(parents=True)
    oci_path.write_text(json.dumps({"materialSource": "local-build"}))
    monkeypatch.setattr(stackctl, "load_candidate_manifest", lambda *args, **kwargs: {"baselineId": DIGEST})
    monkeypatch.setattr(stackctl, "deployment_candidate_dir", lambda *args: tmp_path)
    with pytest.raises(ValueError, match="requires deployment instance prevalidate"):
        hosted._hosted_candidate(DIGEST, "prod")
    with pytest.raises(ValueError, match="fields mismatch"):
        hosted._hosted_candidate(DIGEST, "prevalidate")


@pytest.mark.parametrize("service", ["product-ops-service", "content-service", "gamma-proxy"])
@pytest.mark.parametrize("state", [
    {"health": "not-configured"}, {"health": ""}, {"health": None}, {"health": "unknown"},
    {"running": False}, {"running": 1}, {"oomKilled": True}, {"error": "container start failed"},
])
def test_hosted_provider_exception_never_hides_missing_health_or_process_failure(hosted_runtime, service, state):
    # spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t2
    container = next(item for item in hosted_runtime.runtime["service"]["containers"] if item["composeService"] == service)
    container.update(state)
    evidence = _hosted_report()["evidence"]
    assert evidence["firstPartyReadiness"]["status"] == "blocked"
    if any(field in state for field in ("running", "oomKilled", "error")):
        assert evidence["containerRuntime"]["status"] == "blocked"


def _add_isolated_support(hosted_runtime):
    placement = next(item for item in hosted_runtime.plan if item.plane == "service")
    isolated = hosted_runtime.access["prevalidation"]["isolatedData"]
    runtime = hosted_runtime.runtime["service"]
    hosted_runtime.material["service"]["dataMode"] = "isolated"
    for service in isolated["services"]:
        initializer = service in {"mongo-init", "object-storage-init"}
        runtime["containers"].append({
            "id": service, "composeService": service, "image": isolated["images"][service],
            "imageId": DIGEST, "status": "exited" if initializer else "running",
            "running": not initializer, "exitCode": 0, "oomKilled": False, "error": "",
            "health": "not-configured" if initializer else "healthy",
        })
        runtime["inspect"].append({
            "Id": service, "Image": DIGEST,
            "Config": {"Image": isolated["images"][service], "Labels": {
                "com.docker.compose.project": placement.project,
                "com.docker.compose.service": service,
            }},
        })
    return runtime


@pytest.mark.parametrize("service", ["mongo-init", "object-storage-init"])
@pytest.mark.parametrize("state", [
    {"running": True}, {"running": 0}, {"exitCode": False}, {"exitCode": "0"},
    {"exitCode": 0.0}, {"exitCode": None}, {"exitCode": 1}, {"oomKilled": True},
    {"error": "initialization failed"}, {"status": "running", "running": True, "health": "healthy"},
    {"status": "dead"},
])
def test_hosted_initializer_requires_exact_successful_exit(hosted_runtime, service, state):
    runtime = _add_isolated_support(hosted_runtime)
    container = next(item for item in runtime["containers"] if item["composeService"] == service)
    container.update(state)
    evidence = _hosted_report()["evidence"]
    assert evidence["containerRuntime"]["status"] == "blocked"
    observed = next(item for replica in evidence["runtime"]["replicas"] for item in replica["containers"] if item["service"] == service)
    assert observed["completedTask"] is False


def test_hosted_successful_initializers_do_not_need_daemon_health(hosted_runtime):
    _add_isolated_support(hosted_runtime)
    evidence = _hosted_report()["evidence"]
    assert evidence["containerRuntime"]["status"] == "ready"
    assert evidence["firstPartyReadiness"]["status"] == "ready"
    for replica in evidence["runtime"]["replicas"]:
        for item in replica["containers"]:
            if item["service"] in {"mongo-init", "object-storage-init"}:
                assert item["completedTask"] is True


@pytest.mark.parametrize("service", ["gamma-proxy", "redis"])
def test_unknown_one_shot_label_cannot_bypass_support_liveness(hosted_runtime, service):
    runtime = _add_isolated_support(hosted_runtime)
    item = next(item for item in runtime["containers"] if item["composeService"] == service)
    item.update({"status": "exited", "running": False, "exitCode": 0, "health": "not-configured"})
    raw = next(item for item in runtime["inspect"] if item["Id"] == service)
    raw["Config"]["Labels"]["com.quwoquan.runtime.one-shot"] = "true"
    evidence = _hosted_report()["evidence"]
    assert evidence["containerRuntime"]["status"] == "blocked"


@pytest.mark.parametrize("service", ["gamma-proxy", "redis", "mongo-init"])
@pytest.mark.parametrize("drift", ["project", "service", "pinned-reference", "raw-reference", "image-id", "missing-image-id"])
def test_hosted_support_identity_requires_labels_and_pinned_images(hosted_runtime, service, drift):
    runtime = _add_isolated_support(hosted_runtime)
    item = next(item for item in runtime["containers"] if item["composeService"] == service)
    raw = next(item for item in runtime["inspect"] if item["Id"] == service)
    if drift in {"project", "service"}:
        raw["Config"]["Labels"]["com.docker.compose." + drift] = "foreign"
    elif drift == "pinned-reference":
        item["image"] = "foreign.invalid/image@" + OTHER_DIGEST
    elif drift == "raw-reference":
        raw["Config"]["Image"] = "foreign.invalid/image:latest"
    elif drift == "image-id":
        raw["Image"] = OTHER_DIGEST
    else:
        item.pop("imageId")
    evidence = _hosted_report()["evidence"]
    assert evidence["runtime"]["identity"]["status"] == "blocked"
    assert evidence["rehearsal"]["validated"] is False


@pytest.mark.parametrize("service", ["product-ops-service", "gamma-proxy", "mongo-init"])
@pytest.mark.parametrize("state", [
    {"running": True, "health": "healthy"},
    {"running": True, "health": "starting"},
    {"running": True, "health": "not-configured"},
    {"running": True, "health": "healthy", "oomKilled": True},
    {"running": True, "health": "healthy", "error": "failed"},
    {"running": False, "status": "exited", "exitCode": 0},
    {"running": False, "status": "exited", "exitCode": False},
    {"running": True, "status": "exited", "exitCode": 0},
])
def test_hosted_container_acceptance_matches_executor(service, state):
    from quwoquan_ops.cli.commands import hosted_read_only as hosted
    from quwoquan_ops.cli.prod.prevalidate_prod_hosted import PlaneProjection, _runtime_blockers

    # 不运行 executor：只对比它的纯判定函数，避免未来两处规则再次分叉。
    container_issue, health_issue, _ = hosted._hosted_container_state(
        state, service=service, provider_bound={"product-ops-service"},
    )
    blockers = _runtime_blockers(
        {"containers": [{"composeService": service, "imageId": DIGEST, **state}], "unit": {"enabled": True, "active": True}},
        PlaneProjection("edge", "unused", "unused", (service,), (), ()),
        {"readinessPolicy": {"providerBoundServices": ["product-ops-service"]}},
        {"remoteImageContentDigests": {service: DIGEST}, "contentDigestVerified": True},
        data_mode="external",
    )
    assert bool(container_issue or health_issue) == bool(blockers)


@pytest.mark.parametrize("image_ref", ["", "docker.io/library/redis:latest"])
def test_hosted_rejects_missing_or_unpinned_support_source(monkeypatch, hosted_runtime, image_ref):
    _add_isolated_support(hosted_runtime)
    hosted_runtime.access["prevalidation"]["isolatedData"]["images"]["redis"] = image_ref
    monkeypatch.setattr(stackctl, "load_prod_hosted_access_manifest", lambda: hosted_runtime.access)
    monkeypatch.setattr(stackctl, "resolve_prod_hosted_plan", lambda *args, **kwargs: hosted_runtime.plan)
    evidence = _hosted_report()["evidence"]
    assert evidence["runtime"]["identity"]["status"] == "blocked"
    assert any("redis: support pinned image reference missing" in issue for issue in evidence["runtime"]["identity"]["issues"])


def test_support_reference_is_not_candidate_content_digest_proof(monkeypatch, hosted_runtime):
    from quwoquan_ops.cli.commands import hosted_read_only as hosted

    _add_isolated_support(hosted_runtime)
    evidence = _hosted_report()["evidence"]
    assert evidence["runtime"]["identity"]["status"] == "ready"
    support = [item for replica in evidence["runtime"]["replicas"] for item in replica["containers"] if "pinnedReferenceVerified" in item]
    assert support and all(item["pinnedReferenceVerified"] is True for item in support)
    assert all(item["candidateContentDigestVerified"] is False for item in support)
    assert all(item["candidateContentDigestReason"] for item in support)
    def unavailable(*args):
        raise ValueError("candidate unavailable")
    monkeypatch.setattr(hosted, "_hosted_candidate", unavailable)
    unavailable_evidence = _hosted_report()["evidence"]
    assert unavailable_evidence["runtime"]["identity"]["status"] == "blocked"
    assert unavailable_evidence["rehearsal"]["validated"] is False


def test_duplicate_support_service_is_not_a_unique_runtime_identity(hosted_runtime):
    runtime = _add_isolated_support(hosted_runtime)
    container = next(item for item in runtime["containers"] if item["composeService"] == "redis")
    runtime["containers"].append(dict(container))
    evidence = _hosted_report()["evidence"]
    assert evidence["runtime"]["identity"]["status"] == "blocked"
    assert any("CONTAINER_DUPLICATE" in issue for issue in evidence["runtime"]["identity"]["issues"])


def test_hosted_material_reader_hashes_real_config_bytes_without_exporting_secrets(monkeypatch, tmp_path, hosted_runtime):
    import hashlib
    import shlex
    import sys
    from quwoquan_ops.cli.commands import hosted_read_only as hosted
    from quwoquan_ops.cli.prod import inspect_prod_plane_runtime as inspector

    root = tmp_path / "remote"
    config = root / "runtime/config-root/content-service.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("secret: must-not-be-exported\n")
    config_digest = "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
    (root / "runtime/artifact-identity.json").write_text(json.dumps({"configDigest": DIGEST}))
    (root / "provenance.json").write_text(json.dumps({"candidateDigest": DIGEST, "instance": "prevalidate", "plane": "service", "configSources": {"content-service": {"configurationDigest": OTHER_DIGEST, "effectiveConfigDigest": config_digest}}}))
    monkeypatch.setattr(inspector, "_resolve_key_source", lambda *args: ([], "test-key"))
    def run(argv, **kwargs):
        assert argv[0] == "ssh"
        assert "StrictHostKeyChecking=yes" in argv
        assert kwargs["timeout_seconds"] == 30
        remote = shlex.split(argv[-1])
        assert remote[:2] == ["python3", "-c"]
        return subprocess.run([sys.executable, "-c", remote[2], str(root)], capture_output=True, text=True, check=False)
    monkeypatch.setattr(stackctl, "run", run)
    # fixture 仅替代了 SSH material 边界；此用例恢复真实读取函数执行远端脚本。
    reader = hosted_runtime.material_reader
    result = reader(hosted_runtime.plan[0])
    assert result["configs"]["content-service"]["digest"] == config_digest
    assert "must-not-be-exported" not in json.dumps(result)
    config.write_text("secret: drifted\n")
    drifted = reader(hosted_runtime.plan[0])
    assert drifted["configs"]["content-service"]["digest"] != config_digest
