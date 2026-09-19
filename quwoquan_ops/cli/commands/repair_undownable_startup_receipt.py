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
import re
import stat
from datetime import datetime
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
_PLAN_SCHEMA = "stackctl-local-worktree-startup-reconciliation"


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


def _read_archived_worktree_inputs(target: str, *, recovery: bool = False) -> tuple[dict[str, Any], list[dict[str, str]]]:
    paths = output_paths.archived_worktree_startup_paths(target)
    encoded = [_required_bytes(path) for path in paths]
    startup, duplicate, local_run = [json.loads(item) for item in encoded]
    if not isinstance(startup, dict) or startup != duplicate or encoded[0] != encoded[1]:
        raise ValueError("archived worktree startup receipt copies differ in identity or exact bytes")
    statuses = {"stopped", "running"} if recovery else {"stopped"}
    if startup.get("status") not in statuses or startup.get("workload") != "full":
        raise ValueError("archived worktree reconciliation only admits consistent stopped/full receipts or explicit running recovery")
    # 只复用旧对象的身份/摘要校验；旧 runRoot 不能送入宿主 canonical 路径校验。
    # 原件不改写，原始 runRoot 与 local_run 在下方按 exact repo 路径独立验证。
    environment = output_paths.env_for_target(target)
    validate_startup_attempt({**startup, "runRoot": ""}, expected_env=environment, expected_target=target)
    run_id = startup["attemptId"]
    if not isinstance(run_id, str) or output_paths.safe_segment(run_id) != run_id:
        raise ValueError("archived worktree attemptId is not one exact path segment")
    root = output_paths.ROOT / ".qwq_output/env" / environment
    run_root = root / "runs" / run_id
    observability = root / "observability" / run_id
    expected_binding = {
        "env": environment, "target": target, "runId": run_id,
        "runRoot": str(run_root), "observabilityRoot": str(observability),
    }
    if local_run != expected_binding or startup.get("runRoot") != str(run_root):
        raise ValueError("archived worktree local_run binding differs from exact repository runRoot")
    for directory in (run_root, observability):
        descriptor, _ = output_paths._open_directory_chain(directory, label="archived worktree run binding")
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


def _plan_path(value: Path, *, target: str) -> Path:
    path = value.absolute()
    if path.name != "worktree-startup-reconciliation-plan.json":
        raise ValueError("reconciliation plan must use its exact canonical filename")
    environment = output_paths.env_for_target(target)
    root = output_paths.env_runs_root(environment).absolute()
    if not path.is_relative_to(root) or ".." in path.parts:
        raise ValueError(f"reconciliation plan must stay inside {environment} run evidence")
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


@contextlib.contextmanager
def _fence_reconciliation_locks(target: str):
    """按host→target取得现有锁，绝不创建/替换executor fence。"""
    with contextlib.ExitStack() as scope:
        for path, mode in ((local_runtime_operation_lock_path(), fcntl.LOCK_SH),
                           (local_runtime_operation_lock_path(target), fcntl.LOCK_EX)):
            parent, identities = output_paths._open_directory_chain(path.parent, label="fence reconciliation lock")
            scope.callback(os.close, parent)
            fd = os.open(path.name, output_paths._secure_file_flags(write=False), dir_fd=parent)
            scope.callback(os.close, fd)
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
            output_paths._revalidate_directory_chain(path.parent, label="fence lock", expected_identities=identities)
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("fence lock identity changed")
        yield


