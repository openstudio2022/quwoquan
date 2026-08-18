"""Retire a formal startup receipt whose own candidate topology cannot be torn down.

Normal ``down`` replays the receipt's own candidate topology under the receipt's
own workload.  When that projection merges into a service carrying neither an
image nor a build context nor a gating profile, ``docker compose`` rejects the
whole project, so ``down`` can never converge — and ``up`` refuses to run before
``down`` succeeds.  The target is then permanently deadlocked by frozen evidence
that no governed path can retire, which is exactly the failure mode the sibling
``reclaim-stale-test-live-receipt`` fix addresses for mutable test-live receipts.

Fail-closed stays: the structural defect alone never authorizes a reclaim.  It
only establishes that the normal path is unusable.  A live probe of the target's
own Compose project and canonical ports must independently prove the runtime is
gone, and the operator must confirm explicitly.  Named volumes are preserved
exactly as normal teardown preserves them.

测试经 ``mock.patch.object(stackctl, ...)`` patch 协作符号，因此函数体内一律经
函数内延迟导入 ``_stackctl`` 属性访问，保持 monkeypatch 语义。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

_RECLAIMABLE_TARGETS = ("alpha-local", "beta-local", "gamma-local")
_ARCHIVE_NAME = "undownable_startup_receipt.json"


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


def _runtime_residue(target: str, compose_project: str) -> list[str]:
    """Return live evidence that the described runtime is not fully gone."""
    import quwoquan_ops.cli.stackctl as _stackctl

    residue: list[str] = []
    leases = _stackctl.active_consumer_leases(target)
    if leases:
        residue.append(
            "active consumer leases hold the target: "
            + ", ".join(
                f"{item.get('device')}:{item.get('consumer')}" for item in leases
            )
        )
    container_ids = _stackctl._mutable_test_live_container_ids(compose_project)
    if container_ids:
        residue.append(
            f"Compose project {compose_project} still owns containers: "
            + ",".join(container_ids)
        )
    networks = _stackctl._mutable_test_live_resource_names(
        "network",
        compose_project=compose_project,
    )
    if networks:
        residue.append(
            f"Compose project {compose_project} still owns networks: "
            + ",".join(networks)
        )
    occupied = [
        item
        for item in _stackctl._canonical_port_occupancy_report(target)["ports"]
        if item["open"]
    ]
    if occupied:
        residue.append(
            "canonical target ports remain occupied: "
            + ", ".join(f"{item['name']}:{item['port']}" for item in occupied)
        )
    return residue


def repair_undownable_startup_receipt(
    args: argparse.Namespace,
    *,
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Audit, and on explicit confirmation retire, one undownable receipt."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
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

    try:
        startup = _stackctl.load_startup_attempt(target)
    except (OSError, ValueError) as exc:
        summary = f"canonical startup receipt is unreadable for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {exc}"],
            summary=summary,
        )
    status = str((startup or {}).get("status") or "").strip()
    if startup is None or status == "stopped":
        summary = (
            f"{target} has no non-stopped startup receipt; "
            "an absent or stopped receipt already permits up"
        )
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[summary],
            summary=summary,
        )

    reason = _stackctl._normal_down_structurally_impossible(target, startup)
    if not reason:
        summary = (
            f"{target} receipt status={status} can still be torn down by "
            "candidate-bound normal down"
        )
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[
                summary,
                "run stackctl down --target " + target + " instead",
            ],
            summary=summary,
        )

    compose_project = str(startup.get("composeProject") or "").strip()
    if not compose_project:
        summary = f"{target} receipt names no Compose project to probe"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[summary],
            summary=summary,
        )
    try:
        residue = _runtime_residue(target, compose_project)
    except (OSError, ValueError) as exc:
        summary = f"runtime residue probe failed for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {exc}"],
            summary=summary,
        )
    if residue:
        summary = f"undownable receipt for {target} still describes a live runtime"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=residue,
            summary=summary,
        )

    preserved_volumes = _stackctl._mutable_test_live_resource_names(
        "volume",
        compose_project=compose_project,
    )
    plan = {
        "target": target,
        "environment": environment,
        "fix": "reclaim-undownable-startup-receipt",
        "composeProject": compose_project,
        "receiptStatus": status,
        "structuralReason": reason,
        "receiptRef": _stackctl.relpath(_stackctl.startup_attempt_path(target)),
        "preservedVolumes": preserved_volumes,
        "actions": [
            f"archive the undownable receipt as {_ARCHIVE_NAME}",
            "transition the receipt to stopped so up is admitted again",
        ],
    }
    _stackctl.write_json(report_dir / "repair_plan.json", plan)

    if not bool(
        getattr(args, "confirm_undownable_startup_receipt_reclaim", False)
    ):
        details = [
            f"{target} holds a status={status} receipt whose own candidate "
            "topology cannot produce a valid Compose project",
            reason,
            "no container, network or canonical port belongs to the project",
            f"{len(preserved_volumes)} named volumes stay preserved",
            "rerun with --confirm-undownable-startup-receipt-reclaim to apply",
        ]
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": target,
                "fix": "reclaim-undownable-startup-receipt",
                "status": "passed",
                "auditOnly": True,
                "reclaimed": False,
                "startupAttempt": startup,
                "structuralReason": reason,
                "preservedVolumes": preserved_volumes,
                "details": details,
            },
        )
        summary = (
            "stackctl repair reclaim-undownable-startup-receipt audited " + target
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=target,
            status="ok",
            summary=summary,
            details=details,
        )
        return {
            "exitCode": 0,
            "summary": summary,
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }

    archive_path = report_dir / _ARCHIVE_NAME
    if archive_path.exists():
        summary = f"undownable receipt archive already exists for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {_stackctl.relpath(archive_path)}"],
            summary=summary,
        )
    _stackctl.write_json(archive_path, startup)
    try:
        closure = _stackctl._close_orphan_reclaimed_startup_receipt(
            target,
            startup,
        )
    except (OSError, ValueError) as exc:
        summary = f"undownable receipt retirement failed for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {exc}"],
            summary=summary,
        )

    remaining_volumes = _stackctl._mutable_test_live_resource_names(
        "volume",
        compose_project=compose_project,
    )
    missing_volumes = sorted(set(preserved_volumes) - set(remaining_volumes))
    if missing_volumes:
        summary = f"named volumes were removed while retiring {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: " + ",".join(missing_volumes)],
            summary=summary,
        )

    details = [
        f"archived the undownable receipt to {_stackctl.relpath(archive_path)}",
        closure or f"{target} receipt already carried a terminal status",
        f"{target} can now start, stop and restart again",
        f"{len(remaining_volumes)} named volumes remain preserved",
    ]
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "repair",
            "target": target,
            "fix": "reclaim-undownable-startup-receipt",
            "status": "passed",
            "auditOnly": False,
            "reclaimed": True,
            "startupAttempt": startup,
            "structuralReason": reason,
            "archive": _stackctl.relpath(archive_path),
            "preservedVolumes": remaining_volumes,
            "details": details,
        },
    )
    summary = (
        "stackctl repair reclaim-undownable-startup-receipt completed for " + target
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="repair",
        target=target,
        status="ok",
        summary=summary,
        details=details,
    )
    return {
        "exitCode": 0,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
    }
