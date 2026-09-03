"""Redacted, private diagnostics for App dependency sync attempts."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

from quwoquan_ops.cli.lib.package_reuse.dependency_fs import _directory_fd

_SENSITIVE_MATERIAL_MARKERS = (
    "-----begin private key-----",
    "privatekey",
    "private_key",
    "private-key",
    "trustedpublickeys",
    "trusted_public_keys",
    "trusted-public-keys",
    "keyring",
    "qwq_android_runtime_config_asset_root",
    "runtime-config-trust.json",
)
_REDACTED_DEPENDENCY_MATERIAL = "[REDACTED dependency trust material]"


def dependency_failure_cause(exc: BaseException) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "subprocess_timeout"
    if isinstance(exc, subprocess.CalledProcessError):
        return "subprocess_nonzero"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, UnicodeError):
        return "invalid_text"
    if isinstance(exc, OSError):
        return "io_error"
    if isinstance(exc, TypeError):
        return "type_error"
    if isinstance(exc, ValueError):
        return "value_error"
    if isinstance(exc, RuntimeError):
        return "runtime_error"
    return "unknown_error"


def redact_dependency_failure_text(
    value: object, *, sensitive_values: tuple[str, ...] = ()
) -> str:
    text = str(value or "")
    redacted = False
    for sensitive in sorted(
        {item for item in sensitive_values if item}, key=len, reverse=True
    ):
        if sensitive in text:
            redacted = True
            text = text.replace(sensitive, _REDACTED_DEPENDENCY_MATERIAL)
    if redacted or any(
        marker in text.casefold() for marker in _SENSITIVE_MATERIAL_MARKERS
    ):
        return _REDACTED_DEPENDENCY_MATERIAL
    text = re.sub(
        r"(?i)\b(authorization|password|passwd|token|secret|api[_-]?key)\b"
        r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return re.sub(
        r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text
    )


def write_private_log(
    path: Path, value: str, *, sensitive_values: tuple[str, ...] = ()
) -> None:
    value = redact_dependency_failure_text(
        value,
        sensitive_values=sensitive_values,
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = _directory_fd(path.parent, label="dependency process log parent")
    descriptor = -1
    try:
        os.fchmod(parent, 0o700)
        descriptor = os.open(
            path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("APP.DEPENDENCY.process_log_unsafe")
        os.fchmod(descriptor, 0o600)
        view = memoryview(value.encode("utf-8"))
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("App dependency process log write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)
