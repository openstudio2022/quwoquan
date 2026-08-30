"""Shared contract primitives for dependency projection CAS evidence."""

from __future__ import annotations

import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .android_gradle_capsule import ANDROID_GRADLE_LOGICAL_PATH
from .dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    write_fresh_relative_file,
)
from .ios_pod_capsule import _canonical_bytes, _digest_bytes
from .ios_pod_inputs import (
    IOS_POD_DEPENDENCY_LOGICAL_PATHS,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from .patrol_command_envelope import (
    DEPENDENCY_ENVIRONMENT_KEYS,
    patrol_command_envelope_digest,
    validate_patrol_command_envelope,
)
from .patrol_pub_cache import PATROL_PUB_DEPENDENCY_LOGICAL_PATH
from .pub_cache_capsule import PUB_CACHE_DEPENDENCY_LOGICAL_PATH

EXPECTATION_SCHEMA = "stackctl-app-dependency-projection-expectation.v2"
READBACK_SCHEMA = "stackctl-app-dependency-projection-readback.v2"
CAS_BLOCKER = "APP.DEPENDENCY.projection_cas_drift"
EVIDENCE_BLOCKER = "APP.DEPENDENCY.projection_expectation_invalid"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

ENVIRONMENT_KEYS = DEPENDENCY_ENVIRONMENT_KEYS
COMPONENT_LOGICAL_PATHS = {
    "productionPub": PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
    "patrolPub": PATROL_PUB_DEPENDENCY_LOGICAL_PATH,
    "productionIosPods": IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PRODUCTION_HOST],
    "patrolIosPods": IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PATROL_HOST],
    "androidGradle": ANDROID_GRADLE_LOGICAL_PATH,
}


@dataclass(frozen=True, slots=True)
class DependencyProjectionExpectation:
    evidence_path: Path
    evidence_digest: str
    projection_root: Path
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DependencyProjectionReadback:
    expectation_digest: str
    manifest: dict[str, Any]
    encoded_manifest: bytes


@dataclass(frozen=True, slots=True)
class DependencyProjectionReadbackEvidence:
    evidence_path: Path
    evidence_digest: str
    expectation_digest: str
    manifest: dict[str, Any]


def typed(blocker: str, detail: str) -> ValueError:
    return ValueError(f"{blocker}: {detail}")


def projection_root(path: Path) -> Path:
    try:
        requested = path.expanduser().absolute()
        if requested.is_symlink():
            raise ValueError("projection root is linked")
        root = requested.resolve(strict=True)
        assert_real_directory(root, label="dependency projection root")
    except (OSError, ValueError) as error:
        raise typed(
            EVIDENCE_BLOCKER,
            "projection root is unavailable or linked",
        ) from error
    return root


def relative_path(root: Path, path: Path, *, label: str) -> str:
    absolute = path.expanduser().absolute()
    try:
        relative = absolute.relative_to(root).as_posix()
    except ValueError as error:
        raise typed(EVIDENCE_BLOCKER, f"{label} escapes projection root") from error
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.as_posix() != relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise typed(EVIDENCE_BLOCKER, f"{label} path is unsafe")
    return relative


def component_path(root: Path, relative: object, *, label: str) -> Path:
    raw = str(relative or "")
    pure = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or pure.as_posix() != raw
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise typed(EVIDENCE_BLOCKER, f"{label} path is unsafe")
    return root / Path(*pure.parts)


def read_lock(path: Path, *, component: str) -> tuple[bytes, str]:
    try:
        content, _mode = read_regular_nofollow(path, label=f"{component} lock")
    except ValueError as error:
        raise typed(
            CAS_BLOCKER,
            f"{component} lock is unavailable or linked",
        ) from error
    return content, _digest_bytes(content)


