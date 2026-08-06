#!/usr/bin/env python3
"""Run Gamma release-consumer as a read-only immutable-release consumer verification."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.gamma.gamma_case_result import (
    GammaCaseResultError,
    load_gamma_execution_identity,
    require_unchanged_identity,
    resolve_gamma_evidence_path,
    write_blocked_case_result,
    write_passed_case_result,
)
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)


def default_release_consumer_report_path() -> Path:
    return (
        output_root()
        / "env"
        / "gamma"
        / "runs"
        / "release-consumer"
        / "release_consumer.json"
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_release_consumer_report_path(raw_value: str) -> Path:
    """Keep release-consumer evidence in the immutable-run evidence plane."""

    return resolve_gamma_evidence_path(raw_value, label="Gamma release-consumer CaseResult")


def run_release_consumer(
    *,
    identity: dict[str, object],
) -> dict[str, object]:
    release_id = str(identity["releaseId"])
    import_run_id = str(identity["importRunId"])
    verification_run_id = str(identity["verifyRunId"])
    command = [
        sys.executable,
        "-B",
        "quwoquan_data/scripts/cli.py",
        "ship",
        "verify",
        "--release-id",
        release_id,
        "--env",
        "gamma",
        "--import-run-id",
        import_run_id,
    ]
    command.extend(["--run-id", verification_run_id])
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": command,
        "exitCode": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "outputTail": (result.stdout or "")[-8000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
        help=(
            "canonical Gamma Data release-readiness.json; release/import/verify "
            "identity may not be supplied independently"
        ),
    )
    parser.add_argument("--report", default=str(default_release_consumer_report_path()))
    args = parser.parse_args()

    try:
        report_path = resolve_release_consumer_report_path(args.report)
    except ValueError as exc:
        print(f"Gamma release-consumer GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    report_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    execution_identity: dict[str, str] | None = None
    try:
        execution_identity = load_gamma_execution_identity()
        write_blocked_case_result(
            report_path=report_path,
            phase="release_consumer",
            reason="Gamma release-consumer execution has not completed",
            identity=execution_identity,
        )
    except GammaCaseResultError as exc:
        write_blocked_case_result(
            report_path=report_path,
            phase="release_consumer",
            reason=str(exc),
        )
        print(f"Gamma release-consumer GATE_BLOCK report written: {report_path}", file=sys.stderr)
        return 2

    try:
        identity = load_release_content_identity(
            resolve_readiness_path(args.release_readiness),
            expected_environment="gamma",
        )
    except (ReleaseVideoDeliveryError, ValueError) as exc:
        write_blocked_case_result(
            report_path=report_path,
            phase="release_consumer",
            reason=str(exc),
            identity=execution_identity,
        )
        print(f"Gamma release-consumer GATE_BLOCK report written: {report_path}", file=sys.stderr)
        return 2

    consumer = run_release_consumer(identity=identity)
    ended_at = utc_now()
    if consumer["status"] != "passed":
        write_blocked_case_result(
            report_path=report_path,
            phase="release_consumer",
            reason="Gamma release-consumer release consumer verification failed",
            identity=execution_identity,
            status="failed",
            executed=1,
            failed=1,
        )
        print(f"Gamma release-consumer failed CaseResult written: {report_path}", file=sys.stderr)
        return 1

    try:
        require_unchanged_identity(execution_identity)
        write_passed_case_result(
            report_path=report_path,
            phase="release_consumer",
            identity=execution_identity,
            executed=1,
            skipped=0,
            failed=0,
            executed_at=ended_at,
        )
    except GammaCaseResultError as exc:
        write_blocked_case_result(
            report_path=report_path,
            phase="release_consumer",
            reason=str(exc),
            identity=execution_identity,
            executed=1,
        )
        print(f"Gamma release-consumer GATE_BLOCK report written: {report_path}", file=sys.stderr)
        return 2

    print(f"Gamma release-consumer CaseResult written: {report_path}")
    print(f"Gamma release-consumer execution window: {started_at} -> {ended_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
