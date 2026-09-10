"""Delegate undownable receipt repair to attested orphan recovery.

A formal startup receipt does not contain transport-exact published endpoint
ownership. The existing orphan Compose protocol is therefore the only governed
repair implementation: it samples Docker PortBindings, seals a create-once
attestation, preserves named volumes, and requires a second explicit
confirmation before it can retire a structurally undownable receipt.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import consumer_lease_dir, list_consumer_leases
from quwoquan_ops.cli.lib.local_runtime_reservation import local_runtime_operation_lock_path
from quwoquan_ops.cli.lib.startup_attempt_receipt import (
    _write_transaction_journal_exclusive,
    validate_startup_attempt,
)

_RECLAIMABLE_TARGETS = ("alpha-local", "beta-local", "gamma-local")
_ATTESTATION_NAME = "orphaned-compose-teardown-attestation.json"
_PLAN_SCHEMA = "stackctl-alpha-worktree-startup-reconciliation"


def _digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _required_bytes(path: Path) -> bytes:
    encoded = output_paths._read_secure_bytes(path, label="worktree startup reconciliation")
    if encoded is None:
        raise ValueError(f"required reconciliation input is absent: {path}")
    return encoded


def _require_absent(path: Path) -> None:
    if output_paths._read_secure_bytes(path, label="reconciliation exclusion") is not None:
        raise ValueError(f"active or unknown reconciliation exclusion: {path}")


def _read_legacy_inputs(target: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    paths = output_paths.legacy_worktree_startup_paths(target)
    encoded = [_required_bytes(path) for path in paths]
    startup, duplicate, local_run = [json.loads(item) for item in encoded]
    if not isinstance(startup, dict) or startup != duplicate or encoded[0] != encoded[1]:
        raise ValueError("legacy startup receipt copies differ in identity or exact bytes")
    if startup.get("status") != "stopped" or startup.get("workload") != "full":
        raise ValueError("legacy reconciliation only admits consistent stopped/full receipts")
    # 只复用旧对象的身份/摘要校验；旧 runRoot 不能送入宿主 canonical 路径校验。
    # 原件不改写，原始 runRoot 与 local_run 在下方按 exact repo 路径独立验证。
    validate_startup_attempt({**startup, "runRoot": ""}, expected_env="alpha", expected_target=target)
    run_id = startup["attemptId"]
    if not isinstance(run_id, str) or output_paths.safe_segment(run_id) != run_id:
        raise ValueError("legacy attemptId is not one exact path segment")
    root = output_paths.ROOT / ".qwq_output/env/alpha"
    run_root = root / "runs" / run_id
    observability = root / "observability" / run_id
    expected_binding = {
        "env": "alpha", "target": target, "runId": run_id,
        "runRoot": str(run_root), "observabilityRoot": str(observability),
    }
    if local_run != expected_binding or startup.get("runRoot") != str(run_root):
        raise ValueError("legacy local_run binding differs from exact repository runRoot")
    for directory in (run_root, observability):
        descriptor, _ = output_paths._open_directory_chain(directory, label="legacy run binding")
        os.close(descriptor)
    process = paths[0].parent
    for excluded in (
        process / "test_live_startup_attempt.json",
        process / ".startup_attempt.json.fanout-transaction.json",
        process / "workloads/content-release/startup_attempt.json",
        process / "workloads/content-commercial/startup_attempt.json",
    ):
        _require_absent(excluded)
    host_process = output_paths.target_local_dir(target) / "process"
    for name in ("startup_attempt.json", "test_live_startup_attempt.json", "local_run.json"):
        _require_absent(host_process / name)
    return startup, [
        {"source": str(path), "digest": _digest(raw)}
        for path, raw in zip(paths, encoded, strict=True)
    ]


def _read_execution_exclusions(target: str) -> None:
    """只读探测 durable fence/slot 与现有锁，不创建锁或接管未知持有者。"""
    lock = local_runtime_operation_lock_path(target)
    _require_absent(lock.with_suffix(".executor.json"))
    _require_absent(output_paths.deployment_target_path(
        target, "process", "environment-execution", "execution-slot.json",
    ))
    for path in (local_runtime_operation_lock_path(), lock):
        if output_paths._read_secure_bytes(path, label="runtime lock readback") is None:
            continue
        parent_fd, identities = output_paths._open_directory_chain(path.parent, label="runtime lock")
        try:
            descriptor = os.open(path.name, output_paths._secure_file_flags(write=False), dir_fd=parent_fd)
            try:
                mode = fcntl.LOCK_SH if path != lock else fcntl.LOCK_EX
                fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
                output_paths._revalidate_directory_chain(path.parent, label="runtime lock", expected_identities=identities)
                opened = os.fstat(descriptor)
                current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISREG(current.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    raise ValueError("runtime lock identity changed during readback")
            finally:
                os.close(descriptor)
        finally:
            os.close(parent_fd)


def _runtime_readback(target: str, project: str, *, check_execution: bool = True) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if check_execution:
        _read_execution_exclusions(target)
    # 不用 stale/PID/TTL 把未知 lease 当空闲；必须显式 released。
    try:
        descriptor, _ = output_paths._open_directory_chain(consumer_lease_dir(target), label="consumer lease directory")
    except FileNotFoundError:
        pass
    else:
        os.close(descriptor)
    leases = list_consumer_leases(target)
    if any(not item.get("releasedAt") for item in leases):
        raise ValueError("unreleased or unknown consumer lease blocks reconciliation")
    topology = _stackctl.load_environment_topology()
    manifest = _stackctl.load_port_manifest()
    profile = str(_stackctl.get_target(topology, target).get("portProfile") or "")
    endpoints = _stackctl.project_canonical_runtime_owned_ports(port_profile=profile, manifest=manifest)
    ports = _stackctl._runtime_owned_port_occupancy_report(
        target, published_ports=endpoints, topology=topology, manifest=manifest,
    )["publishedEndpoints"]
    if not ports or any(item.get("open") is not False for item in ports):
        raise ValueError("active or unknown runtime-owned endpoint blocks reconciliation")
    containers = _stackctl._mutable_test_live_container_ids(project)
    networks = _stackctl._mutable_test_live_resource_names("network", compose_project=project)
    volumes = _stackctl._mutable_test_live_resource_names("volume", compose_project=project)
    if containers or networks:
        raise ValueError(f"Compose project still owns containers/networks: {containers!r}/{networks!r}")
    return {"composeProject": project, "containers": containers, "networks": networks,
            "publishedEndpoints": ports, "preservedVolumes": volumes, "leases": leases,
            "priorExecutorFence": None, "executionSlot": None}


def _plan_path(value: Path) -> Path:
    path = value.absolute()
    if path.name != "worktree-startup-reconciliation-plan.json":
        raise ValueError("reconciliation plan must use its exact canonical filename")
    root = output_paths.env_runs_root("alpha").absolute()
    if not path.is_relative_to(root) or ".." in path.parts:
        raise ValueError("reconciliation plan must stay inside Alpha run evidence")
    descriptor, _ = output_paths._open_directory_chain(path.parent, label="reconciliation plan")
    os.close(descriptor)
    return path


def _archive_actions(inputs: list[dict[str, str]], plan_path: Path) -> list[dict[str, str]]:
    # 主 guard 最后离开原路径；部分移动仍保留 guard，绝不清理或隐式续跑。
    names = ("startup_attempt.json", "full-startup_attempt.json", "local_run.json")
    return [
        {**inputs[index], "destination": str(plan_path.parent / "archive" / names[index])}
        for index in (1, 2, 0)
    ]


def _move_originals(actions: list[dict[str, str]], plan_path: Path) -> None:
    archive = plan_path.parent / "archive"
    # 新建独占归档目录：既有目录（包括失败执行遗留）与 symlink 一律不接管。
    with contextlib.ExitStack() as scope:
        parent_fd, parent_ids = output_paths._open_directory_chain(plan_path.parent, label="archive parent")
        scope.callback(os.close, parent_fd)
        source_fds: list[tuple[int, tuple[tuple[int, int], ...]]] = []
        for action in actions:
            source = Path(action["source"])
            descriptor, identities = output_paths._open_directory_chain(source.parent, label="archive source")
            scope.callback(os.close, descriptor)
            source_fds.append((descriptor, identities))
            if os.fstat(descriptor).st_dev != os.fstat(parent_fd).st_dev:
                raise ValueError("archive must be on the source filesystem; copying/deletion is forbidden")
            if _digest(_required_bytes(source)) != action["digest"]:
                raise ValueError("reconciliation source bytes changed before archive")
        output_paths._revalidate_directory_chain(plan_path.parent, label="archive parent", expected_identities=parent_ids)
        os.mkdir(archive.name, 0o700, dir_fd=parent_fd)
        archive_fd = os.open(archive.name, output_paths._secure_directory_flags(), dir_fd=parent_fd)
        scope.callback(os.close, archive_fd)
        for action, (source_fd, identities) in zip(actions, source_fds, strict=True):
            source, destination = Path(action["source"]), Path(action["destination"])
            before = os.stat(source.name, dir_fd=source_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("reconciliation source changed to symlink or non-regular file")
            if _digest(_required_bytes(source)) != action["digest"]:
                raise ValueError("reconciliation source bytes changed during archive; preserve partial archive")
            output_paths._revalidate_directory_chain(source.parent, label="archive source", expected_identities=identities)
            output_paths._revalidate_directory_chain(plan_path.parent, label="archive parent", expected_identities=parent_ids)
            latest = os.stat(source.name, dir_fd=source_fd, follow_symlinks=False)
            if ((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
                    != (latest.st_dev, latest.st_ino, latest.st_mtime_ns, latest.st_ctime_ns)):
                raise ValueError("reconciliation source changed immediately before move")
            os.rename(source.name, destination.name, src_dir_fd=source_fd, dst_dir_fd=archive_fd)
            os.fsync(source_fd)
            os.fsync(archive_fd)
            after = os.stat(destination.name, dir_fd=archive_fd, follow_symlinks=False)
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                    or _digest(_required_bytes(destination)) != action["digest"]):
                raise ValueError("archive readback drifted; preserve partial archive")
        os.fsync(parent_fd)


def _reconcile_worktree_startup(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
    action = args.worktree_startup_reconciliation
    moved = False
    try:
        startup, inputs = _read_legacy_inputs(target)
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        if getattr(args, "orphaned_compose_attestation", "") or getattr(args, "confirm_orphaned_compose_teardown", False):
            raise ValueError("worktree reconciliation cannot be combined with Compose teardown")
        if action == "plan":
            if confirmed or plan_ref:
                raise ValueError("planning cannot consume apply confirmation or an existing plan")
            plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json")
            readback = _runtime_readback(target, startup["composeProject"])
            if _read_legacy_inputs(target)[1] != inputs:
                raise ValueError("legacy receipt bytes changed during live readback")
            _read_execution_exclusions(target)
            plan = {"schema": _PLAN_SCHEMA, "repository": str(output_paths.ROOT),
                    "target": target, "attemptId": startup["attemptId"], "readback": readback,
                    "actions": _archive_actions(inputs, plan_path)}
            raw = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            _write_transaction_journal_exclusive(plan_path, raw)
            exact_ref = f"{plan_path}={_digest(raw)}"
        elif action == "apply":
            if not confirmed or not plan_ref:
                raise ValueError("apply requires explicit confirmation and exact --worktree-startup-plan-ref PATH=sha256:DIGEST")
            path_text, expected_digest = plan_ref.rsplit("=", 1)
            plan_path = _plan_path(Path(path_text))
            raw = _required_bytes(plan_path)
            if _digest(raw) != expected_digest:
                raise ValueError("reconciliation plan digest changed")
            plan = json.loads(raw)
            if (not isinstance(plan, dict) or set(plan) != {"schema", "repository", "target", "attemptId", "readback", "actions"}
                    or plan["schema"] != _PLAN_SCHEMA or plan["repository"] != str(output_paths.ROOT)
                    or plan["target"] != target or plan["attemptId"] != startup["attemptId"]
                    or plan["actions"] != _archive_actions(inputs, plan_path)):
                raise ValueError("reconciliation plan identity/source/destination/digest changed")
            _read_execution_exclusions(target)
            with _stackctl._local_stack_operation_lock(target):
                if (_read_legacy_inputs(target)[1] != inputs
                        or _runtime_readback(target, startup["composeProject"], check_execution=False) != plan["readback"]
                        or _required_bytes(plan_path) != raw):
                    raise ValueError("reconciliation inputs or live resource readback changed since plan")
                _move_originals(plan["actions"], plan_path)
                moved = True
            exact_ref = plan_ref
        else:
            raise ValueError("unknown worktree reconciliation action")
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        return _blocked(report_dir=report_dir, target=target, details=[str(exc)],
                        summary="OPS.RUNTIME.reconcile_required: worktree reconciliation GATE_BLOCK")
    result = {"exitCode": 0, "status": "applied" if moved else "planned", "auditOnly": not moved,
              "planRef": exact_ref, "archived": moved, "destructiveRepairPerformed": False,
              "summary": "Alpha worktree startup reconciliation " + ("applied" if moved else "planned"),
              "details": ["only exact receipt originals may be moved; no container/network/volume/port mutation",
                          "apply requires reviewed exact plan ref and --confirm-undownable-startup-receipt-reclaim"],
              "reportDir": _stackctl.relpath(report_dir)}
    _stackctl.write_json(report_dir / "report.json", result)
    _stackctl._write_summary_bundle(report_dir, command="repair", target=target, status="ok",
                                   summary=result["summary"], details=result["details"])
    return result


def _blocked(
    *,
    report_dir: Path,
    target: str,
    details: list[str],
    summary: str,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    _stackctl._write_summary_bundle(
        report_dir,
        command="repair",
        target=target,
        status="failed",
        summary=summary,
        details=details,
    )
    return {
        "exitCode": 2,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
    }


def repair_undownable_startup_receipt(
    args: argparse.Namespace,
    *,
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Map the undownable receipt command onto the exact attestation protocol."""

    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
    if getattr(args, "worktree_startup_reconciliation", ""):
        return _reconcile_worktree_startup(args, report_dir=report_dir)
    if target not in _RECLAIMABLE_TARGETS:
        summary = (
            "reclaim-undownable-startup-receipt is only available for "
            + ", ".join(_RECLAIMABLE_TARGETS)
        )
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[summary],
            summary=summary,
        )

    confirmed = bool(
        getattr(args, "confirm_undownable_startup_receipt_reclaim", False)
    )
    attestation_value = str(
        getattr(args, "orphaned_compose_attestation", "") or ""
    ).strip()
    if confirmed and not attestation_value:
        summary = "undownable receipt confirmation requires the planned attestation"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[
                summary,
                "pass --orphaned-compose-attestation with the exact path returned by the planning run",
            ],
            summary=summary,
        )
    if not attestation_value:
        attestation_value = str(report_dir / _ATTESTATION_NAME)

    delegated = argparse.Namespace(**vars(args))
    delegated.orphaned_compose_attestation = attestation_value
    delegated.confirm_orphaned_compose_teardown = confirmed
    return _stackctl._repair_orphaned_compose(
        delegated,
        environment=environment,
        report_dir=report_dir,
    )
