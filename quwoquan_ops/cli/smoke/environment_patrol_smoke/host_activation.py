"""Patrol UAT 宿主的 runtime config activation 编排。

与生产 canonical launcher 同构的两阶段冷启动：先用带 request digest 的专用冷启动激活
runtime config，再由 `patrol test` 正常启动宿主进入 Flutter。激活语义、CAS 判否与回执一致
性检查复用 `canonical_app_instance.activation.activate_runtime_config`，不在宿主侧另写一份。

`patrol test` 自己负责宿主的 build 与 install，但 activation 必须发生在宿主已安装、Flutter
尚未启动的窗口内，因此本模块先把宿主装到设备上，再投递请求；`patrol test` 随后的重装是
`install -r` 语义，已落盘的 active package 保留。
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
from quwoquan_ops.cli.lib.flutter_android_device_proxy import REAL_FLUTTER_ENV
from quwoquan_ops.cli.lib.package_reuse.patrol_command_envelope import (
    validate_patrol_command_environment,
)

from .constants import (
    APP_DIR,
    PATROL_ANDROID_ACTIVATION_COMPONENT,
    PATROL_ANDROID_PACKAGE,
    PATROL_HOST_DIR,
    PATROL_IOS_BUNDLE_ID,
)
from .execution import run_command

_ACTIVATION_TIMEOUT_SECONDS = 60.0
_HOST_BUILD_TIMEOUT_SECONDS = 1800
_HOST_INSTALL_TIMEOUT_SECONDS = 600
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTIVATION_ERROR_CODES = frozenset(
    {
        "APP.LAUNCH.compile_failed",
        "APP.LAUNCH.install_failed",
        "APP.LAUNCH.runtime_config_activation_failed",
    }
)
_ACTIVATION_ERROR_SUMMARIES = {
    "APP.LAUNCH.compile_failed": (
        "Patrol host compile did not complete; inspect the run-scoped build log"
    ),
    "APP.LAUNCH.install_failed": (
        "Patrol host install did not complete; inspect the run-scoped install log"
    ),
    "APP.LAUNCH.runtime_config_activation_failed": (
        "Patrol host runtime config activation did not complete"
    ),
}


class PatrolHostActivationError(RuntimeError):
    """宿主 activation 判否。调用方据此阻断，不得降级为跳过。"""

    def __init__(self, code: str) -> None:
        if code not in _ACTIVATION_ERROR_CODES:
            raise ValueError("Patrol host activation error code is invalid")
        self.code = code
        self.detail = _ACTIVATION_ERROR_SUMMARIES[code]
        super().__init__(f"GATE_BLOCK: {code}: {self.detail}")


def _canonical_device_module(name: str) -> Any:
    """按包导入生产 canonical launcher 的模块。

    `quwoquan_app/scripts/device` 不在包搜索路径上，因此先挂载该物理根，再走正常导入——
    activation 语义只有生产这一份实现，宿主编排不复制。
    """

    device_root = str(APP_DIR / "scripts" / "device")
    if device_root not in sys.path:
        sys.path.insert(0, device_root)
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise PatrolHostActivationError(
            "APP.LAUNCH.runtime_config_activation_failed"
        ) from error


def _is_android(device: dict[str, Any]) -> bool:
    return str(device.get("targetPlatform") or "").strip().lower().startswith("android")


def _canonical_device_shape(device: dict[str, Any]) -> tuple[str, bool]:
    target = str(device.get("targetPlatform") or "").strip().lower()
    if target.startswith("android"):
        platform = "android"
    elif target == "ios":
        platform = "ios"
    else:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    emulator = device.get("emulator")
    if type(emulator) is not bool:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    return platform, emulator


def _canonical_flutter_executable(command_env: dict[str, str]) -> str:
    try:
        identity = validate_patrol_command_environment(command_env)
    except (OSError, TypeError, ValueError) as error:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed") from error
    raw = command_env.get(REAL_FLUTTER_ENV)
    if not isinstance(raw, str) or not raw.strip():
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    value = raw.strip()
    if value != identity["executable"]:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    current = Path(candidate.anchor)
    try:
        for part in candidate.parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
        mode = candidate.lstat().st_mode
    except PatrolHostActivationError:
        raise
    except OSError as error:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed") from error
    if not stat.S_ISREG(mode) or not os.access(candidate, os.X_OK):
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    return value


def _canonical_android_debug_bridge(command_env: dict[str, str]) -> str:
    """Resolve adb only from locations authorized by the sealed command env."""

    home_value = str(command_env.get("HOME") or "").strip()
    home_dir = Path(home_value) if home_value else Path("/__qwq_missing_home__")
    try:
        raw = resolve_android_debug_bridge(
            environ=dict(command_env),
            home_dir=home_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise PatrolHostActivationError("APP.LAUNCH.install_failed") from error
    if not isinstance(raw, str) or not raw:
        raise PatrolHostActivationError("APP.LAUNCH.install_failed")
    candidate = Path(raw)
    if (
        not candidate.is_absolute()
        or str(candidate) != raw
        or any(part in {"", ".", ".."} for part in candidate.parts[1:])
    ):
        raise PatrolHostActivationError("APP.LAUNCH.install_failed")

    executable = "adb.exe" if os.name == "nt" else "adb"
    allowed: set[Path] = set()
    for entry in str(command_env.get("PATH") or "").split(os.pathsep):
        if entry:
            allowed.add(Path(entry) / executable)
    for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        sdk_root = str(command_env.get(key) or "").strip()
        if sdk_root:
            allowed.add(Path(sdk_root) / "platform-tools" / executable)
    if home_value:
        allowed.update(
            {
                home_dir
                / "Library"
                / "Android"
                / "sdk"
                / "platform-tools"
                / executable,
                home_dir / "Android" / "Sdk" / "platform-tools" / executable,
            }
        )
    if (
        candidate not in allowed
        or not candidate.is_file()
        or not os.access(candidate, os.X_OK)
    ):
        raise PatrolHostActivationError("APP.LAUNCH.install_failed")
    return raw


def _host_artifact(device: dict[str, Any]) -> Path:
    if _is_android(device):
        return (
            PATROL_HOST_DIR
            / "build"
            / "app"
            / "outputs"
            / "flutter-apk"
            / "app-debug.apk"
        )
    ios_product = "iphonesimulator" if device.get("emulator") is True else "iphoneos"
    return PATROL_HOST_DIR / "build" / "ios" / ios_product / "Runner.app"


def _build_host(
    device: dict[str, Any],
    command_env: dict[str, str],
    log_directory: Path,
) -> None:
    flutter = _canonical_flutter_executable(command_env)
    if _is_android(device):
        command = [flutter, "build", "apk", "--debug", "--no-pub"]
    else:
        command = [flutter, "build", "ios", "--debug"]
        if device.get("emulator") is True:
            command.extend(["--simulator", "--no-codesign"])
        command.append("--no-pub")
    try:
        result = run_command(
            command,
            cwd=PATROL_HOST_DIR,
            env=command_env,
            timeout_seconds=_HOST_BUILD_TIMEOUT_SECONDS,
            log_path=log_directory / "patrol-host-build.log",
        )
        if result.get("exitCode") != 0:
            raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
        artifact = _host_artifact(device)
        if not artifact.exists():
            raise PatrolHostActivationError("APP.LAUNCH.compile_failed")
    except PatrolHostActivationError:
        raise
    except Exception as error:
        raise PatrolHostActivationError("APP.LAUNCH.compile_failed") from error


def _install_host(
    device: dict[str, Any],
    command_env: dict[str, str],
    log_directory: Path,
) -> None:
    device_id = str(device.get("id") or "").strip()
    if not device_id:
        raise PatrolHostActivationError("APP.LAUNCH.install_failed")
    artifact = _host_artifact(device)
    if _is_android(device):
        adb = _canonical_android_debug_bridge(command_env)
        command = [adb, "-s", device_id, "install", "-r", str(artifact)]
    elif device.get("emulator") is True:
        command = ["xcrun", "simctl", "install", device_id, str(artifact)]
    else:
        command = [
            "xcrun", "devicectl", "device", "install", "app",
            "--device", device_id, str(artifact),
        ]
    try:
        result = run_command(
            command,
            cwd=PATROL_HOST_DIR,
            env=command_env,
            timeout_seconds=_HOST_INSTALL_TIMEOUT_SECONDS,
            log_path=log_directory / "patrol-host-install.log",
        )
        if result.get("exitCode") != 0:
            raise PatrolHostActivationError("APP.LAUNCH.install_failed")
    except PatrolHostActivationError:
        raise
    except Exception as error:
        raise PatrolHostActivationError("APP.LAUNCH.install_failed") from error


def _validated_activation_receipt(
    receipt: object,
    launcher_handoff: dict[str, Any],
) -> dict[str, Any]:
    """把可公开的宿主成功证据绑定回 canonical handoff 身份。"""

    if not isinstance(receipt, dict) or receipt.get("status") != "activated":
        raise PatrolHostActivationError("APP.LAUNCH.runtime_config_activation_failed")
    active_package_digest = receipt.get("activePackageDigest")
    request_digest = receipt.get("requestDigest")
    if (
        _DIGEST_PATTERN.fullmatch(str(active_package_digest or "")) is None
        or _DIGEST_PATTERN.fullmatch(str(request_digest or "")) is None
    ):
        raise PatrolHostActivationError("APP.LAUNCH.runtime_config_activation_failed")

    identity_fields = (
        ("packageDigest", "runtimeConfigPackageDigest"),
        ("trustEnvelopeDigest", "runtimeConfigTrustEnvelopeDigest"),
        ("effectiveLaunchManifestDigest", "effectiveLaunchManifestDigest"),
        ("environment", "environment"),
        ("buildProfile", "buildProfile"),
        ("target", "target"),
    )
    for receipt_field, handoff_field in identity_fields:
        expected = launcher_handoff.get(handoff_field)
        if expected in {None, ""} or receipt.get(receipt_field) != expected:
            raise PatrolHostActivationError(
                "APP.LAUNCH.runtime_config_activation_failed"
            )
    if active_package_digest != launcher_handoff.get("runtimeConfigPackageDigest"):
        raise PatrolHostActivationError("APP.LAUNCH.runtime_config_activation_failed")
    return receipt


def activate_patrol_host_runtime_config(
    args: argparse.Namespace,
    device: dict[str, Any],
    launcher_handoff: dict[str, Any],
    command_env: dict[str, str],
    log_directory: Path,
) -> dict[str, Any]:
    """在 UAT 宿主上执行与生产同构的 runtime config activation。

    返回 active activation 回执，供上层写入证据。任何一步判否都抛
    `PatrolHostActivationError`，不允许降级为「未激活也继续跑 UAT」——那会让宿主在没有
    runtime config 的情况下声称通过。
    """

    platform, emulator = _canonical_device_shape(device)
    if platform == "android":
        device_kind = "android_emulator" if emulator else "android_physical"
        activation_component = PATROL_ANDROID_ACTIVATION_COMPONENT
        application_id = PATROL_ANDROID_PACKAGE
    else:
        device_kind = "ios-simulator" if emulator else "ios-physical"
        activation_component = ""
        application_id = PATROL_IOS_BUNDLE_ID

    _build_host(device, command_env, log_directory)
    _install_host(device, command_env, log_directory)

    try:
        activation_module = _canonical_device_module(
            "canonical_app_instance.activation"
        )
        driver_module = _canonical_device_module("run_app_instance")
        driver = driver_module.build_platform_driver(
            device_kind=device_kind,
            device_id=str(device["id"]),
            application_id=application_id,
            # 宿主的 Flutter 入口由 patrol test 决定，activation 阶段不启动 Flutter；
            # entrypoint 只为满足 driver 的构造契约。
            entrypoint="lib/main.dart",
            activation_component=activation_component,
        )
        receipt = activation_module.activate_runtime_config(
            handoff=launcher_handoff,
            platform_driver=driver,
            activation_timeout_seconds=_ACTIVATION_TIMEOUT_SECONDS,
        )
        return _validated_activation_receipt(receipt, launcher_handoff)
    except PatrolHostActivationError:
        raise
    except Exception as error:
        raise PatrolHostActivationError(
            "APP.LAUNCH.runtime_config_activation_failed"
        ) from error


def ensure_patrol_host_runtime_config(
    args: argparse.Namespace,
    device: dict[str, Any],
    launcher_handoff: dict[str, Any],
    command_env: dict[str, str],
    log_directory: Path,
    report: dict[str, Any],
) -> None:
    """激活宿主并把通过态写进证据；判否抛 `PatrolHostActivationError`。"""

    receipt = activate_patrol_host_runtime_config(
        args,
        device,
        launcher_handoff,
        command_env,
        log_directory,
    )
    report["hostRuntimeConfigActivation"] = {
        "status": "activated",
        "activePackageDigest": str(receipt["activePackageDigest"]),
        "requestDigest": str(receipt["requestDigest"]),
    }


def record_patrol_host_activation_gate_block(
    error: PatrolHostActivationError,
    report: dict[str, Any],
    device: dict[str, Any],
    device_manifest_path: Any,
    local_tls_trust: Any,
    android_port_reverse: Any,
    release_uat_state_reset: Any,
) -> None:
    """把宿主 activation 判否落进证据。

    宿主没拿到 runtime config 时不存在「继续跑但结论可信」的中间态，因此本设备判否收尾，
    不把未激活的宿主跑出一份通过态回执。
    """

    first_blocker = error.code
    report["hostRuntimeConfigActivation"] = {
        "status": "gate_block",
        "firstBlocker": first_blocker,
        "failureReason": error.detail,
    }
    report["runs"].append(
        {
            "device": device,
            "status": "gate_block",
            "firstBlocker": first_blocker,
            "failureReason": error.detail,
            "preflight": {
                "deviceManifestPath": device_manifest_path,
                "localTlsTrust": local_tls_trust,
                "androidPortReverse": android_port_reverse,
                "releaseUatStateReset": release_uat_state_reset,
            },
        }
    )
