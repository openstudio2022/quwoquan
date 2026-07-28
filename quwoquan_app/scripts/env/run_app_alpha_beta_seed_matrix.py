#!/usr/bin/env python3
"""Verify Alpha/Beta Remote packages against one immutable data release."""

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
    / "repo"
    / "runs"
    / "app-release-matrix"
    / "alpha-beta.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: list[str]) -> dict[str, object]:
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
        "outputTail": (result.stdout or "")[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--alpha-import-run-id", required=True)
    parser.add_argument("--beta-import-run-id", required=True)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "schema": "app-remote-release-matrix",
        "releaseId": args.release_id,
        "startedAt": utc_now(),
        "composition": "production_remote",
        "environments": {},
    }
    environments = report["environments"]
    assert isinstance(environments, dict)
    for environment, import_run_id in (
        ("alpha", args.alpha_import_run_id),
        ("beta", args.beta_import_run_id),
    ):
        package = run(
            [
                "bash",
                "quwoquan_app/scripts/env/build_app_env_package.sh",
                "--env",
                environment,
            ]
        )
        verify = run(
            [
                sys.executable,
                "-B",
                "quwoquan_data/scripts/cli.py",
                "ship",
                "verify",
                "--release-id",
                args.release_id,
                "--env",
                environment,
                "--import-run-id",
                import_run_id,
            ]
        )
        environments[environment] = {
            "importRunId": import_run_id,
            "package": package,
            "releaseConsumer": verify,
        }

    failed = [
        environment
        for environment, evidence in environments.items()
        if any(
            check.get("status") != "passed"
            for check in (
                evidence["package"],
                evidence["releaseConsumer"],
            )
        )
    ]
    report["endedAt"] = utc_now()
    report["status"] = "failed" if failed else "passed"
    report["failedEnvironments"] = failed
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"App Remote release matrix report written: {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
