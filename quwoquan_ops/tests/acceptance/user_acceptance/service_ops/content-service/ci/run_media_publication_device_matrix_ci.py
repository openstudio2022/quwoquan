#!/usr/bin/env python3
"""Run the production-Remote media publication Patrol journey on real devices."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[7]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


TARGETS = {
    "beta": ("beta-local", "local-beta"),
    "gamma": ("gamma-local", "local-gamma"),
    "prod-sim": ("prod-sim", "local-prod-sim"),
}
PATROL_TARGET = (
    "test/user_acceptance/patrol/content/"
    "media_publication_remote__user_acceptance_test.dart"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=tuple(TARGETS), required=True)
    parser.add_argument("--platform", choices=("android", "ios", "all"), required=True)
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--report", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def build_command(args: argparse.Namespace) -> list[str]:
    target_name, environment_alias = TARGETS[args.environment]
    target = get_target(load_environment_topology(), target_name)
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} has no publicBases")
    required = (
        "api",
        "productOps",
        "mediaAvatar",
        "mediaImage",
        "mediaVideo",
        "mediaUpload",
        "rtc",
    )
    missing = [key for key in required if not _required_url(public_bases, key)]
    if missing:
        raise ValueError(
            f"{target_name} is missing public bases: {', '.join(sorted(missing))}"
        )
    runtime_env = "prod" if args.environment == "prod-sim" else args.environment
    report = args.report.strip() or str(
        _output_root()
        / "env"
        / runtime_env
        / "runs"
        / "device-matrix"
        / f"media-publication-{args.platform}.json"
    )
    command = [
        sys.executable,
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--env-name",
        environment_alias,
        "--runtime-env",
        runtime_env,
        "--api-contract-env",
        runtime_env,
        "--gateway-base-url",
        _required_url(public_bases, "api"),
        "--product-ops-base-url",
        _required_url(public_bases, "productOps"),
        "--media-avatar-base-url",
        _required_url(public_bases, "mediaAvatar"),
        "--media-image-base-url",
        _required_url(public_bases, "mediaImage"),
        "--media-video-base-url",
        _required_url(public_bases, "mediaVideo"),
        "--media-upload-base-url",
        _required_url(public_bases, "mediaUpload"),
        "--rtc-media-connection-url",
        _required_url(public_bases, "rtc"),
        "--target",
        PATROL_TARGET,
        "--platform",
        args.platform,
        "--report",
        report,
    ]
    for device_id in args.device_id:
        normalized = str(device_id).strip()
        if normalized:
            command.extend(("--device-id", normalized))
    if args.dry_run:
        command.append("--dry-run")
    return command


def _required_url(public_bases: dict[str, Any], key: str) -> str:
    value = str(public_bases.get(key) or "").strip()
    return value


def _output_root() -> Path:
    configured = os.environ.get("QWQ_OUTPUT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return REPO_ROOT / ".qwq_output"


def main() -> int:
    args = _parse_args()
    try:
        command = build_command(args)
    except ValueError as exc:
        print(f"GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
