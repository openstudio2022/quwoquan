"""Exact-resource recovery for an orphaned local Compose project.

Docker 采样、端点所有权与 attestation 判据自成一条子主题，见
`test_orphan_compose_teardown__attestation_inventory__local_contract_test`；
candidate 客观不可用时的合法拆除见
`test_orphan_compose_teardown__undownable_candidate__local_contract_test`。
"""

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t3
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t4
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t5
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t6
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t7
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t8
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t9

from __future__ import annotations

import argparse
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.cli.lib import startup_attempt_receipt
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    CONTAINER_ID,
    NETWORK_ID,
    PROJECT,
    SECOND_CONTAINER_ID,
    SECOND_NETWORK_ID,
    install_stackctl_fakes,
    multi_sample,
    post_sample,
    repair_args,
    sample,
    write_completed_partial_consumption,
)
from quwoquan_ops.tests.support.startup_attempt_receipt_test_support import (
    _composition,
)


def _with_legacy_livekit_udp_endpoint(
    snapshot: dict[str, object],
) -> dict[str, object]:
    endpoint = {
        "role": "livekit-rtc-udp",
        "hostPort": 2019,
        "protocol": "udp",
    }
    snapshot["canonicalPorts"].append(
        {"name": "livekit-rtc-udp", "port": 17160, "open": True}
    )
    snapshot["publishedEndpoints"] = [
        endpoint,
        {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"},
    ]
    snapshot["containers"][0]["publishedEndpoints"] = [
        {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
    ]
    snapshot["containers"][1]["name"] = "quwoquan_alpha_release-livekit-sfu-1"
    snapshot["containers"][1]["service"] = "livekit-sfu"
    snapshot["containers"][1]["labels"][
        "com.docker.compose.service"
    ] = "livekit-sfu"
    snapshot["containers"][1]["publishedEndpoints"] = [endpoint]
    return snapshot



def test_repair_plans_without_mutation_then_consumes_only_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _with_legacy_livekit_udp_endpoint(multi_sample())
    post_snapshot = post_sample(snapshot)
    samples = iter((snapshot, snapshot, post_snapshot))
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: next(samples),
    )
    commands: list[list[str]] = []
    waited: list[object] = []
    monkeypatch.setattr(
        stackctl,
        "_wait_for_published_endpoints_released",
        lambda endpoints: waited.append(list(endpoints)) or [],
    )

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        commands.append(argv)
        return CompletedProcess(argv, 0, "removed", "")

    monkeypatch.setattr(stackctl, "run", run_command)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    planned = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0
    assert path.is_file()
    assert commands == []

    consumed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    assert consumed["exitCode"] == 0
    assert commands == [
        ["docker", "rm", "--force", CONTAINER_ID],
        ["docker", "rm", "--force", SECOND_CONTAINER_ID],
        ["docker", "network", "rm", NETWORK_ID],
        ["docker", "network", "rm", SECOND_NETWORK_ID],
    ]
    consumption = path.with_name("orphaned-compose-teardown-consumption.json")
    payload = json.loads(consumption.read_text(encoding="utf-8"))
    assert payload["preservedVolumeNames"] == [
        "quwoquan_alpha_release_mongo-data"
    ]
    assert payload["status"] == "passed"
    assert payload["removedContainerIds"] == [
        CONTAINER_ID,
        SECOND_CONTAINER_ID,
    ]
    assert payload["removedNetworkIds"] == [NETWORK_ID, SECOND_NETWORK_ID]
    assert waited == [
        [
            {"role": "livekit-rtc-udp", "hostPort": 2019, "protocol": "udp"},
            {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"},
        ]
    ]


def test_stale_mutable_receipt_plan_and_confirmation_seal_exact_resources_then_allow_receipt_reclaim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    project = "quwoquan_alpha_test_live"
    stale_receipt = {
        "schema": "stackctl.mutable_test_live_startup_attempt",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "environment": "alpha",
        "target": "alpha-local",
        "status": "running",
        "workload": "full",
        "composeProject": project,
        "attemptId": "test-live-observability-stale",
        "retiredGeneration": "pre-observability-log-sink-digest",
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: None)
    monkeypatch.setattr(
        stackctl,
        "load_test_live_startup_attempt",
        lambda _target: (_ for _ in ()).throw(
            ValueError("test-live startup receipt fields mismatch")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(stale_receipt),
    )
    discovery_calls: list[str] = []
    monkeypatch.setattr(
        contract,
        "discover_exact_project",
        lambda **kwargs: discovery_calls.append(str(kwargs["target"])) or project,
    )
    snapshot = multi_sample(project=project)
    samples = iter((snapshot, snapshot, post_sample(snapshot)))
    sampled_projects: list[str] = []

    def sample_snapshot(**kwargs: object) -> dict[str, object]:
        sampled_projects.append(str(kwargs["project"]))
        return next(samples)

    monkeypatch.setattr(contract, "sample_snapshot", sample_snapshot)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda argv: commands.append(list(argv))
        or CompletedProcess(argv, 0, "removed", ""),
    )
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    planned = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )

    assert planned["exitCode"] == 0
    assert discovery_calls == ["alpha-local"]
    assert commands == []
    plan = json.loads((report_dir / "repair_plan.json").read_text(encoding="utf-8"))
    assert plan["project"] == project
    assert plan["projectKind"] == "mutable_test_live"
    assert plan["containerIds"] == [CONTAINER_ID, SECOND_CONTAINER_ID]
    assert plan["networkIds"] == [NETWORK_ID, SECOND_NETWORK_ID]
    assert plan["preservedVolumeNames"] == [f"{project}_mongo-data"]
    attestation = contract.load_attestation(
        path,
        allowed_root=tmp_path,
        expected_target="alpha-local",
    )
    assert attestation["project"] == project
    assert "projectKind" not in attestation

    confirmed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert confirmed["exitCode"] == 0
    assert sampled_projects == [project, project, project]
    assert commands == [
        ["docker", "rm", "--force", CONTAINER_ID],
        ["docker", "rm", "--force", SECOND_CONTAINER_ID],
        ["docker", "network", "rm", NETWORK_ID],
        ["docker", "network", "rm", SECOND_NETWORK_ID],
    ]
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["preservedVolumeNames"] == [f"{project}_mongo-data"]

    monkeypatch.setattr(stackctl, "_mutable_test_live_container_ids", lambda _project: [])
    monkeypatch.setattr(
        stackctl,
        "_mutable_test_live_resource_names",
        lambda kind, *, compose_project: (
            [f"{project}_mongo-data"] if kind == "volume" else []
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_runtime_owned_port_occupancy_report",
        lambda _target, **_kwargs: {"publishedEndpoints": []},
    )
    monkeypatch.setattr(
        stackctl,
        "test_live_startup_attempt_path",
        lambda _target: tmp_path / "process/test_live_startup_attempt.json",
    )
    reclaimed: list[str] = []
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda target: reclaimed.append(target) or dict(stale_receipt),
    )
    stale_report_dir = tmp_path / "stale-receipt-report"
    stale_report_dir.mkdir()
    stale_result = stackctl._repair_stale_test_live_receipt(
        argparse.Namespace(
            target="alpha-local",
            fix="reclaim-stale-test-live-receipt",
            confirm_stale_test_live_receipt_reclaim=True,
        ),
        environment="alpha",
        report_dir=stale_report_dir,
    )

    assert stale_result["exitCode"] == 0
    assert reclaimed == ["alpha-local"]


def test_stale_mutable_receipt_project_mismatch_blocks_before_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    stale = {
        "schema": "stackctl.mutable_test_live_startup_attempt",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "environment": "alpha",
        "target": "alpha-local",
        "status": "running",
        "workload": "full",
        "composeProject": "quwoquan_beta_test_live",
        "attemptId": "test-live-foreign-project",
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: None)
    monkeypatch.setattr(
        stackctl,
        "load_test_live_startup_attempt",
        lambda _target: (_ for _ in ()).throw(
            ValueError("test-live startup receipt fields mismatch")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: stale,
    )
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda _argv: (_ for _ in ()).throw(
            AssertionError("foreign stale receipt must block before Docker")
        ),
    )

    result = stackctl._repair_orphaned_compose(
        repair_args(
            tmp_path / "orphaned-compose-teardown-attestation.json",
            confirm=False,
        ),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert "bounded replacement boundary" in result["details"][0]


def test_unreadable_unsafe_mutable_receipt_never_falls_back_to_untrusted_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: None)
    monkeypatch.setattr(
        stackctl,
        "load_test_live_startup_attempt",
        lambda _target: (_ for _ in ()).throw(
            stackctl.UnsafeTestLiveStartupReceiptPath("symlink receipt")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: (_ for _ in ()).throw(
            AssertionError("unsafe receipt must not be decoded through fallback")
        ),
    )

    result = stackctl._repair_orphaned_compose(
        repair_args(
            tmp_path / "orphaned-compose-teardown-attestation.json",
            confirm=False,
        ),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert "symlink receipt" in result["details"][0]


def test_receipt_and_attestation_project_conflict_blocks_before_docker_or_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    attested_project = "quwoquan_alpha_release_78142_3"
    receipt_project = "quwoquan_alpha_release_99103_1"
    attestation = contract.seal_attestation(sample(project=attested_project))
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    contract.write_attestation_create_once(
        path,
        attestation,
        allowed_root=tmp_path,
    )
    receipt_path = tmp_path / "process/startup_attempt.json"
    composition = _composition()
    monkeypatch.setattr(
        startup_attempt_receipt,
        "startup_attempt_path",
        lambda _target: receipt_path,
    )
    monkeypatch.setattr(startup_attempt_receipt, "output_root", lambda: tmp_path)
    startup_attempt_receipt.transition_startup_attempt(
        env="alpha",
        target="alpha-local",
        attempt_id="receipt-project-conflict",
        status="prepared",
        workload="content-release",
        compose_project=receipt_project,
        candidate_digest="sha256:" + "b" * 64,
        configuration_digest="sha256:" + "c" * 64,
        provider_runtime_digest="sha256:" + "d" * 64,
        observability_log_sink_digest="sha256:" + "e" * 64,
        image_transport_tag=composition["imageVersion"],
        image_composition=composition,
    )
    startup_attempt_receipt.transition_startup_attempt(
        env="alpha",
        target="alpha-local",
        attempt_id="receipt-project-conflict",
        status="stopped",
    )
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        startup_attempt_receipt.load_startup_attempt,
    )
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("project conflict must block before Docker sampling")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda _argv: (_ for _ in ()).throw(
            AssertionError("project conflict must block before Docker mutation")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("project conflict must block before receipt transition")
        ),
    )
    monkeypatch.setattr(
        contract,
        "write_consumption_create_once",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("project conflict must block before terminal fact")
        ),
    )
    result = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert "differs from the current startup receipt" in result["details"][0]
    assert not path.with_name("orphaned-compose-teardown-consumption.json").exists()


