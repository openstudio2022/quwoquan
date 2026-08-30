"""Run one fixed Provider user journey against its selected environment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import (  # noqa: E402
    read_latest_debug_otp,
)
from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    materialize_local_capture_ui_acceptance_phone,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    deployment_candidate_dir,
    target_local_dir,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (  # noqa: E402
    compile_provider_runtime_composition,
    validate_provider_runtime_composition,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402
    load_startup_attempt,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (  # noqa: E402
    load_test_live_startup_attempt,
)
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (  # noqa: E402
    ProtectedOTPBroker,
    ProtectedOTPBrokerBinding,
)


if __name__ == "__main__":
    # 以脚本方式执行时，包内子模块的 `from quwoquan_ops.ci.provider_conformance
    # import run_provider_patrol_uat` 必须解析到当前模块对象，才能与 import 形态
    # 共享同一命名空间（含 mock.patch 语义），且避免同一文件被二次加载。
    import sys as _sys

    _sys.modules.setdefault(
        "quwoquan_ops.ci.provider_conformance.run_provider_patrol_uat",
        _sys.modules[__name__],
    )


# 实现单轨落在 provider_patrol_lib/ 包内；本文件保留 CLI 组装（_parse_args/main）
# 与被测源码子串，其余符号从包内 re-export。被测试 patch 的符号一律由包内实现
# 经本模块命名空间在调用时读取，保持与拆分前单文件相同的 mock.patch 语义。
from quwoquan_ops.ci.provider_conformance.provider_patrol_lib.runtime_identity import (  # noqa: E402,F401
    _DIGEST_PREFIX,
    _NONPROD_ENVIRONMENTS,
    _RUNTIME_IDENTITY_COMMON_FIELDS,
    _RUNTIME_IDENTITY_ENV,
    _RUNTIME_IDENTITY_IMMUTABLE_FIELDS,
    _RUNTIME_IDENTITY_MUTABLE_FIELDS,
    _RUNTIME_IDENTITY_SCHEMA,
    _UNKNOWN_IDENTITIES,
    ProviderPatrolRuntimeIdentity,
    _append_runtime_identity_arguments,
    _load_nonprod_runtime_identity,
    _require_digest,
    _select_nonprod_runtime_identity,
    _sha256_bytes,
)
from quwoquan_ops.ci.provider_conformance.provider_patrol_lib.mutable_runtime import (  # noqa: E402,F401
    _MUTABLE_PLAN_FIELDS,
    _load_mutable_runtime_plan,
    _load_mutable_test_live_runtime_identity,
    _read_regular_json,
)
from quwoquan_ops.ci.provider_conformance.provider_patrol_lib.report_evidence import (  # noqa: E402,F401
    _SMS_ASSERTION_COUNT,
    _SMS_CAPABILITY_ID,
    _bind_runtime_evidence_to_patrol_report,
    _declared_provider_assertion_ids,
    _patrol_assertion_evidence,
    _required_environment,
    _required_url,
    _runtime_evidence,
    _safe_patrol_log,
    _sensitive_representations,
    _validated_broker_port,
    _validated_test_execution,
)


_TARGET_NAMES = {
    "alpha": ("alpha-local", "alpha-local"),
    "beta": ("beta-local", "local-beta"),
    "gamma": ("gamma-local", "local-gamma"),
    "prod": ("prod-hosted", "prod-hosted"),
}
_LOCAL_CAPTURE_UI_ACTOR_POOL_SIZE = 128
_PROTECTED_SMS_DEFINE_KEYS = frozenset({
    "QWQ_PROVIDER_UAT_SMS_PHONE",
    "QWQ_PROVIDER_UAT_SMS_OTP",
    "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
    "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
    "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
})


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="android",
    )
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


def _android_broker_device_ids(
    *,
    platform: str,
    explicit_device_id: str,
) -> tuple[str, ...]:
    if platform not in {"android", "all"}:
        return ()
    if explicit_device_id:
        return (explicit_device_id,)
    completed = subprocess.run(
        ["adb", "devices"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("failed to discover Android OTP broker devices")
    device_ids = tuple(
        fields[0]
        for line in completed.stdout.splitlines()[1:]
        for fields in (line.split(),)
        if len(fields) >= 2 and fields[1] == "device"
    )
    if not device_ids:
        raise RuntimeError("local-capture OTP UAT requires an Android device")
    return device_ids


def _local_capture_phone_values(raw_value: str) -> tuple[str, str]:
    """Return App-local digits and the Provider's canonical E.164 recipient."""

    normalized = raw_value.strip()
    local_digits = normalized[3:] if normalized.startswith("+86") else normalized
    if (
        len(local_digits) != 11
        or not local_digits.isascii()
        or not local_digits.isdigit()
        or not local_digits.startswith("1")
    ):
        raise ValueError(
            "local-capture OTP UAT requires an 11-digit +86 phone identity"
        )
    return local_digits, f"+86{local_digits}"


