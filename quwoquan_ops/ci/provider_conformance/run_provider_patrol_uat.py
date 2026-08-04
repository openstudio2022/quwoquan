"""Run one fixed Provider user journey against its selected environment."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import (  # noqa: E402
    read_latest_debug_otp,
)
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (  # noqa: E402
    ProtectedOTPBroker,
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
    parser.add_argument("--local-capture-otp-broker", action="store_true")
    return parser.parse_args()


def _configure_android_broker_reverse(
    *,
    action: str,
    device_id: str,
    port: int,
) -> None:
    if not device_id:
        raise ValueError(
            "local-capture Android OTP UAT requires "
            "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID"
        )
    endpoint = f"tcp:{port}"
    command = ["adb", "-s", device_id, "reverse"]
    if action == "add":
        command.extend((endpoint, endpoint))
    elif action == "remove":
        command.extend(("--remove", endpoint))
    else:
        raise ValueError("unsupported Android broker reverse action")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and action == "add":
        raise RuntimeError("failed to install protected OTP broker port reverse")


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
    if args.local_capture_otp_broker:
        define_keys += (
            "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
            "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
        )
    invalid_define_keys = [
        key
        for key in define_keys
        if not key.startswith("QWQ_PROVIDER_UAT_")
    ]
    if invalid_define_keys:
        raise ValueError("Provider Patrol define keys must use QWQ_PROVIDER_UAT_*")
    generated_define_keys = {
        "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
        "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
    } if args.local_capture_otp_broker else set()
    missing_define_keys = [
        key
        for key in define_keys
        if key not in generated_define_keys
        and not command_environment.get(key, "").strip()
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
    broker: ProtectedOTPBroker | None = None
    broker_port = 0
    broker_reverse_added = False
    try:
        if args.local_capture_otp_broker:
            if environment not in {"alpha", "beta", "gamma"}:
                raise ValueError(
                    "local-capture OTP broker is forbidden for Prod evidence"
                )
            if command_environment.get("QWQ_PROVIDER_UAT_SMS_OTP", "").strip():
                raise ValueError(
                    "local-capture OTP UAT must not preload an OTP"
                )
            broker = ProtectedOTPBroker(
                environment=environment,
                target_name=target_name,
                recipient=_required_environment("QWQ_PROVIDER_UAT_SMS_PHONE"),
                reader=read_latest_debug_otp,
            )
            binding = broker.start()
            command_environment["QWQ_PROVIDER_UAT_OTP_BROKER_URL"] = binding.url
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN"
            ] = binding.token
            parsed_broker_url = urlparse(binding.url)
            broker_port = int(parsed_broker_url.port or 0)
            if broker_port <= 0:
                raise RuntimeError("protected OTP broker did not bind a port")
            if args.platform == "android":
                _configure_android_broker_reverse(
                    action="add",
                    device_id=device_id,
                    port=broker_port,
                )
                broker_reverse_added = True
        return subprocess.run(
            command,
            cwd=ROOT,
            env=command_environment,
            check=False,
        ).returncode
    finally:
        if broker_reverse_added:
            _configure_android_broker_reverse(
                action="remove",
                device_id=device_id,
                port=broker_port,
            )
        if broker is not None:
            broker.close()


if __name__ == "__main__":
    raise SystemExit(main())
