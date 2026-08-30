"""candidate 客观不可用时的合法拆除：判据与 receipt 退休。

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t10
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t11
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t12

normal down 强绑 candidate 重放拓扑，candidate 不可寻址时那条路永不收敛。
本文件锁定「什么才算客观不可能」以及拆除后回执必须退休这两件事，把它与
精确资源采样、repair 执行收敛分开承载。
"""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    PROJECT,
    install_stackctl_fakes,
    multi_sample,
    post_sample,
    repair_args,
    write_completed_partial_consumption,
)


def _sealed_workload_projection(
    tmp_path: Path,
    services: dict[str, dict[str, object]],
) -> Path:
    path = tmp_path / "projected.compose.yaml"
    path.write_text(
        json.dumps({"services": services}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("services", "expect_named"),
    [
        ({"rtc-service": {"networks": ["edge"]}}, True),
        (
            {"rtc-service": {"networks": ["edge"], "profiles": ["edge-media"]}},
            False,
        ),
        ({"rtc-service": {"image": "sha256:" + "f" * 64}}, False),
    ],
)
def test_normal_down_impossibility_is_named_only_for_ungated_imageless_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    services: dict[str, dict[str, object]],
    expect_named: bool,
) -> None:
    """只有「无 image、无 build、又无 profile 门控」才让 normal down 不可能。

    带 profile 的条目会被 Compose 在该 profile 未激活时整体排除,自带 image 的
    条目本就有效;这两种都必须继续走 candidate-bound normal down,不能借这条
    出口绕过它。
    """

    projection = _sealed_workload_projection(tmp_path, services)
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: tmp_path,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: {"composeFiles": [projection]},
    )

    reason = stackctl._normal_down_structurally_impossible(
        "alpha-local",
        {
            "status": "partial",
            "workload": "content-release",
            "candidateDigest": "sha256:" + "a" * 64,
        },
    )

    assert bool(reason) is expect_named
    if expect_named:
        assert "rtc-service" in reason


def test_missing_candidate_is_a_named_reason_not_an_empty_string(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """candidate 被回收后 normal down 已不可能，判定不得把这个失败塌陷成空值。

    回收 candidate store 之后回执引用的目录就不在了。此时报 "" 等于宣告
    「继续走 normal down」，而那条路永远不会收敛，环境被冻结的证据锁死。
    """

    absent = tmp_path / "candidates" / "runtime-full" / ("sha256-" + "a" * 64)
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: absent,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("an absent candidate must not be loaded as a topology")
        ),
    )

    reason = stackctl._normal_down_structurally_impossible(
        "gamma-local",
        {
            "status": "running",
            "workload": "full",
            "candidateDigest": "sha256:" + "a" * 64,
        },
    )

    assert "no longer present" in reason
    assert str(absent) in reason


def test_unreadable_candidate_topology_is_named_rather_than_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """candidate 在场但拓扑读不出来，同样让 normal down 不可能，必须说出原因。"""

    from quwoquan_ops.cli.lib.runtime_topology_package import (
        RuntimeTopologyPackageError,
    )

    present = tmp_path / "candidate"
    present.mkdir()
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: present,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeTopologyPackageError("workload projection is missing")
        ),
    )

    reason = stackctl._normal_down_structurally_impossible(
        "gamma-local",
        {
            "status": "running",
            "workload": "full",
            "candidateDigest": "sha256:" + "b" * 64,
        },
    )

    assert "cannot project workload=full" in reason
    assert "workload projection is missing" in reason


