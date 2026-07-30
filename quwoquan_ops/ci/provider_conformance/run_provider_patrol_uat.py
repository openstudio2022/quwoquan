"""Run one fixed Provider user journey against its selected environment."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


_TARGET_NAMES = {
    "alpha": ("alpha-local", "alpha-local"),
    "beta": ("beta-local", "local-beta"),
    "gamma": ("gamma-local", "local-gamma"),
    "prod": ("prod-hosted", "prod-hosted"),
}


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_url(public_bases: dict[str, Any], name: str) -> str:
    value = str(public_bases.get(name) or "").strip()
    if not value:
        raise ValueError(f"environment topology publicBases.{name} is required")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--platform", choices=("android", "ios"), default="android")
    parser.add_argument("--unauthenticated", action="store_true")
    parser.add_argument("--define-key", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    environment = _required_environment(
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT"
    )
    try:
        target_name, environment_alias = _TARGET_NAMES[environment]
    except KeyError as exc:
        raise ValueError(
            f"unsupported Provider Patrol environment: {environment}"
        ) from exc
    target = get_target(load_environment_topology(), target_name)
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} publicBases are required")

    result_path = Path(
        _required_environment("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH")
    )
    report_path = result_path.with_name(f"{result_path.stem}.patrol-report.json")
    command = [
        sys.executable,
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--env-name",
        environment_alias,
        "--runtime-env",
        environment,
        "--api-contract-env",
        environment,
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
        args.target,
        "--platform",
        args.platform,
        "--report",
        str(report_path),
    ]
    device_id = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID", ""
    ).strip()
    if device_id:
        command.extend(("--device-id", device_id))
    command_environment = dict(os.environ)
    define_keys = tuple(
        str(key).strip() for key in args.define_key if str(key).strip()
    )
    invalid_define_keys = [
        key
        for key in define_keys
        if not key.startswith("QWQ_PROVIDER_UAT_")
    ]
    if invalid_define_keys:
        raise ValueError("Provider Patrol define keys must use QWQ_PROVIDER_UAT_*")
    missing_define_keys = [
        key
        for key in define_keys
        if not command_environment.get(key, "").strip()
    ]
    if missing_define_keys:
        raise ValueError(
            "Provider Patrol define values are required: "
            + ", ".join(missing_define_keys)
        )
    if define_keys:
        command_environment["QWQ_PROVIDER_UAT_DART_DEFINE_KEYS"] = ",".join(
            define_keys
        )
    if args.unauthenticated:
        command.append("--unauthenticated-auth-entry")
        for key in (
            "TEST_AUTH_TOKEN",
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_PERSONA_ID",
        ):
            command_environment.pop(key, None)
    return subprocess.run(
        command,
        cwd=ROOT,
        env=command_environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
