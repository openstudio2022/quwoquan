"""Readback of built App artifact identity and signing material.

``stackctl package --kind app-artifact`` must not trust the identity it asked
the toolchain to build; it reads application/bundle id and signature back out of
the produced artifact. That readback owns its own toolchain discovery and typed
failures, so it lives beside the writer instead of inside it.

角色：lib。owner 为 quwoquan_ops/cli/commands/package_app_artifact.py。
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    runtime_config_trust_envelope_digest,
    validate_runtime_config_trust_envelope,
)

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUNTIME_CONFIG_TRUST_RESOURCE = "qwq_runtime/runtime-config-trust.json"
_MAX_RUNTIME_CONFIG_TRUST_BYTES = 1024 * 1024
_MAX_ARTIFACT_ARCHIVE_ENTRY_BYTES = 128 * 1024 * 1024
_MAX_ARTIFACT_ARCHIVE_ENTRIES = 100_000
_MAX_ARTIFACT_ARCHIVE_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


class AppArtifactBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppArtifactTrustReadback:
    artifact_digest: str
    signing_identity_digest: str
    runtime_config_trust_envelope_digest: str


def _safe_zip_entry(info: zipfile.ZipInfo) -> str:
    raw = info.orig_filename
    if raw != info.filename or "\x00" in raw:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
            "archive entry contains a truncated NUL name"
        )
    normalized_input = raw[:-1] if info.is_dir() and raw.endswith("/") else raw
    pure = PurePosixPath(normalized_input)
    if (
        not normalized_input
        or raw.startswith("/")
        or "\\" in raw
        or "\x00" in raw
        or re.match(r"^[A-Za-z]:", raw)
        or pure.as_posix() != normalized_input
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise AppArtifactBuildError(
            f"APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: {raw!r}"
        )
    file_type = stat.S_IFMT(info.external_attr >> 16)
    expected_type = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
    if file_type not in {0, expected_type}:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
            f"non-regular archive entry {raw!r}"
        )
    return pure.as_posix()


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def artifact_filesystem_identity(artifact: Path) -> tuple[int, ...]:
    try:
        metadata = os.stat(artifact, follow_symlinks=False)
    except OSError as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_snapshot_drift: artifact cannot be inspected"
        ) from error
    return _file_identity(metadata)


def _update_digest_from_stable_regular_file(
    path: Path,
    digest: Any,
) -> tuple[int, ...]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_snapshot_drift: file cannot be opened no-follow"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact member is not a single-link regular file"
            )
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        try:
            path_after = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact member disappeared during digest"
            ) from error
        if _file_identity(before) != _file_identity(after) or _file_identity(
            after
        ) != _file_identity(path_after):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact member changed during digest"
            )
        return _file_identity(after)
    finally:
        os.close(descriptor)


def _stable_regular_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    _update_digest_from_stable_regular_file(path, digest)
    return "sha256:" + digest.hexdigest()


def _stable_artifact_digest(path: Path) -> str:
    metadata = os.stat(path, follow_symlinks=False)
    if stat.S_ISREG(metadata.st_mode):
        return _stable_regular_file_digest(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_snapshot_drift: artifact is not regular"
        )
    root_before = _file_identity(metadata)
    directories: dict[Path, tuple[int, ...]] = {}
    files: list[tuple[str, Path, tuple[int, ...]]] = []
    for current, directory_names, file_names in os.walk(path, followlinks=False):
        current_path = Path(current)
        current_metadata = os.stat(current_path, follow_symlinks=False)
        if not stat.S_ISDIR(current_metadata.st_mode):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: artifact directory changed"
            )
        directories[current_path] = _file_identity(current_metadata)
        for name in directory_names:
            child = current_path / name
            child_metadata = os.stat(child, follow_symlinks=False)
            if not stat.S_ISDIR(child_metadata.st_mode):
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_snapshot_drift: "
                    "artifact contains a directory symlink or special entry"
                )
        for name in file_names:
            child = current_path / name
            child_metadata = os.stat(child, follow_symlinks=False)
            if not stat.S_ISREG(child_metadata.st_mode) or child_metadata.st_nlink != 1:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_snapshot_drift: "
                    "artifact contains a linked or special file"
                )
            relative = child.relative_to(path).as_posix()
            files.append((relative, child, _file_identity(child_metadata)))
    digest = hashlib.sha256()
    observed_files: dict[Path, tuple[int, ...]] = {}
    for relative, child, expected_identity in sorted(files):
        relative_bytes = relative.encode("utf-8")
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(expected_identity[4].to_bytes(8, "big"))
        observed_identity = _update_digest_from_stable_regular_file(child, digest)
        if observed_identity != expected_identity:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: artifact member changed"
            )
        observed_files[child] = observed_identity
    for directory, expected_identity in directories.items():
        if artifact_filesystem_identity(directory) != expected_identity:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: artifact directory changed"
            )
    for child, expected_identity in observed_files.items():
        if artifact_filesystem_identity(child) != expected_identity:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: artifact member changed"
            )
    if artifact_filesystem_identity(path) != root_before:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_snapshot_drift: artifact root changed"
        )
    return "sha256:" + digest.hexdigest()


def _read_zipped_runtime_config_trust(
    *,
    artifact_root_descriptor: int,
    artifact_name: str,
    platform: str,
    artifact_format: str,
) -> bytes:
    try:
        descriptor = os.open(
            artifact_name,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=artifact_root_descriptor,
        )
    except OSError as error:
        code = "unsafe_entry" if error.errno == errno.ELOOP else "malformed"
        raise AppArtifactBuildError(
            f"APP.PACKAGE.artifact_runtime_config_trust_{code}: "
            "archive cannot be opened no-follow"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                "archive is not a single-link regular file"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            try:
                with zipfile.ZipFile(handle) as archive:
                    infos = archive.infolist()
                    if len(infos) > _MAX_ARTIFACT_ARCHIVE_ENTRIES:
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                            "archive entry count exceeds the safety bound"
                        )
                    entries: dict[str, list[zipfile.ZipInfo]] = {}
                    immediate_ipa_apps: set[str] = set()
                    total_compressed = 0
                    total_uncompressed = 0
                    for info in infos:
                        normalized = _safe_zip_entry(info)
                        entries.setdefault(normalized, []).append(info)
                        if info.file_size < 0 or info.compress_size < 0:
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                                f"negative archive entry size {normalized}"
                            )
                        total_compressed += info.compress_size
                        total_uncompressed += info.file_size
                        if (
                            total_compressed > _MAX_ARTIFACT_ARCHIVE_TOTAL_BYTES
                            or total_uncompressed > _MAX_ARTIFACT_ARCHIVE_TOTAL_BYTES
                        ):
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                                "archive total size exceeds the safety bound"
                            )
                        if info.flag_bits & 0x1:
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                                f"encrypted archive entry {normalized}"
                            )
                        if (
                            info.file_size > _MAX_ARTIFACT_ARCHIVE_ENTRY_BYTES
                            or info.compress_size > _MAX_ARTIFACT_ARCHIVE_ENTRY_BYTES
                        ):
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                                f"oversized archive entry {normalized}"
                            )
                        current_position = handle.tell()
                        handle.seek(info.header_offset)
                        local_header = handle.read(8)
                        handle.seek(current_position)
                        if len(local_header) != 8 or local_header[:4] != b"PK\x03\x04":
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                                f"invalid local header for {normalized}"
                            )
                        if struct.unpack_from("<H", local_header, 6)[0] & 0x1:
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                                f"encrypted local archive entry {normalized}"
                            )
                        match = re.match(r"^Payload/([^/]+\.app)(?:/|$)", normalized)
                        if match:
                            immediate_ipa_apps.add(match.group(1))
                    if platform == "ios" and artifact_format == "ipa":
                        if len(immediate_ipa_apps) != 1:
                            raise AppArtifactBuildError(
                                "APP.PACKAGE.artifact_runtime_config_trust_ambiguous: "
                                "IPA must contain one immediate Payload app"
                            )
                        app_name = next(iter(immediate_ipa_apps))
                        trust_entry = (
                            f"Payload/{app_name}/{_RUNTIME_CONFIG_TRUST_RESOURCE}"
                        )
                        package_entry = (
                            f"Payload/{app_name}/qwq_runtime/"
                            "runtime-config-package.json"
                        )
                    elif platform == "android" and artifact_format in {"apk", "aab"}:
                        prefix = (
                            "base/assets/" if artifact_format == "aab" else "assets/"
                        )
                        trust_entry = f"{prefix}{_RUNTIME_CONFIG_TRUST_RESOURCE}"
                        package_entry = (
                            f"{prefix}qwq_runtime/runtime-config-package.json"
                        )
                    else:
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                            f"unsupported {platform}/{artifact_format} archive"
                        )
                    if entries.get(package_entry):
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_package_forbidden"
                        )
                    trust_candidates = entries.get(trust_entry, [])
                    if len(trust_candidates) > 1:
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_trust_ambiguous: "
                            f"duplicate canonical trust entry {trust_entry}"
                        )
                    if not trust_candidates or trust_candidates[0].is_dir():
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_trust_missing"
                        )
                    info = trust_candidates[0]
                    if not 0 < info.file_size <= _MAX_RUNTIME_CONFIG_TRUST_BYTES:
                        raise AppArtifactBuildError(
                            "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                            "trust resource size is invalid"
                        )
                    payload = archive.read(info)
            except AppArtifactBuildError:
                raise
            except (
                EOFError,
                KeyError,
                OSError,
                RuntimeError,
                zlib.error,
                zipfile.BadZipFile,
            ) as error:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                    "artifact archive cannot be read"
                ) from error
            after = os.fstat(handle.fileno())
        try:
            path_after = os.stat(
                artifact_name,
                dir_fd=artifact_root_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_readback_drift: "
                "archive path disappeared after readback"
            ) from error
        if _file_identity(before) != _file_identity(after) or _file_identity(
            after
        ) != _file_identity(path_after):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_readback_drift"
            )
        return payload
    finally:
        os.close(descriptor)


def _read_app_runtime_config_trust(
    *, artifact_root_descriptor: int, artifact_name: str
) -> bytes:
    descriptors: list[int] = []
    try:
        try:
            app_descriptor = os.open(
                artifact_name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=artifact_root_descriptor,
            )
            descriptors.append(app_descriptor)
            app_before = os.fstat(app_descriptor)
            runtime_descriptor = os.open(
                "qwq_runtime",
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=app_descriptor,
            )
            descriptors.append(runtime_descriptor)
            runtime_before = os.fstat(runtime_descriptor)
        except OSError as error:
            code = (
                "unsafe_entry"
                if error.errno in {errno.ELOOP, errno.ENOTDIR}
                else "missing"
            )
            raise AppArtifactBuildError(
                f"APP.PACKAGE.artifact_runtime_config_trust_{code}: "
                ".app trust directory cannot be opened no-follow"
            ) from error
        if not stat.S_ISDIR(app_before.st_mode) or not stat.S_ISDIR(
            runtime_before.st_mode
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                ".app trust path contains a non-directory"
            )
        try:
            os.stat(
                "runtime-config-package.json",
                dir_fd=runtime_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                ".app runtime package sibling cannot be inspected"
            ) from error
        else:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_package_forbidden"
            )
        try:
            trust_descriptor = os.open(
                "runtime-config-trust.json",
                os.O_RDONLY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=runtime_descriptor,
            )
            descriptors.append(trust_descriptor)
        except OSError as error:
            code = "unsafe_entry" if error.errno == errno.ELOOP else "missing"
            raise AppArtifactBuildError(
                f"APP.PACKAGE.artifact_runtime_config_trust_{code}: "
                ".app trust file cannot be opened no-follow"
            ) from error
        trust_before = os.fstat(trust_descriptor)
        if (
            not stat.S_ISREG(trust_before.st_mode)
            or trust_before.st_nlink != 1
            or not 0 < trust_before.st_size <= _MAX_RUNTIME_CONFIG_TRUST_BYTES
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                ".app trust file is not a bounded single-link regular file"
            )
        chunks: list[bytes] = []
        remaining = _MAX_RUNTIME_CONFIG_TRUST_BYTES + 1
        while remaining > 0:
            chunk = os.read(trust_descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        try:
            os.stat(
                "runtime-config-package.json",
                dir_fd=runtime_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
                ".app runtime package sibling cannot be inspected"
            ) from error
        else:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_package_forbidden"
            )
        trust_after = os.fstat(trust_descriptor)
        runtime_after = os.fstat(runtime_descriptor)
        app_after = os.fstat(app_descriptor)
        try:
            trust_path_after = os.stat(
                "runtime-config-trust.json",
                dir_fd=runtime_descriptor,
                follow_symlinks=False,
            )
            runtime_path_after = os.stat(
                "qwq_runtime",
                dir_fd=app_descriptor,
                follow_symlinks=False,
            )
            app_path_after = os.stat(
                artifact_name,
                dir_fd=artifact_root_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_readback_drift: "
                ".app trust path disappeared after readback"
            ) from error
        if (
            _file_identity(trust_before) != _file_identity(trust_after)
            or _file_identity(runtime_before) != _file_identity(runtime_after)
            or _file_identity(app_before) != _file_identity(app_after)
            or _file_identity(trust_after) != _file_identity(trust_path_after)
            or _file_identity(runtime_after) != _file_identity(runtime_path_after)
            or _file_identity(app_after) != _file_identity(app_path_after)
            or len(payload) != trust_before.st_size
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_readback_drift"
            )
        return payload
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _decode_runtime_config_trust(payload: bytes) -> dict[str, Any]:
    if not payload or len(payload) > _MAX_RUNTIME_CONFIG_TRUST_BYTES:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
            "trust resource size is invalid"
        )

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key}")
            result[key] = value
        return result

    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (TypeError, UnicodeDecodeError, ValueError) as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_malformed"
        ) from error
    if not isinstance(decoded, dict):
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
            "trust resource must be an object"
        )
    return decoded


def read_runtime_config_trust_envelope(
    *,
    artifact_root: Path,
    artifact: Path,
    platform: str,
    artifact_format: str,
    build_profile: str,
    expected_build_input_digest: str,
    expected_artifact_digest: str,
    expected_artifact_filesystem_identity: tuple[int, ...],
    expected_signing_identity_digest: str,
) -> AppArtifactTrustReadback:
    """Bind the manifest to the trust envelope read from the final artifact."""

    if any(
        _SHA256_DIGEST.fullmatch(value) is None
        for value in (
            expected_build_input_digest,
            expected_artifact_digest,
            expected_signing_identity_digest,
        )
    ):
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_digest_invalid"
        )
    if (
        not isinstance(expected_artifact_filesystem_identity, tuple)
        or len(expected_artifact_filesystem_identity) != 7
        or any(
            not isinstance(value, int)
            for value in expected_artifact_filesystem_identity
        )
    ):
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_snapshot_drift: expected identity is invalid"
        )
    root = artifact_root.expanduser().absolute()
    target = artifact.expanduser().absolute()
    if target.parent != root or target.name in {"", ".", ".."}:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
            "artifact must be an immediate attempt-root child"
        )
    try:
        root_descriptor = os.open(
            root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_unsafe_entry: "
            "attempt root cannot be opened no-follow"
        ) from error
    try:
        try:
            root_before = os.fstat(root_descriptor)
            root_path_before = os.stat(root, follow_symlinks=False)
            artifact_before = os.stat(
                target.name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "attempt root or artifact cannot be inspected"
            ) from error
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or _file_identity(root_before) != _file_identity(root_path_before)
            or _file_identity(artifact_before) != expected_artifact_filesystem_identity
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "attempt root or artifact identity changed"
            )
        if platform == "ios" and artifact_format == "app":
            if target.suffix != ".app":
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                    "iOS .app artifact extension is invalid"
                )
            payload = _read_app_runtime_config_trust(
                artifact_root_descriptor=root_descriptor,
                artifact_name=target.name,
            )
        elif (platform, artifact_format) in {
            ("android", "apk"),
            ("android", "aab"),
            ("ios", "ipa"),
        }:
            if target.suffix.lower() != f".{artifact_format}":
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                    "mobile archive extension is invalid"
                )
            payload = _read_zipped_runtime_config_trust(
                artifact_root_descriptor=root_descriptor,
                artifact_name=target.name,
                platform=platform,
                artifact_format=artifact_format,
            )
        else:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_runtime_config_trust_malformed: "
                f"unsupported {platform}/{artifact_format} artifact"
            )
        try:
            observed_artifact_digest_before = _stable_artifact_digest(target)
            observed_signing_identity_digest = signing_digest(platform, target)
            observed_artifact_digest = _stable_artifact_digest(target)
            artifact_after = os.stat(
                target.name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            root_after = os.fstat(root_descriptor)
            root_path_after = os.stat(root, follow_symlinks=False)
        except AppArtifactBuildError:
            raise
        except OSError as error:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact observation could not complete"
            ) from error
        if (
            observed_artifact_digest_before != observed_artifact_digest
            or _file_identity(artifact_before) != _file_identity(artifact_after)
            or _file_identity(root_before) != _file_identity(root_after)
            or _file_identity(root_after) != _file_identity(root_path_after)
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact changed during final observation"
            )
        if observed_artifact_digest != expected_artifact_digest:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: artifact digest changed"
            )
        if observed_signing_identity_digest != expected_signing_identity_digest:
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: signing identity changed"
            )
    finally:
        os.close(root_descriptor)
    envelope = _decode_runtime_config_trust(payload)
    issues = validate_runtime_config_trust_envelope(envelope)
    if issues:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_invalid: " + "; ".join(issues)
        )
    if envelope.get("buildProfile") != build_profile:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_profile_mismatch"
        )
    try:
        observed_digest = runtime_config_trust_envelope_digest(envelope)
    except ValueError as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_invalid"
        ) from error
    if observed_digest != expected_build_input_digest:
        raise AppArtifactBuildError(
            "APP.PACKAGE.artifact_runtime_config_trust_digest_mismatch"
        )
    return AppArtifactTrustReadback(
        artifact_digest=observed_artifact_digest,
        signing_identity_digest=observed_signing_identity_digest,
        runtime_config_trust_envelope_digest=observed_digest,
    )


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
                raise AppArtifactBuildError("APP.PACKAGE.signature_readback_failed")
            return "sha256:" + match.group(1).replace(":", "").lower()
        apksigner = locate_android_tool("apksigner")
        if not apksigner:
            raise AppArtifactBuildError("APP.PACKAGE.signature_tool_missing: apksigner")
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
