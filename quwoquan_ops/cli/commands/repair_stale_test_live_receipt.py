"""Reclaim a test-live startup receipt the current contract can no longer admit.

The receipt field set evolves with the runtime it describes, and the receipt is
frozen evidence that cannot be migrated in place.  Every operational path reads
it first and fails closed, so a receipt written by a retired generation leaves
its target unable to start, stop or restart at all.

Fail-closed is right and stays: the stale document is untrusted, so nothing in
it may establish that its runtime is gone.  Only a live probe of the target's
own Compose project and canonical ports can, and reclaiming is refused unless
that probe is clean.  Named volumes are preserved exactly as normal teardown
preserves them.

测试经 ``mock.patch.object(stackctl, ...)`` patch 协作符号，因此函数体内一律经
函数内延迟导入 ``_stackctl`` 属性访问，保持 monkeypatch 语义。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

_RECLAIMABLE_TARGETS = ("alpha-local", "beta-local", "gamma-local")
_ARCHIVE_NAME = "stale_test_live_receipt.json"


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


def repair_stale_test_live_receipt(
    args: argparse.Namespace,
    *,
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Audit, and on explicit confirmation reclaim, one inadmissible receipt."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
    if target not in _RECLAIMABLE_TARGETS:
        summary = (
            "reclaim-stale-test-live-receipt is only available for "
            + ", ".join(_RECLAIMABLE_TARGETS)
        )
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[summary],
            summary=summary,
        )

    try:
        stale = _stackctl.read_stale_test_live_startup_attempt(target)
    except (OSError, ValueError) as exc:
        summary = f"stale test-live receipt is unreadable for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {exc}"],
            summary=summary,
        )
    if stale is None:
        summary = (
            f"{target} has no inadmissible test-live receipt; "
            "an admissible or absent receipt owns the normal down path"
        )
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[summary],
            summary=summary,
        )

    compose_project = f"quwoquan_{environment}_test_live"
    try:
        residue = _runtime_residue(target, compose_project)
    except (OSError, ValueError) as exc:
        summary = f"test-live runtime residue probe failed for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {exc}"],
            summary=summary,
        )
    if residue:
        summary = (
            f"stale test-live receipt for {target} still describes a live runtime"
        )
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
        "fix": "reclaim-stale-test-live-receipt",
        "composeProject": compose_project,
        "receiptRef": _stackctl.relpath(
            _stackctl.test_live_startup_attempt_path(target)
        ),
        "preservedVolumes": preserved_volumes,
        "actions": [
            f"archive the inadmissible receipt as {_ARCHIVE_NAME}",
            "remove the receipt from the target process directory",
        ],
    }
    _stackctl.write_json(report_dir / "repair_plan.json", plan)

    if not bool(getattr(args, "confirm_stale_test_live_receipt_reclaim", False)):
        details = [
            f"{target} holds an inadmissible test-live receipt and no live runtime",
            "no container, network or canonical port belongs to the project",
            f"{len(preserved_volumes)} named volumes stay preserved",
            "rerun with --confirm-stale-test-live-receipt-reclaim to apply",
        ]
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": target,
                "fix": "reclaim-stale-test-live-receipt",
                "status": "passed",
                "auditOnly": True,
                "reclaimed": False,
                "staleReceipt": stale,
                "preservedVolumes": preserved_volumes,
                "details": details,
            },
        )
        summary = f"stackctl repair reclaim-stale-test-live-receipt audited {target}"
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
        summary = f"stale test-live receipt archive already exists for {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: {_stackctl.relpath(archive_path)}"],
            summary=summary,
        )
    _stackctl.write_json(archive_path, stale)
    try:
        reclaimed = _stackctl.reclaim_stale_test_live_startup_attempt(target)
    except (OSError, ValueError) as exc:
        summary = f"stale test-live receipt reclaim failed for {target}"
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
        summary = f"named volumes were removed while reclaiming {target}"
        return _blocked(
            report_dir=report_dir,
            target=target,
            details=[f"{summary}: " + ",".join(missing_volumes)],
            summary=summary,
        )

    details = [
        f"archived the inadmissible receipt to {_stackctl.relpath(archive_path)}",
        f"{target} can now start, stop and restart again",
        f"{len(remaining_volumes)} named volumes remain preserved",
    ]
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "repair",
            "target": target,
            "fix": "reclaim-stale-test-live-receipt",
            "status": "passed",
            "auditOnly": False,
            "reclaimed": True,
            "staleReceipt": reclaimed,
            "archive": _stackctl.relpath(archive_path),
            "preservedVolumes": remaining_volumes,
            "details": details,
        },
    )
    summary = f"stackctl repair reclaim-stale-test-live-receipt completed for {target}"
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
