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
from pathlib import Path
from typing import Any

_RECLAIMABLE_TARGETS = ("alpha-local", "beta-local", "gamma-local")
_ATTESTATION_NAME = "orphaned-compose-teardown-attestation.json"


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