def _validate_failed_planning_report(target: str, report: dict[str, Any]) -> str:
    """只接受尚未产生资源执行事实的已知计划失败。"""
    allowed_reasons = {
        "canonical startup receipt is unreadable: OPS.RUNTIME.reconcile_required: worktree-local startup receipt requires explicit reconciliation",
        f"no exact project is discoverable for orphan Compose target {target}",
    }
    details = report.get("details")
    if not isinstance(details, list) or len(details) != 1 or details[0] not in allowed_reasons:
        raise ValueError("failure is not a known pre-resource planning rejection")
    if (report.get("target") != target or report.get("command") != "repair"
            or report.get("fix") != "reclaim-undownable-startup-receipt"
            or report.get("status") != "gate_block" or report.get("destructiveRepairPerformed") is not False
            or report.get("destructiveRepairOutcome") != "none" or report.get("steps") != []
            or report.get("executionJournal") != "" or report.get("consumption") != ""):
        raise ValueError("report does not prove exact pre-resource startup-guard rejection")
    return details[0]


def _validate_failed_executor(target: str, path: Path, fence: dict[str, Any], reason: str) -> str:
    """时间与失败事实绑定后再验证执行者已结束，不以PID单独授权。"""
    owner = str(fence.get("owner", ""))
    match = re.fullmatch(r"pid=([1-9][0-9]*) target=(\S+) startedAt=(\S+) worktree=(\S+) lane=(\S+) headSha=([0-9a-f]{40})", owner)
    if not match or match[2] != target or match[4] != str(output_paths.ROOT) or fence.get("executionClaimId") != "":
        raise ValueError("fence executor identity is not an unclaimed invocation in this worktree")
    summary_raw = _required_bytes(path.with_name("summary.json"))
    summary = json.loads(summary_raw)
    started = datetime.fromisoformat(match[3].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(summary["generatedAt"].replace("Z", "+00:00"))
    if (summary.get("target") != target or summary.get("command") != "repair"
            or summary.get("details") != [reason] or not 0 <= (ended - started).total_seconds() <= 5):
        raise ValueError("failure report does not bind fence execution time")
    try:
        os.kill(int(match[1]), 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("prior executor still exists; no fence takeover")
    return _digest(summary_raw)


def _failed_guard_report(target: str, exact_ref: str, fence: dict[str, Any]) -> dict[str, str]:
    text, expected_digest = exact_ref.rsplit("=", 1)
    path = Path(text).absolute()
    output_paths.validate_env_run_evidence_dir(path.parent, env_name=output_paths.env_for_target(target))
    if path.name != "report.json":
        raise ValueError("fence reconciliation requires exact report.json")
    raw = _required_bytes(path)
    report = json.loads(raw)
    if _digest(raw) != expected_digest or not isinstance(report, dict):
        raise ValueError("report does not prove exact pre-resource startup-guard rejection")
    reason = _validate_failed_planning_report(target, report)
    for name in (_ATTESTATION_NAME, "orphaned-compose-teardown-journal.json", "orphaned-compose-teardown-consumption.json"):
        _require_absent(path.parent / name)
    summary_digest = _validate_failed_executor(target, path, fence, reason)
    return {"ref": str(path), "digest": expected_digest, "summaryDigest": summary_digest}


def _fence_reconciliation_inputs(target: str, report_ref: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as stackctl

    startup, originals = _read_archived_worktree_inputs(target, recovery=True)
    path = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
    raw = _required_bytes(path)
    fence = json.loads(raw)
    if set(fence) != {"target", "executorNonce", "owner", "executionClaimId"} or fence["target"] != target:
        raise ValueError("executor fence shape/target mismatch")
    failure = _failed_guard_report(target, report_ref, fence)
    _require_absent(output_paths.deployment_target_path(target, "process", "environment-execution", "execution-slot.json"))
    if any(not item.get("releasedAt") for item in list_consumer_leases(target)):
        raise ValueError("unreleased lease blocks fence reconciliation")
    project = startup["composeProject"]
    # 只清理零mutation调用遗留的fence；旧栈资源本身保留并绑定，随后单独授权恢复。
    resources = {"containers": sorted(stackctl._mutable_test_live_container_ids(project)),
                 "networks": sorted(stackctl._mutable_test_live_resource_names("network", compose_project=project)),
                 "volumes": sorted(stackctl._mutable_test_live_resource_names("volume", compose_project=project))}
    return {"target": target, "fence": {"source": str(path), "digest": _digest(raw)},
            "failure": failure, "originals": originals, "resources": resources}


def _reconcile_failed_executor(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    target = str(args.target)
    applying = args.worktree_startup_reconciliation == "fence-apply"
    try:
        report_ref = str(getattr(args, "failed_repair_report_ref", "") or "")
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        if not report_ref or applying != confirmed or applying != bool(plan_ref):
            raise ValueError("fence apply requires report, exact plan and explicit confirmation; plan takes report only")
        with _fence_reconciliation_locks(target):
            inputs = _fence_reconciliation_inputs(target, report_ref)
            if applying:
                text, expected = plan_ref.rsplit("=", 1)
                plan_path = _plan_path(Path(text), target=target)
                raw = _required_bytes(plan_path)
                if _digest(raw) != expected or json.loads(raw) != {"schema": _PLAN_SCHEMA + "-fence", **inputs}:
                    raise ValueError("fence reconciliation plan or live inputs changed")
                action = {**inputs["fence"], "destination": str(plan_path.parent / "archive/executor-fence.json")}
                if _fence_reconciliation_inputs(target, report_ref) != inputs:
                    raise ValueError("fence inputs drifted before archive")
                _move_originals([action], plan_path)
            else:
                plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json", target=target)
                raw = (json.dumps({"schema": _PLAN_SCHEMA + "-fence", **inputs}, sort_keys=True, indent=2) + "\n").encode()
                _write_transaction_journal_exclusive(plan_path, raw)
                plan_ref = f"{plan_path}={_digest(raw)}"
        return {"exitCode": 0, "summary": "failed executor fence " + ("archived" if applying else "reconciliation planned"),
                "planRef": plan_ref, "destructiveRepairPerformed": False,
                "details": [plan_ref, "runtime resources and startup originals preserved"], "reportDir": str(report_dir)}
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
        return _blocked(report_dir=report_dir, target=target, details=[str(error)],
                        summary="OPS.RUNTIME.executor_reconcile_required: fence reconciliation blocked")


_OWNER_PATTERN = re.compile(r"pid=([1-9][0-9]*) target=(\S+) startedAt=(\S+) worktree=(\S+) lane=(\S+) headSha=([0-9a-f]{40})")


def _takeover_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Freeze an alpha-local-only CAS handoff without weakening other fences."""
    from quwoquan_ops.cli.lib.candidate_evidence import validate_candidate_ref

    target = str(args.target)
    if target != "alpha-local" or os.environ.get("QWQ_OUTPUT_ROOT"):
        raise ValueError("executor takeover is available only for canonical alpha-local")
    fence_path = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
    raw = _required_bytes(fence_path)
    fence = json.loads(raw)
    expected_ref = str(getattr(args, "executor_fence_ref", "") or "")
    if expected_ref != f"{fence_path}={_digest(raw)}":
        raise ValueError("executor takeover requires the exact current fence digest")
    if set(fence) != {"target", "executorNonce", "owner", "executionClaimId"} or fence.get("target") != target:
        raise ValueError("executor takeover fence shape/target mismatch")
    owner = str(fence.get("owner") or "")
    match = _OWNER_PATTERN.fullmatch(owner)
    if not match or match[2] != target:
        raise ValueError("executor takeover previous owner is malformed")
    expected_owner = str(getattr(args, "expected_previous_owner", "") or "")
    expected_worktree = str(getattr(args, "expected_previous_worktree", "") or "")
    expected_lane = str(getattr(args, "expected_previous_lane", "") or "")
    if expected_owner != owner or expected_worktree != match[4] or expected_lane != match[5]:
        raise ValueError("executor takeover previous owner/worktree/lane CAS mismatch")
    try:
        os.kill(int(match[1]), 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("executor still exists; takeover denied")
    _require_absent(output_paths.deployment_target_path(target, "process", "environment-execution", "execution-slot.json"))
    # A stale consumer lease can only be released through the normal consumer
    # command after this executor fence is archived. Takeover does not mutate
    # device/runtime resources; the lease keeps its own exact generation CAS.
    candidate_ref = str(getattr(args, "candidate_evidence", "") or "")
    canonical_ref, candidate_raw, candidate, _ = validate_candidate_ref(candidate_ref, repo_root=output_paths.ROOT)
    current = output_paths._read_secure_json_object(fence_path, label="target executor fence")
    if current != fence:
        raise ValueError("executor takeover fence changed during validation")
    return {
        "target": target,
        "previousFence": {"source": str(fence_path), "digest": _digest(raw), "owner": owner, "executorNonce": fence["executorNonce"]},
        "expectedPrevious": {"worktree": expected_worktree, "lane": expected_lane},
        "candidateEvidence": {"ref": canonical_ref, "digest": _digest(candidate_raw), "leadLane": candidate["lead_lane"]},
        "executorInactive": True,
    }


def _reconcile_takeover(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    applying = args.worktree_startup_reconciliation == "takeover-apply"
    try:
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        if applying != confirmed or applying != bool(plan_ref):
            raise ValueError("takeover apply requires exact plan and explicit confirmation")
        with _fence_reconciliation_locks(str(args.target)):
            inputs = _takeover_inputs(args)
            payload = {"schema": _PLAN_SCHEMA + "-takeover", **inputs}
            if applying:
                text, digest = plan_ref.rsplit("=", 1)
                plan_path = _plan_path(Path(text), target=str(args.target))
                raw = _required_bytes(plan_path)
                if _digest(raw) != digest or json.loads(raw) != payload:
                    raise ValueError("executor takeover plan or expected inputs changed")
                if _takeover_inputs(args) != inputs:
                    raise ValueError("executor takeover inputs drifted before CAS")
                fence_path = Path(inputs["previousFence"]["source"])
                archive = plan_path.parent / "archive"
                _move_originals([{
                    "source": str(fence_path),
                    "digest": inputs["previousFence"]["digest"],
                    "destination": str(archive / "previous-executor-fence.json"),
                }], plan_path)
                receipt = {
                    "schema": "stackctl-executor-takeover-receipt-v1",
                    **inputs,
                    "newOwner": {"worktree": str(output_paths.ROOT), "lane": inputs["candidateEvidence"]["leadLane"]},
                    "status": "applied",
                }
                receipt_path = plan_path.parent / "executor-takeover-receipt.json"
                _write_transaction_journal_exclusive(receipt_path, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
                receipt_ref = f"{receipt_path}={_digest(_required_bytes(receipt_path))}"
            else:
                plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json", target=str(args.target))
                raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
                _write_transaction_journal_exclusive(plan_path, raw)
                plan_ref = f"{plan_path}={_digest(raw)}"
                receipt_ref = ""
        return {"exitCode": 0, "summary": "alpha-local executor takeover " + ("applied" if applying else "planned"),
                "planRef": plan_ref, "receiptRef": receipt_ref, "details": [plan_ref] + ([receipt_ref] if receipt_ref else []),
                "destructiveRepairPerformed": False, "reportDir": str(report_dir)}
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        return _blocked(report_dir=report_dir, target=str(args.target), details=[str(error)],
                        summary="OPS.RUNTIME.executor_reconcile_required: managed takeover blocked")


def _current_fence_inputs(target: str, exact_ref: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as stackctl

    if target not in _RECLAIMABLE_TARGETS or os.environ.get("QWQ_OUTPUT_ROOT"):
        raise ValueError("current fence recovery requires canonical local runtime authority")
    text, digest = exact_ref.rsplit("=", 1)
    path = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
    if Path(text).absolute() != path.absolute():
        raise ValueError("executor fence path differs from selected target")
    raw = _required_bytes(path)
    fence = json.loads(raw)
    if (_digest(raw) != digest or set(fence) != {"target", "executorNonce", "owner", "executionClaimId"}
            or fence["target"] != target or not fence["executorNonce"] or fence["executionClaimId"]):
        raise ValueError("executor fence exact identity is invalid")
    match = re.fullmatch(r"pid=([1-9][0-9]*) target=(\S+) startedAt=(\S+) worktree=(\S+) lane=(\S+) headSha=([0-9a-f]{40})", fence["owner"])
    if not match or match[2] != target or match[4] != str(output_paths.ROOT):
        raise ValueError("executor owner is not this worktree/target")
    try:
        os.kill(int(match[1]), 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("executor still exists; recovery denied")
    process = output_paths.target_process_dir(target)
    originals = []
    startup = None
    for relative in ("startup_attempt.json", "workloads/full/startup_attempt.json"):
        source = process / relative
        encoded = _required_bytes(source)
        value = validate_startup_attempt(json.loads(encoded), expected_target=target)
        if startup is not None and value != startup:
            raise ValueError("canonical startup copies differ")
        if value["workload"] != "full":
            raise ValueError("current fence recovery only supports full runtime")
        startup = value
        originals.append({"source": str(source), "digest": _digest(encoded)})
    for relative in ("test_live_startup_attempt.json", ".startup_attempt.json.fanout-transaction.json"):
        _require_absent(process / relative)
    _require_absent(output_paths.deployment_target_path(target, "process", "environment-execution", "execution-slot.json"))
    resources = _runtime_readback(target, startup["composeProject"], check_execution=False)
    mutable = stackctl.orphan_compose_teardown.mutable_test_live_project(target)
    if stackctl._mutable_test_live_container_ids(mutable) or stackctl._mutable_test_live_resource_names("network", compose_project=mutable):
        raise ValueError("test-live resources block current fence recovery")
    return {"target": target, "fence": {"source": str(path), "digest": digest},
            "startup": originals, "resources": resources}


def _reconcile_current_fence(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    target = str(args.target)
    applying = args.worktree_startup_reconciliation == "current-fence-apply"
    try:
        fence_ref = str(getattr(args, "executor_fence_ref", "") or "")
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        if not fence_ref or applying != confirmed or applying != bool(plan_ref):
            raise ValueError("current fence apply requires exact fence/plan and explicit confirmation")
        with _fence_reconciliation_locks(target):
            inputs = _current_fence_inputs(target, fence_ref)
            payload = {"schema": _PLAN_SCHEMA + "-current-fence", **inputs}
            if applying:
                text, digest = plan_ref.rsplit("=", 1)
                plan_path = _plan_path(Path(text), target=target)
                raw = _required_bytes(plan_path)
                if _digest(raw) != digest or json.loads(raw) != payload:
                    raise ValueError("current fence plan or live inputs changed")
                if _current_fence_inputs(target, fence_ref) != inputs:
                    raise ValueError("current fence inputs changed before archive")
                _move_originals([{**inputs["fence"], "destination": str(plan_path.parent / "archive/executor-fence.json")}], plan_path)
            else:
                plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json", target=target)
                raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
                _write_transaction_journal_exclusive(plan_path, raw)
                plan_ref = f"{plan_path}={_digest(raw)}"
        return {"exitCode": 0, "summary": "current executor fence " + ("archived" if applying else "planned"),
                "planRef": plan_ref, "details": [plan_ref, "startup bytes and named volumes preserved; no resource deletion"],
                "destructiveRepairPerformed": False, "reportDir": str(report_dir)}
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        return _blocked(report_dir=report_dir, target=target, details=[str(error)],
                        summary="OPS.RUNTIME.executor_reconcile_required: current fence recovery blocked")


def _recovery_plan_identity(target: str, startup: dict[str, Any], inputs: list[dict[str, str]], digest: str) -> dict[str, Any]:
    return {"schema": _PLAN_SCHEMA + "-recovery", "repository": str(output_paths.ROOT),
            "target": target, "inputs": inputs, "attemptId": startup["attemptId"],
            "attestationDigest": digest}


def _owned_recovery_fence(target: str) -> None:
    fence_path = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
    raw = output_paths._read_secure_bytes(fence_path, label="current recovery executor fence")
    if raw is None:
        return
    fence = json.loads(raw)
    if (not isinstance(fence, dict) or fence.get("target") != target
            or not str(fence.get("owner", "")).startswith(f"pid={os.getpid()} ")
            or not fence.get("executorNonce")):
        raise ValueError("worktree recovery does not own the current executor fence")


def _recovery_gate(target: str, startup: dict[str, Any], inputs: list[dict[str, str]],
                   plan_path: Path, raw: bytes | None, attestation_path: Path,
                   plan: dict[str, Any]) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as stackctl

    if _read_archived_worktree_inputs(target, recovery=True)[1] != inputs:
        raise ValueError("worktree startup originals changed before resource recovery")
    _owned_recovery_fence(target)
    _require_absent(output_paths.deployment_target_path(target, "process", "environment-execution", "execution-slot.json"))
    if any(not lease.get("releasedAt") for lease in list_consumer_leases(target)):
        raise ValueError("unreleased consumer lease blocks worktree recovery")
    if not stackctl._normal_down_structurally_impossible(target, startup):
        raise ValueError("candidate-bound normal down became available")
    if raw is not None:
        if _required_bytes(plan_path) != raw:
            raise ValueError("worktree recovery plan changed before mutation")
        attestation = stackctl.orphan_compose_teardown.load_attestation(
            attestation_path, allowed_root=output_paths.env_runs_root(output_paths.env_for_target(target)),
            expected_target=target, allow_expired=True,
        )
        if attestation["attestationDigest"] != plan["attestationDigest"]:
            raise ValueError("worktree recovery attestation changed")
    return {"startup": startup, "staleMutableStartup": None, "expectedProject": startup["composeProject"]}


def _recover_worktree_startup(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    """绑定旧原件的显式恢复；复用 orphan 执行器，不改写任何 startup 原件。"""
    import quwoquan_ops.cli.stackctl as stackctl
    from .repair_runtime_recovery import _repair_orphaned_compose

    target = str(args.target)
    applying = args.worktree_startup_reconciliation == "recover-apply"
    try:
        startup, inputs = _read_archived_worktree_inputs(target, recovery=True)
        _read_execution_exclusions(target)
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        if applying != confirmed or applying != bool(plan_ref):
            raise ValueError("recovery apply requires explicit confirmation and exact plan; planning accepts neither")
        if getattr(args, "orphaned_compose_attestation", "") or getattr(args, "confirm_orphaned_compose_teardown", False):
            raise ValueError("worktree recovery derives its own exact orphan attestation")
        if startup["status"] != "running":
            raise ValueError("worktree recovery requires running/full; stopped receipts use archive plan/apply")
        if not stackctl._normal_down_structurally_impossible(target, startup):
            raise ValueError("candidate-bound normal down remains available; orphan recovery denied")
        if applying:
            text, expected_digest = plan_ref.rsplit("=", 1)
            plan_path = _plan_path(Path(text), target=target)
            raw = _required_bytes(plan_path)
            if _digest(raw) != expected_digest:
                raise ValueError("worktree recovery plan digest changed")
            plan = json.loads(raw)
            expected = _recovery_plan_identity(target, startup, inputs, plan.get("attestationDigest"))
            if plan != expected:
                raise ValueError("worktree recovery source or plan identity changed")
        else:
            plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json", target=target)
            if plan_path.exists():
                raise ValueError("worktree recovery plan slot already exists")
            plan = {}
            raw = None
        attestation_path = plan_path.parent / _ATTESTATION_NAME

        def gate() -> dict[str, Any]:
            # 执行器已持有target锁，只重验原件及本次fence。
            return _recovery_gate(target, startup, inputs, plan_path, raw, attestation_path, plan)

        delegated = argparse.Namespace(**vars(args))
        delegated.orphaned_compose_attestation = str(attestation_path)
        delegated.confirm_orphaned_compose_teardown = applying
        result = _repair_orphaned_compose(delegated, environment=output_paths.env_for_target(target),
                                         report_dir=report_dir, worktree_recovery_gate=gate)
        if result["exitCode"] != 0:
            return result
        if not applying:
            attestation = stackctl.orphan_compose_teardown.load_attestation(
                attestation_path, allowed_root=output_paths.env_runs_root(output_paths.env_for_target(target)), expected_target=target,
            )
            plan = _recovery_plan_identity(target, startup, inputs, attestation["attestationDigest"])
            raw = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            _write_transaction_journal_exclusive(plan_path, raw)
            return {**result, "planRef": f"{plan_path}={_digest(raw)}", "archived": False}
        # orphan 的成功终态已经验证exact journal/step/consumption；再次检查零资源再归档。
        _read_execution_exclusions(target)
        with stackctl._local_stack_operation_lock(target):
            gate()
            _runtime_readback(target, startup["composeProject"], check_execution=False)
            _move_originals(_archive_actions(inputs, plan_path), plan_path)
        result = {**result, "planRef": plan_ref, "archived": True,
                  "summary": f"{target} exact resource recovery and worktree startup archive completed"}
        stackctl.write_json(report_dir / "worktree-recovery-result.json", result)
        return result
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        return _blocked(report_dir=report_dir, target=target, details=[str(error)],
                        summary="OPS.RUNTIME.reconcile_required: worktree recovery incomplete; preserve originals and resource journal")


def _reconcile_worktree_startup(args: argparse.Namespace, *, report_dir: Path) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
    action = args.worktree_startup_reconciliation
    moved = False
    try:
        startup, inputs = _read_archived_worktree_inputs(target)
        plan_ref = str(getattr(args, "worktree_startup_plan_ref", "") or "")
        confirmed = bool(getattr(args, "confirm_undownable_startup_receipt_reclaim", False))
        if getattr(args, "orphaned_compose_attestation", "") or getattr(args, "confirm_orphaned_compose_teardown", False):
            raise ValueError("worktree reconciliation cannot be combined with Compose teardown")
        if action == "plan":
            if confirmed or plan_ref:
                raise ValueError("planning cannot consume apply confirmation or an existing plan")
            plan_path = _plan_path(report_dir / "worktree-startup-reconciliation-plan.json", target=target)
            readback = _runtime_readback(target, startup["composeProject"])
            if _read_archived_worktree_inputs(target)[1] != inputs:
                raise ValueError("archived worktree receipt bytes changed during live readback")
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
            plan_path = _plan_path(Path(path_text), target=target)
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
                if (_read_archived_worktree_inputs(target)[1] != inputs
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
              "summary": f"{target} worktree startup reconciliation " + ("applied" if moved else "planned"),
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
    if getattr(args, "worktree_startup_reconciliation", "") in {"takeover-plan", "takeover-apply"}:
        return _reconcile_takeover(args, report_dir=report_dir)
    if getattr(args, "worktree_startup_reconciliation", "") in {"current-fence-plan", "current-fence-apply"}:
        return _reconcile_current_fence(args, report_dir=report_dir)
    if getattr(args, "worktree_startup_reconciliation", "") in {"fence-plan", "fence-apply"}:
        return _reconcile_failed_executor(args, report_dir=report_dir)
    if getattr(args, "worktree_startup_reconciliation", "") in {"recover-plan", "recover-apply"}:
        return _recover_worktree_startup(args, report_dir=report_dir)
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
