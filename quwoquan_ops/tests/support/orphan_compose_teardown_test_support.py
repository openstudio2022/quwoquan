"""Shared fixtures for the orphaned local Compose recovery contract tests.

采样、attestation 参数与 stackctl 替身被恢复路径的多个子主题共用（精确资源
采样、repair 执行与收敛、candidate 不可用时的合法拆除），集中在此以免各子
主题各自复制一份 Docker inventory 形状而彼此漂移。
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest


CONTAINER_ID = "a" * 64
NETWORK_ID = "b" * 64
SECOND_CONTAINER_ID = "d" * 64
SECOND_NETWORK_ID = "e" * 64
IMAGE_DIGEST = "sha256:" + "c" * 64
PROJECT = "quwoquan_alpha_release"


def ports(*, opened: bool = True) -> list[dict[str, object]]:
    return [{"name": "api-edge", "port": 17000, "open": opened}]


def docker_inventory(
    *,
    project: str = PROJECT,
) -> dict[tuple[str, ...], CompletedProcess[str]]:
    labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.service": "gamma-proxy",
        "com.docker.compose.config-hash": "config-a",
        "com.docker.compose.project.config_files": "/repo/compose.yaml",
        "com.docker.compose.project.working_dir": "/repo",
    }
    network_labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.network": "default",
        "com.docker.compose.config-hash": "config-b",
    }
    volume_labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.volume": "mongo-data",
        "com.docker.compose.config-hash": "config-c",
    }
    label_filter = f"label=com.docker.compose.project={project}"
    volume_name = f"{project}_mongo-data"
    return {
        (
            "docker",
            "ps",
            "--no-trunc",
            "-aq",
            "--filter",
            label_filter,
        ): CompletedProcess(
            [], 0, CONTAINER_ID + "\n", ""
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
            [], 0, NETWORK_ID + "\n", ""
        ),
        ("docker", "volume", "ls", "-q", "--filter", label_filter        ): CompletedProcess([], 0, volume_name + "\n", ""),
        ("docker", "inspect", CONTAINER_ID): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": CONTAINER_ID,
                        "Name": f"/{project}-gamma-proxy-1",
                        "Image": IMAGE_DIGEST,
                        "Config": {
                            "Image": "quwoquan/api-edge:release",
                            "Labels": labels,
                            "Env": ["APP_ENV=alpha"],
                        },
                        "HostConfig": {
                            "PortBindings": {
                                "17000/tcp": [
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
        ("docker", "network", "inspect", NETWORK_ID): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": NETWORK_ID,
                        "Name": f"{project}_default",
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
            volume_name,
        ): CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Name": volume_name,
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


def sample(*, project: str = PROJECT) -> dict[str, object]:
    inventory = docker_inventory(project=project)

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        return inventory[tuple(argv)]

    return contract.sample_snapshot(
        target="alpha-local",
        project=project,
        canonical_ports=ports(),
        port_manifest=load_port_manifest(),
        port_profile="alpha-local",
        run_command=run_command,
    )


def post_sample(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        **snapshot,
        "canonicalPorts": [
            {**item, "open": False} for item in snapshot["canonicalPorts"]
        ],
        "publishedEndpoints": [],
        "containers": [],
        "networks": [],
    }


def multi_sample(*, project: str = PROJECT) -> dict[str, object]:
    snapshot = json.loads(json.dumps(sample(project=project)))
    second_container = dict(snapshot["containers"][0])
    second_container["id"] = SECOND_CONTAINER_ID
    second_container["name"] = f"{project}-worker-1"
    second_container["service"] = "worker"
    second_container["labels"] = {
        **second_container["labels"],
        "com.docker.compose.service": "worker",
    }
    second_container["publishedEndpoints"] = []
    snapshot["containers"].append(second_container)
    second_network = dict(snapshot["networks"][0])
    second_network["id"] = SECOND_NETWORK_ID
    second_network["name"] = f"{project}_internal"
    second_network["labels"] = {
        **second_network["labels"],
        "com.docker.compose.network": "internal",
    }
    snapshot["networks"].append(second_network)
    return snapshot


def repair_args(path: Path, *, confirm: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        fix="reclaim-orphaned-compose",
        orphaned_compose_attestation=str(path),
        confirm_orphaned_compose_teardown=confirm,
    )


def install_stackctl_fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
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
        lambda _target: {
            "target": "alpha-local",
            "status": "stopped",
            "composeProject": PROJECT,
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {"profile": "alpha-local", "ports": ports()},
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
        "_published_endpoint_is_occupied",
        lambda _endpoint: False,
    )
    monkeypatch.setattr(
        stackctl,
        "_wait_for_published_endpoints_released",
        lambda *repair_args, **_kwargs: [],
    )
    monkeypatch.setattr(stackctl, "_write_summary_bundle", lambda *repair_args, **_kwargs: None)
    return report_dir


def write_completed_partial_consumption(
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
