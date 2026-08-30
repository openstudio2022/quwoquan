"""New-process readback of projected dependency-domain CAS identities."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .android_gradle_capsule import (
    ANDROID_GRADLE_DEPENDENCY_SCHEMA,
    canonical_bytes,
    digest_bytes,
)
from .dependency_fs import assert_real_directory, read_regular_nofollow
from .dependency_projection_contract import (
    CAS_BLOCKER,
    EVIDENCE_BLOCKER,
    READBACK_SCHEMA,
    DependencyProjectionReadback,
    component_path,
    environment_identity,
    load_expectation,
    read_lock,
    typed,
)
from .dependency_projection_prepare import _pub_transient, pub_identity, scan_pods
from .ios_pod_capsule import _canonical_bytes, _digest_bytes
from .patrol_command_envelope import (
    PATROL_COMMAND_ENVELOPE_DIGEST_ENV,
    patrol_command_envelope_digest,
    validate_patrol_command_environment,
)
from .pub_cache_capsule import build_pub_cache_snapshot

_GRADLE_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}$")
_TRANSIENT_SUFFIXES = (".lock", ".lck", ".part", ".tmp")


def _audit_extra_nodes(
    *,
    root: Path,
    expected_files: set[str],
    expected_directories: set[str],
    admitted_extra: Callable[[str, bool], bool],
    component: str,
) -> None:
    try:
        assert_real_directory(root, label=f"{component} domain root")
        for current, directories, files in os.walk(root, followlinks=False):
            base = Path(current)
            for name in sorted(directories):
                path = base / name
                metadata = path.lstat()
                relative = path.relative_to(root).as_posix()
                if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                    raise ValueError(f"unsafe directory node {relative}")
                if relative not in expected_directories and not admitted_extra(
                    relative, True
                ):
                    raise ValueError(f"undeclared dependency directory {relative}")
            for name in sorted(files):
                path = base / name
                relative = path.relative_to(root).as_posix()
                if relative in expected_files:
                    continue
                read_regular_nofollow(path, label=f"{component} transient {relative}")
                if not admitted_extra(relative, False):
                    raise ValueError(f"undeclared dependency file {relative}")
    except (OSError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"{component} contains unsafe or unclassified bytes: {error}",
        ) from error


def _revalidate_pub(
    *, root: Path, component: str, expected: Mapping[str, Any]
) -> dict[str, Any]:
    cache = component_path(root, expected.get("treePath"), label=component)
    lock = component_path(root, expected.get("lockPath"), label=component)
    _lock, lock_digest = read_lock(lock, component=component)
    if lock_digest != expected.get("lockDigest"):
        raise typed(CAS_BLOCKER, f"{component} lock bytes drifted")
    try:
        snapshot = build_pub_cache_snapshot(
            lock_path=lock,
            cache_root=cache,
            admitted_extra=_pub_transient,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"{component} dependency-domain scan failed: {error}",
        ) from error
    identity = pub_identity(snapshot)
    declared = {
        key: expected.get(key)
        for key in (
            "manifestDigest",
            "treeDigest",
            "entryCount",
            "directoryCount",
            "lockDigest",
        )
    }
    if identity != declared:
        raise typed(CAS_BLOCKER, f"{component} locked package bytes drifted")
    return identity


def _revalidate_ios(
    *, root: Path, component: str, expected: Mapping[str, Any]
) -> dict[str, Any]:
    pods = component_path(root, expected.get("treePath"), label=component)
    lock = component_path(root, expected.get("lockPath"), label=component)
    identity = scan_pods(pods, lock, component=component)
    declared = {
        key: expected.get(key) for key in ("treeDigest", "entryCount", "lockDigest")
    }
    if identity != declared:
        raise typed(
            CAS_BLOCKER,
            f"{component} converged Pods or lock bytes drifted",
        )
    return identity


def _android_transient(relative: str, is_directory: bool) -> bool:
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] != "home":
        return False
    if len(parts) >= 3 and parts[1:3] == ("caches", "modules-2"):
        return not is_directory and relative == "home/caches/modules-2/modules-2.lock"
    if len(parts) >= 2 and parts[1] == "wrapper":
        return not is_directory and parts[-1].endswith(_TRANSIENT_SUFFIXES)
    if not is_directory and parts[-1] in {"CACHEDIR.TAG", "gc.properties"}:
        return True
    if len(parts) >= 2 and parts[1] in {
        ".tmp",
        "android",
        "daemon",
        "native",
        "notifications",
        "workers",
        "kotlin-profile",
    }:
        return True
    if len(parts) < 3 or parts[1] != "caches":
        return False
    cache = parts[2]
    return bool(
        cache == "journal-1"
        or _GRADLE_VERSION.fullmatch(cache)
        or cache.startswith(("transforms-", "build-cache-", "jars-"))
        or cache in {"generated-gradle-jars", "kotlin-dsl"}
    )


def _android_entries(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if (
        manifest.get("schema") != ANDROID_GRADLE_DEPENDENCY_SCHEMA
        or not isinstance(manifest.get("entries"), list)
        or manifest.get("entryCount") != len(manifest["entries"])
    ):
        raise typed(EVIDENCE_BLOCKER, "androidGradle expected manifest is invalid")
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in manifest["entries"]:
        if not isinstance(item, Mapping):
            raise typed(EVIDENCE_BLOCKER, "androidGradle expected entry is invalid")
        relative = str(item.get("path") or "")
        pure = PurePosixPath(relative)
        if (
            not relative
            or pure.as_posix() != relative
            or any(part in {"", ".", ".."} for part in pure.parts)
            or relative in seen
        ):
            raise typed(
                EVIDENCE_BLOCKER,
                "androidGradle expected entry path is unsafe or duplicated",
            )
        seen.add(relative)
        result.append(item)
    return result


def _revalidate_android(
    *, root: Path, component: str, expected: Mapping[str, Any]
) -> dict[str, Any]:
    tree = component_path(root, expected.get("treePath"), label=component)
    manifest = expected.get("manifest")
    if not isinstance(manifest, Mapping):
        raise typed(EVIDENCE_BLOCKER, "androidGradle expected manifest is missing")
    entries = _android_entries(manifest)
    expected_files: set[str] = set()
    expected_directories: set[str] = set()
    try:
        for item in entries:
            relative = str(item["path"])
            expected_files.add(relative)
            pure = PurePosixPath(relative)
            for size in range(1, len(pure.parts)):
                expected_directories.add(PurePosixPath(*pure.parts[:size]).as_posix())
            content, mode = read_regular_nofollow(
                tree / Path(*pure.parts),
                label=f"androidGradle dependency {relative}",
            )
            if (
                item.get("mode") != mode
                or item.get("size") != len(content)
                or item.get("sha256") != digest_bytes(content)
            ):
                raise ValueError(f"declared dependency node drifted: {relative}")
    except (OSError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"androidGradle declared bytes drifted: {error}",
        ) from error
    _audit_extra_nodes(
        root=tree,
        expected_files=expected_files,
        expected_directories=expected_directories,
        admitted_extra=_android_transient,
        component=component,
    )
    encoded = canonical_bytes(manifest)
    identity = {
        "manifestDigest": digest_bytes(encoded),
        "treeDigest": manifest.get("treeDigest"),
        "entryCount": manifest.get("entryCount"),
    }
    declared = {
        key: expected.get(key) for key in ("manifestDigest", "treeDigest", "entryCount")
    }
    if identity != declared:
        raise typed(
            EVIDENCE_BLOCKER,
            "androidGradle expected identity is internally inconsistent",
        )
    return identity


def _revalidate_source(source: Mapping[str, Any]) -> None:
    path = Path(str(source.get("manifestPath") or ""))
    try:
        encoded, _mode = read_regular_nofollow(
            path,
            label="package source capsule manifest",
        )
    except ValueError as error:
        raise typed(
            EVIDENCE_BLOCKER,
            "source capsule manifest is unavailable after command",
        ) from error
    if _digest_bytes(encoded) != source.get("manifestDigest"):
        raise typed(
            EVIDENCE_BLOCKER,
            "source capsule manifest bytes drifted after command",
        )


def _revalidate_environment(
    *,
    manifest: Mapping[str, Any],
    owner: str | None,
    environment: Mapping[str, str] | None,
) -> None:
    if (owner is None) != (environment is None):
        raise typed(
            EVIDENCE_BLOCKER,
            "command environment owner and values must be supplied together",
        )
    if owner is None or environment is None:
        return
    environments = manifest.get("environments")
    expected = environments.get(owner) if isinstance(environments, Mapping) else None
    if (
        not isinstance(expected, Mapping)
        or environment_identity(environment) != expected
    ):
        raise typed(CAS_BLOCKER, f"{owner} command dependency environment drifted")


def _revalidate_patrol_command_envelope(
    *,
    manifest: Mapping[str, Any],
    owner: str | None,
    environment: Mapping[str, str] | None,
) -> str | None:
    envelope = manifest.get("patrolCommandEnvelope")
    if envelope is None:
        return None
    try:
        expected_digest = patrol_command_envelope_digest(envelope)
    except (TypeError, ValueError) as error:
        raise typed(EVIDENCE_BLOCKER, "Patrol command envelope is invalid") from error
    if owner != "patrol":
        return expected_digest
    if environment is None:
        raise typed(EVIDENCE_BLOCKER, "Patrol command environment is missing")
    try:
        validate_patrol_command_environment(environment)
    except (OSError, TypeError, ValueError) as error:
        raise typed(CAS_BLOCKER, "Patrol command toolchain identity drifted") from error
    if environment.get(PATROL_COMMAND_ENVELOPE_DIGEST_ENV) != expected_digest:
        raise typed(CAS_BLOCKER, "Patrol command envelope selection drifted")
    return expected_digest


def readback_from_expectation(
    *,
    expectation: object,
    observed_components: Mapping[str, Mapping[str, Any]],
    command_environment_owner: str | None = None,
    command_environment: Mapping[str, str] | None = None,
) -> DependencyProjectionReadback:
    """Build a readback from identities captured by the same safe tree scan."""

    manifest = getattr(expectation, "manifest", None)
    projection = getattr(expectation, "projection_root", None)
    evidence_digest = getattr(expectation, "evidence_digest", None)
    if (
        not isinstance(manifest, Mapping)
        or not isinstance(projection, Path)
        or not isinstance(evidence_digest, str)
    ):
        raise typed(EVIDENCE_BLOCKER, "dependency expectation object is invalid")
    source = manifest["source"]
    components = manifest["components"]
    if not isinstance(source, Mapping) or not isinstance(components, Mapping):
        raise typed(EVIDENCE_BLOCKER, "dependency expectation fields are invalid")
    _revalidate_source(source)
    _revalidate_environment(
        manifest=manifest,
        owner=command_environment_owner,
        environment=command_environment,
    )
    patrol_digest = _revalidate_patrol_command_envelope(
        manifest=manifest,
        owner=command_environment_owner,
        environment=command_environment,
    )
    observed = {key: dict(value) for key, value in sorted(observed_components.items())}
    if set(observed) != set(components):
        raise typed(EVIDENCE_BLOCKER, "captured dependency component set drifted")
    for component, raw in sorted(components.items()):
        if not isinstance(raw, Mapping):
            raise typed(EVIDENCE_BLOCKER, f"{component} expectation is invalid")
        identity_fields = {
            "pub": (
                "manifestDigest",
                "treeDigest",
                "entryCount",
                "directoryCount",
                "lockDigest",
            ),
            "iosPods": ("treeDigest", "entryCount", "lockDigest"),
            "androidGradle": ("manifestDigest", "treeDigest", "entryCount"),
        }.get(str(raw.get("kind") or ""))
        if identity_fields is None:
            raise typed(EVIDENCE_BLOCKER, f"{component} expectation kind is unsupported")
        declared = {key: raw.get(key) for key in identity_fields}
        if observed[component] != declared:
            raise typed(CAS_BLOCKER, f"{component} captured identity drifted")
    result = {
        "schema": READBACK_SCHEMA,
        "expectationDigest": evidence_digest,
        "projectionRoot": str(projection),
        "sourceManifestDigest": source.get("manifestDigest"),
        "components": observed,
        "patrolCommandEnvelopeDigest": patrol_digest,
    }
    encoded = _canonical_bytes(result)
    return DependencyProjectionReadback(
        expectation_digest=evidence_digest,
        manifest=result,
        encoded_manifest=encoded,
    )


def revalidate_dependency_projection_cas(
    *,
    projection_root: Path,
    evidence_path: Path,
    expected_digest: str,
    command_environment_owner: str | None = None,
    command_environment: Mapping[str, str] | None = None,
) -> DependencyProjectionReadback:
    """Re-open every selected dependency domain after one external command."""

    expectation = load_expectation(
        projection_root_path=projection_root,
        evidence_path=evidence_path,
        expected_digest=expected_digest,
    )
    manifest = expectation.manifest
    source = manifest["source"]
    components = manifest["components"]
    _revalidate_source(source)
    _revalidate_environment(
        manifest=manifest,
        owner=command_environment_owner,
        environment=command_environment,
    )
    patrol_command_envelope_digest_value = _revalidate_patrol_command_envelope(
        manifest=manifest,
        owner=command_environment_owner,
        environment=command_environment,
    )
    observed: dict[str, dict[str, Any]] = {}
    for component, raw in sorted(components.items()):
        if not isinstance(raw, Mapping):
            raise typed(EVIDENCE_BLOCKER, f"{component} expectation is invalid")
        if raw.get("kind") == "pub":
            observed[component] = _revalidate_pub(
                root=expectation.projection_root,
                component=component,
                expected=raw,
            )
        elif raw.get("kind") == "iosPods":
            observed[component] = _revalidate_ios(
                root=expectation.projection_root,
                component=component,
                expected=raw,
            )
        elif raw.get("kind") == "androidGradle":
            observed[component] = _revalidate_android(
                root=expectation.projection_root,
                component=component,
                expected=raw,
            )
        else:
            raise typed(
                EVIDENCE_BLOCKER,
                f"{component} expectation kind is unsupported",
            )
    result = {
        "schema": READBACK_SCHEMA,
        "expectationDigest": expectation.evidence_digest,
        "projectionRoot": str(expectation.projection_root),
        "sourceManifestDigest": source.get("manifestDigest"),
        "components": observed,
        "patrolCommandEnvelopeDigest": patrol_command_envelope_digest_value,
    }
    encoded = _canonical_bytes(result)
    return DependencyProjectionReadback(
        expectation_digest=expectation.evidence_digest,
        manifest=result,
        encoded_manifest=encoded,
    )