def test_absent_receipt_plan_discovers_once_then_confirmation_uses_attested_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: None)
    project = "quwoquan_alpha_release_78142_3"
    snapshot = multi_sample(project=project)
    samples = iter((snapshot, snapshot, post_sample(snapshot)))
    sampled_projects: list[str] = []

    def sample_snapshot(**kwargs: object) -> dict[str, object]:
        sampled_projects.append(str(kwargs["project"]))
        return next(samples)

    monkeypatch.setattr(contract, "sample_snapshot", sample_snapshot)
    discovery_calls = 0

    def discover_exact_project(**_kwargs: object) -> str:
        nonlocal discovery_calls
        discovery_calls += 1
        if discovery_calls != 1:
            raise AssertionError("confirmation must use the attested exact project")
        return project

    monkeypatch.setattr(contract, "discover_exact_project", discover_exact_project)
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda argv: CompletedProcess(argv, 0, "removed", ""),
    )
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    planned = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    consumed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert planned["exitCode"] == 0
    assert consumed["exitCode"] == 0
    assert discovery_calls == 1
    assert sampled_projects == [project, project, project]
    assert contract.load_attestation(
        path,
        allowed_root=tmp_path,
        expected_target="alpha-local",
        allow_expired=True,
    )["project"] == project


def test_partial_failure_is_consumed_with_exact_success_journal_and_cannot_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    samples = iter((snapshot, snapshot))
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: next(samples),
    )
    commands: list[list[str]] = []

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        commands.append(argv)
        if argv[-1] == SECOND_CONTAINER_ID:
            return CompletedProcess(argv, 1, "", "container removal failed")
        return CompletedProcess(argv, 0, "removed", "")

    monkeypatch.setattr(stackctl, "run", run_command)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    planned = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    assert failed["exitCode"] == 2
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["destructiveRepairPerformed"] is True
    assert report["destructiveRepairOutcome"] == "partial_failure"
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "partial_failure"
    assert consumption["removedContainerIds"] == [CONTAINER_ID]
    assert consumption["removedNetworkIds"] == []
    assert consumption["failedCommand"] == [
        "docker",
        "rm",
        "--force",
        SECOND_CONTAINER_ID,
    ]
    step = json.loads(
        path.with_name("orphaned-compose-teardown-step-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert step["resourceId"] == CONTAINER_ID
    assert path.with_name("orphaned-compose-teardown-journal.json").is_file()
    journal = json.loads(
        path.with_name("orphaned-compose-teardown-journal.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["resourceId"] for item in journal["steps"]] == [
        CONTAINER_ID,
        SECOND_CONTAINER_ID,
        NETWORK_ID,
        SECOND_NETWORK_ID,
    ]

    replay = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    assert replay["exitCode"] == 2
    assert "not eligible" in replay["details"][0]
    assert len(commands) == 2


def test_completed_partial_consumption_converges_audit_only_without_removal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: post_sample(snapshot),
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda argv: commands.append(argv),
    )

    result = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 0
    assert commands == []
    convergence = json.loads(
        path.with_name("orphaned-compose-teardown-convergence.json").read_text(
            encoding="utf-8"
        )
    )
    assert convergence["status"] == "passed"
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["auditOnly"] is True
    assert report["destructiveRepairPerformed"] is False
    assert report["startupAttempt"] == {
        "target": "alpha-local",
        "status": "stopped",
        "composeProject": PROJECT,
    }


@pytest.mark.parametrize("invalid_kind", ["failed-command", "incomplete-ids"])
def test_convergence_rejects_ineligible_partial_consumption_before_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(
        path,
        snapshot,
        removed_containers=(
            [CONTAINER_ID] if invalid_kind == "incomplete-ids" else None
        ),
        failed_command=(
            ["docker", "network", "rm", NETWORK_ID]
            if invalid_kind == "failed-command"
            else None
        ),
    )
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("ineligible convergence must not inspect Docker")
        ),
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))

    result = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert "not eligible" in result["details"][0]
    assert commands == []
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()


