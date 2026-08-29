"""Bind page-smoke evidence to the App that Patrol actually installed.

Patrol executes against the physically isolated ``test_host/patrol`` App.  This
module therefore reads identity from that host's build output and from the
installed payload.  It deliberately does not copy candidate, launcher handoff,
runtime-package, trust, or launch-attempt identity into the binding.
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.android import (
    resolve_android_debug_bridge,
)
from quwoquan_ops.cli.lib.generated.app_launch_contract import LAUNCH_BLOCKERS

from .constants import PATROL_HOST_DIR, REPO_ROOT

TESTED_APP_ARTIFACT_BINDING_SCHEMA = (
    "environment-page-smoke.tested-app-artifact-binding.v1"
)
TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA = (
    "environment-page-smoke.tested-app-artifact-binding-set.v1"
)
TESTED_APP_ARTIFACT_BINDING_PROVENANCE = "test_host_patrol"
APP_PAGE_ARTIFACT_BINDING_BLOCKER = "APP.UAT.page_artifact_binding_missing"
if APP_PAGE_ARTIFACT_BINDING_BLOCKER not in LAUNCH_BLOCKERS:
    raise RuntimeError(
        "canonical app-launch contract is missing the page artifact binding blocker"
    )

CANONICAL_COMPARISON_KEYS = (
    "applicationId",
    "artifactDigest",
    "sourceProjectionDigest",
    "runtimeConfigPackageDigest",
    "trustDigest",
    "launchAttemptId",
)
_TEST_HOST_UNOWNED_COMPARISON_KEYS = CANONICAL_COMPARISON_KEYS[2:]
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_APPLICATION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+$"
)
_READBACK_TIMEOUT_SECONDS = 120

CommandRunner = Callable[..., subprocess.CompletedProcess[Any]]


class TestedAppArtifactBindingError(RuntimeError):
    """Typed fail-closed result for an absent or unverifiable App binding."""

    code = APP_PAGE_ARTIFACT_BINDING_BLOCKER

    def __init__(self, detail: str) -> None:
        normalized = " ".join(str(detail).split()).strip() or "unknown readback failure"
        super().__init__(f"{self.code}: {normalized}")
        self.detail = normalized


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _platform_for_device(device: dict[str, Any]) -> str:
    target = str(device.get("targetPlatform") or "").strip().lower()
    if target.startswith("android"):
        return "android"
    if target == "ios":
        return "ios"
    raise TestedAppArtifactBindingError(
        f"unsupported device targetPlatform={target or '<missing>'}"
    )


def tested_app_build_artifact_path(device: dict[str, Any]) -> Path:
    """Return the final Patrol-host build output for the exact device class."""

    platform = _platform_for_device(device)
    if platform == "android":
        return (
            PATROL_HOST_DIR
            / "build"
            / "app"
            / "outputs"
            / "apk"
            / "debug"
            / "app-debug.apk"
        )
    sdk_directory = (
        "debug-iphonesimulator" if bool(device.get("emulator")) else "debug-iphoneos"
    )
    return (
        PATROL_HOST_DIR
        / "build"
        / "ios_integ"
        / "Build"
        / "Products"
        / sdk_directory
        / "Runner.app"
    )


def _snapshot_payload_files(
    root: Path,
    files: Iterable[Path],
) -> tuple[tuple[object, ...], ...]:
    snapshot: list[tuple[object, ...]] = []
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise TestedAppArtifactBindingError(
                f"payload contains an unsafe or missing file: {path}"
            )
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as error:
            raise TestedAppArtifactBindingError(
                "payload file escaped its declared root"
            ) from error
        stat = path.stat()
        snapshot.append(
            (
                relative,
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
            )
        )
    return tuple(snapshot)


def _tree_payload_digest(
    root: Path, files: Iterable[Path] | None = None
) -> tuple[str, int]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise TestedAppArtifactBindingError(
            f"payload tree is missing or unsafe: {root}"
        )

    def inventory() -> tuple[Path, ...]:
        entries = tuple(root.rglob("*"))
        unsafe = next((path for path in entries if path.is_symlink()), None)
        if unsafe is not None:
            raise TestedAppArtifactBindingError(
                f"payload tree contains a symlink: {unsafe}"
            )
        return tuple(path for path in entries if path.is_file())

    payload_files = inventory() if files is None else tuple(files)
    before = _snapshot_payload_files(root, payload_files)
    if not before:
        raise TestedAppArtifactBindingError(f"payload tree is empty: {root}")
    digest = hashlib.sha256()
    for relative, _device, _inode, size, _modified in before:
        encoded_relative = str(relative).encode("utf-8")
        digest.update(len(encoded_relative).to_bytes(8, "big"))
        digest.update(encoded_relative)
        digest.update(int(size).to_bytes(8, "big"))
        with (root / str(relative)).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    final_files = inventory() if files is None else payload_files
    if payload_files != final_files or before != _snapshot_payload_files(
        root, final_files
    ):
        raise TestedAppArtifactBindingError(
            "payload tree changed during digest readback"
        )
    return "sha256:" + digest.hexdigest(), len(before)


def artifact_payload_digest(path: Path, platform: str) -> str:
    """Use the AppArtifact payload algorithm and reject concurrent rewrites."""

    if not path.is_absolute() or path.is_symlink():
        raise TestedAppArtifactBindingError(
            "build artifact path must be an absolute non-symlink path"
        )
    if platform == "android":
        if path.suffix.lower() != ".apk" or not path.is_file():
            raise TestedAppArtifactBindingError(
                f"Android build artifact is not a readable APK: {path}"
            )
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if before_identity != after_identity:
            raise TestedAppArtifactBindingError(
                "Android build artifact changed during digest readback"
            )
        return "sha256:" + digest.hexdigest()
    if platform != "ios" or path.suffix.lower() != ".app":
        raise TestedAppArtifactBindingError(
            f"iOS build artifact is not an App bundle: {path}"
        )
    return _tree_payload_digest(path)[0]


def _locate_android_aapt(command_env: dict[str, str]) -> str:
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        root = str(command_env.get(variable) or "").strip()
        if not root:
            continue
        candidates = sorted((Path(root) / "build-tools").glob("*/aapt"))
        executable = next(
            (
                candidate
                for candidate in reversed(candidates)
                if candidate.is_file() and os.access(candidate, os.X_OK)
            ),
            None,
        )
        if executable is not None:
            return str(executable)
    return shutil.which("aapt", path=command_env.get("PATH")) or ""


def _run_text(
    run: CommandRunner,
    command: list[str],
    *,
    command_env: dict[str, str],
) -> subprocess.CompletedProcess[Any]:
    try:
        return run(
            command,
            env=command_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=_READBACK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TestedAppArtifactBindingError(
            f"readback command could not execute: {command[0]}: {error}"
        ) from error


def _text_output(result: subprocess.CompletedProcess[Any]) -> str:
    output = result.stdout
    if isinstance(output, bytes):
        try:
            return output.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TestedAppArtifactBindingError(
                "identity readback output is not UTF-8"
            ) from error
    return str(output or "")


def _read_android_apk_identity(
    artifact: Path,
    *,
    command_env: dict[str, str],
    run: CommandRunner,
    aapt: str,
) -> str:
    executable = aapt or _locate_android_aapt(command_env)
    if not executable:
        raise TestedAppArtifactBindingError(
            "Android APK identity tool aapt is unavailable"
        )
    result = _run_text(
        run,
        [executable, "dump", "badging", str(artifact)],
        command_env=command_env,
    )
    match = re.search(r"^package: name='([^']+)'", _text_output(result), re.MULTILINE)
    if result.returncode != 0 or match is None:
        raise TestedAppArtifactBindingError("Android APK applicationId readback failed")
    return match.group(1).strip()


def _read_ios_bundle_identity(artifact: Path) -> str:
    info_path = artifact / "Info.plist"
    if info_path.is_symlink() or not info_path.is_file():
        raise TestedAppArtifactBindingError("iOS App Info.plist is unavailable")
    try:
        payload = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise TestedAppArtifactBindingError(
            "iOS App Info.plist is unreadable"
        ) from error
    return str(payload.get("CFBundleIdentifier") or "").strip()


def _read_artifact_identity(
    artifact: Path,
    platform: str,
    *,
    command_env: dict[str, str],
    run: CommandRunner,
    android_aapt: str,
) -> str:
    if platform == "android":
        return _read_android_apk_identity(
            artifact,
            command_env=command_env,
            run=run,
            aapt=android_aapt,
        )
    return _read_ios_bundle_identity(artifact)


def _declared_application_id(command: list[str], platform: str) -> str:
    flag = "--package-name" if platform == "android" else "--bundle-id"
    values: list[str] = []
    for index, argument in enumerate(command):
        if argument.startswith(flag + "="):
            values.append(argument.split("=", 1)[1].strip())
        elif argument == flag and index + 1 < len(command):
            values.append(str(command[index + 1]).strip())
    distinct = tuple(dict.fromkeys(value for value in values if value))
    if len(distinct) != 1:
        raise TestedAppArtifactBindingError(
            f"Patrol command must declare exactly one {flag}"
        )
    return distinct[0]


def _validate_application_id(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if _APPLICATION_ID_PATTERN.fullmatch(normalized) is None:
        raise TestedAppArtifactBindingError(f"{label} is missing or invalid")
    return normalized


def _validate_digest(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if _DIGEST_PATTERN.fullmatch(normalized) is None:
        raise TestedAppArtifactBindingError(f"{label} is missing or invalid")
    return normalized


def _android_installed_readback(
    *,
    device_id: str,
    application_id: str,
    command_env: dict[str, str],
    run: CommandRunner,
    adb: str,
    aapt: str,
) -> dict[str, str]:
    executable = adb or resolve_android_debug_bridge(environ=command_env)
    if not executable:
        raise TestedAppArtifactBindingError("Android adb is unavailable")

    def installed_path() -> str:
        result = _run_text(
            run,
            [executable, "-s", device_id, "shell", "pm", "path", application_id],
            command_env=command_env,
        )
        paths = [
            line.removeprefix("package:").strip()
            for line in _text_output(result).splitlines()
            if line.strip().startswith("package:")
        ]
        if (
            result.returncode != 0
            or len(paths) != 1
            or not paths[0].startswith("/")
            or not paths[0].lower().endswith(".apk")
        ):
            raise TestedAppArtifactBindingError(
                "installed Android base.apk path is missing or ambiguous"
            )
        return paths[0]

    before_path = installed_path()
    with tempfile.TemporaryDirectory(prefix="qwq-patrol-installed-apk.") as temporary:
        destination = Path(temporary) / "base.apk"
        pull = _run_text(
            run,
            [executable, "-s", device_id, "pull", before_path, str(destination)],
            command_env=command_env,
        )
        if pull.returncode != 0 or not destination.is_file():
            raise TestedAppArtifactBindingError(
                "installed Android base.apk pull/readback failed"
            )
        digest = artifact_payload_digest(destination, "android")
        installed_identity = _read_android_apk_identity(
            destination,
            command_env=command_env,
            run=run,
            aapt=aapt,
        )
    if before_path != installed_path():
        raise TestedAppArtifactBindingError(
            "installed Android base.apk changed during readback"
        )
    return {
        "status": "readable",
        "method": "adb_pm_path_pull_base_apk",
        "applicationId": installed_identity,
        "artifactDigest": digest,
        "locatorDigest": _sha256_bytes(before_path.encode("utf-8")),
    }


def _ios_installed_readback(
    *,
    device: dict[str, Any],
    application_id: str,
    command_env: dict[str, str],
    run: CommandRunner,
) -> dict[str, str]:
    if not bool(device.get("emulator")):
        raise TestedAppArtifactBindingError(
            "physical iOS installed App payload readback is unavailable"
        )
    device_id = str(device.get("id") or "").strip()

    def installed_path() -> Path:
        result = _run_text(
            run,
            [
                "xcrun",
                "simctl",
                "get_app_container",
                device_id,
                application_id,
                "app",
            ],
            command_env=command_env,
        )
        raw_path = _text_output(result).strip()
        if result.returncode != 0 or not raw_path:
            raise TestedAppArtifactBindingError(
                "installed iOS App container readback is unavailable"
            )
        candidate = Path(raw_path)
        if not candidate.is_absolute() or candidate.is_symlink():
            raise TestedAppArtifactBindingError(
                "installed iOS App container path is unsafe"
            )
        resolved = candidate.resolve()
        if resolved.suffix.lower() != ".app" or not resolved.is_dir():
            raise TestedAppArtifactBindingError(
                "installed iOS App container is not a readable App bundle"
            )
        return resolved

    before_path = installed_path()
    digest = artifact_payload_digest(before_path, "ios")
    installed_identity = _read_ios_bundle_identity(before_path)
    if before_path != installed_path():
        raise TestedAppArtifactBindingError(
            "installed iOS App container changed during readback"
        )
    return {
        "status": "readable",
        "method": "simctl_get_app_container_app_tree",
        "applicationId": installed_identity,
        "artifactDigest": digest,
        "locatorDigest": _sha256_bytes(str(before_path).encode("utf-8")),
    }


def _git_host_source_files(host_root: Path, repo_root: Path) -> tuple[Path, ...]:
    try:
        relative_root = host_root.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise TestedAppArtifactBindingError(
            "Patrol host source root escaped the repository"
        ) from error
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                relative_root,
            ],
            capture_output=True,
            check=False,
            timeout=_READBACK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TestedAppArtifactBindingError(
            f"Patrol host source inventory is unavailable: {error}"
        ) from error
    if result.returncode != 0 or not isinstance(result.stdout, bytes):
        raise TestedAppArtifactBindingError(
            "Patrol host source inventory could not be read"
        )
    try:
        names = [value.decode("utf-8") for value in result.stdout.split(b"\0") if value]
    except UnicodeDecodeError as error:
        raise TestedAppArtifactBindingError(
            "Patrol host source inventory contains a non-UTF-8 path"
        ) from error
    files = tuple(repo_root / name for name in names)
    if not files:
        raise TestedAppArtifactBindingError("Patrol host source inventory is empty")
    return files


def _host_source_digest(
    repo_root: Path,
    files: tuple[Path, ...],
) -> tuple[str, int]:
    """Hash regular source bytes and repository-contained symlink identities."""

    def snapshot() -> tuple[tuple[object, ...], ...]:
        entries: list[tuple[object, ...]] = []
        for path in sorted(files):
            try:
                relative = path.relative_to(repo_root).as_posix()
            except ValueError as error:
                raise TestedAppArtifactBindingError(
                    "Patrol host source escaped the repository"
                ) from error
            stat = path.lstat()
            if path.is_symlink():
                link_target = os.readlink(path)
                if os.path.isabs(link_target):
                    raise TestedAppArtifactBindingError(
                        "Patrol host source contains an absolute symlink"
                    )
                resolved_target = (path.parent / link_target).resolve()
                try:
                    resolved_target.relative_to(repo_root)
                except ValueError as error:
                    raise TestedAppArtifactBindingError(
                        "Patrol host source symlink escaped the repository"
                    ) from error
                kind = "symlink"
                content_identity = link_target
            elif path.is_file():
                kind = "file"
                content_identity = ""
            else:
                raise TestedAppArtifactBindingError(
                    f"Patrol host source entry is missing or unsafe: {path}"
                )
            entries.append(
                (
                    relative,
                    kind,
                    content_identity,
                    stat.st_dev,
                    stat.st_ino,
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            )
        return tuple(entries)

    before = snapshot()
    if not before:
        raise TestedAppArtifactBindingError("Patrol host source inventory is empty")
    digest = hashlib.sha256(b"test-host-source-v1\0")
    for relative, kind, link_target, _device, _inode, size, _modified in before:
        relative_bytes = str(relative).encode("utf-8")
        kind_bytes = str(kind).encode("ascii")
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(len(kind_bytes).to_bytes(8, "big"))
        digest.update(kind_bytes)
        if kind == "symlink":
            payload = str(link_target).encode("utf-8")
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
            continue
        digest.update(int(size).to_bytes(8, "big"))
        with (repo_root / str(relative)).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    if before != snapshot():
        raise TestedAppArtifactBindingError(
            "Patrol host source changed during digest readback"
        )
    return "sha256:" + digest.hexdigest(), len(before)


def host_source_identity(
    *,
    host_root: Path = PATROL_HOST_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, object]:
    """Hash actual host sources without calling it a production projection."""

    canonical_repo_root = repo_root.resolve()
    canonical_host_root = host_root.resolve()
    if host_root.is_symlink() or not canonical_host_root.is_dir():
        raise TestedAppArtifactBindingError(
            "Patrol host source root is missing or unsafe"
        )
    try:
        relative_root = canonical_host_root.relative_to(canonical_repo_root)
    except ValueError as error:
        raise TestedAppArtifactBindingError(
            "Patrol host source root escaped the repository"
        ) from error
    before_files = _git_host_source_files(canonical_host_root, canonical_repo_root)
    source_digest, file_count = _host_source_digest(
        canonical_repo_root,
        before_files,
    )
    after_files = _git_host_source_files(canonical_host_root, canonical_repo_root)
    if before_files != after_files:
        raise TestedAppArtifactBindingError(
            "Patrol host source inventory changed during digest readback"
        )
    root_material = (str(canonical_repo_root) + "\0" + str(canonical_host_root)).encode(
        "utf-8"
    )
    return {
        "root": relative_root.as_posix(),
        "rootIdentityDigest": _sha256_bytes(root_material),
        "sourceDigest": source_digest,
        "sourceFileCount": file_count,
    }


def _typed_missing(fields: Iterable[str]) -> list[dict[str, str]]:
    return [
        {
            "field": field,
            "errorCode": APP_PAGE_ARTIFACT_BINDING_BLOCKER,
            "reason": (
                f"{TESTED_APP_ARTIFACT_BINDING_PROVENANCE} does not own "
                f"canonical {field}"
            ),
        }
        for field in fields
    ]


def _canonical_comparison(
    application_id: str,
    artifact_digest: str,
) -> dict[str, object]:
    return {
        "applicationId": application_id,
        "artifactDigest": artifact_digest,
        "sourceProjectionDigest": "",
        "runtimeConfigPackageDigest": "",
        "trustDigest": "",
        "launchAttemptId": "",
        "typedMissing": _typed_missing(_TEST_HOST_UNOWNED_COMPARISON_KEYS),
    }


def build_tested_app_artifact_binding(
    *,
    platform: str,
    device_id: str,
    command_application_id: str,
    build_application_id: str,
    build_artifact_path: str,
    build_artifact_digest: str,
    installed_application_id: str,
    installed_artifact_digest: str,
    installed_readback_method: str,
    installed_locator_digest: str,
    host_source: dict[str, object],
) -> dict[str, object]:
    """Build and strictly validate one comparison-ready binding."""

    if platform not in {"android", "ios"}:
        raise TestedAppArtifactBindingError("binding platform is invalid")
    normalized_device_id = str(device_id or "").strip()
    if not normalized_device_id:
        raise TestedAppArtifactBindingError("binding deviceId is missing")
    command_identity = _validate_application_id(
        command_application_id,
        "Patrol command application identity",
    )
    build_identity = _validate_application_id(
        build_application_id,
        "build artifact application identity",
    )
    installed_identity = _validate_application_id(
        installed_application_id,
        "installed artifact application identity",
    )
    if len({command_identity, build_identity, installed_identity}) != 1:
        raise TestedAppArtifactBindingError(
            "Patrol command, build artifact, and installed artifact identity mismatch"
        )
    build_digest = _validate_digest(
        build_artifact_digest,
        "build artifact digest",
    )
    installed_digest = _validate_digest(
        installed_artifact_digest,
        "installed artifact digest",
    )
    if build_digest != installed_digest:
        raise TestedAppArtifactBindingError(
            "installed artifact bytes differ from the final build artifact"
        )
    method = str(installed_readback_method or "").strip()
    if not method:
        raise TestedAppArtifactBindingError(
            "installed artifact readback method is missing"
        )
    locator_digest = _validate_digest(
        installed_locator_digest,
        "installed artifact locator digest",
    )
    host_root = str(host_source.get("root") or "").strip()
    if not host_root:
        raise TestedAppArtifactBindingError("Patrol host source root is missing")
    host_root_identity = _validate_digest(
        str(host_source.get("rootIdentityDigest") or ""),
        "Patrol host root identity digest",
    )
    host_source_digest = _validate_digest(
        str(host_source.get("sourceDigest") or ""),
        "Patrol host source digest",
    )
    file_count = host_source.get("sourceFileCount")
    if (
        not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count <= 0
    ):
        raise TestedAppArtifactBindingError(
            "Patrol host source file count is missing or invalid"
        )
    identity_kind = "applicationId" if platform == "android" else "bundleId"
    binding: dict[str, object] = {
        "schema": TESTED_APP_ARTIFACT_BINDING_SCHEMA,
        "status": "passed",
        "provenance": TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
        "nonPromotable": True,
        "platform": platform,
        "deviceId": normalized_device_id,
        "applicationIdentity": {
            "kind": identity_kind,
            "value": build_identity,
            identity_kind: build_identity,
            "commandReadback": command_identity,
            "buildArtifactReadback": build_identity,
            "installedArtifactReadback": installed_identity,
        },
        "buildArtifact": {
            "path": str(build_artifact_path or "").strip(),
            "format": "apk" if platform == "android" else "app",
            "artifactDigest": build_digest,
        },
        "installedArtifactReadback": {
            "status": "readable",
            "method": method,
            "applicationId": installed_identity,
            "artifactDigest": installed_digest,
            "locatorDigest": locator_digest,
        },
        "hostSource": {
            "root": host_root,
            "rootIdentityDigest": host_root_identity,
            "sourceDigest": host_source_digest,
            "sourceFileCount": file_count,
        },
        "canonicalComparison": _canonical_comparison(
            build_identity,
            build_digest,
        ),
    }
    validate_tested_app_artifact_binding(binding)
    return binding


def tested_app_artifact_comparison(
    binding: dict[str, object],
) -> dict[str, str]:
    """Return the six exact keys consumed by strict page-UAT aggregation."""

    comparison = binding.get("canonicalComparison")
    if not isinstance(comparison, dict):
        raise TestedAppArtifactBindingError(
            "canonical comparison projection is missing"
        )
    return {key: str(comparison.get(key) or "") for key in CANONICAL_COMPARISON_KEYS}


def validate_tested_app_artifact_binding(
    binding: dict[str, object],
) -> dict[str, str]:
    """Reject proxy, copied, incomplete, or cross-artifact binding evidence."""

    if binding.get("schema") != TESTED_APP_ARTIFACT_BINDING_SCHEMA:
        raise TestedAppArtifactBindingError("binding schema is invalid")
    if binding.get("status") != "passed":
        raise TestedAppArtifactBindingError("binding status is not passed")
    if binding.get("provenance") != TESTED_APP_ARTIFACT_BINDING_PROVENANCE:
        raise TestedAppArtifactBindingError("binding provenance is invalid")
    if binding.get("nonPromotable") is not True:
        raise TestedAppArtifactBindingError("test-host binding must be nonPromotable")
    platform = str(binding.get("platform") or "")
    identity = binding.get("applicationIdentity")
    build = binding.get("buildArtifact")
    installed = binding.get("installedArtifactReadback")
    source = binding.get("hostSource")
    if not all(
        isinstance(value, dict) for value in (identity, build, installed, source)
    ):
        raise TestedAppArtifactBindingError("binding evidence sections are incomplete")
    assert isinstance(identity, dict)
    assert isinstance(build, dict)
    assert isinstance(installed, dict)
    assert isinstance(source, dict)
    expected_kind = "applicationId" if platform == "android" else "bundleId"
    if platform not in {"android", "ios"} or identity.get("kind") != expected_kind:
        raise TestedAppArtifactBindingError(
            "binding application identity kind is invalid"
        )
    identities = {
        _validate_application_id(str(identity.get(field) or ""), field)
        for field in (
            "value",
            "commandReadback",
            "buildArtifactReadback",
            "installedArtifactReadback",
        )
    }
    identities.add(
        _validate_application_id(
            str(identity.get(expected_kind) or ""),
            f"applicationIdentity.{expected_kind}",
        )
    )
    identities.add(
        _validate_application_id(
            str(installed.get("applicationId") or ""),
            "installedArtifactReadback.applicationId",
        )
    )
    if len(identities) != 1:
        raise TestedAppArtifactBindingError(
            "binding application identities are not equal"
        )
    if installed.get("status") != "readable":
        raise TestedAppArtifactBindingError(
            "installed artifact readback status is not readable"
        )
    build_digest = _validate_digest(
        str(build.get("artifactDigest") or ""),
        "buildArtifact.artifactDigest",
    )
    installed_digest = _validate_digest(
        str(installed.get("artifactDigest") or ""),
        "installedArtifactReadback.artifactDigest",
    )
    _validate_digest(
        str(installed.get("locatorDigest") or ""),
        "installedArtifactReadback.locatorDigest",
    )
    if build_digest != installed_digest:
        raise TestedAppArtifactBindingError(
            "binding build/install artifact digests are not equal"
        )
    _validate_digest(
        str(source.get("rootIdentityDigest") or ""),
        "hostSource.rootIdentityDigest",
    )
    _validate_digest(
        str(source.get("sourceDigest") or ""),
        "hostSource.sourceDigest",
    )
    if not str(source.get("root") or "").strip():
        raise TestedAppArtifactBindingError("hostSource.root is missing")
    if not str(build.get("path") or "").strip():
        raise TestedAppArtifactBindingError("buildArtifact.path is missing")
    comparison = tested_app_artifact_comparison(binding)
    only_identity = next(iter(identities))
    if comparison["applicationId"] != only_identity:
        raise TestedAppArtifactBindingError(
            "canonical comparison applicationId is not a readback"
        )
    if comparison["artifactDigest"] != build_digest:
        raise TestedAppArtifactBindingError(
            "canonical comparison artifactDigest is not a readback"
        )
    if any(comparison[key] for key in _TEST_HOST_UNOWNED_COMPARISON_KEYS):
        raise TestedAppArtifactBindingError(
            "test-host binding copied a canonical identity it does not own"
        )
    raw_comparison = binding["canonicalComparison"]
    assert isinstance(raw_comparison, dict)
    expected_missing = _typed_missing(_TEST_HOST_UNOWNED_COMPARISON_KEYS)
    if raw_comparison.get("typedMissing") != expected_missing:
        raise TestedAppArtifactBindingError(
            "canonical comparison typed-missing projection is invalid"
        )
    return comparison


def collect_tested_app_artifact_binding(
    *,
    device: dict[str, Any],
    patrol_command: list[str],
    command_env: dict[str, str],
    artifact_path: Path | None = None,
    host_source: dict[str, object] | None = None,
    run: CommandRunner = subprocess.run,
    android_adb: str = "",
    android_aapt: str = "",
) -> dict[str, object]:
    """Collect identity after Patrol and prove build/install payload equality."""

    platform = _platform_for_device(device)
    device_id = str(device.get("id") or "").strip()
    if not device_id:
        raise TestedAppArtifactBindingError("deviceId is missing")
    command_identity = _declared_application_id(patrol_command, platform)
    build_path = (artifact_path or tested_app_build_artifact_path(device)).absolute()
    first_build_digest = artifact_payload_digest(build_path, platform)
    build_identity = _read_artifact_identity(
        build_path,
        platform,
        command_env=command_env,
        run=run,
        android_aapt=android_aapt,
    )
    if first_build_digest != artifact_payload_digest(build_path, platform):
        raise TestedAppArtifactBindingError(
            "build artifact changed during identity readback"
        )
    if platform == "android":
        installed = _android_installed_readback(
            device_id=device_id,
            application_id=build_identity,
            command_env=command_env,
            run=run,
            adb=android_adb,
            aapt=android_aapt,
        )
    else:
        installed = _ios_installed_readback(
            device=device,
            application_id=build_identity,
            command_env=command_env,
            run=run,
        )
    final_build_digest = artifact_payload_digest(build_path, platform)
    if first_build_digest != final_build_digest:
        raise TestedAppArtifactBindingError(
            "build artifact changed across installed-payload readback"
        )
    source = host_source if host_source is not None else host_source_identity()
    try:
        evidence_path = build_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        evidence_path = str(build_path)
    return build_tested_app_artifact_binding(
        platform=platform,
        device_id=device_id,
        command_application_id=command_identity,
        build_application_id=build_identity,
        build_artifact_path=evidence_path,
        build_artifact_digest=final_build_digest,
        installed_application_id=str(installed.get("applicationId") or ""),
        installed_artifact_digest=str(installed.get("artifactDigest") or ""),
        installed_readback_method=str(installed.get("method") or ""),
        installed_locator_digest=str(installed.get("locatorDigest") or ""),
        host_source=source,
    )
