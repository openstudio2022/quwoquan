"""Docker 采样、transport-exact 端点所有权与 create-once attestation 判据。

repair 编排、partial 消费与 convergence 自成一条子主题，见
`test_orphan_compose_teardown__recovery__local_contract_test`；candidate 客观
不可用时的合法拆除见
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

import copy
import errno
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.cli.lib.orphan_compose_teardown import constants as contract_constants
from quwoquan_ops.cli.lib.port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
)
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    CONTAINER_ID,
    IMAGE_DIGEST,
    NETWORK_ID,
    PROJECT,
    docker_inventory,
    ports,
    post_sample,
    sample,
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
    assert loaded["snapshot"]["publishedEndpoints"] == [
        {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
    ]
    assert loaded["snapshot"]["containers"][0]["imageDigest"] == IMAGE_DIGEST
    assert loaded["snapshot"]["containers"][0]["publishedEndpoints"] == [
        {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
    ]
    assert loaded["snapshot"]["networks"][0]["id"] == NETWORK_ID
    assert loaded["snapshot"]["volumes"][0]["name"].endswith("mongo-data")
    with pytest.raises(contract.OrphanComposeTeardownError, match="already exists"):
        contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)


def test_atomic_fact_writer_preserves_storage_failure_and_allows_same_path_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attestation = contract.seal_attestation(sample())
    path = tmp_path / "orphaned-compose-teardown-attestation.json"
    real_fsync = contract_constants.os.fsync
    failed = False

    def fail_file_sync_once(descriptor: int) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError(errno.ENOSPC, "no space left on device")
        real_fsync(descriptor)

    monkeypatch.setattr(contract_constants.os, "fsync", fail_file_sync_once)
    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match=r"sync temporary file.*errno 28.*no space left on device",
    ):
        contract.write_attestation_create_once(path, attestation, allowed_root=tmp_path)

    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))
    assert contract.write_attestation_create_once(
        path,
        attestation,
        allowed_root=tmp_path,
    ) == path


def test_parent_directory_sync_failure_rolls_back_published_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "orphaned-compose-teardown-step-001.json"
    real_fsync = contract_constants.os.fsync
    failed = False

    def fail_parent_sync_once(descriptor: int) -> None:
        nonlocal failed
        if not failed and contract_constants.os.path.isdir(f"/dev/fd/{descriptor}"):
            failed = True
            raise OSError(errno.EIO, "input/output error")
        real_fsync(descriptor)

    monkeypatch.setattr(contract_constants.os, "fsync", fail_parent_sync_once)
    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match=r"sync parent directory.*errno 5.*input/output error",
    ):
        contract._write_create_once(path, {"status": "passed"}, label="step receipt")

    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))
    assert contract._write_create_once(
        path,
        {"status": "passed"},
        label="step receipt",
    ) == path


def test_run_scoped_formal_project_is_sampled_and_attested_exactly() -> None:
    project = "quwoquan_alpha_release_78142_3"
    inventory = docker_inventory(project=project)
    commands: list[list[str]] = []

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        commands.append(argv)
        return inventory[tuple(argv)]

    snapshot = contract.sample_snapshot(
        target="alpha-local",
        project=project,
        canonical_ports=ports(),
        port_manifest=load_port_manifest(),
        port_profile="alpha-local",
        run_command=run_command,
    )
    attestation = contract.seal_attestation(snapshot)

    assert snapshot["project"] == project
    assert attestation["project"] == project
    assert attestation["snapshot"]["project"] == project
    assert any(
        f"label=com.docker.compose.project={project}" in command
        for command in commands
    )
    assert all(
        f"label=com.docker.compose.project={PROJECT}" not in command
        for command in commands
    )


def test_absent_receipt_discovers_one_exact_formal_project_from_docker_labels() -> None:
    project = "quwoquan_alpha_release_78142_3"
    outputs = iter((f"quwoquan_beta_release\n{project}\n", f"{project}\n"))
    commands: list[list[str]] = []

    def run_command(argv: list[str]) -> CompletedProcess[str]:
        commands.append(argv)
        return CompletedProcess(argv, 0, next(outputs), "")

    discovered = contract.discover_exact_project(
        target="alpha-local",
        run_command=run_command,
    )

    assert discovered == project
    assert commands == [
        [
            "docker",
            "ps",
            "--all",
            "--no-trunc",
            "--filter",
            "label=com.docker.compose.project",
            "--format",
            '{{.Label "com.docker.compose.project"}}',
        ],
        [
            "docker",
            "network",
            "ls",
            "--filter",
            "label=com.docker.compose.project",
            "--format",
            '{{.Label "com.docker.compose.project"}}',
        ],
    ]


@pytest.mark.parametrize(
    ("container_projects", "network_projects", "message"),
    [
        ("quwoquan_beta_release\n", "", "no exact project"),
        (
            "quwoquan_alpha_release_78142_3\n",
            "quwoquan_alpha_release_99103_1\n",
            "multiple exact projects",
        ),
    ],
)
def test_absent_receipt_project_discovery_fails_closed_on_non_unique_identity(
    container_projects: str,
    network_projects: str,
    message: str,
) -> None:
    outputs = iter((container_projects, network_projects))

    with pytest.raises(contract.OrphanComposeTeardownError, match=message):
        contract.discover_exact_project(
            target="alpha-local",
            run_command=lambda argv: CompletedProcess(argv, 0, next(outputs), ""),
        )


@pytest.mark.parametrize("drift_side", ["aggregate", "container"])
def test_attestation_rejects_published_endpoint_inventory_drift(
    drift_side: str,
) -> None:
    snapshot = json.loads(json.dumps(sample()))
    if drift_side == "aggregate":
        snapshot["publishedEndpoints"] = []
    else:
        snapshot["containers"][0]["publishedEndpoints"] = []

    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match="published endpoint inventory mismatch",
    ):
        contract.seal_attestation(snapshot)


def test_attestation_rejects_unknown_endpoint_role_and_legacy_port_fields() -> None:
    unknown_role = json.loads(json.dumps(sample()))
    endpoint = {"role": "unknown-edge", "hostPort": 17000, "protocol": "tcp"}
    unknown_role["publishedEndpoints"] = [endpoint]
    unknown_role["containers"][0]["publishedEndpoints"] = [endpoint]

    with pytest.raises(contract.OrphanComposeTeardownError, match="role is not canonical"):
        contract.seal_attestation(unknown_role)

    wrong_protocol = json.loads(json.dumps(sample()))
    endpoint = {"role": "api-edge", "hostPort": 17000, "protocol": "udp"}
    wrong_protocol["publishedEndpoints"] = [endpoint]
    wrong_protocol["containers"][0]["publishedEndpoints"] = [endpoint]
    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match="publisher identity is not canonical",
    ):
        contract.seal_attestation(wrong_protocol)

    legacy = json.loads(json.dumps(sample()))
    legacy["projectPublishedHostPorts"] = [17000]
    with pytest.raises(contract.OrphanComposeTeardownError, match="snapshot fields mismatch"):
        contract.seal_attestation(legacy)


def test_attestation_refuses_a_role_owning_multiple_container_ports() -> None:
    """白名单的「独占容器发布口」集丢掉了 containerPort，覆盖关系必须就地断言。

    该集与 inventory 归因等价只在「同一 role 在同一 composeService+protocol 下只有一个
    容器口」时成立。这个前提由 port manifest 的两条校验保证，但那是跨文件不变量；放宽
    任一条，白名单就会比 inventory 宽，本该判否的非 canonical hostPort 会被放行。
    """
    snapshot = sample()
    manifest = load_port_manifest()
    inflated = copy.deepcopy(manifest)
    # 让 api-edge 在同一 gamma-proxy/tcp 下多认领一个容器口。
    inflated["roles"]["api-edge"]["composePublishedEndpoints"].append(
        {"composeService": "gamma-proxy", "containerPort": 18079, "protocol": "tcp"}
    )

    from quwoquan_ops.cli.lib.orphan_compose_teardown import attestation as attestation_module

    with mock.patch.object(
        attestation_module, "load_port_manifest", return_value=inflated
    ):
        with pytest.raises(
            contract.OrphanComposeTeardownError,
            match="owns multiple container ports",
        ):
            contract.seal_attestation(snapshot)


def test_publisher_identity_reads_the_declared_port_profile_not_the_target_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """port profile 只能来自 topology 的 `portProfile` 声明位。

    target 名与 profile 名今天同形，用 target 名当 profile 名在今天不可观测；
    一旦分叉，publisher 身份就会按一个从未被声明的 profile 解析。这里把声明位
    改成一个不存在的 profile：若实现读的是声明位，密封必然判否。
    """
    topology = contract_constants.load_environment_topology()
    drifted = json.loads(json.dumps(topology))
    attested_target = contract_constants.get_target(drifted, "alpha-local")
    assert str(attested_target["portProfile"]) == "alpha-local"
    attested_target["portProfile"] = "profile-that-is-not-declared"
    monkeypatch.setattr(
        contract_constants,
        "load_environment_topology",
        lambda: drifted,
    )

    with pytest.raises(contract.OrphanComposeTeardownError):
        contract.seal_attestation(sample())


def test_publisher_identity_fails_closed_when_no_port_profile_is_declared() -> None:
    """缺席的 `portProfile` 是判否，不得回落到 target 名。"""
    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match="declares no portProfile",
    ):
        contract_constants.declared_port_profile("prod-hosted")


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
            project=PROJECT,
            canonical_ports=ports(),
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_inventory_rejects_unknown_compose_publisher_even_on_canonical_host_port() -> None:
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["Config"]["Labels"]["com.docker.compose.service"] = "api-edge"
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")

    with pytest.raises(contract.OrphanComposeTeardownError, match="publisher identity"):
        contract.sample_snapshot(
            target="alpha-local",
            project=PROJECT,
            canonical_ports=ports(),
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
            run_command=lambda argv: inventory[tuple(argv)],
        )


def test_inventory_rejects_published_role_absent_from_the_target_inventory() -> None:
    inventory = docker_inventory()

    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match="no canonical port in the target inventory: api-edge",
    ):
        contract.sample_snapshot(
            target="alpha-local",
            project=PROJECT,
            canonical_ports=[{"name": "livekit-rtc-udp", "port": 17160, "open": True}],
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
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
            project=PROJECT,
            canonical_ports=ports(),
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
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
        publisher_roles=compose_published_endpoint_roles(
            load_port_manifest(), "alpha-local"
        ),
        container_role_closure=compose_publisher_container_role_closure(
            compose_published_endpoint_roles(load_port_manifest(), "alpha-local")
        ),
    )
    inspection["Mounts"] = [second, first]
    reversed_order = contract._container_descriptor(
        inspection,
        project=PROJECT,
        publisher_roles=compose_published_endpoint_roles(
            load_port_manifest(), "alpha-local"
        ),
        container_role_closure=compose_publisher_container_role_closure(
            compose_published_endpoint_roles(load_port_manifest(), "alpha-local")
        ),
    )
    changed_first = {**first, "Destination": "/runtime/content-changed"}
    inspection["Mounts"] = [second, changed_first]
    changed = contract._container_descriptor(
        inspection,
        project=PROJECT,
        publisher_roles=compose_published_endpoint_roles(
            load_port_manifest(), "alpha-local"
        ),
        container_role_closure=compose_publisher_container_role_closure(
            compose_published_endpoint_roles(load_port_manifest(), "alpha-local")
        ),
    )

    assert forward["configurationDigest"] == reversed_order["configurationDigest"]
    assert forward["configurationDigest"] != changed["configurationDigest"]


def test_inventory_rejects_port_outside_canonical_target_block() -> None:
    # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-002.t1
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["HostConfig"]["PortBindings"]["17000/tcp"][0]["HostPort"] = "18000"
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    with pytest.raises(contract.OrphanComposeTeardownError, match="another target block"):
        contract.sample_snapshot(
            target="alpha-local",
            project=PROJECT,
            canonical_ports=ports(),
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
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
    container[0]["Config"]["Labels"]["com.docker.compose.service"] = "livekit-sfu"
    container[0]["HostConfig"]["PortBindings"] = {
        "7882/udp": [{"HostIp": "127.0.0.1", "HostPort": "2019"}]
    }
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    inventory[
        (
            "docker",
            "ps",
            "--no-trunc",
            "-q",
            "--filter",
            "publish=2019/udp",
        )
    ] = CompletedProcess([], 0, CONTAINER_ID + "\n", "")

    snapshot = contract.sample_snapshot(
        target="alpha-local",
        project=PROJECT,
        canonical_ports=[
            *ports(),
            {"name": "livekit-rtc-udp", "port": 17160, "open": True},
        ],
        port_manifest=load_port_manifest(),
        port_profile="alpha-local",
        run_command=lambda argv: inventory[tuple(argv)],
        other_target_port_blocks=[
            {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999},
            {"target": "gamma-local", "blockStart": 19000, "blockEnd": 19999},
        ],
        port_probe=lambda endpoint: endpoint
        == {"role": "livekit-rtc-udp", "hostPort": 2019, "protocol": "udp"},
    )

    assert snapshot["publishedEndpoints"] == [
        {"role": "livekit-rtc-udp", "hostPort": 2019, "protocol": "udp"}
    ]
    attestation = contract.seal_attestation(snapshot)
    with pytest.raises(contract.OrphanComposeTeardownError, match="remain occupied"):
        contract.assert_post_teardown_state(
            attestation,
            post_sample(snapshot),
            port_probe=lambda endpoint: endpoint["hostPort"] == 2019,
        )
    contract.assert_post_teardown_state(
        attestation,
        post_sample(snapshot),
        port_probe=lambda _endpoint: False,
    )


def test_inventory_resolves_shared_container_port_by_canonical_host_port() -> None:
    """service-core 共用容器口 18081：归属只能由 canonical hostPort 定位。"""
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["Config"]["Labels"]["com.docker.compose.service"] = "service-core"
    container[0]["HostConfig"]["PortBindings"] = {
        "18081/tcp": [
            {"HostIp": "127.0.0.1", "HostPort": "17210"},
            {"HostIp": "127.0.0.1", "HostPort": "17200"},
        ]
    }
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")
    for host_port in ("17210", "17200"):
        inventory[
            (
                "docker",
                "ps",
                "--no-trunc",
                "-q",
                "--filter",
                f"publish={host_port}/tcp",
            )
        ] = CompletedProcess([], 0, CONTAINER_ID + "\n", "")

    snapshot = contract.sample_snapshot(
        target="alpha-local",
        project=PROJECT,
        canonical_ports=[
            *ports(),
            {"name": "user-service", "port": 17210, "open": True},
            {"name": "chat-service", "port": 17200, "open": True},
        ],
        port_manifest=load_port_manifest(),
        port_profile="alpha-local",
        run_command=lambda argv: inventory[tuple(argv)],
        port_probe=lambda _endpoint: True,
    )

    assert snapshot["publishedEndpoints"] == [
        {"role": "chat-service", "hostPort": 17200, "protocol": "tcp"},
        {"role": "user-service", "hostPort": 17210, "protocol": "tcp"},
    ]
    contract.seal_attestation(snapshot)


def test_inventory_refuses_to_guess_a_shared_container_port_host_port_drift() -> None:
    """共用容器口上的非 canonical 主机端口无法归因，只能判否而不是猜一个 role。"""
    inventory = docker_inventory()
    container_key = ("docker", "inspect", CONTAINER_ID)
    container = json.loads(inventory[container_key].stdout)
    container[0]["Config"]["Labels"]["com.docker.compose.service"] = "service-core"
    container[0]["HostConfig"]["PortBindings"] = {
        "18081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "17999"}]
    }
    inventory[container_key] = CompletedProcess([], 0, json.dumps(container), "")

    with pytest.raises(
        contract.OrphanComposeTeardownError,
        match="cannot be attributed",
    ):
        contract.sample_snapshot(
            target="alpha-local",
            project=PROJECT,
            canonical_ports=ports(),
            port_manifest=load_port_manifest(),
            port_profile="alpha-local",
            run_command=lambda argv: inventory[tuple(argv)],
            port_probe=lambda _endpoint: True,
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
        port_probe=lambda _endpoint: False,
    )
    changed_volume = post_sample(snapshot)
    changed_volume["volumes"] = []
    with pytest.raises(contract.OrphanComposeTeardownError, match="volumes must be preserved"):
        contract.assert_post_teardown_state(
            attestation,
            changed_volume,
            port_probe=lambda _endpoint: False,
        )