@pytest.mark.parametrize("post_drift", ["resource", "volume"])
def test_convergence_rejects_reappeared_resource_or_volume_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    post_drift: str,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    post = post_sample(snapshot)
    if post_drift == "resource":
        post["containers"] = [snapshot["containers"][0]]
    else:
        post["volumes"] = []
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: post)
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))

    result = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert commands == []
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()


def test_convergence_rejects_noncanonical_port_still_occupied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _with_legacy_livekit_udp_endpoint(multi_sample())
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    consumption_path = path.with_name("orphaned-compose-teardown-consumption.json")
    consumption_bytes = consumption_path.read_bytes()
    monkeypatch.setattr(
        stackctl,
        "_wait_for_published_endpoints_released",
        lambda endpoints: [
            endpoint for endpoint in endpoints if endpoint["hostPort"] == 2019
        ],
    )
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("occupied endpoint must block receipt transition")
        ),
    )
    monkeypatch.setattr(
        contract,
        "write_convergence_create_once",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("occupied endpoint must block convergence fact")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_publish_orphan_terminal_success",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("occupied endpoint must block terminal success")
        ),
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))

    result = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert "2019" in result["details"][0]
    assert commands == []
    assert consumption_path.read_bytes() == consumption_bytes
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()


@pytest.mark.parametrize(
    ("leases", "startup", "message"),
    [
        ([{"device": "emulator-5554", "consumer": "flutter-run"}], None, "zero active"),
        ([], {"status": "running"}, "candidate-bound normal down"),
        ([], {"status": "prepared"}, "candidate-bound normal down"),
    ],
)
def test_repair_blocks_active_lease_or_nonstopped_receipt_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    leases: list[dict[str, str]],
    startup: dict[str, str] | None,
    message: str,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: leases)
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: startup)
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("blocked recovery must not inspect or mutate Docker")
        ),
    )

    result = stackctl._repair_orphaned_compose(
        repair_args(
            tmp_path / "orphaned-compose-teardown-attestation.json",
            confirm=False,
        ),
        environment="alpha",
        report_dir=report_dir,
    )

    assert result["exitCode"] == 2
    assert message in result["details"][0]


def test_repair_parser_requires_explicit_attestation_and_confirmation_surface() -> None:
    args = stackctl.build_parser().parse_args(
        [
            "repair",
            "--target",
            "gamma-local",
            "--fix",
            "reclaim-orphaned-compose",
            "--orphaned-compose-attestation",
            "/tmp/orphaned-compose-teardown-attestation.json",
            "--confirm-orphaned-compose-teardown",
        ]
    )

    assert args.fix == "reclaim-orphaned-compose"
    assert args.confirm_orphaned_compose_teardown is True
