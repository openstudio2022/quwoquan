#!/usr/bin/env python3
"""Prevalidate an official Android package without publishing a latest pointer."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    prevalidate_android_distribution_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    scratch_parent = Path(
        os.environ.get("RUNNER_TEMP")
        or tempfile.gettempdir()
    ).expanduser().resolve()
    try:
        with tempfile.TemporaryDirectory(
            prefix="qwq-android-distribution-preflight-",
            dir=scratch_parent,
        ) as directory:
            report = prevalidate_android_distribution_candidate(
                package_manifest_path=Path(args.package_manifest),
                scratch_root=Path(directory) / "distribution",
            )
    except (OSError, ValueError, OfficialDistributionReleaseError) as error:
        report = {
            "schema": "client-app.android.distribution-prevalidation",
            "status": "GATE_BLOCK",
            "issues": [str(error)],
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "component-ready" else 2


if __name__ == "__main__":
    sys.exit(main())
