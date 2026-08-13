"""stackctl repair 运行时恢复域: 操作锁、端口释放探测与 orphan compose 收敛。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- 操作锁家族: `_prod_release_lock` / `_local_stack_operation_lock` /
  `_global_local_operation_lock` / `_global_local_build_cache_lock` /
  `_global_output_layout_reconciliation_lock`;
- 端口探测: `socket_probe` / `_wait_for_network_ports_released` /
  `_wait_for_exact_tcp_ports_released`;
- orphan compose 收敛: `_current_runtime_health_scope` /
  `_orphan_compose_runtime_gate` / `_wait_for_attested_orphan_compose_ports_released` /
  `_complete_orphan_compose_audit_convergence` / `_repair_orphaned_compose`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import re
import socket
import time

from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Mapping


@contextlib.contextmanager
def _prod_release_lock() -> Any:
    import quwoquan_ops.cli.stackctl as _stackctl

    lock_path = _stackctl._release_state_dir() / ".global-deploy.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = f"{os.getpid()}-{time.time_ns()}"
    if lock_path.is_dir():
        raise RuntimeError(
            "release lock path must be a file; inspect and remove the directory: "
            f"{lock_path}"
        )
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                f"prod release lock is held by {holder}: {lock_path}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _local_stack_operation_lock(target_name: str) -> Any:
    """为本机所有本地环境操作保留唯一的 Compose/package 临界区。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(target_name).strip()
    if target not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        raise ValueError(f"local stack operation lock does not support {target!r}")
    lock_path = _stackctl.local_runtime_operation_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = f"pid={os.getpid()} target={target} startedAt={_stackctl.utc_now()}"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                f"local stack operation is already running: {holder}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _global_local_operation_lock(
    *,
    scope: str,
    affected_targets: Sequence[str],
) -> Any:
    """Reserve the one host-global boundary shared by runtime and repair work."""
    import quwoquan_ops.cli.stackctl as _stackctl

    lock_path = _stackctl.local_runtime_operation_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = (
        f"pid={os.getpid()} scope={scope} mode=exclusive "
        f"startedAt={_stackctl.utc_now()}"
    )
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                "local runtime operation is already running: " + holder
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield {
                "path": _stackctl.relpath(lock_path),
                "mode": "exclusive",
                "scope": scope,
                "owner": owner,
                "affectedTargets": list(affected_targets),
            }
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _global_local_build_cache_lock() -> Any:
    """Exclusively reserve the daemon-global local BuildKit cache boundary."""
    import quwoquan_ops.cli.stackctl as _stackctl


    with _stackctl._global_local_operation_lock(
        scope="global-local-build-cache",
        affected_targets=_stackctl.LOCAL_BUILD_CACHE_TARGETS,
    ) as evidence:
        yield evidence


@contextlib.contextmanager
def _global_output_layout_reconciliation_lock() -> Any:
    """Block runtime/package work while layout identities are planned or moved."""
    import quwoquan_ops.cli.stackctl as _stackctl


    with _stackctl._global_local_operation_lock(
        scope="global-output-layout-reconciliation",
        affected_targets=(*_stackctl.LOCAL_BUILD_CACHE_TARGETS, "repo"),
    ) as evidence:
        yield evidence


