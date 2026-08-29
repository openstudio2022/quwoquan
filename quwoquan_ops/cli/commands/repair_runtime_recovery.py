"""stackctl repair 运行时恢复域: 操作锁、端口释放探测与 orphan compose 收敛。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- production release 锁与本机全局 scope wrapper；
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
import time

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


def _normal_down_structurally_impossible(
    target_name: str,
    startup: Mapping[str, Any],
) -> str:
    """Name the defect that makes candidate-bound down unusable for this receipt.

    Normal down replays the receipt's own candidate topology under the receipt's
    own workload, so it is objectively impossible in two shapes. The candidate
    may be gone or unreadable, which is what a reclaim of the candidate store
    leaves behind. Or the candidate may still project into a service carrying
    neither an image nor a build context and no gating profile, which makes
    `docker compose` reject the whole project. Either way down can never
    converge while up refuses to run before down, so the receipt is frozen
    evidence no governed path can retire.

    A non-empty reason is the objective evidence that the orphan path is the
    only remaining governed exit; "" keeps the normal path mandatory. An
    unreadable candidate must never collapse into "": that would report the
    normal path as usable precisely when it cannot work.
    """

    import yaml

    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.runtime_topology_package import (
        RuntimeTopologyPackageError,
        load_runtime_topology_package,
    )

    candidate_digest = str(startup.get("candidateDigest") or "").strip()
    workload = str(startup.get("workload") or "full").strip()
    if not candidate_digest:
        return ""
    try:
        candidate_root = _stackctl.deployment_candidate_dir(
            target_name,
            candidate_digest,
        ).resolve()
    except ValueError:
        # 非法 digest 说明回执自身损坏，而不是 candidate 被回收；这不是本出口的
        # 判据，仍然交给 normal down 报出它自己的身份校验失败。
        return ""
    if not candidate_root.is_dir():
        return (
            f"candidate {candidate_digest} is no longer present at "
            f"{candidate_root}; the receipt's own topology cannot be replayed"
        )
    try:
        topology = load_runtime_topology_package(
            candidate_root,
            environment=target_name.removesuffix("-local"),
            target=target_name,
            workload=workload,
        )
    except (OSError, RuntimeTopologyPackageError, ValueError) as exc:
        return (
            f"candidate {candidate_digest} cannot project workload={workload} "
            f"into a runtime topology: {exc}"
        )
    merged: dict[str, dict[str, Any]] = {}
    for path in topology["composeFiles"]:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            return (
                f"candidate {candidate_digest} carries an unreadable Compose "
                f"file {path}: {exc}"
            )
        if not isinstance(document, Mapping):
            return (
                f"candidate {candidate_digest} Compose file {path} is not a "
                "mapping document"
            )
        for name, definition in (document.get("services") or {}).items():
            if isinstance(definition, Mapping):
                merged.setdefault(str(name), {}).update(definition)
    broken = sorted(
        name
        for name, definition in merged.items()
        if "image" not in definition
        and "build" not in definition
        and not definition.get("profiles")
    )
    if not broken:
        return ""
    return (
        f"candidate {candidate_digest} projects workload={workload} into an "
        "invalid Compose project; services without image, build or gating "
        "profile: " + ",".join(broken)
    )


def _close_orphan_reclaimed_startup_receipt(
    target_name: str,
    startup: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, str]:
    """Retire a non-stopped receipt whose runtime the orphan path just removed.

    A receipt admitted through the structurally-impossible-down exit still
    claims live resources after teardown removed them, whether the exit was
    taken because the candidate is gone or because it projected an invalid
    Compose project. Leaving it non-stopped would keep blocking every later up,
    so the receipt is transitioned to stopped with the reclaim named as its
    failure. Already-stopped receipts and absent receipts need nothing.
    """

    import quwoquan_ops.cli.stackctl as _stackctl

    if startup is None:
        return None, ""
    if not isinstance(startup, Mapping):
        raise ValueError("startup receipt must be an object")
    status = str(startup.get("status") or "").strip()
    if status == "stopped":
        return startup, ""
    attempt_id = str(startup.get("attemptId") or "").strip()
    if not attempt_id:
        raise ValueError("non-stopped startup receipt requires attemptId")
    stopped = _stackctl.transition_startup_attempt(
        env=str(startup.get("env") or target_name.removesuffix("-local")),
        target=target_name,
        attempt_id=attempt_id,
        status="stopped",
        failure=(
            "reclaimed by governed orphan Compose teardown; candidate-bound "
            "down was structurally impossible for this receipt"
        ),
    )
    return stopped, f"retired startup receipt status={status} attempt={attempt_id}"


def _orphan_compose_runtime_gate(target_name: str) -> dict[str, Any] | None:
    """Return the receipt when normal candidate-bound down cannot apply.

    An absent or stopped receipt claims nothing, so exact-resource recovery owns
    the residue outright. A non-stopped receipt still claims the runtime, and it
    keeps priority: recovery is admitted only when that receipt's own candidate
    is objectively unusable, never on an operator's word. Otherwise the residue
    belongs to candidate-bound normal down.
    """
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
    if status != "stopped" and not _stackctl._normal_down_structurally_impossible(
        target_name,
        startup,
    ):
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

    snapshot = attestation.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose attestation snapshot is missing"
        )
    published_endpoints = (
        _stackctl.orphan_compose_teardown._normalize_published_endpoints(
            snapshot.get("publishedEndpoints")
        )
    )
    if not published_endpoints:
        return
    occupied = _stackctl._wait_for_published_endpoints_released(
        published_endpoints
    )
    if occupied:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "attested project published endpoints remain occupied after bounded "
            "teardown wait: "
            + ", ".join(
                f"{item['role']}:{item['hostPort']}/{item['protocol']}"
                for item in occupied
            )
        )


def _complete_orphan_compose_audit_convergence(
    *,
    target_name: str,
    attestation_path: Path,
    attestation: Mapping[str, Any],
    consumption: Mapping[str, Any],
    canonical_ports: Sequence[Mapping[str, Any]],
    port_manifest: dict[str, Any],
    port_profile: str,
    other_target_port_blocks: Sequence[Mapping[str, Any]],
    report_dir: Path,
    startup: Mapping[str, Any] | None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    _stackctl._wait_for_attested_orphan_compose_ports_released(target_name, attestation)
    post_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
        target=target_name,
        project=str(attestation.get("project") or ""),
        canonical_ports=canonical_ports,
        port_manifest=port_manifest,
        port_profile=port_profile,
        run_command=_stackctl.run,
        require_removable=False,
        other_target_port_blocks=other_target_port_blocks,
        port_probe=_stackctl._published_endpoint_is_occupied,
    )
    _stackctl.orphan_compose_teardown.assert_post_teardown_state(
        attestation,
        post_snapshot,
        port_probe=_stackctl._published_endpoint_is_occupied,
    )
    canonical_startup, closure = _stackctl._close_orphan_reclaimed_startup_receipt(
        target_name,
        startup,
    )
    convergence_path = attestation_path.with_name(
        "orphaned-compose-teardown-convergence.json"
    )
    convergence_ref = _stackctl.relpath(convergence_path)
    report_dir_ref = _stackctl.relpath(report_dir)
    summary = f"stackctl orphan Compose audit convergence passed for {target_name}"
    details = [
        "audit-only convergence completed; no Docker removal command was executed",
        f"partialConsumptionDigest={consumption['consumptionDigest']}",
        f"convergence={convergence_ref}",
    ]
    if closure:
        details.append(closure)
    report = {
        "command": "repair",
        "target": target_name,
        "fix": "reclaim-orphaned-compose",
        "status": "passed",
        "auditOnly": True,
        "destructiveRepairPerformed": False,
        "startupAttempt": canonical_startup,
        "attestation": _stackctl.relpath(attestation_path),
        "attestationDigest": attestation["attestationDigest"],
        "consumptionDigest": consumption["consumptionDigest"],
        "convergence": convergence_ref,
        "details": details,
    }
    _stackctl.orphan_compose_teardown.write_convergence_create_once(
        attestation_path,
        attestation=attestation,
        consumption=consumption,
        current_snapshot=post_snapshot,
    )
    publication_issues = _stackctl._publish_orphan_terminal_success(
        report_dir=report_dir,
        target_name=target_name,
        summary=summary,
        details=details,
        report=report,
    )
    # 终态成功事实不因派生报告发布失败而降级，但发布问题必须留在 details 里可读；
    # 这里显式收敛，避免依赖被调用方对 details 的原地修改。
    details.extend(issue for issue in publication_issues if issue not in details)
    return {
        "exitCode": 0,
        "summary": summary,
        "details": details,
        "reportDir": report_dir_ref,
        "convergence": convergence_ref,
    }


def _commit_orphan_compose_terminal_consumption(
    *,
    target_name: str,
    fix: str,
    attestation_path: Path,
    attestation: Mapping[str, Any],
    startup: Mapping[str, Any] | None,
    execution_journal: Path,
    destructive_steps: Sequence[Mapping[str, Any]],
    report_dir: Path,
    recovered_execution: bool,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    snapshot = attestation["snapshot"]
    container_ids = [item["id"] for item in snapshot["containers"]]
    network_ids = [item["id"] for item in snapshot["networks"]]
    canonical_startup, closure = _stackctl._close_orphan_reclaimed_startup_receipt(
        target_name,
        startup,
    )
    consumption_path = attestation_path.with_name(
        "orphaned-compose-teardown-consumption.json"
    )
    consumption_ref = _stackctl.relpath(consumption_path)
    journal_ref = _stackctl.relpath(execution_journal)
    report_dir_ref = _stackctl.relpath(report_dir)
    summary = (
        f"stackctl reconciled exact orphan Compose removal for {target_name}"
        if recovered_execution
        else f"stackctl removed exact orphan Compose resources for {target_name}"
    )
    details = [
        (
            "reconciled completed exact removal from create-once journal and step receipts; "
            "no Docker removal command was replayed"
            if recovered_execution
            else f"removed exact attested containers={','.join(container_ids) or 'none'}"
        ),
        f"removed exact attested networks={','.join(network_ids) or 'none'}",
        "preserved named volumes="
        + (",".join(item["name"] for item in snapshot["volumes"]) or "none"),
        f"consumption={consumption_ref}",
    ]
    if closure:
        details.append(closure)
    report = {
        "command": "repair",
        "target": target_name,
        "fix": fix,
        "status": "passed",
        "destructiveRepairPerformed": True,
        "startupAttempt": canonical_startup,
        "attestation": _stackctl.relpath(attestation_path),
        "attestationDigest": attestation["attestationDigest"],
        "consumption": consumption_ref,
        "executionJournal": journal_ref,
        "steps": list(destructive_steps),
        "details": details,
    }
    _stackctl.orphan_compose_teardown.write_consumption_create_once(
        attestation_path,
        attestation=attestation,
        removed_containers=container_ids,
        removed_networks=network_ids,
        status="passed",
        removal_outcome="complete",
    )
    publication_issues = _stackctl._publish_orphan_terminal_success(
        report_dir=report_dir,
        target_name=target_name,
        summary=summary,
        details=details,
        report=report,
    )
    details.extend(issue for issue in publication_issues if issue not in details)
    return {
        "exitCode": 0,
        "summary": summary,
        "details": details,
        "reportDir": report_dir_ref,
        "consumption": consumption_ref,
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
    step_receipt_issues: list[str] = []
    recovering_from_journal = False
    removal_verified = False
    step_evidence_verified = False
    try:
        with _stackctl._local_stack_operation_lock(target_name):
            startup = _stackctl._orphan_compose_runtime_gate(target_name)
            status = str((startup or {}).get("status") or "").strip()
            require_removable = startup is None or status == "stopped"
            consumption_path = attestation_path.with_name(
                "orphaned-compose-teardown-consumption.json"
            )
            journal_path = attestation_path.with_name(
                "orphaned-compose-teardown-journal.json"
            )
            consumption_exists = consumption_path.exists() or consumption_path.is_symlink()
            journal_exists = journal_path.exists() or journal_path.is_symlink()
            if confirmed:
                attestation = _stackctl.orphan_compose_teardown.load_attestation(
                    attestation_path,
                    allowed_root=allowed_root,
                    expected_target=target_name,
                    allow_expired=consumption_exists or journal_exists,
                )
                active_attestation = attestation
                project = _stackctl.orphan_compose_teardown.require_canonical_project(
                    target_name,
                    attestation.get("project"),
                )
                if startup is not None:
                    receipt_project = (
                        _stackctl.orphan_compose_teardown.require_canonical_project(
                            target_name,
                            startup.get("composeProject"),
                        )
                    )
                    if project != receipt_project:
                        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                            "orphan Compose attestation project differs from the current startup receipt"
                        )
            elif startup is None:
                project = _stackctl.orphan_compose_teardown.discover_exact_project(
                    target=target_name,
                    run_command=_stackctl.run,
                )
            else:
                project = _stackctl.orphan_compose_teardown.require_canonical_project(
                    target_name,
                    startup.get("composeProject"),
                )
            canonical_report = _stackctl._canonical_port_occupancy_report(target_name)
            canonical_ports = canonical_report["ports"]
            port_profile = str(canonical_report.get("profile") or "").strip()
            if not port_profile:
                raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                    "orphan Compose target port profile is required"
                )
            port_manifest = _stackctl.load_port_manifest()
            other_target_port_blocks = _stackctl._other_local_target_port_blocks(target_name)
            if not confirmed:
                snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                    target=target_name,
                    project=project,
                    canonical_ports=canonical_ports,
                    port_manifest=port_manifest,
                    port_profile=port_profile,
                    run_command=_stackctl.run,
                    require_removable=require_removable,
                    other_target_port_blocks=other_target_port_blocks,
                    port_probe=_stackctl._published_endpoint_is_occupied,
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
                    port_manifest=port_manifest,
                    port_profile=port_profile,
                    other_target_port_blocks=other_target_port_blocks,
                    report_dir=report_dir,
                    startup=startup,
                )
            if journal_exists:
                recovering_from_journal = True
                execution_journal = journal_path
                _stackctl.orphan_compose_teardown.validate_execution_journal_for_recovery(
                    attestation_path,
                    attestation=attestation,
                )
                _stackctl._wait_for_attested_orphan_compose_ports_released(
                    target_name,
                    attestation,
                )
                recovered_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                    target=target_name,
                    project=project,
                    canonical_ports=canonical_ports,
                    port_manifest=port_manifest,
                    port_profile=port_profile,
                    run_command=_stackctl.run,
                    require_removable=False,
                    other_target_port_blocks=other_target_port_blocks,
                    port_probe=_stackctl._published_endpoint_is_occupied,
                )
                _stackctl.orphan_compose_teardown.assert_post_teardown_state(
                    attestation,
                    recovered_snapshot,
                    port_probe=_stackctl._published_endpoint_is_occupied,
                )
                removal_verified = True
                _stackctl.orphan_compose_teardown.complete_execution_step_receipts(
                    attestation_path,
                    attestation=attestation,
                    step_writer=(
                        _stackctl.orphan_compose_teardown.write_step_receipt_create_once
                    ),
                )
                step_evidence_verified = True
                return _stackctl._commit_orphan_compose_terminal_consumption(
                    target_name=target_name,
                    fix=args.fix,
                    attestation_path=attestation_path,
                    attestation=attestation,
                    startup=startup,
                    execution_journal=journal_path,
                    destructive_steps=[],
                    report_dir=report_dir,
                    recovered_execution=True,
                )
            _stackctl.orphan_compose_teardown.assert_not_consumed(attestation_path)
            current_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                target=target_name,
                project=project,
                canonical_ports=canonical_ports,
                port_manifest=port_manifest,
                port_profile=port_profile,
                run_command=_stackctl.run,
                require_removable=require_removable,
                other_target_port_blocks=other_target_port_blocks,
                port_probe=_stackctl._published_endpoint_is_occupied,
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
                attempted_command = []
                try:
                    _stackctl.orphan_compose_teardown.write_step_receipt_create_once(
                        attestation_path,
                        attestation=attestation,
                        index=index,
                        command=command,
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as step_exc:
                    step_receipt_issues.append(
                        f"step {index} receipt publication failed: {step_exc}"
                    )
            _stackctl._wait_for_attested_orphan_compose_ports_released(
                target_name,
                attestation,
            )
            post_snapshot = _stackctl.orphan_compose_teardown.sample_snapshot(
                target=target_name,
                project=project,
                canonical_ports=canonical_ports,
                port_manifest=port_manifest,
                port_profile=port_profile,
                run_command=_stackctl.run,
                require_removable=False,
                other_target_port_blocks=other_target_port_blocks,
                port_probe=_stackctl._published_endpoint_is_occupied,
            )
            _stackctl.orphan_compose_teardown.assert_post_teardown_state(
                attestation,
                post_snapshot,
                port_probe=_stackctl._published_endpoint_is_occupied,
            )
            removal_verified = True
            _stackctl.orphan_compose_teardown.complete_execution_step_receipts(
                attestation_path,
                attestation=attestation,
                step_writer=(
                    _stackctl.orphan_compose_teardown.write_step_receipt_create_once
                ),
            )
            step_evidence_verified = True
            return _stackctl._commit_orphan_compose_terminal_consumption(
                target_name=target_name,
                fix=args.fix,
                attestation_path=attestation_path,
                attestation=attestation,
                startup=startup,
                execution_journal=execution_journal,
                destructive_steps=destructive_steps,
                report_dir=report_dir,
                recovered_execution=False,
            )
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
        if recovering_from_journal or removal_verified:
            removal_outcome = (
                "complete_terminal_fact_pending"
                if step_evidence_verified
                else "complete_step_fact_pending"
                if removal_verified
                else "journal_evidence_unverified"
            )
            destructive_performed = True if removal_verified else None
        if (
            active_attestation is not None
            and execution_journal is not None
            and not recovering_from_journal
            and (not removal_verified or step_evidence_verified)
        ):
            # 已证完整的销毁不得被回写成 partial_failure：此处只有终态事实待写，
            # removal 本身仍是 complete_*，覆写会把假失败刻进 create-once 回执。
            if not removal_verified:
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
        details = [str(exc), *step_receipt_issues]
        if step_evidence_verified:
            details.append(
                "complete exact removal remains proven by the create-once journal, step receipts, and post-state; no Docker removal command was replayed"
            )
        elif removal_verified:
            details.append(
                "complete exact removal is proven by post-state, but one or more create-once step receipts remain unpublished; no consumption fact was written"
            )
        elif recovering_from_journal:
            details.append(
                "existing execution evidence did not validate; no Docker removal command was replayed and no consumption fact was written"
            )
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
        return _stackctl._finish_orphan_repair_gate_block(
            report_dir=report_dir,
            target_name=target_name,
            fix=args.fix,
            details=details,
            destructive_performed=destructive_performed,
            removal_outcome=removal_outcome,
            execution_journal=execution_journal,
            consumption_path=consumption_path,
            destructive_steps=destructive_steps,
        )
