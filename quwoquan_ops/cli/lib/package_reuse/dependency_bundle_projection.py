"""Materialize one verified five-component App dependency bundle privately."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .android_gradle_projection import (
    materialize_capsule_android_gradle_home,
    private_gradle_environment,
)
from .input_capsule import verify_package_input_capsule_with_dependencies
from .ios_pod_inputs import (
    IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
    IOS_POD_DEPENDENCY_DIRECTORIES,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
    IOS_PODFILE_RELATIVES,
    ios_pod_resolution_inputs,
)
from .ios_pod_projection import (
    IosPodProjection,
    OfflinePodInstallResult,
    isolated_cocoapods_environment,
    materialize_ios_pod_projection,
    run_offline_cocoapods_install,
)
from .patrol_pub_projection import materialize_capsule_patrol_pub_cache
from .pub_cache_capsule import _digest_bytes
from .pub_cache_projection import materialize_capsule_pub_cache

_PROXY_KEYS = frozenset(
    {
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    }
)


@dataclass(frozen=True, slots=True)
class AppDependencyProjection:
    """Private dependency paths and command environments for one source tree."""

    production_pub_cache: Path
    patrol_pub_cache: Path | None
    android_gradle_home: Path | None
    ios_projections: tuple[tuple[str, IosPodProjection], ...]
    pod_install_results: tuple[tuple[str, OfflinePodInstallResult], ...]
    production_environment: dict[str, str]
    patrol_environment: dict[str, str] | None


def _manifest_entries(manifest: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = manifest.get("entries")
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        raise TypeError("App dependency source capsule entries are invalid")
    return list(raw)


def _pub_manifest_digest(snapshot: object) -> str:
    encoded = getattr(snapshot, "encoded_sync_manifest", None)
    if not isinstance(encoded, bytes):
        raise TypeError("App dependency Pub sync manifest is missing")
    return _digest_bytes(encoded)


def _literal_absolute_path(value: object, *, label: str) -> str:
    raw = str(value or "")
    path = Path(raw)
    if (
        not raw
        or not path.is_absolute()
        or str(path) != raw
        or any(part in {"", ".", ".."} for part in path.parts[1:])
    ):
        raise ValueError(f"{label} is not a literal absolute path")
    return raw


def _private_search_path(base: Mapping[str, str]) -> str:
    """Expand current-user shorthand while rejecting cwd-relative lookup."""

    raw = str(base.get("PATH") or "")
    if not raw:
        raise ValueError("App dependency private PATH is empty")
    entries = raw.split(os.pathsep)
    if any(not entry for entry in entries):
        raise ValueError("App dependency private PATH contains an empty entry")

    normalized: list[str] = []
    for entry in entries:
        if entry == "~" or entry.startswith("~/"):
            shorthand = Path(entry)
            if (
                str(shorthand) != entry
                or any(part in {"", ".", ".."} for part in shorthand.parts[1:])
            ):
                raise ValueError(
                    "App dependency private PATH entry is not a literal path"
                )
            home = _literal_absolute_path(
                base.get("HOME"),
                label="App dependency base HOME",
            )
            expanded = home if entry == "~" else str(Path(home) / entry[2:])
            normalized.append(
                _literal_absolute_path(
                    expanded,
                    label="App dependency private PATH entry",
                )
            )
            continue
        normalized.append(
            _literal_absolute_path(
                entry,
                label="App dependency private PATH entry",
            )
        )
    return os.pathsep.join(normalized)


def _private_flutter_environment(
    *,
    base: Mapping[str, str],
    state_root: Path,
) -> dict[str, str]:
    """Isolate Flutter config/plugin generation from developer-global state."""

    search_path = _private_search_path(base)
    state = state_root.expanduser().absolute()
    if state.exists() or state.is_symlink():
        raise ValueError("App dependency Flutter private state must be fresh")
    state.mkdir(parents=True, mode=0o700)
    home = state / "home"
    config = state / "xdg-config"
    cache = state / "xdg-cache"
    home.mkdir(mode=0o700)
    config.mkdir(mode=0o700)
    cache.mkdir(mode=0o700)
    environment = {
        key: value
        for key, value in base.items()
        if key not in _PROXY_KEYS
        and key not in {"HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "PATH"}
    }
    environment.update(
        {
            "PATH": search_path,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_CACHE_HOME": str(cache),
            "FLUTTER_SWIFT_PACKAGE_MANAGER": IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _ios_projection(
    *,
    capsule_root: Path,
    projection_root: Path,
    private_state_root: Path,
    pod_executable: str | Path,
    dependency_host: str,
    upstream_dependency_digest: str,
    base_environment: Mapping[str, str],
    replay: bool,
    verified_snapshot: object | None = None,
) -> tuple[IosPodProjection, OfflinePodInstallResult | None, dict[str, str]]:
    relative_lock = IOS_PODFILE_RELATIVES[dependency_host]
    ios_root = (projection_root / relative_lock).parent
    projection = materialize_ios_pod_projection(
        snapshot_root=(
            capsule_root / IOS_POD_DEPENDENCY_DIRECTORIES[dependency_host]
        ),
        ios_root=ios_root,
        private_state_root=private_state_root / dependency_host,
        pod_executable=pod_executable,
        resolution_inputs=ios_pod_resolution_inputs(
            repo_root=projection_root,
            dependency_host=dependency_host,
        ),
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=dependency_host,
        verified_snapshot=verified_snapshot,
    )
    result = (
        run_offline_cocoapods_install(
            projection=projection,
            pod_executable=pod_executable,
            base_environment=base_environment,
        )
        if replay
        else None
    )
    environment = isolated_cocoapods_environment(
        base=base_environment,
        projection=projection,
    )
    return projection, result, environment


def materialize_dependency_bundle_projection(
    *,
    manifest_path: Path,
    projection_root: Path,
    private_state_root: Path,
    platform: str,
    base_environment: Mapping[str, str],
    pod_executable: str | Path | None = None,
    include_patrol: bool = False,
    replay_ios: bool = True,
) -> AppDependencyProjection:
    """Verify the complete package capsule, then project only private closures.

    iOS replay, when requested here, runs under OS-level network denial. A
    caller that must run offline ``pub get`` first can defer it to
    :func:`replay_ios_dependency_projections`. Android always receives the
    projected forced-offline multi-root Gradle home.
    """

    if platform not in {"android", "ios", "web"}:
        raise ValueError("App dependency projection platform is unsupported")
    manifest_ref = manifest_path.expanduser().absolute()
    if manifest_ref.name != "manifest.json" or manifest_ref.is_symlink():
        raise ValueError("App dependency source capsule manifest is invalid")
    capsule_root = manifest_ref.parent
    projection = projection_root.expanduser().absolute()
    private = private_state_root.expanduser().absolute()
    verified_capsule = verify_package_input_capsule_with_dependencies(capsule_root)
    entries = _manifest_entries(verified_capsule.manifest)
    snapshots = verified_capsule.dependency_snapshots
    if snapshots is None:
        raise ValueError("App dependency verified capsule snapshots are missing")
    production_pub, patrol_pub, _production_ios, _patrol_ios, _android = snapshots

    production_cache = materialize_capsule_pub_cache(
        capsule_root=capsule_root,
        manifest_entries=entries,
        projection_root=projection,
        verified_snapshot=production_pub,
    )
    production_environment = _private_flutter_environment(
        base=base_environment,
        state_root=private / "flutter" / IOS_POD_PRODUCTION_HOST,
    )
    production_environment["PUB_CACHE"] = str(production_cache)
    patrol_cache: Path | None = None
    patrol_environment: dict[str, str] | None = None
    if include_patrol:
        patrol_cache = materialize_capsule_patrol_pub_cache(
            capsule_root=capsule_root,
            manifest_entries=entries,
            projection_root=projection,
            verified_snapshot=patrol_pub,
        )
        patrol_environment = _private_flutter_environment(
            base=base_environment,
            state_root=private / "flutter" / IOS_POD_PATROL_HOST,
        )
        patrol_environment["PUB_CACHE"] = str(patrol_cache)

    gradle_home: Path | None = None
    if platform == "android":
        gradle_home = materialize_capsule_android_gradle_home(
            capsule_root=capsule_root,
            manifest_entries=entries,
            projection_root=projection,
        )
        production_environment = private_gradle_environment(
            gradle_user_home=gradle_home,
            base=production_environment,
        )
        if patrol_environment is not None:
            patrol_environment = private_gradle_environment(
                gradle_user_home=gradle_home,
                base=patrol_environment,
            )

    ios_projections: list[tuple[str, IosPodProjection]] = []
    pod_results: list[tuple[str, OfflinePodInstallResult]] = []
    if platform == "ios":
        if pod_executable is None:
            raise ValueError("iOS App dependency projection requires CocoaPods")
        hosts = [IOS_POD_PRODUCTION_HOST]
        if include_patrol:
            hosts.append(IOS_POD_PATROL_HOST)
        for host in hosts:
            upstream = (
                _pub_manifest_digest(production_pub)
                if host == IOS_POD_PRODUCTION_HOST
                else _pub_manifest_digest(patrol_pub)
            )
            base = (
                production_environment
                if host == IOS_POD_PRODUCTION_HOST
                else patrol_environment
            )
            if base is None:
                raise ValueError("Patrol iOS dependency environment is missing")
            verified_ios = (
                _production_ios
                if host == IOS_POD_PRODUCTION_HOST
                else _patrol_ios
            )
            ios_projection, result, environment = _ios_projection(
                capsule_root=capsule_root,
                projection_root=projection,
                private_state_root=private,
                pod_executable=pod_executable,
                dependency_host=host,
                upstream_dependency_digest=upstream,
                base_environment=base,
                replay=replay_ios,
                verified_snapshot=verified_ios,
            )
            ios_projections.append((host, ios_projection))
            if result is not None:
                pod_results.append((host, result))
            if host == IOS_POD_PRODUCTION_HOST:
                production_environment = environment
            else:
                patrol_environment = environment

    return AppDependencyProjection(
        production_pub_cache=production_cache,
        patrol_pub_cache=patrol_cache,
        android_gradle_home=gradle_home,
        ios_projections=tuple(ios_projections),
        pod_install_results=tuple(pod_results),
        production_environment=production_environment,
        patrol_environment=patrol_environment,
    )


def replay_ios_dependency_projections(
    *,
    dependency_projection: AppDependencyProjection,
    pod_executable: str | Path,
) -> tuple[tuple[str, OfflinePodInstallResult], ...]:
    """Replay previously materialized iOS hosts after offline ``pub get``."""

    results: list[tuple[str, OfflinePodInstallResult]] = []
    for host, ios_projection in dependency_projection.ios_projections:
        environment = (
            dependency_projection.production_environment
            if host == IOS_POD_PRODUCTION_HOST
            else dependency_projection.patrol_environment
        )
        if environment is None:
            raise ValueError("Patrol iOS dependency environment is missing")
        results.append(
            (
                host,
                run_offline_cocoapods_install(
                    projection=ios_projection,
                    pod_executable=pod_executable,
                    base_environment=environment,
                ),
            )
        )
    return tuple(results)
