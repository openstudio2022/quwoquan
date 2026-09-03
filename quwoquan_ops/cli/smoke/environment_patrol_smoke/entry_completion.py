"""Finalize the report and exit status for the Patrol smoke entry point."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def finalize_main_report(
    report_path: Path,
    report: dict[str, Any],
    *,
    failed: bool,
    gate_blocked: bool,
    dry_run: bool,
    page_evidence_resolver: Any | None,
    now: Callable[[], str],
    report_writer: Callable[..., None],
) -> int:
    """Settle the aggregate status, persist the report, and return its code."""

    report["status"] = (
        "gate_block"
        if gate_blocked
        else ("failed" if failed else ("dry_run" if dry_run else "passed"))
    )
    if failed:
        report["failureReason"] = (
            "local TLS preflight blocked one or more Patrol runs"
            if gate_blocked
            else "one or more Patrol runs failed"
        )
    report["endedAt"] = now()
    report_writer(
        report_path,
        report,
        app_uat_page_evidence_resolver=page_evidence_resolver,
    )
    return 2 if report["status"] == "gate_block" else (1 if failed else 0)