def environment_identity(environment: Mapping[str, str]) -> dict[str, Any]:
    values = {
        key: str(environment[key]) for key in ENVIRONMENT_KEYS if key in environment
    }
    return {
        "values": values,
        "digest": _digest_bytes(
            _canonical_bytes(
                {
                    "schema": "stackctl-app-dependency-command-environment.v1",
                    "values": values,
                }
            )
        ),
    }


def source_identity(manifest_path: Path) -> dict[str, Any]:
    try:
        requested = manifest_path.expanduser().absolute()
        if requested.is_symlink():
            raise ValueError("source capsule manifest is linked")
        path = requested.resolve(strict=True)
        encoded, _mode = read_regular_nofollow(
            path,
            label="package source capsule manifest",
        )
        value = json.loads(encoded)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise typed(EVIDENCE_BLOCKER, "source capsule manifest is invalid") from error
    if not isinstance(value, Mapping) or not isinstance(value.get("entries"), list):
        raise typed(EVIDENCE_BLOCKER, "source capsule manifest fields are invalid")
    markers: dict[str, dict[str, Any]] = {}
    logicals = set(COMPONENT_LOGICAL_PATHS.values())
    for item in value["entries"]:
        if not isinstance(item, Mapping) or item.get("logicalPath") not in logicals:
            continue
        logical = str(item["logicalPath"])
        if logical in markers:
            raise typed(
                EVIDENCE_BLOCKER,
                f"source dependency marker is duplicated: {logical}",
            )
        markers[logical] = {
            "logicalPath": logical,
            "digest": str(item.get("digest") or ""),
            "size": item.get("size"),
        }
    return {
        "manifestPath": str(path),
        "manifestDigest": _digest_bytes(encoded),
        "baselineId": str(value.get("baselineId") or ""),
        "inputDigest": str(
            value.get("deploymentInputDigest") or value.get("inputDigest") or ""
        ),
        "inputCount": value.get(
            "deploymentInputFileCount",
            value.get("inputCount"),
        ),
        "dependencyMarkers": [markers[key] for key in sorted(markers)],
    }


def validate_source_markers(
    source: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]]
) -> None:
    markers = {
        str(item.get("logicalPath")): item
        for item in source.get("dependencyMarkers", [])
        if isinstance(item, Mapping)
    }
    for component in components:
        marker = markers.get(COMPONENT_LOGICAL_PATHS[component])
        if (
            marker is None
            or not DIGEST.fullmatch(str(marker.get("digest") or ""))
            or not isinstance(marker.get("size"), int)
            or marker["size"] <= 0
        ):
            raise typed(
                EVIDENCE_BLOCKER,
                f"source dependency marker is missing or invalid: {component}",
            )


def write_expectation(
    *, root: Path, manifest: dict[str, Any], evidence_path: Path
) -> DependencyProjectionExpectation:
    encoded = _canonical_bytes(manifest)
    requested = evidence_path.expanduser().absolute()
    parent = requested.parent.resolve(strict=True)
    path = parent / requested.name
    if path.exists() or path.is_symlink():
        raise typed(
            EVIDENCE_BLOCKER,
            "expectation evidence destination must be fresh",
        )
    try:
        write_fresh_relative_file(
            root=parent,
            relative=path.name,
            content=encoded,
            mode=0o600,
        )
    except (OSError, ValueError) as error:
        raise typed(EVIDENCE_BLOCKER, "expectation evidence write failed") from error
    return load_expectation(
        projection_root_path=root,
        evidence_path=path,
        expected_digest=_digest_bytes(encoded),
    )


