"""Exact-resource recovery for an orphaned local Compose project."""

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
import contextlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract


_CONTAINER_ID = "a" * 64
_NETWORK_ID = "b" * 64
_SECOND_CONTAINER_ID = "d" * 64
_SECOND_NETWORK_ID = "e" * 64
_IMAGE_DIGEST = "sha256:" + "c" * 64
_PROJECT = "quwoquan_alpha_release"


def _ports(*, opened: bool = True) -> list[dict[str, object]]:
    return [{"name": "api-edge", "port": 17000, "open": opened}]


def _docker_inventory() -> dict[tuple[str, ...], CompletedProcess[str]]:
    labels = {
        "com.docker.compose.project": _PROJECT,
        "com.docker.compose.service": "api-edge",
        "com.docker.compose.config-hash": "config-a",
        "com.docker.compose.project.config_files": "/repo/compose.yaml",
        "com.docker.compose.project.working_dir": "/repo",
    }
    network_labels = {
        "com.docker.compose.project": _PROJECT,
        "com.docker.compose.network": "default",
        "com.docker.compose.config-hash": "config-b",
    }
    volume_labels = {
        "com.docker.compose.project": _PROJECT,
        "com.docker.compose.volume": "mongo-data",
        "com.docker.compose.config-hash": "config-c",
    }
    label_filter = f"label=com.docker.compose.project={_PROJECT}"
    return {
        (
            "docker",
            "ps",
            "--no-trunc",
            "-aq",
            "--filter",
            label_filter,
        ): CompletedProcess(
            [], 0, _CONTAINER_ID + "\n", ""
        ),
        (
            "docker",
            "network",
            "ls",
            "--no-trunc",
            "-q",
            "--filter",
            label_filter,
        ): CompletedProcess(
            [], 0, _NETWORK_ID + "\n", ""
        ),
        ("docker", "volume", "ls", "-q", "--filter", label_filter): CompletedProcess(
            [], 0, "quwoquan_alpha_release_mongo-data\n", ""
        ),
        ("docker", "inspect", _CONTAINER_ID): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": _CONTAINER_ID,
                        "Name": "/quwoquan_alpha_release-api-edge-1",
                        "Image": _IMAGE_DIGEST,
                        "Config": {
                            "Image": "quwoquan/api-edge:release",
                            "Labels": labels,
                            "Env": ["APP_ENV=alpha"],
                        },
                        "HostConfig": {
                            "PortBindings": {
                                "8443/tcp": [
                                    {"HostIp": "127.0.0.1", "HostPort": "17000"}
                                ]
                            }
                        },
                        "Mounts": [],
                        "NetworkSettings": {"Ports": {}},
                    }
                ]
            ),
            "",
        ),
        ("docker", "network", "inspect", _NETWORK_ID): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": _NETWORK_ID,
                        "Name": "quwoquan_alpha_release_default",
                        "Labels": network_labels,
                        "Driver": "bridge",
                        "EnableIPv6": False,
                        "IPAM": {"Driver": "default"},
                        "Internal": False,
                        "Attachable": False,
                        "Options": {},
                    }
                ]
            ),
            "",
        ),
        (
            "docker",
            "volume",
            "inspect",
            "quwoquan_alpha_release_mongo-data",
        ): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Name": "quwoquan_alpha_release_mongo-data",
                        "Labels": volume_labels,
                        "Driver": "local",
                        "Options": {},
                        "Scope": "local",
                    }
                ]
            ),
            "",
        ),
    }


def _sample() -> dict[str, object]:
    inventory = _docker_inventory()

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        return inventory[tuple(argv)]

    return contract.sample_snapshot(
        target="alpha-local",
        canonical_ports=_ports(),
        run_command=run_command,
    )


def _post_sample(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        **snapshot,
        "canonicalPorts": _ports(opened=False),
        "containers": [],
        "networks": [],
    }


