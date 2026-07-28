#!/usr/bin/env python3
"""Run Gamma T3 as a read-only immutable-release consumer verification."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT = (
    ROOT
    / ".qwq_output"
    / "env"
    / "gamma"
    / "runs"
    / "release-consumer"
    / "t3.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_release_consumer(
    *,
    release_id: str,
    import_run_id: str,
    verification_run_id: str,
) -> dict[str, object]:
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
    if verification_run_id:
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
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--import-run-id", required=True)
    parser.add_argument("--verification-run-id", default="")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    consumer = run_release_consumer(
        release_id=args.release_id,
        import_run_id=args.import_run_id,
        verification_run_id=args.verification_run_id,
    )
    report = {
        "schema": "gamma-t3-release-consumer-v1",
        "status": consumer["status"],
        "environment": "gamma",
        "releaseId": args.release_id,
        "importRunId": args.import_run_id,
        "verificationRunId": args.verification_run_id,
        "composition": "production_remote",
        "mutationPolicy": "read_only",
        "startedAt": utc_now(),
        "consumer": consumer,
        "endedAt": utc_now(),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Gamma T3 release-consumer report written: {report_path}")
    return 0 if consumer["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
