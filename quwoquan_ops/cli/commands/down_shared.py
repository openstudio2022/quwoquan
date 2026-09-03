"""stackctl `down` 域 mutable test-live teardown 共享实现。

从 stackctl.py 逐字迁出仅被 down 域消费的 mutable test-live teardown 家族:

- `_mutable_test_live_resource_names` / `_mutable_test_live_container_ids`:
  受控枚举 compose project 归属的容器与卷名;
- `_mutable_test_live_runtime_plan_from_receipt`:从 startup receipt 投影
  teardown runtime plan;
- `_mutable_test_live_teardown_manifest`:teardown manifest 与容器/卷闭包;
- `_command_mutable_test_live_down`:mutable test-live 栈的受控停止与
  端口释放确认。

`command_down` / `_command_down_unlocked` 等编排入口在
`commands/down_domain.py`;`_wait_for_published_endpoints_released` /
`mutable_test_live_runtime` 等协作符号仍由 stackctl 命名空间拥有。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import os
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Mapping


def _mutable_test_live_resource_names(
    resource: str,
    *,
    compose_project: str,
) -> list[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    result = _stackctl.run(
        [
            "docker",
            resource,
            "ls",
            "--format",
            "{{.Name}}",
            "--filter",
            f"label=com.docker.compose.project={compose_project}",
        ],
        timeout_seconds=30,
    )
    if result.returncode != 0:
        raise ValueError(
            f"mutable test-live {resource} inventory failed: "
            + "; ".join(_stackctl._command_details(result))
        )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _mutable_test_live_container_ids(compose_project: str) -> list[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    lookup = _stackctl.run(
        [
            "docker",
            "ps",
            "-aq",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={compose_project}",
        ],
        timeout_seconds=30,
    )
    if lookup.returncode != 0:
        raise ValueError(
            "mutable test-live Compose container inventory failed: "
            + "; ".join(_stackctl._command_details(lookup))
        )
    return sorted({line.strip() for line in lookup.stdout.splitlines() if line.strip()})


def _mutable_test_live_runtime_plan_from_receipt(
    receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    import quwoquan_ops.cli.stackctl as _stackctl

    run_root = Path(str(receipt.get("runRoot") or ""))
    try:
        run_root_metadata = run_root.lstat()
    except FileNotFoundError as exc:
        raise ValueError("mutable test-live receipt runRoot is missing") from exc
    if not stat.S_ISDIR(run_root_metadata.st_mode) or run_root.is_symlink():
        raise ValueError("mutable test-live receipt runRoot must be a regular directory")
    runtime_plan = _stackctl._dev_session_regular_json(
        run_root / "mutable-runtime-plan.json",
        label="mutable test-live runtime plan",
    )
    if runtime_plan.get("schema") != "stackctl.mutable_test_live_runtime":
        raise ValueError("mutable test-live runtime plan schema mismatch")
    for field in (
        "environment",
        "target",
        "composeProject",
        "composeDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
        "portProfile",
        "portBlock",
        "publishedPorts",
        "tlsProfile",
        "resolverHandoffDigest",
        "publicWebPackage",
    ):
        if runtime_plan.get(field) != receipt.get(field):
            raise ValueError(f"mutable test-live receipt/plan drift: {field}")
    workspace = runtime_plan.get("workspaceIdentity")
    if not isinstance(workspace, Mapping):
        raise ValueError("mutable test-live runtime plan workspace identity is missing")
    for receipt_field, plan_field in (
        ("sourceRevision", "sourceRevision"),
        ("workspaceStatusDigest", "workspaceStatusDigest"),
        ("mutableStateDigest", "mutableStateDigest"),
    ):
        if receipt.get(receipt_field) != workspace.get(plan_field):
            raise ValueError(
                f"mutable test-live receipt/plan drift: {receipt_field}"
            )
    return runtime_plan, run_root


def _compose_service_profiles(
    payloads: Iterable[Mapping[str, Any]],
) -> dict[str, set[str]]:
    """Collect each service's declared Compose profiles across the overlay set.

    A service may appear in several overlays with its `profiles` key declared in
    only one of them. Unioning keeps the gate on the conservative side: a wider
    profile set can only ever move a service into the expected roster, never out
    of it.
    """
    declared: dict[str, set[str]] = {}
    for payload in payloads:
        services = payload.get("services")
        if services is not None and not isinstance(services, dict):
            raise ValueError("mutable test-live execution Compose services are invalid")
        for name, definition in (services or {}).items():
            profiles = (
                definition.get("profiles")
                if isinstance(definition, Mapping)
                else None
            )
            if profiles is not None and not isinstance(profiles, list):
                raise ValueError(
                    "mutable test-live execution Compose profiles are invalid"
                )
            declared.setdefault(str(name), set()).update(
                str(item) for item in (profiles or [])
            )
    return declared


def _compose_activated_services(
    payloads: Iterable[Mapping[str, Any]],
    *,
    activated_profiles: Iterable[str],
) -> set[str]:
    """Return only the services Compose can materialize under these profiles.

    A profile-gated service has no container while its profile stays inactive,
    so counting it as expected turns a by-design projection into a false roster
    drift and strands both teardown and content binding.
    """
    activated = {str(item) for item in activated_profiles}
    return {
        name
        for name, profiles in _compose_service_profiles(payloads).items()
        if not profiles or (profiles & activated)
    }


def _mutable_test_live_teardown_manifest(
    *,
    receipt: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    run_root: Path,
    port_manifest: dict[str, Any],
    port_profile: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Seal the exact running Compose identity into a teardown-only model."""
    import quwoquan_ops.cli.stackctl as _stackctl

    compose_project = str(receipt.get("composeProject") or "")
    publisher_roles = _stackctl.compose_published_endpoint_roles(
        port_manifest,
        port_profile,
    )
    container_role_closure = _stackctl.compose_publisher_container_role_closure(
        publisher_roles
    )
    receipt_endpoints = _stackctl.orphan_compose_teardown._normalize_published_endpoints(
        receipt.get("publishedPorts")
    )
    execution_refs = runtime_plan.get("executionComposeFiles")
    if not isinstance(execution_refs, list) or not execution_refs:
        raise ValueError("mutable test-live runtime plan has no execution Compose files")
    activated_profiles = runtime_plan.get("composeProfiles")
    if activated_profiles is not None and not isinstance(activated_profiles, list):
        raise ValueError("mutable test-live runtime plan Compose profiles are invalid")
    activated_profiles = [str(item) for item in (activated_profiles or [])]
    declared_config_files: set[str] = set()
    execution_payloads: dict[str, dict[str, Any]] = {}
    for index, raw_ref in enumerate(execution_refs):
        ref = Path(str(raw_ref or ""))
        path = ref if ref.is_absolute() else _stackctl.ROOT / ref
        path = Path(os.path.abspath(path))
        if not path.is_relative_to(run_root):
            raise ValueError("mutable test-live execution Compose file escapes runRoot")
        compose = _stackctl._dev_session_regular_json(
            path,
            label=f"mutable test-live execution Compose file {index}",
        )
        declared_config_files.add(str(path))
        if path.name in execution_payloads:
            raise ValueError("mutable test-live execution Compose filename is duplicated")
        execution_payloads[path.name] = compose
    source_refs = runtime_plan.get("composeFiles")
    if source_refs is not None and not isinstance(source_refs, list):
        raise ValueError("mutable test-live source Compose file refs are invalid")
    for raw_ref in source_refs or []:
        ref = Path(str(raw_ref or ""))
        path = ref if ref.is_absolute() else _stackctl.ROOT / ref
        path = Path(os.path.abspath(path))
        if not path.is_relative_to(_stackctl.ROOT):
            raise ValueError("mutable test-live source Compose file escapes repository")
        declared_config_files.add(str(path))
    expected_services = _compose_activated_services(
        execution_payloads.values(),
        activated_profiles=activated_profiles,
    )
    if not expected_services:
        raise ValueError("mutable test-live execution Compose service roster is empty")

    container_ids = _stackctl._mutable_test_live_container_ids(compose_project)
    if not container_ids:
        raise ValueError("mutable test-live Compose project has no inspectable containers")
    inspected = _stackctl.run(["docker", "inspect", *container_ids], timeout_seconds=30)
    if inspected.returncode != 0:
        raise ValueError("mutable test-live Compose project inspection failed")
    try:
        containers = json.loads(inspected.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("mutable test-live Compose project inspection is not JSON") from exc
    if not isinstance(containers, list):
        raise ValueError("mutable test-live Compose project inspection is invalid")

    network_names = _stackctl._mutable_test_live_resource_names(
        "network",
        compose_project=compose_project,
    )
    network_keys: dict[str, str] = {}
    if network_names:
        network_result = _stackctl.run(
            ["docker", "network", "inspect", *network_names],
            timeout_seconds=30,
        )
        if network_result.returncode != 0:
            raise ValueError("mutable test-live Compose network inspection failed")
        try:
            network_documents = json.loads(network_result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "mutable test-live Compose network inspection is not JSON"
            ) from exc
        if not isinstance(network_documents, list):
            raise ValueError("mutable test-live Compose network inspection is invalid")
        for network in network_documents:
            try:
                name = str(network["Name"])
                labels = network["Labels"]
                network_key = str(labels["com.docker.compose.network"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "mutable test-live Compose network labels are invalid"
                ) from exc
            if (
                labels.get("com.docker.compose.project") != compose_project
                or not network_key
                or name not in network_names
                or name in network_keys
            ):
                raise ValueError("mutable test-live Compose network identity drifted")
            network_keys[name] = network_key
        if set(network_keys) != set(network_names):
            raise ValueError("mutable test-live Compose network roster drifted")

    services: dict[str, Any] = {}
    actual_ids: set[str] = set()
    actual_published_endpoints: list[dict[str, object]] = []
    for container in containers:
        try:
            container_id = str(container["Id"])
            config = container["Config"]
            labels = config["Labels"]
            service = str(labels["com.docker.compose.service"])
            image_ref = str(config["Image"])
            attached_networks = set((container["NetworkSettings"]["Networks"] or {}))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("mutable test-live container inspection is invalid") from exc
        config_files = {
            str(Path(os.path.abspath(item.strip())))
            for item in str(
                labels.get("com.docker.compose.project.config_files") or ""
            ).split(",")
            if item.strip()
        }
        archived_config_files_match = False
        if (
            config_files
            and len(config_files) == len(execution_payloads)
            and not config_files.issubset(declared_config_files)
        ):
            archived_root = Path(os.path.abspath(_stackctl.env_runs_root(str(receipt["environment"]))))
            archived_config_files_match = True
            archived_payloads: list[Mapping[str, Any]] = []
            for raw_path in config_files:
                archived_path = Path(raw_path)
                if (
                    not archived_path.is_relative_to(archived_root)
                    or archived_path.parent.name != "compose"
                    or archived_path.parent.parent.name != "mutable-runtime"
                    or archived_path.parent.parent.parent.name
                    != str(receipt.get("target") or "")
                    or archived_path.name not in execution_payloads
                ):
                    archived_config_files_match = False
                    break
                try:
                    archived_payload = _stackctl._dev_session_regular_json(
                        archived_path,
                        label="archived mutable test-live execution Compose file",
                    )
                except ValueError:
                    archived_config_files_match = False
                    break
                archived_payloads.append(archived_payload)
            if archived_config_files_match:
                try:
                    archived_services = _compose_activated_services(
                        archived_payloads,
                        activated_profiles=activated_profiles,
                    )
                except ValueError:
                    archived_config_files_match = False
                else:
                    archived_config_files_match = (
                        archived_services == expected_services
                    )
        identity_issues: list[str] = []
        if container_id not in container_ids:
            identity_issues.append("container-id")
        if labels.get("com.docker.compose.project") != compose_project:
            identity_issues.append("project")
        if labels.get("com.docker.compose.oneoff") == "True":
            identity_issues.append("oneoff")
        if not str(labels.get("com.docker.compose.config-hash") or ""):
            identity_issues.append("config-hash")
        if (
            not config_files
            or (
                not config_files.issubset(declared_config_files)
                and not archived_config_files_match
            )
        ):
            unexpected_config_files = config_files - declared_config_files
            outside_run_root = sum(
                not Path(path).is_relative_to(run_root)
                for path in unexpected_config_files
            )
            unexpected_refs = [
                _stackctl.relpath(Path(path))
                if Path(path).is_relative_to(_stackctl.ROOT)
                else str(Path(path))
                for path in sorted(unexpected_config_files)[:3]
            ]
            identity_issues.append(
                "config-files"
                f"[actual={len(config_files)},declared={len(declared_config_files)},"
                f"unexpected={len(unexpected_config_files)},"
                f"outsideRunRoot={outside_run_root},"
                f"unexpectedRefs={unexpected_refs}]"
            )
        if service not in expected_services:
            identity_issues.append("service-roster")
        if service in services:
            identity_issues.append("duplicate-service")
        if not image_ref:
            identity_issues.append("image")
        if not attached_networks.issubset(network_keys):
            identity_issues.append("network")
        if identity_issues:
            raise ValueError(
                "mutable test-live container is not bound to this receipt: "
                f"{service} ({','.join(identity_issues)})"
            )
        actual_ids.add(container_id)
        actual_published_endpoints.extend(
            _stackctl.orphan_compose_teardown._published_endpoints(
                container,
                compose_service=service,
                publisher_roles=publisher_roles,
                container_role_closure=container_role_closure,
            )
        )
        service_payload: dict[str, Any] = {"image": image_ref}
        if attached_networks:
            service_payload["networks"] = sorted(
                network_keys[name] for name in attached_networks
            )
        services[service] = service_payload
    service_roster_valid = set(services) == expected_services
    if str(receipt.get("status") or "") == "partial":
        # A failed startup can legitimately materialize only the dependency
        # prefix reached before the failing service. Every observed container
        # above is still bound to the exact receipt/runRoot/config/network;
        # requiring the not-yet-created suffix makes canonical recovery
        # impossible and strands preserved volumes.
        service_roster_valid = set(services).issubset(expected_services)
    if actual_ids != set(container_ids) or not service_roster_valid:
        raise ValueError("mutable test-live Compose service roster drifted")
    normalized_actual_endpoints = (
        _stackctl.orphan_compose_teardown._normalize_published_endpoints(
            actual_published_endpoints
        )
    )
    published_endpoint_roster_valid = normalized_actual_endpoints == receipt_endpoints
    if str(receipt.get("status") or "") == "partial":
        # The absent service suffix of a partial startup also has no live
        # publisher. Each observed endpoint has already passed canonical
        # service/role/port validation above, so recovery accepts only a
        # receipt-declared subset; an added or drifted live publisher remains
        # fail-closed.
        published_endpoint_roster_valid = all(
            endpoint in receipt_endpoints
            for endpoint in normalized_actual_endpoints
        )
    if not published_endpoint_roster_valid:
        raise ValueError("mutable test-live Compose published endpoint identity drifted")

    volumes = _stackctl._mutable_test_live_resource_names(
        "volume",
        compose_project=compose_project,
    )
    manifest: dict[str, Any] = {"services": dict(sorted(services.items()))}
    if network_keys:
        manifest["networks"] = {
            key: {"name": name}
            for name, key in sorted(network_keys.items(), key=lambda item: item[1])
        }
    return manifest, container_ids, volumes


def _reclaim_orphaned_project_networks(
    network_names: list[str],
    *,
    compose_project: str,
) -> tuple[list[str], list[str]]:
    """Remove project-labeled Compose networks that have no attached endpoints.

    A partially failed startup can create the project networks without any
    surviving container; `docker compose down` then has nothing to tear down
    (the container branch is skipped) and every subsequent `down` blocks on the
    same orphaned networks. Reclaiming only endpoint-free networks whose
    project label is re-checked at removal time restores idempotent
    convergence without touching live or foreign resources.

    返回 `(reclaimed, issues)`。未被回收的网络一律带原因进 issues：残留网络会让
    调用方的 residual 检查判否，但只报「网络仍在」说不出为什么，操作员无从判断该等
    Docker、改权限，还是去找占用它的容器；inspect/rm 的 stderr 丢掉后就再也拿不回来。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    reclaimed: list[str] = []
    issues: list[str] = []

    def _reason(name: str, reason: str) -> None:
        issues.append(f"orphaned Compose network was not reclaimed: {name}: {reason}")

    for name in network_names:
        inspected = _stackctl.run(
            ["docker", "network", "inspect", name],
            timeout_seconds=30,
        )
        if inspected.returncode != 0:
            _reason(
                name,
                "docker network inspect failed with exit code "
                f"{inspected.returncode}: {str(inspected.stderr or '').strip()}",
            )
            continue
        try:
            documents = json.loads(inspected.stdout)
            containers = documents[0].get("Containers") or {}
            labels = documents[0].get("Labels") or {}
        except (json.JSONDecodeError, IndexError, AttributeError, TypeError) as exc:
            _reason(name, f"docker network inspect payload is unreadable: {exc}")
            continue
        # 名单来自 label 过滤枚举，但枚举与删除之间存在名字重用窗口；
        # 删除时点复核 project label，避免误删他人同名网络。
        observed_project = labels.get("com.docker.compose.project")
        if observed_project != compose_project:
            _reason(
                name,
                "Compose project label is not this project at removal time: "
                f"{observed_project!r}",
            )
            continue
        if containers:
            _reason(
                name,
                "network still has attached endpoints: "
                + ",".join(sorted(str(item) for item in containers)),
            )
            continue
        removal = _stackctl.run(
            ["docker", "network", "rm", name],
            timeout_seconds=30,
        )
        if removal.returncode != 0:
            _reason(
                name,
                f"docker network rm failed with exit code {removal.returncode}: "
                + str(removal.stderr or "").strip(),
            )
            continue
        reclaimed.append(name)
    return sorted(reclaimed), issues


def _command_mutable_test_live_down(
    args: argparse.Namespace,
    *,
    env_name: str,
    report_dir: Path,
    receipt: Mapping[str, Any],
    allow_active_immutable_ports: bool = False,
) -> dict[str, Any]:
    """Stop one receipt-bound mutable runtime without deleting named volumes."""
    import quwoquan_ops.cli.stackctl as _stackctl

    compose_project = str(receipt.get("composeProject") or "")
    attempt_id = str(receipt.get("attemptId") or "")
    blocker_kind = ""
    details: list[str] = []
    command: list[str] = []
    stopped_receipt: dict[str, Any] | None = None
    preserved_volumes: list[str] = []
    resource_release_issues: list[str] = []
    try:
        runtime_plan, run_root = _stackctl._mutable_test_live_runtime_plan_from_receipt(receipt)
        topology = _stackctl.load_environment_topology()
        port_manifest = _stackctl.load_port_manifest()
        release_scope = _stackctl._project_target_runtime_owned_ports(
            args.target,
            published_ports=receipt.get("publishedPorts"),
            topology=topology,
            manifest=port_manifest,
        )
        container_ids = _stackctl._mutable_test_live_container_ids(compose_project)
        if container_ids:
            manifest, manifest_container_ids, preserved_volumes = (
                _stackctl._mutable_test_live_teardown_manifest(
                    receipt=receipt,
                    runtime_plan=runtime_plan,
                    run_root=run_root,
                    port_manifest=port_manifest,
                    port_profile=str(receipt.get("portProfile") or ""),
                )
            )
            if set(manifest_container_ids) != set(container_ids):
                raise ValueError(
                    "mutable test-live container inventory changed before teardown"
                )
            manifest_path = report_dir / "mutable-test-live-teardown-compose.json"
            _stackctl.write_json(manifest_path, manifest)

            app_command = [
                "bash",
                "quwoquan_app/scripts/device/run_stop_app_instance.sh",
                "--env",
                env_name,
                "--quiet",
            ]
            app_result = _stackctl.run(app_command)
            if app_result.returncode != 0:
                blocker_kind = "mutable_test_live_app_stop_failed"
                raise ValueError(
                    "mutable test-live App stop failed: "
                    + "; ".join(_stackctl._command_details(app_result))
                )

            command = [
                "docker",
                "compose",
                "-p",
                compose_project,
                "--project-directory",
                str(run_root),
                "-f",
                str(manifest_path),
                "down",
                "--remove-orphans",
                "--timeout",
                "30",
            ]
            down_result = _stackctl.run(command, timeout_seconds=180)
            details.extend(_stackctl._command_details(down_result))
            if down_result.returncode != 0:
                blocker_kind = "mutable_test_live_compose_down_failed"
                raise ValueError(
                    "mutable test-live Compose down failed: "
                    + "; ".join(_stackctl._command_details(down_result))
                )
        else:
            preserved_volumes = _stackctl._mutable_test_live_resource_names(
                "volume",
                compose_project=compose_project,
            )
            details.append(
                "mutable test-live teardown recovery observed no remaining project containers"
            )

        blocker_kind = "mutable_test_live_teardown_not_converged"
        remaining_container_ids = _stackctl._mutable_test_live_container_ids(compose_project)
        if remaining_container_ids:
            resource_release_issues.append(
                "mutable test-live Compose containers remain after down"
            )
        remaining_networks = _stackctl._mutable_test_live_resource_names(
            "network",
            compose_project=compose_project,
        )
        reclaim_issues: list[str] = []
        if remaining_networks:
            reclaimed_networks, reclaim_issues = (
                _stackctl._reclaim_orphaned_project_networks(
                    remaining_networks,
                    compose_project=compose_project,
                )
            )
            if reclaimed_networks:
                details.append(
                    "mutable test-live orphaned Compose networks reclaimed: "
                    + ",".join(reclaimed_networks)
                )
            remaining_networks = _stackctl._mutable_test_live_resource_names(
                "network",
                compose_project=compose_project,
            )
        if reclaim_issues:
            # 回收失败的原因无条件留在 details：只在「网络仍在」时才带出，会让
            # inspect/rm 失败后该网络恰好被别的进程删掉的情形丢掉全部根因，回执只剩
            # 「已收敛」——正是本项要修的静默。判否条件仍只由 remaining 非空决定。
            details.extend(reclaim_issues)
        if remaining_networks:
            # 判否条件不变（网络仍在即 fail-closed），但把未回收的逐条原因一起带出：
            # 只报「仍在」时操作员无从判断该等 Docker、修权限，还是去找占用的容器。
            resource_release_issues.append(
                "mutable test-live Compose networks remain after down: "
                + ",".join(remaining_networks)
            )
            resource_release_issues.extend(reclaim_issues)
        remaining_volumes = _stackctl._mutable_test_live_resource_names(
            "volume",
            compose_project=compose_project,
        )
        missing_volumes = sorted(set(preserved_volumes) - set(remaining_volumes))
        if missing_volumes:
            resource_release_issues.append(
                "mutable test-live named volumes were removed: "
                + ",".join(missing_volumes)
            )
        if allow_active_immutable_ports:
            details.append(
                "mutable partial teardown preserved the active immutable runtime "
                "and its canonical port ownership"
            )
        else:
            occupied_endpoints = _stackctl._wait_for_published_endpoints_released(
                release_scope
            )
            resource_release_issues.extend(
                "canonical endpoint remains occupied after mutable down: "
                f"{endpoint['role']}:{endpoint['hostPort']}/{endpoint['protocol']}"
                for endpoint in occupied_endpoints
            )
        if resource_release_issues:
            raise ValueError("; ".join(resource_release_issues))

        stopped_receipt = _stackctl.transition_test_live_startup_attempt(
            environment=env_name,
            target=args.target,
            attempt_id=attempt_id,
            status="stopped",
            runtime_plan=runtime_plan,
            run_root=run_root,
            failure="",
        )
        details.extend(
            [
                f"attemptId={attempt_id}",
                f"composeProject={compose_project}",
                f"containersReleased={len(container_ids)}",
                f"namedVolumesPreserved={len(preserved_volumes)}",
            ]
        )
        blocker_kind = ""
        exit_code = 0
        status = "ok"
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        exit_code = 2
        status = "gate_block"
        if not blocker_kind:
            blocker_kind = "mutable_test_live_teardown_identity_invalid"
        details.append(str(exc))

    report = {
        "command": "down",
        "target": args.target,
        "workload": "full",
        "status": status,
        "exitCode": exit_code,
        "blockerKind": blocker_kind,
        "runtimeMode": "mutable-test-live",
        "attemptId": attempt_id,
        "composeProject": compose_project,
        "runRoot": str(receipt.get("runRoot") or ""),
        "argv": command,
        "destructiveRepairPerformed": False,
        "destructiveActions": [],
        "activeImmutableRuntimePreserved": allow_active_immutable_ports,
        "namedVolumesPreserved": preserved_volumes,
        "resourceReleaseIssues": resource_release_issues,
        "startupAttempt": stopped_receipt or dict(receipt),
        "details": details,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    summary = (
        f"stackctl down completed for {args.target}"
        if exit_code == 0
        else f"stackctl down is GATE_BLOCK for {args.target}"
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={
            "runtimeMode": "mutable-test-live",
            "attemptId": attempt_id,
            "composeProject": compose_project,
            "blockerKind": blocker_kind,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "blockerKind": blocker_kind,
        "runtimeMode": "mutable-test-live",
    }