def _multi_sample() -> dict[str, object]:
    snapshot = json.loads(json.dumps(_sample()))
    second_container = dict(snapshot["containers"][0])
    second_container["id"] = _SECOND_CONTAINER_ID
    second_container["name"] = "quwoquan_alpha_release-worker-1"
    second_container["service"] = "worker"
    second_container["labels"] = {
        **second_container["labels"],
        "com.docker.compose.service": "worker",
    }
    snapshot["containers"].append(second_container)
    second_network = dict(snapshot["networks"][0])
    second_network["id"] = _SECOND_NETWORK_ID
    second_network["name"] = "quwoquan_alpha_release_internal"
    second_network["labels"] = {
        **second_network["labels"],
        "com.docker.compose.network": "internal",
    }
    snapshot["networks"].append(second_network)
    return snapshot


def test_attestation_binds_exact_compose_resources_and_is_create_once(
    tmp_path: Path,
) -> None:
    snapshot = _sample()
    attestation = contract.seal_attestation(snapshot)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)
    loaded = contract.load_attestation(
        path,
        allowed_root=tmp_path,
        expected_target="alpha-local",
    )

    assert loaded == attestation
    assert loaded["project"] == _PROJECT
    assert loaded["snapshot"]["containers"][0]["imageDigest"] == _IMAGE_DIGEST
    assert loaded["snapshot"]["networks"][0]["id"] == _NETWORK_ID
    assert loaded["snapshot"]["volumes"][0]["name"].endswith("mongo-data")
    with pytest.raises(contract.OrphanComposeTeardownError, match="already exists"):
        contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)


