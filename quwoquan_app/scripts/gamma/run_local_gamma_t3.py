#!/usr/bin/env python3
"""Run Gamma T3 as a read-only immutable-release consumer verification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)
from quwoquan_ops.cli.lib.output_paths import output_root


def default_t3_report_path() -> Path:
    return (
        output_root()
        / "env"
        / "gamma"
        / "runs"
        / "release-consumer"
        / "t3.json"
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_t3_report_path(raw_value: str) -> Path:
    """Keep T3 evidence in the immutable-run evidence plane."""

    evidence_root = (output_root() / "env" / "gamma" / "runs").resolve()
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(
            "Gamma T3 report must stay below QWQ_OUTPUT_ROOT/env/gamma/runs"
        ) from exc
    return candidate


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
    parser.add_argument("--report", default=str(default_t3_report_path()))
    args = parser.parse_args()

    try:
        report_path = resolve_t3_report_path(args.report)
    except ValueError as exc:
        print(f"Gamma T3 GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        identity = load_release_content_identity(
            resolve_readiness_path(args.release_readiness),
            expected_environment="gamma",
        )
    except (ReleaseVideoDeliveryError, ValueError) as exc:
        report = {
            "schema": "gamma-t3-release-consumer",
            "status": "gate_block",
            "environment": "gamma",
            "composition": "production_remote",
            "mutationPolicy": "read_only",
            "reason": str(exc),
            "startedAt": utc_now(),
            "endedAt": utc_now(),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Gamma T3 GATE_BLOCK report written: {report_path}", file=sys.stderr)
        return 2

    consumer = run_release_consumer(identity=identity)
    report = {
        "schema": "gamma-t3-release-consumer",
        "status": consumer["status"],
        "environment": "gamma",
        "release": {
            "releaseId": identity["releaseId"],
            "sourceOwner": identity["sourceOwner"],
            "manifestDigest": identity["manifestDigest"],
            "mediaManifestDigest": identity["mediaManifestDigest"],
            "importRunId": identity["importRunId"],
            "verifyRunId": identity["verifyRunId"],
            "readinessReceiptRef": identity["readinessReceiptRef"],
        },
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
