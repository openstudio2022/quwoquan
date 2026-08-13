"""iOS Simulator 系统信任安装与 HTTPS 探针（逐字搬移）。

``_require_success`` / ``_probe_ios_system_trust`` 是测试的 patch 锚点，
包内消费一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import hashlib
import platform
from pathlib import Path

import quwoquan_ops.cli.lib.local_device_trust as _pkg

from ..output_paths import target_cache_dir
from .constants import _ROOT
from .device_commands import _target_probe_url
from .errors import LocalDeviceTrustError


def _ios_probe_binary(target: str) -> Path:
    source = _ROOT / "quwoquan_ops/cli/tools/ios_simulator_system_trust_probe.swift"
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    binary = target_cache_dir(target) / "device-trust" / f"ios-probe-{source_digest}"
    if binary.is_file():
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    sdk = _pkg._require_success(
        ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"],
        action="iOS Simulator SDK resolution",
    ).stdout.strip()
    architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
    _pkg._require_success(
        [
            "xcrun",
            "--sdk",
            "iphonesimulator",
            "swiftc",
            "-sdk",
            sdk,
            "-target",
            f"{architecture}-apple-ios17.0-simulator",
            str(source),
            "-o",
            str(binary),
        ],
        action="iOS system-trust probe build",
        timeout=180,
    )
    return binary


def _probe_ios_system_trust(target: str, device: str) -> str:
    probe = _ios_probe_binary(target)
    result = _pkg._require_success(
        [
            "xcrun",
            "simctl",
            "spawn",
            device,
            str(probe),
            _target_probe_url(target),
        ],
        action="iOS Simulator default system-trust HTTPS probe",
        timeout=40,
    )
    if "system-trust-ok" not in result.stdout:
        raise LocalDeviceTrustError("iOS system-trust probe emitted no success receipt")
    return result.stdout.strip()


def _install_ios(
    target: str,
    device: str,
    root: Path,
    *,
    endpoint_probe: bool,
) -> str:
    _pkg._require_success(
        ["xcrun", "simctl", "keychain", device, "add-root-cert", str(root)],
        action="iOS Simulator root certificate installation",
    )
    if endpoint_probe:
        return _pkg._probe_ios_system_trust(target, device)
    return "system-root-installed; endpoint-probe-deferred"