def test_attestation_rejects_stale_arbitrary_project_and_live_drift(
    tmp_path: Path,
) -> None:
    sampled_at = datetime.now(timezone.utc)
    snapshot = _sample()
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
    inventory = _docker_inventory()
    network_key = ("docker", "network", "inspect", _NETWORK_ID)
    network = json.loads(inventory[network_key].stdout)
    network[0]["Containers"] = {"d" * 64: {"Name": "foreign-live-container"}}
    inventory[network_key] = CompletedProcess([], 0, json.dumps(network), "")

    with pytest.raises(contract.OrphanComposeTeardownError, match="non-attested"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=_ports(),
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_inventory_rejects_truncated_docker_identity_even_if_inspect_expands_it() -> None:
    inventory = _docker_inventory()
    label_filter = f"label=com.docker.compose.project={_PROJECT}"
    list_key = (
        "docker",
        "ps",
        "--no-trunc",
        "-aq",
        "--filter",
        label_filter,
    )
    short_id = _CONTAINER_ID[:12]
    full_inspection = inventory[("docker", "inspect", _CONTAINER_ID)]
    inventory[list_key] = CompletedProcess([], 0, short_id + "\n", "")
    inventory[("docker", "inspect", short_id)] = full_inspection

    with pytest.raises(contract.OrphanComposeTeardownError, match="set drifted"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=_ports(),
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_container_mount_set_order_is_canonical_but_mount_fields_remain_strict() -> None:
    inspection = json.loads(
        _docker_inventory()[("docker", "inspect", _CONTAINER_ID)].stdout
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
        project=_PROJECT,
        canonical_ports={17000},
    )
    inspection["Mounts"] = [second, first]
    reversed_order = contract._container_descriptor(
        inspection,
        project=_PROJECT,
        canonical_ports={17000},
    )
    changed_first = {**first, "Destination": "/runtime/content-changed"}
    inspection["Mounts"] = [second, changed_first]
    changed = contract._container_descriptor(
        inspection,
        project=_PROJECT,
        canonical_ports={17000},
    )

    assert forward["configurationDigest"] == reversed_order["configurationDigest"]
    assert forward["configurationDigest"] != changed["configurationDigest"]


def test_inventory_rejects_port_outside_canonical_target_block() -> None:
    inventory = _docker_inventory()
    container_key = ("docker", "inspect", _CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["HostConfig"]["PortBindings"]["8443/tcp"][0]["HostPort"] = "18000"
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    with pytest.raises(contract.OrphanComposeTeardownError, match="another target block"):
        contract.sample_snapshot(
            target="alpha-local",
            canonical_ports=_ports(),
            run_command=lambda argv: inventory[tuple(argv)],
            other_target_port_blocks=[
                {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999}
            ],
            port_probe=lambda _port: True,
        )


def test_inventory_attests_live_legacy_port_outside_all_target_blocks() -> None:
    inventory = _docker_inventory()
    container_key = ("docker", "inspect", _CONTAINER_ID)
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
    ] = CompletedProcess([], 0, _CONTAINER_ID + "\n", "")

    snapshot = contract.sample_snapshot(
        target="alpha-local",
        canonical_ports=_ports(),
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
            _post_sample(snapshot),
            port_probe=lambda port: port == 2019,
        )
    contract.assert_post_teardown_state(
        attestation,
        _post_sample(snapshot),
        port_probe=lambda _port: False,
    )


def test_removal_plan_uses_only_exact_ids_and_preserves_volumes() -> None:
    snapshot = _sample()
    attestation = contract.seal_attestation(snapshot)

    assert contract.exact_removal_commands(attestation) == [
        ["docker", "rm", "--force", _CONTAINER_ID],
        ["docker", "network", "rm", _NETWORK_ID],
    ]
    contract.assert_post_teardown_state(
        attestation,
        _post_sample(snapshot),
        port_probe=lambda _port: False,
    )
    changed_volume = _post_sample(snapshot)
    changed_volume["volumes"] = []
    with pytest.raises(contract.OrphanComposeTeardownError, match="volumes must be preserved"):
        contract.assert_post_teardown_state(
            attestation,
            changed_volume,
            port_probe=lambda _port: False,
        )


def _args(path: Path, *, confirm: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        fix="reclaim-orphaned-compose",
        orphaned_compose_attestation=str(path),
        confirm_orphaned_compose_teardown=confirm,
    )


def _install_stackctl_fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    monkeypatch.setattr(stackctl, "env_runs_root", lambda _env: tmp_path)
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))
    monkeypatch.setattr(
        stackctl,
        "_local_stack_operation_lock",
        lambda _target: contextlib.nullcontext(),
    )
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: [])
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        lambda _target: {"target": "alpha-local", "status": "stopped"},
    )
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {"ports": _ports()},
    )
    monkeypatch.setattr(
        stackctl,
        "_other_local_target_port_blocks",
        lambda _target: [
            {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999},
            {"target": "gamma-local", "blockStart": 19000, "blockEnd": 19999},
        ],
    )
    monkeypatch.setattr(stackctl, "socket_probe", lambda _port: False)
    monkeypatch.setattr(
        stackctl,
        "_wait_for_network_ports_released",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        stackctl,
        "_wait_for_exact_tcp_ports_released",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(stackctl, "_write_summary_bundle", lambda *_args, **_kwargs: None)
    return report_dir


def _write_completed_partial_consumption(
    path: Path,
    snapshot: dict[str, object],
    *,
    removed_containers: list[str] | None = None,
    failed_command: list[str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    attestation = contract.seal_attestation(snapshot)
    contract.write_attestation_create_once(
        path,
        attestation,
        allowed_root=path.parent,
    )
    commands = contract.exact_removal_commands(attestation)
    contract.write_execution_journal_create_once(
        path,
        attestation=attestation,
        commands=commands,
    )
    for index, command in enumerate(commands, start=1):
        contract.write_step_receipt_create_once(
            path,
            attestation=attestation,
            index=index,
            command=command,
        )
    expected_container_ids = [
        item["id"] for item in snapshot["containers"]
    ]
    expected_network_ids = [item["id"] for item in snapshot["networks"]]
    contract.write_consumption_create_once(
        path,
        attestation=attestation,
        removed_containers=(
            expected_container_ids
            if removed_containers is None
            else removed_containers
        ),
        removed_networks=expected_network_ids,
        status="partial_failure",
        failed_command=failed_command or [],
        removal_outcome="partial_failure",
    )
    consumption = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    return attestation, consumption


def test_repair_plans_without_mutation_then_consumes_only_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    snapshot["projectPublishedHostPorts"] = [17000, 2019]
    snapshot["nonCanonicalPublishedHostPorts"] = [2019]
    post_snapshot = _post_sample(snapshot)
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
        _args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0
    assert path.is_file()
    assert commands == []

    consumed = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )
    assert consumed["exitCode"] == 0
    assert commands == [
        ["docker", "rm", "--force", _CONTAINER_ID],
        ["docker", "rm", "--force", _SECOND_CONTAINER_ID],
        ["docker", "network", "rm", _NETWORK_ID],
        ["docker", "network", "rm", _SECOND_NETWORK_ID],
    ]
    consumption = path.with_name("orphaned-compose-teardown-consumption.json")
    payload = json.loads(consumption.read_text(encoding="utf-8"))
    assert payload["preservedVolumeNames"] == [
        "quwoquan_alpha_release_mongo-data"
    ]
    assert payload["status"] == "passed"
    assert payload["removedContainerIds"] == [
        _CONTAINER_ID,
        _SECOND_CONTAINER_ID,
    ]
    assert payload["removedNetworkIds"] == [_NETWORK_ID, _SECOND_NETWORK_ID]
    assert waited == ["alpha-local", [2019]]


def test_partial_failure_is_consumed_with_exact_success_journal_and_cannot_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    samples = iter((snapshot, snapshot))
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: next(samples),
    )
    commands: list[list[str]] = []

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        commands.append(argv)
        if argv[-1] == _SECOND_CONTAINER_ID:
            return CompletedProcess(argv, 1, "", "container removal failed")
        return CompletedProcess(argv, 0, "removed", "")

    monkeypatch.setattr(stackctl, "run", run_command)
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    planned = stackctl._repair_orphaned_compose(
        _args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0

    failed = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
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
    assert consumption["removedContainerIds"] == [_CONTAINER_ID]
    assert consumption["removedNetworkIds"] == []
    assert consumption["failedCommand"] == [
        "docker",
        "rm",
        "--force",
        _SECOND_CONTAINER_ID,
    ]
    step = json.loads(
        path.with_name("orphaned-compose-teardown-step-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert step["resourceId"] == _CONTAINER_ID
    assert path.with_name("orphaned-compose-teardown-journal.json").is_file()
    journal = json.loads(
        path.with_name("orphaned-compose-teardown-journal.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["resourceId"] for item in journal["steps"]] == [
        _CONTAINER_ID,
        _SECOND_CONTAINER_ID,
        _NETWORK_ID,
        _SECOND_NETWORK_ID,
    ]

    replay = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
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
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    _write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: _post_sample(snapshot),
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda argv: commands.append(argv),
    )

    result = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
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
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    _write_completed_partial_consumption(
        path,
        snapshot,
        removed_containers=(
            [_CONTAINER_ID] if invalid_kind == "incomplete-ids" else None
        ),
        failed_command=(
            ["docker", "network", "rm", _NETWORK_ID]
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
        _args(path, confirm=True),
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
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    _write_completed_partial_consumption(path, snapshot)
    post = _post_sample(snapshot)
    if post_drift == "resource":
        post["containers"] = [snapshot["containers"][0]]
    else:
        post["volumes"] = []
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: post)
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))

    result = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
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
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
    snapshot = _multi_sample()
    snapshot["projectPublishedHostPorts"] = [17000, 2019]
    snapshot["nonCanonicalPublishedHostPorts"] = [2019]
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    _write_completed_partial_consumption(path, snapshot)
    monkeypatch.setattr(
        stackctl,
        "_wait_for_exact_tcp_ports_released",
        lambda _ports: [2019],
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(stackctl, "run", lambda argv: commands.append(argv))

    result = stackctl._repair_orphaned_compose(
        _args(path, confirm=True),
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
    report_dir = _install_stackctl_fakes(monkeypatch, tmp_path)
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
        _args(
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