def socket_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_network_ports_released(
    target_name: str,
    *,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 0.5,
    port_reporter: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Wait for target-owned host forwards to converge after compose down.

    Docker Desktop/Colima can remove containers before its host forwarding
    process closes the corresponding listening sockets. A single immediate
    probe therefore creates a false cleanup failure. The bounded wait keeps
    the fail-closed resource-release contract without restarting or otherwise
    mutating the shared container runtime.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    deadline = time.monotonic() + timeout_seconds
    reporter = port_reporter or _stackctl._network_report
    while True:
        occupied = [
            item for item in reporter(target_name)["ports"] if item["open"]
        ]
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(poll_interval_seconds)


def _wait_for_exact_tcp_ports_released(
    ports: Sequence[int],
    *,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 0.5,
) -> list[int]:
    import quwoquan_ops.cli.stackctl as _stackctl

    exact_ports = sorted(set(ports))
    deadline = time.monotonic() + timeout_seconds
    while True:
        occupied = [port for port in exact_ports if _stackctl.socket_probe(port)]
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(poll_interval_seconds)


def _current_runtime_health_scope(target_name: str) -> str:
    """Return the health scope promised by the canonical current startup attempt.

    Bounded content stacks intentionally do not start the full Assistant and
    external Provider planes. The target-scoped transactional startup receipt
    is the sole authority; missing, stopped or drifted identity fails closed to
    full scope and never consults retired environment state.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return "full"
    try:
        startup_attempt = _stackctl.load_startup_attempt(target_name)
    except ValueError:
        return "full"
    expected_environment = target_name.removesuffix("-local")
    if (
        not isinstance(startup_attempt, dict)
        or startup_attempt.get("status") != "running"
        or startup_attempt.get("target") != target_name
        or startup_attempt.get("env") != expected_environment
        or not str(startup_attempt.get("composeProject") or "").strip()
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup_attempt.get("configurationDigest") or ""),
        )
        is None
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup_attempt.get("imageTransportTag") or ""),
        )
        is None
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup_attempt.get("providerRuntimeDigest") or ""),
        )
        is None
    ):
        return "full"
    workload = str(startup_attempt.get("workload") or "").strip()
    if workload == "content-release":
        return "content-consumer"
    if workload == "content-commercial":
        return "content-commercial"
    return "full"


def _orphan_compose_runtime_gate(target_name: str) -> dict[str, Any] | None:
    """Return the stopped receipt when normal candidate-bound down cannot apply."""
    import quwoquan_ops.cli.stackctl as _stackctl


    leases = _stackctl.active_consumer_leases(target_name)
    if leases:
        identities = ", ".join(
            f"{item.get('device')}:{item.get('consumer')}" for item in leases
        )
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose teardown requires zero active consumer leases"
            + (f": {identities}" if identities else "")
        )
    try:
        startup = _stackctl.load_startup_attempt(target_name)
    except (OSError, ValueError) as exc:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            f"canonical startup receipt is unreadable: {exc}"
        ) from exc
    if startup is None:
        return None
    status = str(startup.get("status") or "").strip()
    if status != "stopped":
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose teardown requires an absent or stopped startup receipt; "
            f"status={status or '<missing>'} must use candidate-bound normal down"
        )
    return startup


def _wait_for_attested_orphan_compose_ports_released(
    target_name: str,
    attestation: Mapping[str, Any],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    canonical_occupied = _stackctl._wait_for_network_ports_released(
        target_name,
        port_reporter=_stackctl._canonical_port_occupancy_report,
    )
    if canonical_occupied:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "canonical target ports remain occupied after bounded teardown wait: "
            + ", ".join(
                f"{item['name']}:{item['port']}" for item in canonical_occupied
            )
        )
    snapshot = attestation.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose attestation snapshot is missing"
        )
    noncanonical_ports = snapshot.get("nonCanonicalPublishedHostPorts")
    if not isinstance(noncanonical_ports, list) or any(
        isinstance(item, bool) or not isinstance(item, int)
        for item in noncanonical_ports
    ):
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "attested non-canonical port inventory is invalid"
        )
    noncanonical_occupied = _stackctl._wait_for_exact_tcp_ports_released(
        noncanonical_ports
    )
    if noncanonical_occupied:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "attested non-canonical TCP ports remain occupied after bounded teardown wait: "
            + ", ".join(str(item) for item in noncanonical_occupied)
        )


def _complete_orphan_compose_audit_convergence(
    *,
    target_name: str,
    attestation_path: Path,
    attestation: Mapping[str, Any],
    consumption: Mapping[str, Any],
    canonical_ports: Sequence[Mapping[str, Any]],
    other_target_port_blocks: Sequence[Mapping[str, Any]],
    report_dir: Path,
    startup: Mapping[str, Any] | None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    _stackctl._wait_for_attested_orphan_compose_ports_released(target_name, attestation)
    post_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
        target=target_name,
        canonical_ports=canonical_ports,
        run_command=_stackctl.run,
        require_removable=False,
        other_target_port_blocks=other_target_port_blocks,
        port_probe=_stackctl.socket_probe,
    )
    _stackctl.orphan_compose_teardown.assert_post_teardown_state(
        attestation,
        post_snapshot,
        port_probe=_stackctl.socket_probe,
    )
    convergence_path = _stackctl.orphan_compose_teardown.write_convergence_create_once(
        attestation_path,
        attestation=attestation,
        consumption=consumption,
        current_snapshot=post_snapshot,
    )
    details = [
        "audit-only convergence completed; no Docker removal command was executed",
        f"partialConsumptionDigest={consumption['consumptionDigest']}",
        f"convergence={_stackctl.relpath(convergence_path)}",
    ]
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "repair",
            "target": target_name,
            "fix": "reclaim-orphaned-compose",
            "status": "passed",
            "auditOnly": True,
            "destructiveRepairPerformed": False,
            "startupAttempt": startup,
            "attestation": _stackctl.relpath(attestation_path),
            "attestationDigest": attestation["attestationDigest"],
            "consumptionDigest": consumption["consumptionDigest"],
            "convergence": _stackctl.relpath(convergence_path),
            "details": details,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="repair",
        target=target_name,
        status="ok",
        summary=f"stackctl orphan Compose audit convergence passed for {target_name}",
        details=details,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl orphan Compose audit convergence passed for {target_name}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "convergence": _stackctl.relpath(convergence_path),
    }


def _repair_orphaned_compose(
    args: argparse.Namespace,
    *,
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target_name = str(args.target)
    attestation_value = str(
        getattr(args, "orphaned_compose_attestation", "") or ""
    ).strip()
    if not attestation_value:
        details = [
            "--orphaned-compose-attestation is required; arbitrary Compose project input is not accepted"
        ]
        return {
            "exitCode": 2,
            "summary": f"stackctl orphan Compose repair is GATE_BLOCK for {target_name}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }
    attestation_path = Path(attestation_value)
    allowed_root = _stackctl.env_runs_root(environment)
    confirmed = bool(
        getattr(args, "confirm_orphaned_compose_teardown", False)
    )
    active_attestation: dict[str, Any] | None = None
    execution_journal: Path | None = None
    attempted_command: list[str] = []
    confirmed_container_ids: list[str] = []
    confirmed_network_ids: list[str] = []
    destructive_steps: list[dict[str, Any]] = []
    try:
        with _stackctl._local_stack_operation_lock(target_name):
            startup = _stackctl._orphan_compose_runtime_gate(target_name)
            canonical_ports = _stackctl._canonical_port_occupancy_report(target_name)["ports"]
            other_target_port_blocks = _stackctl._other_local_target_port_blocks(target_name)
            if not confirmed:
                snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                    target=target_name,
                    canonical_ports=canonical_ports,
                    run_command=_stackctl.run,
                    other_target_port_blocks=other_target_port_blocks,
                    port_probe=_stackctl.socket_probe,
                )
                attestation = _stackctl.orphan_compose_teardown.seal_attestation(snapshot)
                written_path = _stackctl.orphan_compose_teardown.write_attestation_create_once(
                    attestation_path,
                    attestation,
                    allowed_root=allowed_root,
                )
                details = [
                    f"created read-only attestation={_stackctl.relpath(written_path)}",
                    f"project={attestation['project']}",
                    f"containers={len(snapshot['containers'])}",
                    f"networks={len(snapshot['networks'])}",
                    f"preservedVolumes={len(snapshot['volumes'])}",
                    "no Compose resource was removed; rerun with the same path and --confirm-orphaned-compose-teardown after review",
                ]
                _stackctl.write_json(
                    report_dir / "report.json",
                    {
                        "command": "repair",
                        "target": target_name,
                        "fix": args.fix,
                        "status": "planned",
                        "destructiveRepairPerformed": False,
                        "startupAttempt": startup,
                        "attestation": _stackctl.relpath(written_path),
                        "attestationDigest": attestation["attestationDigest"],
                        "details": details,
                    },
                )
                _stackctl.write_json(
                    report_dir / "repair_plan.json",
                    {
                        "target": target_name,
                        "fix": args.fix,
                        "project": attestation["project"],
                        "attestation": _stackctl.relpath(written_path),
                        "attestationDigest": attestation["attestationDigest"],
                        "containerIds": [
                            item["id"] for item in snapshot["containers"]
                        ],
                        "networkIds": [item["id"] for item in snapshot["networks"]],
                        "preservedVolumeNames": [
                            item["name"] for item in snapshot["volumes"]
                        ],
                        "actions": [
                            "review the create-once exact-resource attestation",
                            "rerun repair with the same attestation path and explicit confirmation",
                        ],
                    },
                )
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="repair",
                    target=target_name,
                    status="ok",
                    summary=f"stackctl orphan Compose teardown planned for {target_name}",
                    details=details,
                )
                return {
                    "exitCode": 0,
                    "summary": f"stackctl orphan Compose teardown planned for {target_name}",
                    "details": details,
                    "reportDir": _stackctl.relpath(report_dir),
                    "attestation": _stackctl.relpath(written_path),
                }

            consumption_exists = (
                attestation_path.with_name(
                    "orphaned-compose-teardown-consumption.json"
                ).exists()
                or attestation_path.with_name(
                    "orphaned-compose-teardown-consumption.json"
                ).is_symlink()
            )
            attestation = _stackctl.orphan_compose_teardown.load_attestation(
                attestation_path,
                allowed_root=allowed_root,
                expected_target=target_name,
                allow_expired=consumption_exists,
            )
            active_attestation = attestation
            if consumption_exists:
                consumption = (
                    _stackctl.orphan_compose_teardown.load_partial_consumption_for_convergence(
                        attestation_path,
                        attestation=attestation,
                    )
                )
                _stackctl.orphan_compose_teardown.validate_execution_evidence_for_convergence(
                    attestation_path,
                    attestation=attestation,
                )
                return _stackctl._complete_orphan_compose_audit_convergence(
                    target_name=target_name,
                    attestation_path=attestation_path,
                    attestation=attestation,
                    consumption=consumption,
                    canonical_ports=canonical_ports,
                    other_target_port_blocks=other_target_port_blocks,
                    report_dir=report_dir,
                    startup=startup,
                )
            _stackctl.orphan_compose_teardown.assert_not_consumed(attestation_path)
            current_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                target=target_name,
                canonical_ports=canonical_ports,
                run_command=_stackctl.run,
                other_target_port_blocks=other_target_port_blocks,
                port_probe=_stackctl.socket_probe,
            )
            _stackctl.orphan_compose_teardown.assert_snapshot_unchanged(
                attestation,
                current_snapshot,
            )
            commands = _stackctl.orphan_compose_teardown.exact_removal_commands(attestation)
            execution_journal = (
                _stackctl.orphan_compose_teardown.write_execution_journal_create_once(
                    attestation_path,
                    attestation=attestation,
                    commands=commands,
                )
            )
            for index, command in enumerate(commands, start=1):
                attempted_command = command
                result = _stackctl.run(command)
                destructive_steps.append(
                    {
                        "argv": command,
                        "exitCode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
                if result.returncode != 0:
                    raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                        "exact orphan Compose resource removal failed: "
                        + " ".join(command[:3])
                    )
                if command[:3] == ["docker", "rm", "--force"]:
                    confirmed_container_ids.append(command[-1])
                else:
                    confirmed_network_ids.append(command[-1])
                _stackctl.orphan_compose_teardown.write_step_receipt_create_once(
                    attestation_path,
                    attestation=attestation,
                    index=index,
                    command=command,
                )
                attempted_command = []
            _stackctl._wait_for_attested_orphan_compose_ports_released(
                target_name,
                attestation,
            )
            post_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                target=target_name,
                canonical_ports=_stackctl._canonical_port_occupancy_report(target_name)["ports"],
                run_command=_stackctl.run,
                require_removable=False,
                other_target_port_blocks=other_target_port_blocks,
                port_probe=_stackctl.socket_probe,
            )
            _stackctl.orphan_compose_teardown.assert_post_teardown_state(
                attestation,
                post_snapshot,
                port_probe=_stackctl.socket_probe,
            )
            snapshot = attestation["snapshot"]
            container_ids = [item["id"] for item in snapshot["containers"]]
            network_ids = [item["id"] for item in snapshot["networks"]]
            consumption_path = _stackctl.orphan_compose_teardown.write_consumption_create_once(
                attestation_path,
                attestation=attestation,
                removed_containers=container_ids,
                removed_networks=network_ids,
                status="passed",
                removal_outcome="complete",
            )
            details = [
                f"removed exact attested containers={','.join(container_ids) or 'none'}",
                f"removed exact attested networks={','.join(network_ids) or 'none'}",
                "preserved named volumes="
                + (
                    ",".join(item["name"] for item in snapshot["volumes"])
                    or "none"
                ),
                f"consumption={_stackctl.relpath(consumption_path)}",
            ]
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "command": "repair",
                    "target": target_name,
                    "fix": args.fix,
                    "status": "passed",
                    "destructiveRepairPerformed": True,
                    "startupAttempt": startup,
                    "attestation": _stackctl.relpath(attestation_path),
                    "attestationDigest": attestation["attestationDigest"],
                    "consumption": _stackctl.relpath(consumption_path),
                    "executionJournal": _stackctl.relpath(execution_journal),
                    "steps": destructive_steps,
                    "details": details,
                },
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="repair",
                target=target_name,
                status="ok",
                summary=f"stackctl removed exact orphan Compose resources for {target_name}",
                details=details,
            )
            return {
                "exitCode": 0,
                "summary": f"stackctl removed exact orphan Compose resources for {target_name}",
                "details": details,
                "reportDir": _stackctl.relpath(report_dir),
                "consumption": _stackctl.relpath(consumption_path),
            }
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        _stackctl.orphan_compose_teardown.OrphanComposeTeardownError,
    ) as exc:
        consumption_path: Path | None = None
        consumption_issue = ""
        removal_outcome = "none"
        destructive_performed: bool | None = False
        if active_attestation is not None and execution_journal is not None:
            removal_outcome = (
                "partial_failure"
                if confirmed_container_ids or confirmed_network_ids
                else "unknown_after_attempt"
                if attempted_command
                else "aborted_before_attempt"
            )
            destructive_performed = (
                True
                if confirmed_container_ids or confirmed_network_ids
                else None
                if attempted_command
                else False
            )
            try:
                consumption_path = (
                    _stackctl.orphan_compose_teardown.write_consumption_create_once(
                        attestation_path,
                        attestation=active_attestation,
                        removed_containers=confirmed_container_ids,
                        removed_networks=confirmed_network_ids,
                        status="partial_failure",
                        failed_command=attempted_command,
                        removal_outcome=removal_outcome,
                    )
                )
            except (OSError, RuntimeError, TypeError, ValueError) as receipt_exc:
                consumption_issue = str(receipt_exc)
        details = [str(exc)]
        if confirmed_container_ids or confirmed_network_ids:
            details.append(
                "confirmed removed exact resources before failure: "
                + ",".join(confirmed_container_ids + confirmed_network_ids)
            )
        if attempted_command:
            details.append(
                "failed command may have changed its exact resource; inspect the execution journal before any new attestation: "
                + " ".join(attempted_command)
            )
        if consumption_path is not None:
            details.append(f"partial consumption={_stackctl.relpath(consumption_path)}")
        if consumption_issue:
            details.append(f"partial consumption receipt failure={consumption_issue}")
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": target_name,
                "fix": args.fix,
                "status": "gate_block",
                "destructiveRepairPerformed": destructive_performed,
                "destructiveRepairOutcome": removal_outcome,
                "executionJournal": (
                    _stackctl.relpath(execution_journal) if execution_journal else ""
                ),
                "consumption": (
                    _stackctl.relpath(consumption_path) if consumption_path else ""
                ),
                "steps": destructive_steps,
                "details": details,
            },
        )
        _stackctl.write_json(
            report_dir / "repair_plan.json",
            {
                "target": target_name,
                "fix": args.fix,
                "actions": [
                    "resolve the recorded identity, receipt, lease, expiry, or live-resource drift",
                    "create a new attestation only after the prior path is preserved for audit",
                ],
            },
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=target_name,
            status="failed",
            summary=f"stackctl orphan Compose repair is GATE_BLOCK for {target_name}",
            details=details,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl orphan Compose repair is GATE_BLOCK for {target_name}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }
