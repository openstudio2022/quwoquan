"""Atomic identity for every dependency closure consumed by App packaging/UAT.

The active pointer is intentionally small: it selects one immutable generation
of the production Pub cache, Patrol Pub cache, both CocoaPods hosts, and the
multi-root Android Gradle cache.  Domain loaders still verify every component's
full tree; this module prevents them from being selected from different sync
attempts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.output_paths import output_root

from .dependency_fs import assert_real_directory, read_regular_nofollow
from .native_dependency_inputs import native_resolution_input_identity
from .pub_cache_capsule import _canonical_bytes, _digest_bytes

APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA = "stackctl-app-dependency-bundle-active.v2"
APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA = "stackctl-app-dependency-sync-receipt.v3"

APP_DEPENDENCY_COMPONENTS = (
    "productionPub",
    "patrolPub",
    "productionIosPods",
    "patrolIosPods",
    "androidGradle",
)

_ACTIVE_FIELDS = {
    "schema",
    "attemptId",
    "flutterVersion",
    "flutterCommandResolutionDigest",
    "productionPubResolutionInputDigest",
    "patrolPubResolutionInputDigest",
    "nativeResolutionInputDigest",
    "components",
    "receiptRef",
    "receiptDigest",
}
_COMPONENT_FIELDS = {
    "snapshotRef",
    "manifestDigest",
    "manifestSchema",
    "treeDigest",
    "entryCount",
}
_RECEIPT_FIELDS = {
    "schema",
    "claim",
    "attemptId",
    "components",
    "activationEvidence",
}


@dataclass(frozen=True, slots=True)
class AppDependencyBundle:
    """One verified active generation and its immutable component roots."""

    active: dict[str, Any]
    active_root: Path
    component_roots: tuple[tuple[str, Path], ...]
    component_manifests: tuple[tuple[str, dict[str, Any]], ...]

    def component_root(self, name: str) -> Path:
        try:
            return dict(self.component_roots)[name]
        except KeyError as error:
            raise ValueError(f"App dependency component is unavailable: {name}") from error

    def component_manifest(self, name: str) -> dict[str, Any]:
        try:
            return dict(self.component_manifests)[name]
        except KeyError as error:
            raise ValueError(f"App dependency manifest is unavailable: {name}") from error


def managed_dependency_bundle_root() -> Path:
    return (
        output_root().expanduser().absolute()
        / "env/repo/local/app-dependency-sync/cache"
    )


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    encoded, _mode = read_regular_nofollow(path, label=label)
    try:
        value = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"App dependency {label} is invalid") from error
    if not isinstance(value, dict):
        raise TypeError(f"App dependency {label} is not an object")
    return encoded, value


def _safe_ref(value: object, *, label: str) -> Path:
    raw = str(value or "")
    pure = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or pure.as_posix() != raw
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"App dependency {label} is unsafe")
    return Path(*pure.parts)


def _manifest_closure(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    dependency = manifest.get("dependency")
    return dependency if isinstance(dependency, Mapping) else manifest


def _validate_component(
    *,
    root: Path,
    attempt_id: str,
    name: str,
    declaration: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if set(declaration) != _COMPONENT_FIELDS:
        raise ValueError(f"App dependency {name} declaration fields mismatch")
    relative = _safe_ref(declaration.get("snapshotRef"), label=f"{name} snapshotRef")
    expected = Path("snapshots") / attempt_id / name
    if relative != expected:
        raise ValueError(
            f"App dependency {name} snapshotRef is not bound to active attempt"
        )
    component_root = root / relative
    assert_real_directory(component_root, label=f"{name} snapshot root")
    encoded, manifest = _read_json(
        component_root / "manifest.json",
        label=f"{name} snapshot manifest",
    )
    del encoded
    canonical = _canonical_bytes(manifest)
    if declaration.get("manifestDigest") != _digest_bytes(canonical):
        raise ValueError(f"App dependency {name} manifest digest drifted")
    if declaration.get("manifestSchema") != manifest.get("schema"):
        raise ValueError(f"App dependency {name} manifest schema drifted")
    closure = _manifest_closure(manifest)
    if (
        declaration.get("treeDigest") != closure.get("treeDigest")
        or declaration.get("entryCount") != closure.get("entryCount")
    ):
        raise ValueError(f"App dependency {name} closure identity drifted")
    return component_root, manifest


def _current_source_identity(repo_root: Path) -> dict[str, str]:
    # Imports are local to avoid making the production Pub store depend on its
    # own active-bundle loader at module-import time.
    from .patrol_pub_cache import patrol_resolution_input_identity
    from .pub_cache_store import current_flutter_identity, resolution_input_identity

    flutter = current_flutter_identity()
    production = resolution_input_identity(repo_root)
    patrol = patrol_resolution_input_identity(repo_root)
    native = native_resolution_input_identity(repo_root)
    return {
        **flutter,
        "productionPubResolutionInputDigest": production["resolutionInputDigest"],
        "patrolPubResolutionInputDigest": patrol["resolutionInputDigest"],
        "nativeResolutionInputDigest": native["nativeResolutionInputDigest"],
    }


def _validate_receipt(
    *, root: Path, active: Mapping[str, Any], components: Mapping[str, Any]
) -> None:
    receipt_relative = _safe_ref(active.get("receiptRef"), label="receiptRef")
    receipt_path = output_root().expanduser().absolute() / receipt_relative
    encoded, receipt = _read_json(receipt_path, label="sync receipt")
    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("App dependency sync receipt fields mismatch")
    if (
        receipt.get("schema") != APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA
        or receipt.get("claim") != "PREPARED_NOT_ACTIVE"
        or receipt.get("attemptId") != active.get("attemptId")
        or receipt.get("components") != components
        or receipt.get("activationEvidence")
        != {
            "requiredActiveRef": (root / "active.json")
            .relative_to(output_root().expanduser().absolute())
            .as_posix(),
            "requiredAttemptId": active.get("attemptId"),
        }
        or active.get("receiptDigest") != _digest_bytes(_canonical_bytes(receipt))
    ):
        raise ValueError("App dependency sync receipt binding drifted")
    if json.loads(encoded) != receipt:
        raise ValueError("App dependency sync receipt readback drifted")


def load_active_dependency_bundle(*, repo_root: Path) -> AppDependencyBundle:
    """Read active once and verify source, receipt, and all component selectors."""

    repository = repo_root.expanduser().absolute()
    root = managed_dependency_bundle_root()
    assert_real_directory(root, label="managed dependency bundle root")
    _encoded, active = _read_json(root / "active.json", label="bundle active pointer")
    if set(active) != _ACTIVE_FIELDS:
        raise ValueError("App dependency bundle active pointer fields mismatch")
    if active.get("schema") != APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA:
        raise ValueError("App dependency bundle active pointer schema mismatch")
    attempt_id = str(active.get("attemptId") or "")
    if not attempt_id or any(character not in "0123456789abcdef" for character in attempt_id):
        raise ValueError("App dependency bundle attempt identity is invalid")
    current = _current_source_identity(repository)
    for field, expected in current.items():
        if active.get(field) != expected:
            raise ValueError(f"App dependency bundle is stale for {field}")
    raw_components = active.get("components")
    if not isinstance(raw_components, Mapping) or set(raw_components) != set(
        APP_DEPENDENCY_COMPONENTS
    ):
        raise ValueError("App dependency bundle component set mismatch")
    component_roots: list[tuple[str, Path]] = []
    component_manifests: list[tuple[str, dict[str, Any]]] = []
    for name in APP_DEPENDENCY_COMPONENTS:
        declaration = raw_components.get(name)
        if not isinstance(declaration, Mapping):
            raise TypeError(f"App dependency {name} declaration is invalid")
        component_root, manifest = _validate_component(
            root=root,
            attempt_id=attempt_id,
            name=name,
            declaration=declaration,
        )
        component_roots.append((name, component_root))
        component_manifests.append((name, manifest))
    _validate_receipt(root=root, active=active, components=dict(raw_components))
    return AppDependencyBundle(
        active=active,
        active_root=root,
        component_roots=tuple(component_roots),
        component_manifests=tuple(component_manifests),
    )


def component_declaration(*, snapshot_ref: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Build one selector from an already verified domain manifest."""

    closure = _manifest_closure(manifest)
    tree_digest = str(closure.get("treeDigest") or "")
    entry_count = closure.get("entryCount")
    if not tree_digest.startswith("sha256:") or not isinstance(entry_count, int):
        raise ValueError("App dependency component closure identity is incomplete")
    return {
        "snapshotRef": _safe_ref(snapshot_ref.as_posix(), label="snapshotRef").as_posix(),
        "manifestDigest": _digest_bytes(_canonical_bytes(manifest)),
        "manifestSchema": str(manifest.get("schema") or ""),
        "treeDigest": tree_digest,
        "entryCount": entry_count,
    }
