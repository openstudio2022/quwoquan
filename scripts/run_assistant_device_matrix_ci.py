#!/usr/bin/env python3
"""CI wrapper for assistant device matrix jobs.

Keep workflow shell snippets minimal because Android emulator runner executes
scripts through /bin/sh on hosted Linux runners.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build assistant device matrix CLI args from CI env."
    )
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_name = os.environ.get("API_CONTRACT_ENV", "").strip()
    if env_name not in {"alpha", "beta", "gamma"}:
        print(
            f"::error::API_CONTRACT_ENV={env_name!r} 不属于 alpha/beta/gamma",
            file=sys.stderr,
        )
        return 2

    device_id = "emulator-5554"
    if args.platform == "ios":
        device_id = os.environ.get("IOS_DEVICE_ID", "").strip()
        if not device_id:
            print("::error::缺少 IOS_DEVICE_ID，无法执行 iOS 端侧矩阵", file=sys.stderr)
            return 2

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_assistant_device_matrix.py"),
        "--env",
        env_name,
        "--device-id",
        device_id,
        "--report",
        f"artifacts/device-matrix/{env_name}-{args.platform}.json",
    ]

    if env_name == "gamma":
        gamma_base_url = os.environ.get("GAMMA_BASE_URL", "").strip()
        if not gamma_base_url:
            print(
                f"::error::缺少 GAMMA_BASE_URL，无法执行 gamma {args.platform} 端侧矩阵",
                file=sys.stderr,
            )
            return 1
        command.extend(["--skip-beta-services", "--gateway-base-url", gamma_base_url])

    if env_name == "beta":
        command.extend(["--service-start-timeout-seconds", "180"])

    return subprocess.call(command, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
