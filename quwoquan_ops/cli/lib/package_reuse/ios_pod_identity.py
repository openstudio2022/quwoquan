"""Portable CocoaPods command identity for sealed iOS dependency inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_COCOAPODS_VERSION = "1.16.2"

_DIGEST_PREFIX = "sha256:"
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?$")
_EXECUTABLE_PATH = re.compile(r"^Executable Path:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class CocoaPodsIdentity:
    executable: Path | None
    version: str
    executable_digest: str
    runtime_environment_digest: str
    command_resolution_digest: str

    def as_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "executableDigest": self.executable_digest,
            "runtimeEnvironmentDigest": self.runtime_environment_digest,
            "commandResolutionDigest": self.command_resolution_digest,
        }


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _read_regular_nofollow(path: Path, *, label: str) -> tuple[bytes, int]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("iOS Pod capsule requires O_NOFOLLOW")
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
    except OSError as error:
        raise ValueError(f"iOS Pod {label} is unavailable") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"iOS Pod {label} is not a unique regular file")
        content = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            content.extend(chunk)
        after = os.fstat(descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_nlink,
            item.st_size,
            item.st_mtime_ns,
        )
        if identity(before) != identity(after):
            raise ValueError(f"iOS Pod {label} changed during read")
    finally:
        os.close(descriptor)
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    return bytes(content), mode


def _inspect_output(command: list[str], *, private_root: Path) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env={
                "PATH": os.environ.get("PATH", ""),
                "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                "HOME": str(private_root / "user-home"),
                "XDG_CONFIG_HOME": str(private_root / "user-home/.config"),
                "XDG_CACHE_HOME": str(private_root / "user-home/.cache"),
                "CP_HOME_DIR": str(private_root / "cp-home"),
                "CP_CACHE_DIR": str(private_root / "cp-cache"),
                "COCOAPODS_DISABLE_STATS": "true",
                "COCOAPODS_SKIP_UPDATE_MESSAGE": "true",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("iOS Pod CocoaPods inspection failed") from error
    if result.returncode != 0:
        raise ValueError("iOS Pod CocoaPods inspection failed")
    return result.stdout.strip()


def _runtime_environment_digest(value: str, *, expected_version: str) -> str:
    section = ""
    stack: dict[str, str] = {}
    plugins: dict[str, str] = {}
    for raw in value.splitlines():
        line = raw.strip()
        if line == "### Stack":
            section = "stack"
            continue
        if line == "### Plugins":
            section = "plugins"
            continue
        if line.startswith("### "):
            section = ""
            continue
        if section == "stack" and ":" in line:
            key, raw_value = (item.strip() for item in line.split(":", 1))
            if key in {"CocoaPods", "Ruby", "RubyGems"}:
                if key in stack or not raw_value:
                    raise ValueError("iOS Pod CocoaPods runtime stack is invalid")
                stack[key] = raw_value
        elif section == "plugins" and ":" in line:
            key, raw_value = (item.strip() for item in line.split(":", 1))
            if key and raw_value and not key.startswith("```"):
                if key in plugins:
                    raise ValueError("iOS Pod CocoaPods plugin set is duplicated")
                plugins[key] = raw_value
    if stack and stack.get("CocoaPods") != expected_version:
        raise ValueError("iOS Pod CocoaPods runtime version is inconsistent")
    return _digest_bytes(
        _canonical_bytes(
            {
                "stack": dict(sorted(stack.items())),
                "plugins": dict(sorted(plugins.items())),
            }
        )
    )


def inspect_cocoapods_executable(executable: str | Path) -> CocoaPodsIdentity:
    """Bind the exact self-reported CocoaPods executable and supported version."""

    try:
        resolved = Path(executable).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("iOS Pod CocoaPods executable is unavailable") from error
    content, mode = _read_regular_nofollow(resolved, label="CocoaPods executable")
    if not mode & 0o111:
        raise ValueError("iOS Pod CocoaPods executable is not executable")
    with tempfile.TemporaryDirectory(prefix="qwq-pod-inspect-") as raw_private:
        private_root = Path(raw_private)
        for relative in ("user-home", "cp-home", "cp-cache"):
            (private_root / relative).mkdir(mode=0o700)
        version = _inspect_output(
            [str(resolved), "--version"], private_root=private_root
        )
        environment = _inspect_output([str(resolved), "env"], private_root=private_root)
    after_content, after_mode = _read_regular_nofollow(
        resolved, label="CocoaPods executable"
    )
    if after_content != content or after_mode != mode:
        raise ValueError("iOS Pod CocoaPods executable changed during inspection")
    match = _EXECUTABLE_PATH.search(environment)
    if not _VERSION.fullmatch(version) or version != SUPPORTED_COCOAPODS_VERSION:
        raise ValueError(f"iOS Pod requires CocoaPods {SUPPORTED_COCOAPODS_VERSION}")
    if match is None:
        raise ValueError("iOS Pod CocoaPods did not report its executable")
    try:
        reported = Path(match.group(1)).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("iOS Pod reported CocoaPods executable is invalid") from error
    if reported != resolved:
        raise ValueError("iOS Pod CocoaPods executable is internally inconsistent")
    executable_digest = _digest_bytes(content)
    runtime_environment_digest = _runtime_environment_digest(
        environment,
        expected_version=version,
    )
    identity = {
        "version": version,
        "executableDigest": executable_digest,
        "runtimeEnvironmentDigest": runtime_environment_digest,
    }
    return CocoaPodsIdentity(
        executable=resolved,
        version=version,
        executable_digest=executable_digest,
        runtime_environment_digest=runtime_environment_digest,
        command_resolution_digest=_digest_bytes(_canonical_bytes(identity)),
    )