def _private_evidence_manifest(
    encoded: bytes,
    *,
    mode: int,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise typed(
            EVIDENCE_BLOCKER,
            f"{label} evidence is unavailable, linked or invalid",
        ) from error
    if (
        mode != 0o600
        or not isinstance(value, dict)
        or encoded != _canonical_bytes(value)
    ):
        raise typed(
            EVIDENCE_BLOCKER,
            f"{label} evidence is not canonical private bytes",
        )
    return value


def _read_private_evidence(path: Path, *, label: str) -> tuple[bytes, int]:
    try:
        metadata = path.lstat()
        encoded, _normalized_mode = read_regular_nofollow(
            path,
            label=f"projection {label} evidence",
        )
    except (OSError, ValueError) as error:
        raise typed(
            EVIDENCE_BLOCKER,
            f"{label} evidence is unavailable, linked or invalid",
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise typed(
            EVIDENCE_BLOCKER,
            f"{label} evidence is not canonical private bytes",
        )
    return encoded, stat.S_IMODE(metadata.st_mode)


def _absolute_historical_path(value: object, *, label: str) -> Path:
    raw = str(value or "")
    path = Path(raw)
    if (
        not raw
        or not path.is_absolute()
        or str(path) != raw
        or any(part in {"", ".", ".."} for part in path.parts[1:])
    ):
        raise typed(EVIDENCE_BLOCKER, f"historical {label} path is invalid")
    return path


def _historical_relative_path(value: object, *, label: str) -> str:
    raw = str(value or "")
    pure = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or pure.as_posix() != raw
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise typed(EVIDENCE_BLOCKER, f"historical {label} path is invalid")
    return raw


def _historical_source(source: object) -> Mapping[str, Any]:
    if not isinstance(source, Mapping) or set(source) != {
        "manifestPath",
        "manifestDigest",
        "baselineId",
        "inputDigest",
        "inputCount",
        "dependencyMarkers",
    }:
        raise typed(EVIDENCE_BLOCKER, "historical source identity is invalid")
    _absolute_historical_path(source.get("manifestPath"), label="source manifest")
    if (
        not DIGEST.fullmatch(str(source.get("manifestDigest") or ""))
        or not DIGEST.fullmatch(str(source.get("baselineId") or ""))
        or not DIGEST.fullmatch(str(source.get("inputDigest") or ""))
        or not isinstance(source.get("inputCount"), int)
        or isinstance(source.get("inputCount"), bool)
        or source["inputCount"] < 0
        or not isinstance(source.get("dependencyMarkers"), list)
    ):
        raise typed(EVIDENCE_BLOCKER, "historical source identity is invalid")
    marker_paths: list[str] = []
    for marker in source["dependencyMarkers"]:
        if (
            not isinstance(marker, Mapping)
            or set(marker) != {"logicalPath", "digest", "size"}
            or not DIGEST.fullmatch(str(marker.get("digest") or ""))
            or not isinstance(marker.get("size"), int)
            or isinstance(marker.get("size"), bool)
            or marker["size"] <= 0
        ):
            raise typed(EVIDENCE_BLOCKER, "historical source marker is invalid")
        marker_paths.append(
            _historical_relative_path(
                marker.get("logicalPath"),
                label="source marker",
            )
        )
    if marker_paths != sorted(set(marker_paths)):
        raise typed(EVIDENCE_BLOCKER, "historical source markers are not canonical")
    return source


def _historical_count(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise typed(EVIDENCE_BLOCKER, f"historical {label} is invalid")
    return value


def _historical_digest(value: object, *, label: str) -> str:
    raw = str(value or "")
    if not DIGEST.fullmatch(raw):
        raise typed(EVIDENCE_BLOCKER, f"historical {label} is invalid")
    return raw


def _historical_components(components: object) -> Mapping[str, Mapping[str, Any]]:
    if (
        not isinstance(components, Mapping)
        or "productionPub" not in components
        or list(components) != sorted(components)
        or any(name not in COMPONENT_LOGICAL_PATHS for name in components)
    ):
        raise typed(EVIDENCE_BLOCKER, "historical component set is invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for name, raw in components.items():
        if not isinstance(raw, Mapping):
            raise typed(EVIDENCE_BLOCKER, f"historical {name} component is invalid")
        kind = str(raw.get("kind") or "")
        if kind == "pub":
            fields = {
                "kind",
                "treePath",
                "lockPath",
                "manifestDigest",
                "treeDigest",
                "entryCount",
                "directoryCount",
                "lockDigest",
            }
            if name not in {"productionPub", "patrolPub"} or set(raw) != fields:
                raise typed(EVIDENCE_BLOCKER, f"historical {name} Pub fields drifted")
            _historical_count(raw.get("directoryCount"), label=f"{name} directoryCount")
        elif kind == "iosPods":
            fields = {
                "kind",
                "dependencyHost",
                "treePath",
                "lockPath",
                "treeDigest",
                "entryCount",
                "lockDigest",
            }
            expected_host = {
                "productionIosPods": IOS_POD_PRODUCTION_HOST,
                "patrolIosPods": IOS_POD_PATROL_HOST,
            }.get(str(name))
            if (
                expected_host is None
                or set(raw) != fields
                or raw.get("dependencyHost") != expected_host
            ):
                raise typed(EVIDENCE_BLOCKER, f"historical {name} Pods fields drifted")
        elif kind == "androidGradle":
            fields = {
                "kind",
                "treePath",
                "manifest",
                "manifestDigest",
                "treeDigest",
                "entryCount",
            }
            manifest = raw.get("manifest")
            if (
                name != "androidGradle"
                or set(raw) != fields
                or not isinstance(manifest, Mapping)
                or _digest_bytes(_canonical_bytes(manifest))
                != raw.get("manifestDigest")
                or manifest.get("treeDigest") != raw.get("treeDigest")
                or manifest.get("entryCount") != raw.get("entryCount")
            ):
                raise typed(
                    EVIDENCE_BLOCKER,
                    "historical androidGradle manifest identity drifted",
                )
        else:
            raise typed(EVIDENCE_BLOCKER, f"historical {name} kind is unsupported")
        _historical_relative_path(raw.get("treePath"), label=f"{name} tree")
        if kind in {"pub", "iosPods"}:
            _historical_relative_path(raw.get("lockPath"), label=f"{name} lock")
            _historical_digest(raw.get("lockDigest"), label=f"{name} lockDigest")
        if kind in {"pub", "androidGradle"}:
            _historical_digest(
                raw.get("manifestDigest"),
                label=f"{name} manifestDigest",
            )
        _historical_digest(raw.get("treeDigest"), label=f"{name} treeDigest")
        _historical_count(raw.get("entryCount"), label=f"{name} entryCount")
        result[str(name)] = raw
    return result


def _historical_environments(environments: object) -> Mapping[str, Any]:
    if (
        not isinstance(environments, Mapping)
        or "production" not in environments
        or list(environments) != sorted(environments)
        or any(owner not in {"production", "patrol"} for owner in environments)
    ):
        raise typed(EVIDENCE_BLOCKER, "historical environment set is invalid")
    for owner, raw in environments.items():
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"values", "digest"}
            or not isinstance(raw.get("values"), Mapping)
        ):
            raise typed(EVIDENCE_BLOCKER, f"historical {owner} environment is invalid")
        values = raw["values"]
        if (
            any(key not in ENVIRONMENT_KEYS for key in values)
            or any(not isinstance(value, str) for value in values.values())
            or values.get("FLUTTER_SWIFT_PACKAGE_MANAGER") != "false"
            or environment_identity(values) != raw
        ):
            raise typed(
                EVIDENCE_BLOCKER,
                f"historical {owner} environment identity drifted",
            )
    return environments


def _historical_patrol_command_envelope(
    value: object,
    *,
    environments: Mapping[str, Any],
) -> None:
    if value is None:
        if "patrol" in environments:
            raise typed(
                EVIDENCE_BLOCKER,
                "historical Patrol command envelope is missing",
            )
        return
    if "patrol" not in environments:
        raise typed(
            EVIDENCE_BLOCKER,
            "historical Patrol command envelope has no Patrol environment",
        )
    try:
        validated = validate_patrol_command_envelope(value)
        patrol_command_envelope_digest(validated)
    except (TypeError, ValueError) as error:
        raise typed(
            EVIDENCE_BLOCKER,
            "historical Patrol command envelope is invalid",
        ) from error
    if dict(validated["dependencyEnvironment"]) != dict(
        environments["patrol"]["values"]
    ):
        raise typed(
            EVIDENCE_BLOCKER,
            "historical Patrol command environment drifted",
        )


def load_historical_expectation_bytes(
    *,
    evidence_path: Path,
    encoded: bytes,
    evidence_mode: int,
    expected_digest: str,
) -> DependencyProjectionExpectation:
    """Validate already-opened immutable expectation bytes."""
    if not DIGEST.fullmatch(expected_digest):
        raise typed(EVIDENCE_BLOCKER, "expected evidence digest is invalid")
    path = evidence_path.expanduser().absolute()
    manifest = _private_evidence_manifest(
        encoded,
        mode=evidence_mode,
        label="expectation",
    )
    if _digest_bytes(encoded) != expected_digest:
        raise typed(EVIDENCE_BLOCKER, "expectation evidence digest drifted")
    if (
        set(manifest)
        != {
            "schema",
            "projectionRoot",
            "source",
            "components",
            "environments",
            "patrolCommandEnvelope",
        }
        or manifest.get("schema") != EXPECTATION_SCHEMA
    ):
        raise typed(EVIDENCE_BLOCKER, "historical expectation fields drifted")
    historical_root = _absolute_historical_path(
        manifest.get("projectionRoot"),
        label="projection root",
    )
    source = _historical_source(manifest.get("source"))
    components = _historical_components(manifest.get("components"))
    environments = _historical_environments(manifest.get("environments"))
    _historical_patrol_command_envelope(
        manifest.get("patrolCommandEnvelope"),
        environments=environments,
    )
    validate_source_markers(source, components)
    return DependencyProjectionExpectation(
        evidence_path=path,
        evidence_digest=expected_digest,
        projection_root=historical_root,
        manifest=manifest,
    )


def load_historical_expectation(
    *, evidence_path: Path, expected_digest: str
) -> DependencyProjectionExpectation:
    """Load immutable expectation bytes after their live projection was deleted."""

    requested = evidence_path.expanduser().absolute()
    path = requested.parent.resolve(strict=True) / requested.name
    encoded, mode = _read_private_evidence(path, label="expectation")
    return load_historical_expectation_bytes(
        evidence_path=path,
        encoded=encoded,
        evidence_mode=mode,
        expected_digest=expected_digest,
    )


def load_expectation(
    *, projection_root_path: Path, evidence_path: Path, expected_digest: str
) -> DependencyProjectionExpectation:
    root = projection_root(projection_root_path)
    historical = load_historical_expectation(
        evidence_path=evidence_path,
        expected_digest=expected_digest,
    )
    if historical.projection_root != root:
        raise typed(
            EVIDENCE_BLOCKER,
            "expectation evidence projection binding drifted",
        )
    return DependencyProjectionExpectation(
        evidence_path=historical.evidence_path,
        evidence_digest=expected_digest,
        projection_root=root,
        manifest=historical.manifest,
    )


def load_expectation_bytes(
    *,
    projection_root_path: Path,
    evidence_path: Path,
    encoded: bytes,
    evidence_mode: int,
    expected_digest: str,
) -> DependencyProjectionExpectation:
    """Validate stable no-follow expectation bytes without reopening their path."""

    root = projection_root_path
    if (
        not root.is_absolute()
        or str(root) != root.as_posix()
        or any(part in {"", ".", ".."} for part in root.parts[1:])
    ):
        raise typed(
            EVIDENCE_BLOCKER,
            "projection root is not an exact opened path",
        )
    historical = load_historical_expectation_bytes(
        evidence_path=evidence_path,
        encoded=encoded,
        evidence_mode=evidence_mode,
        expected_digest=expected_digest,
    )
    if historical.projection_root != root:
        raise typed(
            EVIDENCE_BLOCKER,
            "expectation evidence projection binding drifted",
        )
    return DependencyProjectionExpectation(
        evidence_path=historical.evidence_path,
        evidence_digest=expected_digest,
        projection_root=root,
        manifest=historical.manifest,
    )


def load_readback_evidence_bytes(
    *,
    evidence_path: Path,
    encoded: bytes,
    evidence_mode: int,
    expected_digest: str,
    expected_expectation_digest: str,
) -> DependencyProjectionReadbackEvidence:
    """Validate already-opened readback bytes without reopening their path."""

    if not DIGEST.fullmatch(expected_digest) or not DIGEST.fullmatch(
        expected_expectation_digest
    ):
        raise typed(EVIDENCE_BLOCKER, "readback evidence digest is invalid")
    path = evidence_path.expanduser().absolute()
    manifest = _private_evidence_manifest(
        encoded,
        mode=evidence_mode,
        label="readback",
    )
    if _digest_bytes(encoded) != expected_digest:
        raise typed(EVIDENCE_BLOCKER, "readback evidence digest drifted")
    if (
        set(manifest)
        != {
            "schema",
            "expectationDigest",
            "projectionRoot",
            "sourceManifestDigest",
            "components",
            "patrolCommandEnvelopeDigest",
        }
        or manifest.get("schema") != READBACK_SCHEMA
        or manifest.get("expectationDigest") != expected_expectation_digest
        or not Path(str(manifest.get("projectionRoot") or "")).is_absolute()
        or not DIGEST.fullmatch(str(manifest.get("sourceManifestDigest") or ""))
        or not isinstance(manifest.get("components"), Mapping)
        or (
            manifest.get("patrolCommandEnvelopeDigest") is not None
            and not DIGEST.fullmatch(
                str(manifest.get("patrolCommandEnvelopeDigest") or "")
            )
        )
    ):
        raise typed(
            EVIDENCE_BLOCKER,
            "readback evidence fields or expectation binding drifted",
        )
    return DependencyProjectionReadbackEvidence(
        evidence_path=path,
        evidence_digest=expected_digest,
        expectation_digest=expected_expectation_digest,
        manifest=manifest,
    )


def load_readback_evidence(
    *,
    evidence_path: Path,
    expected_digest: str,
    expected_expectation_digest: str,
) -> DependencyProjectionReadbackEvidence:
    requested = evidence_path.expanduser().absolute()
    path = requested.parent.resolve(strict=True) / requested.name
    encoded, mode = _read_private_evidence(path, label="readback")
    return load_readback_evidence_bytes(
        evidence_path=path,
        encoded=encoded,
        evidence_mode=mode,
        expected_digest=expected_digest,
        expected_expectation_digest=expected_expectation_digest,
    )


def write_readback_evidence(
    *, readback: DependencyProjectionReadback, evidence_path: Path
) -> DependencyProjectionReadbackEvidence:
    if (
        readback.encoded_manifest != _canonical_bytes(readback.manifest)
        or readback.manifest.get("schema") != READBACK_SCHEMA
        or readback.manifest.get("expectationDigest") != readback.expectation_digest
    ):
        raise typed(EVIDENCE_BLOCKER, "readback result is not canonical or bound")
    requested = evidence_path.expanduser().absolute()
    parent = requested.parent.resolve(strict=True)
    path = parent / requested.name
    if path.exists() or path.is_symlink():
        raise typed(EVIDENCE_BLOCKER, "readback evidence destination must be fresh")
    try:
        write_fresh_relative_file(
            root=parent,
            relative=path.name,
            content=readback.encoded_manifest,
            mode=0o600,
        )
    except (OSError, ValueError) as error:
        raise typed(EVIDENCE_BLOCKER, "readback evidence write failed") from error
    digest = _digest_bytes(readback.encoded_manifest)
    return load_readback_evidence(
        evidence_path=path,
        expected_digest=digest,
        expected_expectation_digest=readback.expectation_digest,
    )
