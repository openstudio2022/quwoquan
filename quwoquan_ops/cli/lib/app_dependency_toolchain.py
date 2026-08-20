"""Resolve App native dependency tools to one self-consistent runtime."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class AppDependencyToolchainError(RuntimeError):
    """A required native dependency tool is absent or internally inconsistent."""


def _inspect_pod(executable: str) -> tuple[str, str]:
    try:
        version = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        environment = subprocess.run(
            [executable, "env"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppDependencyToolchainError(str(error)) from error
    runtime_version = version.stdout.strip()
    match = re.search(r"Executable Path:\s*(\S+)", environment.stdout)
    reported = str(Path(match.group(1)).resolve()) if match else ""
    if version.returncode != 0 or environment.returncode != 0:
        raise AppDependencyToolchainError(
            f"pod inspection failed: version={version.returncode} env={environment.returncode}"
        )
    return runtime_version, reported


def resolve_cocoapods_executable(candidate: str = "") -> str:
    """Normalize a shell wrapper to CocoaPods' exact self-reported executable."""

    discovered = candidate.strip() or shutil.which("pod") or ""
    if not discovered:
        raise AppDependencyToolchainError("pod executable not found")
    wrapper = str(Path(discovered).resolve())
    wrapper_version, reported = _inspect_pod(wrapper)
    if wrapper_version != "1.16.2" or not reported or not Path(reported).is_file():
        raise AppDependencyToolchainError(
            "expected CocoaPods 1.16.2; "
            f"wrapper={wrapper} runtime={wrapper_version or '<missing>'} "
            f"reported={reported or '<missing>'}"
        )
    runtime_version, runtime_reported = _inspect_pod(reported)
    if runtime_version != "1.16.2" or runtime_reported != reported:
        raise AppDependencyToolchainError(
            "CocoaPods runtime is not self-consistent; "
            f"wrapper={wrapper} runtime={runtime_version or '<missing>'} "
            f"reported={runtime_reported or '<missing>'} expected={reported}"
        )
    return reported
