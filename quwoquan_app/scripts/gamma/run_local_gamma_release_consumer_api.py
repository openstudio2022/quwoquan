#!/usr/bin/env python3
"""Run Gamma release-consumer checks without minting an aggregate raw verdict."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.gamma.gamma_case_result import (
    GammaCaseResultError,
    load_gamma_execution_identity,
    load_target_uat_binding,
    require_unchanged_identity,
    resolve_gamma_evidence_path,
)
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.lib.target_uat_binding import target_uat_binding_digest
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


def resolve_release_consumer_report_path(raw_value: str) -> Path:
    return resolve_gamma_evidence_path(
        raw_value, label="Gamma release-consumer diagnostic report"
    )


def run_release_consumer(*, identity: dict[str, object]) -> dict[str, object]:
    command = [
        sys.executable,
        "-B",
        "quwoquan_data/scripts/cli.py",
        "ship",
        "verify",
        "--release-id",
        str(identity["releaseId"]),
        "--env",
        "gamma",
        "--import-run-id",
        str(identity["importRunId"]),
        "--run-id",
        str(identity["verifyRunId"]),
    ]
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
        "mutationPolicy": "read_only",
        "exitCode": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "outputTail": (result.stdout or "")[-8000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
    )
    parser.add_argument("--target-uat-binding", required=True)
    parser.add_argument("--report", default=str(default_release_consumer_report_path()))
    args = parser.parse_args()
    try:
        report_path = resolve_release_consumer_report_path(args.report)
        binding_path = resolve_gamma_evidence_path(
            args.target_uat_binding, label="Gamma TargetUatBinding"
        )
        execution_identity = load_gamma_execution_identity()
        binding, _ = load_target_uat_binding(binding_path)
        release_identity = load_release_content_identity(
            resolve_readiness_path(args.release_readiness),
            expected_environment="gamma",
        )
        if (
            binding.get("releaseId") != release_identity.get("releaseId")
            or binding.get("releaseDigest") != release_identity.get("manifestDigest")
        ):
            raise GammaCaseResultError(
                "release-consumer identity differs from exact TargetUatBinding"
            )
        consumer = run_release_consumer(identity=release_identity)
        require_unchanged_identity(execution_identity)
    except (GammaCaseResultError, ReleaseVideoDeliveryError, ValueError) as exc:
        print(f"Gamma release-consumer GATE_BLOCK: {exc}", file=sys.stderr)
        return 2

    # This phase is a prerequisite diagnostic only. It cannot mint a raw App UAT
    # cell because it has no device, entry surface, carrier, or App artifact
    # readback. The Patrol phase owns the only canonical raw result.
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan.gamma-release-consumer-diagnostic.v1",
                "mutationPolicy": consumer["mutationPolicy"],
                "exitCode": consumer["exitCode"],
                "releaseId": binding["releaseId"],
                "targetUatBindingDigest": target_uat_binding_digest(binding_path.read_bytes()),
                "providerIdentity": binding["provider"]["identity"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return 0 if consumer["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