def _local_capture_ui_actor_index(report_path: Path) -> int:
    """Select one protected UAT identity without persisting a second cursor."""

    digest = hashlib.sha256(str(report_path.resolve()).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _LOCAL_CAPTURE_UI_ACTOR_POOL_SIZE


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
    runtime_identity: ProviderPatrolRuntimeIdentity | None = None
    assertion_ids: tuple[str, ...] = ()
    if environment in _NONPROD_ENVIRONMENTS:
        runtime_identity = _select_nonprod_runtime_identity(
            environment,
            target_name,
        )
        assertion_ids = _declared_provider_assertion_ids()
        public_bases = runtime_identity.public_bases
    else:
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
    if runtime_identity is not None:
        _append_runtime_identity_arguments(command, runtime_identity)
    device_id = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID", ""
    ).strip()
    if device_id:
        command.extend(("--device-id", device_id))
    command_environment = dict(os.environ)
    local_capture_recipient = ""
    local_capture_sensitive_values: tuple[str, ...] = ()
    if args.local_capture_otp_broker:
        raw_phone = command_environment.get(
            "QWQ_PROVIDER_UAT_SMS_PHONE", ""
        ).strip()
        if not raw_phone:
            raw_phone = materialize_local_capture_ui_acceptance_phone(
                environment=environment,
                target_name=target_name,
                actor_index=_local_capture_ui_actor_index(report_path),
            )
        app_phone, local_capture_recipient = _local_capture_phone_values(
            raw_phone
        )
        command_environment["QWQ_PROVIDER_UAT_SMS_PHONE"] = app_phone
        local_capture_sensitive_values = (
            app_phone,
            local_capture_recipient,
        )
    define_keys = tuple(
        str(key).strip() for key in args.define_key if str(key).strip()
    )
    if args.local_capture_otp_broker:
        define_keys += (
            "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
            "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
            "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
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
        "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
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
    broker_binding: ProtectedOTPBrokerBinding | None = None
    broker_port = 0
    broker_reverse_device_ids: list[str] = []
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
            if (
                runtime_identity is None
                or not runtime_identity.local_capture_sms_enabled
            ):
                raise ValueError(
                    "active candidate does not select the SMS local-capture "
                    "Provider composition"
                )
            broker = ProtectedOTPBroker(
                environment=environment,
                target_name=target_name,
                recipient=local_capture_recipient,
                reader=read_latest_debug_otp,
                max_consumptions=2 if args.platform == "all" else 1,
            )
            broker_binding = broker.start()
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_URL"
            ] = broker_binding.url
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN"
            ] = broker_binding.token
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64"
            ] = broker_binding.ca_certificate_base64
            broker_port = _validated_broker_port(broker_binding)
            for android_device_id in _android_broker_device_ids(
                platform=args.platform,
                explicit_device_id=device_id,
            ):
                _configure_android_broker_reverse(
                    action="add",
                    device_id=android_device_id,
                    port=broker_port,
                )
                broker_reverse_device_ids.append(android_device_id)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=command_environment,
            check=False,
        )
        if runtime_identity is not None:
            try:
                _bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=runtime_identity,
                    binding=broker_binding,
                    assertion_ids=assertion_ids,
                    sensitive_values=tuple(
                        dict.fromkeys(
                            (
                                *local_capture_sensitive_values,
                                *(
                                    command_environment.get(key, "").strip()
                                    for key in define_keys
                                    if key in _PROTECTED_SMS_DEFINE_KEYS
                                    if command_environment.get(key, "").strip()
                                ),
                                *(
                                    f"{key}={command_environment.get(key, '').strip()}"
                                    for key in define_keys
                                    if key in _PROTECTED_SMS_DEFINE_KEYS
                                    if command_environment.get(key, "").strip()
                                ),
                            )
                        )
                    ),
                )
            except (OSError, ValueError) as exc:
                print(f"GATE_BLOCK: {exc}", file=sys.stderr)
                return 2
        return completed.returncode
    finally:
        for android_device_id in broker_reverse_device_ids:
            _configure_android_broker_reverse(
                action="remove",
                device_id=android_device_id,
                port=broker_port,
            )
        if broker is not None:
            broker.close()


if __name__ == "__main__":
    raise SystemExit(main())