def test_running_receipt_is_admitted_only_when_its_candidate_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行中回执的准入判据是 candidate 的客观状态，不是操作者的声明。"""

    running = {"target": "gamma-local", "status": "running"}
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: [])
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)

    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa is no longer present",
    )
    assert stackctl._orphan_compose_runtime_gate("gamma-local") == running

    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "",
    )
    with pytest.raises(contract.OrphanComposeTeardownError) as blocked:
        stackctl._orphan_compose_runtime_gate("gamma-local")
    assert "candidate-bound normal down" in str(blocked.value)


def test_teardown_of_an_unusable_candidate_retires_the_running_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """拆掉残留后回执必须转 stopped，否则下一次 up 仍被失效凭据挡住。"""

    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    exact_project = "quwoquan_alpha_release_78142_3"
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "running",
        "attemptId": "attempt-frozen",
        "composeProject": exact_project,
        "candidateDigest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    transitions: list[dict[str, object]] = []
    stopped = {
        **running,
        "status": "stopped",
        "failure": (
            "reclaimed by governed orphan Compose teardown; candidate-bound "
            "down was structurally impossible for this receipt"
        ),
    }

    def transition(**kwargs: object) -> dict[str, object]:
        transitions.append(kwargs)
        return stopped

    monkeypatch.setattr(stackctl, "transition_startup_attempt", transition)
    snapshot = multi_sample(project=exact_project)
    post_snapshot = post_sample(snapshot)
    samples = iter((snapshot, snapshot, post_snapshot))
    sampled_projects: list[str] = []

    def sample_exact_project(**kwargs: object) -> dict[str, object]:
        sampled_projects.append(str(kwargs.get("project") or ""))
        return next(samples)

    monkeypatch.setattr(contract, "sample_snapshot", sample_exact_project)
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
    assert planned["exitCode"] == 0
    assert transitions == []

    consumed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert consumed["exitCode"] == 0
    assert sampled_projects == [exact_project, exact_project, exact_project]
    attestation = contract.load_attestation(
        path,
        allowed_root=tmp_path,
        expected_target="alpha-local",
        allow_expired=True,
    )
    assert attestation["project"] == exact_project
    assert transitions == [
        {
            "env": "alpha",
            "target": "alpha-local",
            "attempt_id": "attempt-frozen",
            "status": "stopped",
            "failure": (
                "reclaimed by governed orphan Compose teardown; candidate-bound "
                "down was structurally impossible for this receipt"
            ),
        }
    ]
    payload = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["preservedVolumeNames"] == [f"{exact_project}_mongo-data"]
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["startupAttempt"] == stopped


def test_empty_undownable_project_is_attested_then_retires_receipt_without_removal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "partial",
        "attemptId": "attempt-empty",
        "composeProject": "quwoquan_alpha_release",
        "candidateDigest": "sha256:" + "a" * 64,
    }
    stopped = {**running, "status": "stopped"}
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **_kwargs: stopped,
    )
    empty_snapshot = post_sample(multi_sample())
    samples: list[bool] = []

    def sample_empty(**kwargs: object) -> dict[str, object]:
        samples.append(bool(kwargs.get("require_removable", True)))
        return empty_snapshot

    monkeypatch.setattr(contract, "sample_snapshot", sample_empty)
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    args = repair_args(path, confirm=False)

    planned = stackctl._repair_orphaned_compose(
        args,
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0

    args.confirm_orphaned_compose_teardown = True
    consumed = stackctl._repair_orphaned_compose(
        args,
        environment="alpha",
        report_dir=report_dir,
    )

    assert consumed["exitCode"] == 0
    assert samples == [False, False, False]
    assert commands == []
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["startupAttempt"] == stopped
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "passed"
    assert consumption["removedContainerIds"] == []
    assert consumption["removedNetworkIds"] == []
    assert consumption["preservedVolumeNames"] == [
        "quwoquan_alpha_release_mongo-data"
    ]


def test_receipt_transition_failure_does_not_publish_passed_consumption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "running",
        "attemptId": "attempt-frozen",
        "composeProject": "quwoquan_alpha_release",
        "candidateDigest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("startup receipt transition failed")
        ),
    )
    snapshot = multi_sample()
    samples = iter((snapshot, snapshot, post_sample(snapshot)))
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: next(samples))
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
    assert planned["exitCode"] == 0

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert failed["exitCode"] == 2
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "partial_failure"
    # 销毁已证完整、只有 startup receipt 迁移失败：removalOutcome 必须保留
    # complete_terminal_fact_pending，不得把假的 partial_failure 刻进 create-once 回执。
    assert consumption["removalOutcome"] == "complete_terminal_fact_pending"
    assert consumption["removedContainerIds"]
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "gate_block"


def test_audit_convergence_transition_failure_does_not_publish_passed_fact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "partial",
        "attemptId": "attempt-frozen",
        "composeProject": "quwoquan_alpha_release",
        "candidateDigest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("startup receipt transition failed")
        ),
    )
    snapshot = multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: post_sample(snapshot),
    )

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert failed["exitCode"] == 2
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "partial_failure"
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "gate_block"


def test_step_receipt_write_failure_retries_from_post_state_without_replaying_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    samples = iter(
        (
            snapshot,
            snapshot,
            post_sample(snapshot),
            post_sample(snapshot),
        )
    )
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: next(samples))
    docker_commands: list[list[str]] = []

    def remove(argv: list[str]) -> CompletedProcess[str]:
        docker_commands.append(argv)
        return CompletedProcess(argv, 0, "removed", "")

    monkeypatch.setattr(stackctl, "run", remove)
    real_writer = contract.write_step_receipt_create_once
    first_step_attempts = 0

    def fail_first_step_twice(*args: object, **kwargs: object) -> Path:
        nonlocal first_step_attempts
        if kwargs.get("index") == 1:
            first_step_attempts += 1
            if first_step_attempts <= 2:
                raise OSError("step receipt store unavailable")
        return real_writer(*args, **kwargs)

    monkeypatch.setattr(contract, "write_step_receipt_create_once", fail_first_step_twice)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    assert stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )["exitCode"] == 0

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    commands_after_failure = list(docker_commands)

    assert failed["exitCode"] == 2
    assert not path.with_name("orphaned-compose-teardown-consumption.json").exists()
    failed_report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert failed_report["destructiveRepairPerformed"] is True
    assert failed_report["destructiveRepairOutcome"] == "complete_step_fact_pending"
    assert failed_report["consumption"] == ""

    recovered = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert recovered["exitCode"] == 0
    assert docker_commands == commands_after_failure
    assert path.with_name("orphaned-compose-teardown-step-001.json").is_file()
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "passed"
    assert consumption["failedCommand"] == []


def test_terminal_consumption_write_failure_retries_from_complete_execution_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "running",
        "attemptId": "attempt-terminal-writer",
        "composeProject": PROJECT,
        "candidateDigest": "sha256:" + "a" * 64,
    }
    startup_state: dict[str, dict[str, object]] = {"value": running}
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        lambda _target: startup_state["value"],
    )
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )

    def transition(**_kwargs: object) -> dict[str, object]:
        stopped = {**running, "status": "stopped"}
        startup_state["value"] = stopped
        return stopped

    monkeypatch.setattr(stackctl, "transition_startup_attempt", transition)
    snapshot = multi_sample()
    samples = iter(
        (
            snapshot,
            snapshot,
            post_sample(snapshot),
            post_sample(snapshot),
            post_sample(snapshot),
        )
    )
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: next(samples))
    docker_commands: list[list[str]] = []

    def remove(argv: list[str]) -> CompletedProcess[str]:
        docker_commands.append(argv)
        return CompletedProcess(argv, 0, "removed", "")

    monkeypatch.setattr(stackctl, "run", remove)
    real_writer = contract.write_consumption_create_once
    write_attempts = 0

    def fail_terminal_and_partial(*args: object, **kwargs: object) -> Path:
        nonlocal write_attempts
        write_attempts += 1
        if write_attempts <= 3:
            raise OSError("consumption store unavailable")
        return real_writer(*args, **kwargs)

    monkeypatch.setattr(contract, "write_consumption_create_once", fail_terminal_and_partial)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    assert stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )["exitCode"] == 0

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    commands_after_failure = list(docker_commands)

    assert failed["exitCode"] == 2
    assert startup_state["value"]["status"] == "stopped"
    assert not path.with_name("orphaned-compose-teardown-consumption.json").exists()
    assert path.with_name("orphaned-compose-teardown-journal.json").is_file()

    retry_failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert retry_failed["exitCode"] == 2
    assert docker_commands == commands_after_failure
    assert not path.with_name("orphaned-compose-teardown-consumption.json").exists()
    retry_report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert retry_report["destructiveRepairPerformed"] is True
    assert retry_report["destructiveRepairOutcome"] == "complete_terminal_fact_pending"
    assert retry_report["consumption"] == ""

    recovered = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert recovered["exitCode"] == 0
    assert docker_commands == commands_after_failure
    assert any("no Docker removal command was replayed" in item for item in recovered["details"])
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "passed"
    assert consumption["removalOutcome"] == "complete"


def test_terminal_convergence_write_failure_retries_without_success_fact(
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
    real_writer = contract.write_convergence_create_once
    write_attempts = 0

    def fail_once(*args: object, **kwargs: object) -> Path:
        nonlocal write_attempts
        write_attempts += 1
        if write_attempts == 1:
            raise OSError("convergence store unavailable")
        return real_writer(*args, **kwargs)

    monkeypatch.setattr(contract, "write_convergence_create_once", fail_once)

    failed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert failed["exitCode"] == 2
    assert not path.with_name("orphaned-compose-teardown-convergence.json").exists()
    assert json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )["status"] == "partial_failure"

    recovered = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert recovered["exitCode"] == 0
    assert json.loads(
        path.with_name("orphaned-compose-teardown-convergence.json").read_text(
            encoding="utf-8"
        )
    )["status"] == "passed"


def test_passed_consumption_is_not_downgraded_when_report_publication_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    samples = iter((snapshot, snapshot, post_sample(snapshot)))
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: next(samples))
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
    assert planned["exitCode"] == 0
    monkeypatch.setattr(
        stackctl,
        "write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("report sink unavailable")
        ),
    )

    committed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert committed["exitCode"] == 0
    assert any("report publication failed" in item for item in committed["details"])
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "passed"
    assert consumption["removalOutcome"] == "complete"


def test_passed_convergence_is_not_downgraded_when_summary_publication_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: post_sample(snapshot))
    monkeypatch.setattr(
        stackctl,
        "_write_summary_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("summary sink unavailable")
        ),
    )

    committed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert committed["exitCode"] == 0
    assert any("report publication failed" in item for item in committed["details"])
    convergence = json.loads(
        path.with_name("orphaned-compose-teardown-convergence.json").read_text(
            encoding="utf-8"
        )
    )
    assert convergence["status"] == "passed"
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert consumption["status"] == "partial_failure"


def test_reclaimed_receipt_is_retired_so_later_up_is_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions: list[dict[str, object]] = []
    stopped = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "stopped",
        "attemptId": "attempt-1",
    }

    def transition(**kwargs: object) -> dict[str, object]:
        transitions.append(kwargs)
        return stopped

    monkeypatch.setattr(stackctl, "transition_startup_attempt", transition)

    canonical, detail = stackctl._close_orphan_reclaimed_startup_receipt(
        "alpha-local",
        {
            "env": "alpha",
            "status": "partial",
            "attemptId": "attempt-1",
        },
    )

    assert canonical == stopped
    assert "attempt-1" in detail
    assert transitions == [
        {
            "env": "alpha",
            "target": "alpha-local",
            "attempt_id": "attempt-1",
            "status": "stopped",
            "failure": (
                "reclaimed by governed orphan Compose teardown; candidate-bound "
                "down was structurally impossible for this receipt"
            ),
        }
    ]

    transitions.clear()
    already_stopped = {
        "env": "alpha",
        "status": "stopped",
        "attemptId": "attempt-1",
    }
    assert stackctl._close_orphan_reclaimed_startup_receipt(
        "alpha-local",
        already_stopped,
    ) == (already_stopped, "")
    assert transitions == []
