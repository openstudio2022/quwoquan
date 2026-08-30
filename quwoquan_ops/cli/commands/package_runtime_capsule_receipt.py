"""Persist typed package input-capsule CAS failure receipts."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.package_runtime_support import _receipt_safe_text

PACKAGE_CAPSULE_CAS_BLOCKER = "OPS.PACKAGE.input_capsule_cas_drift"

def _atomic_write_package_receipt(path: Path, content: str) -> None:
    """Replace one report artifact atomically without following final symlinks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("package report directory is unsafe")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("package report artifact is unsafe")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(
            path.parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _persist_package_capsule_cas_failure(
    *,
    report_dir: Path,
    env_name: str,
    target_name: str,
    package_snapshot: dict[str, object],
    reports: list[dict[str, Any]],
    detail: str,
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Persist the typed CAS blocker before exposing its report reference."""

    import quwoquan_ops.cli.stackctl as _stackctl

    safe_detail = _receipt_safe_text(detail)
    summary = f"stackctl package capsule CAS blocked for {env_name}"
    generated_at = _stackctl.utc_now()
    report_payload = {
        "status": "GATE_BLOCK",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "firstBlocker": PACKAGE_CAPSULE_CAS_BLOCKER,
        "baselineId": str(package_snapshot.get("baselineId") or ""),
        "details": [safe_detail],
        "steps": reports,
        **timing,
    }
    summary_payload = {
        "command": "package",
        "target": target_name,
        "status": "GATE_BLOCK",
        "summary": summary,
        "details": [safe_detail],
        "firstBlocker": PACKAGE_CAPSULE_CAS_BLOCKER,
        "env": env_name,
        "generatedAt": generated_at,
        **timing,
    }
    summary_lines = [
        "# stackctl package",
        "",
        f"- target: `{target_name}`",
        "- status: `GATE_BLOCK`",
        f"- firstBlocker: `{PACKAGE_CAPSULE_CAS_BLOCKER}`",
        f"- summary: {summary}",
        f"- {safe_detail}",
    ]
    _atomic_write_package_receipt(
        report_dir / "report.json",
        json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_package_receipt(
        report_dir / "summary.json",
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    _atomic_write_package_receipt(
        report_dir / "summary.md",
        "\n".join(summary_lines) + "\n",
    )
    return {
        "exitCode": 2,
        "status": "GATE_BLOCK",
        "summary": summary,
        "details": [safe_detail],
        "firstBlocker": PACKAGE_CAPSULE_CAS_BLOCKER,
        "reportDir": _stackctl.relpath(report_dir),
        "baselineId": str(package_snapshot.get("baselineId") or ""),
        **timing,
    }


