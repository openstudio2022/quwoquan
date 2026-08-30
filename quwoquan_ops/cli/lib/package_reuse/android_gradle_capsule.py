"""Exact, privately-synchronized Android Gradle dependency closure.

Only wrapper distributions and Gradle's immutable Maven/plugin artifact cache
are admitted.  Daemons, journals, build caches and the developer's global
``~/.gradle`` never become package inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ANDROID_GRADLE_DEPENDENCY_SCHEMA = "stackctl-android-gradle-dependency.v1"
ANDROID_GRADLE_LOGICAL_PATH = "dependency:android-gradle-v1"
ANDROID_GRADLE_CAPSULE_MANIFEST = Path(
    "dependencies/android-gradle-manifest.json"
)
ANDROID_GRADLE_CAPSULE_TREE = Path("dependencies/android-gradle")
ANDROID_GRADLE_PROJECTION_RELATIVE = Path(
    "quwoquan_app/.dart_tool/qwq_android_gradle_dependency"
)
ANDROID_GRADLE_CONTROL_SCHEMA = "stackctl-android-gradle-control.v1"

_DIGEST_PREFIX = "sha256:"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GRADLE_SHA1 = re.compile(r"^[0-9a-f]{1,40}$")
_WRAPPER_URL = re.compile(
    r"^https://services\.gradle\.org/distributions/"
    r"gradle-[0-9]+(?:\.[0-9]+){1,2}-(?:bin|all)\.zip$"
)
_TRANSIENT_SUFFIXES = (".lock", ".lck", ".part", ".tmp")
_WRAPPER_FILES = (
    "gradlew",
    "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar",
    "gradle/wrapper/gradle-wrapper.properties",
)


@dataclass(frozen=True, slots=True)
class AndroidGradleFile:
    relative: str
    source: Path
    mode: int
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class AndroidGradleSnapshot:
    manifest: dict[str, Any]
    encoded_manifest: bytes
    files: tuple[AndroidGradleFile, ...]
    tree_root: Path


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _safe_relative(value: str) -> str:
    relative = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("Android Gradle dependency path is unsafe")
    return value


def _read_regular_nofollow(path: Path, *, label: str) -> tuple[bytes, int]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("Android Gradle dependency capsule requires O_NOFOLLOW")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ValueError(f"Android Gradle dependency {label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(
                f"Android Gradle dependency {label} is not an independent regular file"
            )
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
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
            raise ValueError(f"Android Gradle dependency {label} changed during read")
    finally:
        os.close(descriptor)
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    return bytes(content), mode


def _properties(path: Path) -> tuple[dict[str, str], bytes]:
    encoded, _mode = _read_regular_nofollow(path, label="wrapper properties")
    values: dict[str, str] = {}
    for raw_line in encoded.decode("utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip() or key.strip() in values:
            raise ValueError("Android Gradle wrapper properties are invalid")
        values[key.strip()] = value.strip()
    return values, encoded


def _relative_gradle_root(*, project_root: Path, gradle_root: Path) -> str:
    repository = project_root.expanduser().absolute()
    root = gradle_root.expanduser().absolute()
    if not root.is_relative_to(repository):
        raise ValueError("Android Gradle wrapper root escapes the project")
    return _safe_relative(root.relative_to(repository).as_posix())


def _wrapper_identity_at(*, root: Path, relative_root: str) -> dict[str, Any]:
    properties_path = root / "gradle/wrapper/gradle-wrapper.properties"
    jar_path = root / "gradle/wrapper/gradle-wrapper.jar"
    script_path = root / "gradlew"
    bat_path = root / "gradlew.bat"
    properties, properties_bytes = _properties(properties_path)
    distribution_url = properties.get("distributionUrl", "").replace("\\:", ":")
    checksum = properties.get("distributionSha256Sum", "")
    if not _WRAPPER_URL.fullmatch(distribution_url) or not _SHA256.fullmatch(checksum):
        raise ValueError(
            "Android Gradle wrapper requires an HTTPS distribution and sha256 pin"
        )
    jar, _jar_mode = _read_regular_nofollow(jar_path, label="wrapper jar")
    script, script_mode = _read_regular_nofollow(script_path, label="wrapper script")
    bat, _bat_mode = _read_regular_nofollow(bat_path, label="wrapper batch script")
    if not (script_mode & 0o111):
        raise ValueError("Android Gradle wrapper script is not executable")
    return {
        "root": relative_root,
        "distributionUrl": distribution_url,
        "distributionSha256": checksum,
        "propertiesDigest": digest_bytes(properties_bytes),
        "wrapperJarDigest": digest_bytes(jar),
        "wrapperScriptDigest": digest_bytes(script),
        "wrapperBatchScriptDigest": digest_bytes(bat),
    }


def wrapper_identity(*, project_root: Path, gradle_root: Path) -> dict[str, Any]:
    relative_root = _relative_gradle_root(
        project_root=project_root,
        gradle_root=gradle_root,
    )
    return _wrapper_identity_at(root=gradle_root, relative_root=relative_root)


def _embedded_wrapper_identity(
    *,
    project_root: Path,
    gradle_root: Path,
    tree_root: Path,
) -> dict[str, Any]:
    relative_root = _relative_gradle_root(
        project_root=project_root,
        gradle_root=gradle_root,
    )
    return _wrapper_identity_at(
        root=tree_root / "wrappers" / relative_root,
        relative_root=relative_root,
    )


def _admitted(relative: str) -> bool:
    path = PurePosixPath(relative)
    parts = path.parts
    # The allow-list below already excludes Gradle's top-level daemon, worker,
    # notification and build-cache state.  Those words remain valid at deeper
    # levels: for example the official Gradle 9.3.1 ``all`` distribution ships
    # Javadoc below ``org/gradle/workers``.  Reject transient file shapes, not
    # legitimate dependency/distribution coordinates that share a directory
    # name with mutable Gradle state.
    if any(part == ".." or part.endswith(_TRANSIENT_SUFFIXES) for part in parts):
        return False
    if parts and parts[0] == "wrappers":
        wrapper_relative = PurePosixPath(*parts[1:]).as_posix()
        return any(
            wrapper_relative.endswith(f"/{name}")
            for name in _WRAPPER_FILES
        )
    if parts[:2] == ("home", "wrapper"):
        return len(parts) >= 4 and parts[2] == "dists"
    if parts[:3] == ("home", "caches", "modules-2"):
        return True
    if parts == ("home", "gradle.properties"):
        return True
    if parts == ("home", "init.d", "qwq-offline.gradle"):
        return True
    if parts[:2] == ("metadata", "resolution-lock.json"):
        return True
    return parts[:2] == ("metadata", "verification-metadata.json")


def _scan_tree(tree_root: Path) -> tuple[AndroidGradleFile, ...]:
    root = tree_root.expanduser().absolute()
    metadata = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Android Gradle dependency tree root is not a real directory")
    files: list[AndroidGradleFile] = []
    for path in sorted(root.rglob("*")):
        node = path.lstat()
        if stat.S_ISDIR(node.st_mode) and not path.is_symlink():
            continue
        relative = _safe_relative(path.relative_to(root).as_posix())
        if not _admitted(relative):
            raise ValueError(
                f"Android Gradle sealed tree contains unmanifested bytes: {relative}"
            )
        content, mode = _read_regular_nofollow(
            path,
            label=f"sealed file {relative}",
        )
        files.append(
            AndroidGradleFile(
                relative=relative,
                source=path,
                mode=mode,
                size=len(content),
                sha256=digest_bytes(content),
            )
        )
    if not files:
        raise ValueError("Android Gradle dependency tree is empty")
    return tuple(files)


def _artifact_records(files: Sequence[AndroidGradleFile]) -> list[dict[str, Any]]:
    prefix = ("home", "caches", "modules-2", "files-2.1")
    records: list[dict[str, Any]] = []
    for item in files:
        parts = PurePosixPath(item.relative).parts
        if parts[: len(prefix)] != prefix or len(parts) != len(prefix) + 5:
            continue
        group, module, version, gradle_hash, filename = parts[len(prefix) :]
        if not all((group, module, version, filename)) or not _GRADLE_SHA1.fullmatch(
            gradle_hash
        ):
            raise ValueError("Android Gradle Maven artifact cache identity is invalid")
        content, _mode = _read_regular_nofollow(
            item.source,
            label=f"Maven artifact {group}:{module}:{version}/{filename}",
        )
        # Gradle's files-2.1 path representation omits SHA-1 leading zeroes.
        # Restore the fixed width before comparison so the compact path form is
        # accepted without weakening the byte-integrity check.
        if hashlib.sha1(content, usedforsecurity=False).hexdigest() != gradle_hash.rjust(
            40, "0"
        ):
            raise ValueError("Android Gradle Maven artifact sha1 directory drifted")
        records.append(
            {
                "coordinate": f"{group}:{module}:{version}",
                "file": filename,
                "gradleSha1": gradle_hash,
                "sha256": item.sha256,
                "size": item.size,
            }
        )
    records.sort(key=lambda item: (item["coordinate"], item["file"], item["sha256"]))
    if not records:
        raise ValueError("Android Gradle Maven/plugin artifact closure is empty")
    return records


def _metadata(path: Path, *, schema: str) -> dict[str, Any]:
    encoded, _mode = _read_regular_nofollow(path, label=path.name)
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Android Gradle {path.name} is invalid") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValueError(f"Android Gradle {path.name} schema mismatch")
    return value


def build_android_gradle_snapshot(
    *,
    project_root: Path,
    tree_root: Path,
    gradle_roots: Sequence[Path],
) -> AndroidGradleSnapshot:
    """Validate and hash one already-sealed, dependency-only Gradle tree."""

    wrappers = [
        _embedded_wrapper_identity(
            project_root=project_root,
            gradle_root=item,
            tree_root=tree_root,
        )
        for item in gradle_roots
    ]
    wrappers.sort(key=lambda item: item["root"])
    if not wrappers or len({item["root"] for item in wrappers}) != len(wrappers):
        raise ValueError("Android Gradle wrapper roots are empty or duplicated")
    files = _scan_tree(tree_root)
    expected_wrapper_paths = {
        (Path("wrappers") / item["root"] / relative).as_posix()
        for item in wrappers
        for relative in _WRAPPER_FILES
    }
    actual_wrapper_paths = {
        item.relative for item in files if item.relative.startswith("wrappers/")
    }
    if actual_wrapper_paths != expected_wrapper_paths:
        raise ValueError("Android Gradle embedded wrapper byte set drifted")
    resolution = _metadata(
        tree_root / "metadata/resolution-lock.json",
        schema="stackctl-android-gradle-resolution-lock.v1",
    )
    verification = _metadata(
        tree_root / "metadata/verification-metadata.json",
        schema="stackctl-android-gradle-verification-metadata.v1",
    )
    artifacts = _artifact_records(files)
    if resolution.get("components") != sorted(
        {item["coordinate"] for item in artifacts}
    ):
        raise ValueError("Android Gradle resolution lock drifted from artifact closure")
    expected_verification = [
        {
            "coordinate": item["coordinate"],
            "file": item["file"],
            "sha256": item["sha256"],
            "size": item["size"],
        }
        for item in artifacts
    ]
    if verification.get("artifacts") != expected_verification:
        raise ValueError("Android Gradle verification metadata drifted from artifacts")
    entries = [item.as_dict() for item in files]
    tree_digest = digest_bytes(
        canonical_bytes(
            {"schema": ANDROID_GRADLE_DEPENDENCY_SCHEMA, "entries": entries}
        )
    )
    manifest = {
        "schema": ANDROID_GRADLE_DEPENDENCY_SCHEMA,
        "wrappers": wrappers,
        "componentCount": len(resolution["components"]),
        "artifactCount": len(artifacts),
        "entryCount": len(entries),
        "treeDigest": tree_digest,
        "entries": entries,
    }
    encoded = canonical_bytes(manifest)
    return AndroidGradleSnapshot(
        manifest=manifest,
        encoded_manifest=encoded,
        files=files,
        tree_root=tree_root.expanduser().absolute(),
    )


def load_android_gradle_snapshot(
    *,
    project_root: Path,
    tree_root: Path,
    manifest_path: Path,
    gradle_roots: Sequence[Path],
) -> AndroidGradleSnapshot:
    """Load one immutable managed/CAS snapshot and reject any byte drift."""

    encoded, _mode = _read_regular_nofollow(
        manifest_path,
        label="managed snapshot manifest",
    )
    try:
        declared = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Android Gradle managed snapshot manifest is invalid") from exc
    if not isinstance(declared, dict) or canonical_bytes(declared) != encoded:
        raise ValueError("Android Gradle managed snapshot manifest is not canonical")
    snapshot = build_android_gradle_snapshot(
        project_root=project_root,
        tree_root=tree_root,
        gradle_roots=gradle_roots,
    )
    if snapshot.manifest != declared or snapshot.encoded_manifest != encoded:
        raise ValueError("Android Gradle managed snapshot CAS drifted")
    return snapshot
