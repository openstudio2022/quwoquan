"""Capture pre-command dependency-domain identities from a private projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .android_gradle_capsule import build_android_gradle_snapshot, digest_bytes
from .android_gradle_store import canonical_android_uat_gradle_invocations
from .dependency_fs import read_regular_nofollow
from .dependency_projection_contract import (
    CAS_BLOCKER,
    EVIDENCE_BLOCKER,
    EXPECTATION_SCHEMA,
    DependencyProjectionExpectation,
    environment_identity,
    read_lock,
    relative_path,
    source_identity,
    typed,
    validate_source_markers,
    write_expectation,
)
from .dependency_projection_contract import (
    projection_root as normalize_projection_root,
)
from .ios_pod_capsule import (
    IOS_POD_CAPSULE_SCHEMA,
    IosPodNode,
    _canonical_bytes,
    _digest_bytes,
    _scan_component,
    _validate_symlink_closure,
)
from .ios_pod_inputs import (
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
    IOS_PODFILE_RELATIVES,
)
from .patrol_command_envelope import build_patrol_command_envelope
from .patrol_pub_cache import PATROL_HOST_RELATIVE
from .pub_cache_capsule import PubCacheSnapshot, build_pub_cache_snapshot


def pub_identity(snapshot: PubCacheSnapshot) -> dict[str, Any]:
    manifest = snapshot.manifest
    return {
        "manifestDigest": _digest_bytes(snapshot.encoded_manifest),
        "treeDigest": manifest["treeDigest"],
        "entryCount": manifest["entryCount"],
        "directoryCount": manifest["directoryCount"],
        "lockDigest": manifest["lockDigest"],
    }


def _pub_component(
    *, root: Path, component: str, cache_root: Path, lock_path: Path
) -> dict[str, Any]:
    try:
        snapshot = build_pub_cache_snapshot(
            lock_path=lock_path,
            cache_root=cache_root,
            reject_unlocked=True,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"{component} pre-command Pub CAS is invalid: {error}",
        ) from error
    return {
        "kind": "pub",
        "treePath": relative_path(root, cache_root, label=f"{component} tree"),
        "lockPath": relative_path(root, lock_path, label=f"{component} lock"),
        **pub_identity(snapshot),
    }


def pods_identity(nodes: Sequence[IosPodNode], lock_digest: str) -> dict[str, Any]:
    values = [item.as_dict() for item in sorted(nodes, key=lambda item: item.relative)]
    return {
        "treeDigest": _digest_bytes(
            _canonical_bytes(
                {
                    "schema": IOS_POD_CAPSULE_SCHEMA,
                    "component": "pods",
                    "entries": values,
                }
            )
        ),
        "entryCount": len(values),
        "lockDigest": lock_digest,
    }


def scan_pods(pods_root: Path, lock_path: Path, *, component: str) -> dict[str, Any]:
    lock, lock_digest = read_lock(lock_path, component=component)
    try:
        manifest_lock, _mode = read_regular_nofollow(
            pods_root / "Manifest.lock",
            label=f"{component} Pods/Manifest.lock",
        )
        if manifest_lock != lock:
            raise ValueError("Podfile.lock and Pods/Manifest.lock differ")
        nodes = _scan_component("pods", pods_root)
        _validate_symlink_closure(nodes)
    except (OSError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"{component} Pods domain is invalid: {error}",
        ) from error
    if not nodes:
        raise typed(CAS_BLOCKER, f"{component} Pods domain is empty")
    return pods_identity(nodes, lock_digest)


def _ios_components(
    *,
    root: Path,
    dependency_projection: Any,
    ios_install_results: Sequence[tuple[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    projections = tuple(dependency_projection.ios_projections)
    if not projections:
        return {}
    results = tuple(
        dependency_projection.pod_install_results
        if ios_install_results is None
        else ios_install_results
    )
    by_host = {str(host): result for host, result in results}
    if len(by_host) != len(results):
        raise typed(EVIDENCE_BLOCKER, "iOS convergence result hosts are duplicated")
    values: dict[str, dict[str, Any]] = {}
    for raw_host, ios_projection in projections:
        host = str(raw_host)
        if host not in {IOS_POD_PRODUCTION_HOST, IOS_POD_PATROL_HOST}:
            raise typed(EVIDENCE_BLOCKER, "iOS projected host is unsupported")
        component = (
            "productionIosPods" if host == IOS_POD_PRODUCTION_HOST else "patrolIosPods"
        )
        result = by_host.get(host)
        if result is None:
            raise typed(
                EVIDENCE_BLOCKER,
                f"{component} converged replay evidence is required",
            )
        ios_root = Path(ios_projection.ios_root)
        pods_root = Path(ios_projection.pods_root)
        expected_ios = root / IOS_PODFILE_RELATIVES[host].parent
        if ios_root.expanduser().absolute() != expected_ios:
            raise typed(EVIDENCE_BLOCKER, f"{component} host root is not canonical")
        identity = scan_pods(
            pods_root,
            ios_root / "Podfile.lock",
            component=component,
        )
        if identity["treeDigest"] != result.converged_tree_digest:
            raise typed(CAS_BLOCKER, f"{component} is not the converged replay tree")
        output_lock = getattr(result.output_snapshot, "lock_bytes", None)
        if (
            not isinstance(output_lock, bytes)
            or _digest_bytes(output_lock) != identity["lockDigest"]
        ):
            raise typed(CAS_BLOCKER, f"{component} converged replay lock drifted")
        values[component] = {
            "kind": "iosPods",
            "dependencyHost": host,
            "treePath": relative_path(root, pods_root, label=f"{component} tree"),
            "lockPath": relative_path(
                root,
                ios_root / "Podfile.lock",
                label=f"{component} lock",
            ),
            **identity,
        }
    if set(by_host) != {str(host) for host, _projection in projections}:
        raise typed(
            EVIDENCE_BLOCKER,
            "iOS convergence result set exceeds projected hosts",
        )
    return values


def _android_component(
    *, root: Path, dependency_projection: Any
) -> dict[str, Any] | None:
    raw_home = dependency_projection.android_gradle_home
    if raw_home is None:
        return None
    home = Path(raw_home).expanduser().absolute()
    tree = home.parent
    invocations = canonical_android_uat_gradle_invocations(root)
    try:
        snapshot = build_android_gradle_snapshot(
            project_root=root,
            tree_root=tree,
            gradle_roots=[item.gradle_root for item in invocations],
        )
    except (OSError, TypeError, ValueError) as error:
        raise typed(
            CAS_BLOCKER,
            f"androidGradle pre-command CAS is invalid: {error}",
        ) from error
    return {
        "kind": "androidGradle",
        "treePath": relative_path(root, tree, label="androidGradle tree"),
        "manifest": snapshot.manifest,
        "manifestDigest": digest_bytes(snapshot.encoded_manifest),
        "treeDigest": snapshot.manifest["treeDigest"],
        "entryCount": snapshot.manifest["entryCount"],
    }


def _environments(
    *, dependency_projection: Any, components: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for owner, environment in (
        ("production", dependency_projection.production_environment),
        ("patrol", dependency_projection.patrol_environment),
    ):
        if environment is None:
            continue
        if not isinstance(environment, Mapping):
            raise typed(
                EVIDENCE_BLOCKER,
                f"{owner} dependency environment is invalid",
            )
        identity = environment_identity(environment)
        values = identity["values"]
        if values.get("FLUTTER_SWIFT_PACKAGE_MANAGER") != "false":
            raise typed(EVIDENCE_BLOCKER, f"{owner} Flutter SPM mode is not disabled")
        pub_component = "productionPub" if owner == "production" else "patrolPub"
        cache = (
            dependency_projection.production_pub_cache
            if owner == "production"
            else dependency_projection.patrol_pub_cache
        )
        if pub_component in components and values.get("PUB_CACHE") != str(
            Path(cache).absolute()
        ):
            raise typed(
                EVIDENCE_BLOCKER,
                f"{owner} PUB_CACHE does not select its projection",
            )
        result[owner] = identity
    if "production" not in result:
        raise typed(EVIDENCE_BLOCKER, "production dependency environment is missing")
    return result


def _patrol_command_envelope(dependency_projection: Any) -> dict[str, Any] | None:
    environment = dependency_projection.patrol_environment
    if environment is None:
        return None
    if not isinstance(environment, Mapping):
        raise typed(EVIDENCE_BLOCKER, "Patrol dependency environment is invalid")
    try:
        return build_patrol_command_envelope(environment)
    except (OSError, TypeError, ValueError) as error:
        raise typed(
            EVIDENCE_BLOCKER,
            "Patrol command envelope is invalid",
        ) from error


def prepare_dependency_projection_cas_evidence(
    *,
    projection_root: Path,
    source_manifest_path: Path,
    dependency_projection: Any,
    evidence_path: Path,
    ios_install_results: Sequence[tuple[str, Any]] | None = None,
) -> DependencyProjectionExpectation:
    """Write a canonical private expectation before the first build command."""

    root = normalize_projection_root(projection_root)
    components: dict[str, dict[str, Any]] = {
        "productionPub": _pub_component(
            root=root,
            component="productionPub",
            cache_root=Path(dependency_projection.production_pub_cache),
            lock_path=root / "quwoquan_app/pubspec.lock",
        )
    }
    if dependency_projection.patrol_pub_cache is not None:
        components["patrolPub"] = _pub_component(
            root=root,
            component="patrolPub",
            cache_root=Path(dependency_projection.patrol_pub_cache),
            lock_path=root / PATROL_HOST_RELATIVE / "pubspec.lock",
        )
    components.update(
        _ios_components(
            root=root,
            dependency_projection=dependency_projection,
            ios_install_results=ios_install_results,
        )
    )
    android = _android_component(root=root, dependency_projection=dependency_projection)
    if android is not None:
        components["androidGradle"] = android
    source = source_identity(source_manifest_path)
    validate_source_markers(source, components)
    manifest = {
        "schema": EXPECTATION_SCHEMA,
        "projectionRoot": str(root),
        "source": source,
        "components": {key: components[key] for key in sorted(components)},
        "environments": _environments(
            dependency_projection=dependency_projection,
            components=components,
        ),
        "patrolCommandEnvelope": _patrol_command_envelope(dependency_projection),
    }
    return write_expectation(
        root=root,
        manifest=manifest,
        evidence_path=evidence_path,
    )
