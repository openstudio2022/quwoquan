"""Exact-resource recovery for an orphaned local Compose project.

candidate 客观不可用时的合法拆除自成一条子主题，见
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

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    CONTAINER_ID,
    IMAGE_DIGEST,
    NETWORK_ID,
    PROJECT,
    SECOND_CONTAINER_ID,
    SECOND_NETWORK_ID,
    docker_inventory,
    install_stackctl_fakes,
    multi_sample,
    ports,
    post_sample,
    repair_args,
    sample,
    write_completed_partial_consumption,
)


def test_attestation_binds_exact_compose_resources_and_is_create_once(
    tmp_path: Path,
) -> None:
    snapshot = sample()
    attestation = contract.seal_attestation(snapshot)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)
    loaded = contract.load_attestation(
        path,
        allowed_root=tmp_path,
        expected_target="alpha-local",
    )

    assert loaded == attestation
    assert loaded["project"] == PROJECT
    assert loaded["snapshot"]["containers"][0]["imageDigest"] == IMAGE_DIGEST
    assert loaded["snapshot"]["networks"][0]["id"] == NETWORK_ID
    assert loaded["snapshot"]["volumes"][0]["name"].endswith("mongo-data")
    with pytest.raises(contract.OrphanComposeTeardownError, match="already exists"):
        contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)


def test_attestation_rejects_stale_arbitrary_project_and_live_drift(
    tmp_path: Path,
) -> None:
    sampled_at = datetime.now(timezone.utc)
    snapshot = sample()
    attestation = contract.seal_attestation(snapshot, sampled_at=sampled_at)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)

    with pytest.raises(contract.OrphanComposeTeardownError, match="stale"):
        contract.load_attestation(
            path,
            allowed_root=tmp_path,
            expected_target="alpha-local",
            now=sampled_at
            + timedelta(seconds=contract.ATTESTATION_TTL_SECONDS + 1),
        )
    forged = dict(attestation)
    forged["project"] = "operator_supplied_project"
    with pytest.raises(contract.OrphanComposeTeardownError, match="project mismatch"):
        contract.validate_attestation(forged, now=sampled_at)
    changed = json.loads(json.dumps(snapshot))
    changed["networks"].append({"id": "extra-live-resource"})
    with pytest.raises(contract.OrphanComposeTeardownError, match="changed"):
        contract.assert_snapshot_unchanged(attestation, changed)


def test_inventory_rejects_foreign_network_attachment_and_out_of_block_port() -> None:
    inventory = docker_inventory()
    network_key = ("docker", "network", "inspect", NETWORK_ID)
    network = json.loads(inventory[network_key].stdout)
    network[0]["Containers"] = {"d" * 64: {"Name": "foreign-live-container"}}
    inventory[network_key] = CompletedProcess([], 0, json.dumps(network), "")

    with pytest.raises(contract.OrphanComposeTeardownError, match="non-attested"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=ports(),
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_inventory_rejects_truncated_docker_identity_even_if_inspect_expands_it() -> None:
    inventory = docker_inventory()
    label_filter = f"label=com.docker.compose.project={PROJECT}"
    list_key = (
        "docker",
        "ps",
        "--no-trunc",
        "-aq",
        "--filter",
        label_filter,
    )
    short_id = CONTAINER_ID[:12]
    full_inspection = inventory[("docker", "inspect", CONTAINER_ID)]
    inventory[list_key] = CompletedProcess([], 0, short_id + "\n", "")
    inventory[("docker", "inspect", short_id)] = full_inspection

    with pytest.raises(contract.OrphanComposeTeardownError, match="set drifted"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=ports(),
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_container_mount_set_order_is_canonical_but_mount_fields_remain_strict() -> None:
    inspection = json.loads(
        docker_inventory()[("docker", "inspect", CONTAINER_ID)].stdout
    )[0]
    first = {
        "Type": "bind",
        "Source": "/candidate/content",
        "Destination": "/runtime/content",
        "Mode": "ro",
        "RW": False,
        "Propagation": "rprivate",
    }
    second = {
        "Type": "volume",
        "Name": "provider-data",
        "Source": "/var/lib/docker/volumes/provider-data/_data",
        "Destination": "/runtime/provider",
        "Driver": "local",
        "Mode": "z",
        "RW": True,
        "Propagation": "",
    }
    inspection["Mounts"] = [first, second]
    forward = contract._container_descriptor(
        inspection,
        project=PROJECT,
        canonical_ports={17000},
    )
    inspection["Mounts"] = [second, first]
    reversed_order = contract._container_descriptor(
        inspection,
        project=PROJECT,
        canonical_ports={17000},
    )
    changed_first = {**first, "Destination": "/runtime/content-changed"}
    inspection["Mounts"] = [second, changed_first]
    changed = contract._container_descriptor(
        inspection,
        project=PROJECT,
        canonical_ports={17000},
    )

    assert forward["configurationDigest"] == reversed_order["configurationDigest"]
    assert forward["configurationDigest"] != changed["configurationDigest"]


def test_inventory_rejects_port_outside_canonical_target_block() -> None:
    # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-002.t1
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["HostConfig"]["PortBindings"]["8443/tcp"][0]["HostPort"] = "18000"
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    with pytest.raises(contract.OrphanComposeTeardownError, match="another target block"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=ports(),
            run_command=lambda argv: inventory[tuple(argv)],
            other_target_port_blocks=[
                {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999}
            ],
            port_probe=lambda _port: True,
        )


def test_inventory_attests_live_legacy_port_outside_all_target_blocks() -> None:
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["HostConfig"]["PortBindings"]["8443/tcp"][0]["HostPort"] = "2019"
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    inventory[
        (
            "docker",
            "ps",
            "--no-trunc",
            "-q",
            "--filter",
            "publish=2019",
        )
    ] = CompletedProcess([], 0, CONTAINER_ID + "\n", "")

    snapshot = contract.sample_snapshot(
        target="alpha-local",
        canonical_ports=ports(),
        run_command=lambda argv: inventory[tuple(argv)],
        other_target_port_blocks=[
            {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999},
            {"target": "gamma-local", "blockStart": 19000, "blockEnd": 19999},
        ],
        port_probe=lambda port: port == 2019,
    )

    assert snapshot["projectPublishedHostPorts"] == [2019]
    assert snapshot["nonCanonicalPublishedHostPorts"] == [2019]
    attestation = contract.seal_attestation(snapshot)
    with pytest.raises(contract.OrphanComposeTeardownError, match="remain occupied"):
        contract.assert_post_teardown_state(
            attestation,
            post_sample(snapshot),
            port_probe=lambda port: port == 2019,
        )
    contract.assert_post_teardown_state(
        attestation,
        post_sample(snapshot),
        port_probe=lambda _port: False,
    )


def test_removal_plan_uses_only_exact_ids_and_preserves_volumes() -> None:
    snapshot = sample()
    attestation = contract.seal_attestation(snapshot)

    assert contract.exact_removal_commands(attestation) == [
        ["docker", "rm", "--force", CONTAINER_ID],
        ["docker", "network", "rm", NETWORK_ID],
    ]
    contract.assert_post_teardown_state(
        attestation,
        post_sample(snapshot),
        port_probe=lambda _port: False,
    )
    changed_volume = post_sample(snapshot)
    changed_volume["volumes"] = []
    with pytest.raises(contract.OrphanComposeTeardownError, match="volumes must be preserved"):
        contract.assert_post_teardown_state(
            attestation,
            changed_volume,
            port_probe=lambda _port: False,
        )


def test_repair_plans_without_mutation_then_consumes_only_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = multi_sample()
    snapshot["projectPublishedHostPorts"] = [17000, 2019]
    snapshot["nonCanonicalPublishedHostPorts"] = [2019]
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
        "_wait_for_network_ports_released",
        lambda target, **_kwargs: waited.append(target) or [],
    )
    monkeypatch.setattr(
        stackctl,
        "_wait_for_exact_tcp_ports_released",
        lambda ports: waited.append(list(ports)) or [],
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
    assert waited == ["alpha-local", [2019]]


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
    snapshot = multi_sample()
    snapshot["projectPublishedHostPorts"] = [17000, 2019]
    snapshot["nonCanonicalPublishedHostPorts"] = [2019]
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(
        stackctl,
        "_wait_for_exact_tcp_ports_released",
        lambda ports: [2019],
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
