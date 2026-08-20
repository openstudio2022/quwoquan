"""Readback of built App artifact identity and signing material.

``stackctl package --kind app-artifact`` must not trust the identity it asked
the toolchain to build; it reads application/bundle id and signature back out of
the produced artifact. That readback owns its own toolchain discovery and typed
failures, so it lives beside the writer instead of inside it.

角色：lib。owner 为 quwoquan_ops/cli/commands/package_app_artifact.py。
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shutil
import subprocess
from pathlib import Path


class AppArtifactBuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def locate_android_tool(name: str) -> str:
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(variable, "").strip()
        if not root:
            continue
        candidates = sorted((Path(root) / "build-tools").glob(f"*/{name}"))
        if candidates:
            return str(candidates[-1])
    return shutil.which(name) or ""


def bundletool_command() -> list[str]:
    executable = os.environ.get("QWQ_BUNDLETOOL_EXECUTABLE", "").strip()
    if executable:
        return [executable]
    discovered = shutil.which("bundletool")
    if discovered:
        return [discovered]
    jar = os.environ.get("QWQ_BUNDLETOOL_JAR", "").strip()
    if jar and Path(jar).is_file():
        java = shutil.which("java")
        if java:
            return [java, "-jar", str(Path(jar).resolve())]
    raise AppArtifactBuildError(
        "APP.PACKAGE.identity_tool_missing: set QWQ_BUNDLETOOL_EXECUTABLE "
        "or QWQ_BUNDLETOOL_JAR for AAB readback"
    )


def read_android_identity(artifact: Path, expected: str) -> str:
    if artifact.suffix == ".aab":
        result = subprocess.run(
            [
                *bundletool_command(),
                "dump",
                "manifest",
                f"--bundle={artifact}",
                "--module=base",
                "--xpath=/manifest/@package",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        actual = result.stdout.strip().strip('"')
        if result.returncode != 0 or actual != expected:
            raise AppArtifactBuildError(
                "APP.PACKAGE.identity_mismatch: "
                f"expected={expected} actual={actual or '<missing>'}"
            )
        return actual
    aapt = locate_android_tool("aapt")
    if not aapt:
        raise AppArtifactBuildError("APP.PACKAGE.identity_tool_missing: aapt")
    result = subprocess.run(
        [aapt, "dump", "badging", str(artifact)],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(r"package: name='([^']+)'", result.stdout)
    actual = match.group(1) if match else ""
    if result.returncode != 0 or actual != expected:
        raise AppArtifactBuildError(
            "APP.PACKAGE.identity_mismatch: "
            f"expected={expected} actual={actual or '<missing>'}"
        )
    return actual


def read_ios_identity(artifact: Path, expected: str) -> str:
    info = artifact / "Info.plist"
    if not info.is_file():
        raise AppArtifactBuildError("APP.PACKAGE.identity_missing: iOS Info.plist")
    value = plistlib.loads(info.read_bytes())
    actual = str(value.get("CFBundleIdentifier") or "")
    if actual != expected:
        raise AppArtifactBuildError(
            f"APP.PACKAGE.identity_mismatch: expected={expected} actual={actual}"
        )
    return actual


def signing_digest(platform: str, artifact: Path) -> str:
    if platform == "android":
        if artifact.suffix == ".aab":
            keytool = shutil.which("keytool")
            if not keytool:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.signature_tool_missing: keytool"
                )
            result = subprocess.run(
                [keytool, "-printcert", "-jarfile", str(artifact)],
                check=False,
                capture_output=True,
                text=True,
            )
            match = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", result.stdout)
            if result.returncode != 0 or match is None:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.signature_readback_failed"
                )
            return "sha256:" + match.group(1).replace(":", "").lower()
        apksigner = locate_android_tool("apksigner")
        if not apksigner:
            raise AppArtifactBuildError(
                "APP.PACKAGE.signature_tool_missing: apksigner"
            )
        result = subprocess.run(
            [apksigner, "verify", "--print-certs", str(artifact)],
            check=False,
            capture_output=True,
            text=True,
        )
        match = re.search(
            r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)", result.stdout
        )
        if result.returncode != 0 or match is None:
            raise AppArtifactBuildError("APP.PACKAGE.signature_readback_failed")
        normalized = match.group(1).replace(":", "").lower()
        return "sha256:" + normalized
    if platform == "ios":
        result = subprocess.run(
            ["codesign", "-d", "--verbose=4", str(artifact)],
            check=False,
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        match = re.search(r"CDHash=([0-9A-Fa-f]+)", combined)
        if match:
            return sha256_bytes(match.group(1).lower().encode("ascii"))
        return sha256_bytes(b"unsigned-ios-simulator")
    return sha256_bytes(b"web-not-applicable")
