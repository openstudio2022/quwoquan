"""Private CocoaPods projection and network-denied install execution."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ios_pod_capsule import (
    IOS_POD_CAPSULE_SCHEMA,
    IosPodNode,
    IosPodSnapshot,
    _canonical_bytes,
    _digest_bytes,
    _read_regular_nofollow,
    build_verified_ios_pod_snapshot,
    is_ephemeral_xcode_user_state,
)
from .ios_pod_inputs import (
    IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
    IOS_POD_PRODUCTION_HOST,
    validate_ios_pod_host,
)
from .ios_pod_store import copy_ios_pod_component, load_verified_ios_pod_capsule

_SANDBOX_EXECUTABLE = Path("/usr/bin/sandbox-exec")
_NETWORK_DENIED_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_PROJECT_RELATIVE = "pods/Pods.xcodeproj/project.pbxproj"
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_$.)}])"
    r'(/[A-Za-z0-9._-]+(?:/[^"\\\s;,)]+)+)'
)
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
class IosPodProjection:
    snapshot: IosPodSnapshot
    ios_root: Path
    pods_root: Path
    cp_home_dir: Path
    cp_cache_dir: Path
    private_home: Path
    resolution_inputs: tuple[tuple[str, Path], ...]
    upstream_dependency_digest: str
    dependency_host: str
    snapshot_root: Path
    projection_root: Path


@dataclass(frozen=True, slots=True)
class OfflinePodInstallResult:
    command: tuple[str, ...]
    second_command: tuple[str, ...]
    first_exit_code: int
    second_exit_code: int
    output_snapshot: IosPodSnapshot
    stdout: str
    stderr: str
    second_stdout: str
    second_stderr: str
    seed_project_digest: str
    projected_project_digest: str
    converged_tree_digest: str

    @property
    def evidence_manifest(self) -> dict[str, Any]:
        return {
            "schema": "stackctl-ios-pod-offline-projection-evidence.v1",
            "dependencyHost": self.output_snapshot.dependency_host,
            "nativeDependencyMode": self.output_snapshot.manifest[
                "nativeDependencyMode"
            ],
            "podfileLockDigest": self.output_snapshot.manifest["podfileLockDigest"],
            "seedProjectDigest": self.seed_project_digest,
            "projectedProjectDigest": self.projected_project_digest,
            "convergedTreeDigest": self.converged_tree_digest,
            "attempts": [
                {"command": list(self.command), "exitCode": self.first_exit_code},
                {
                    "command": list(self.second_command),
                    "exitCode": self.second_exit_code,
                },
            ],
        }


def isolated_cocoapods_environment(
    *,
    base: Mapping[str, str],
    projection: IosPodProjection,
) -> dict[str, str]:
    """Return an environment which cannot consult global Pod/cache/git state."""

    environment = {
        key: value
        for key, value in base.items()
        if key not in _PROXY_KEYS
        and key
        not in {
            "CP_HOME_DIR",
            "CP_CACHE_DIR",
            "COCOAPODS_HOME",
            "COCOAPODS_REPOS_DIR",
            "GIT_CONFIG_GLOBAL",
        }
    }
    environment.update(
        {
            "CP_HOME_DIR": str(projection.cp_home_dir),
            "CP_CACHE_DIR": str(projection.cp_cache_dir),
            "COCOAPODS_HOME": str(projection.cp_home_dir),
            "HOME": str(projection.private_home),
            "XDG_CONFIG_HOME": str(projection.private_home / ".config"),
            "XDG_CACHE_HOME": str(projection.private_home / ".cache"),
            "COCOAPODS_DISABLE_STATS": "true",
            "COCOAPODS_SKIP_UPDATE_MESSAGE": "true",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "FLUTTER_SWIFT_PACKAGE_MANAGER": IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
        }
    )
    return environment


def materialize_ios_pod_projection(
    *,
    snapshot_root: Path,
    ios_root: Path,
    private_state_root: Path,
    pod_executable: str | Path,
    resolution_inputs: Mapping[str, Path],
    upstream_dependency_digest: str,
    dependency_host: str = IOS_POD_PRODUCTION_HOST,
    build_projection_root: Path | None = None,
    verified_snapshot: IosPodSnapshot | None = None,
) -> IosPodProjection:
    """Copy a verified Pod CAS into one fresh writable build projection."""

    ios = ios_root.expanduser().absolute()
    if ios.is_symlink() or not ios.is_dir():
        raise ValueError("iOS Pod build projection ios root is invalid")
    private = private_state_root.expanduser().absolute()
    if private.exists() or private.is_symlink():
        raise ValueError("iOS Pod private state destination must be fresh")
    resolved_ios = ios.resolve(strict=True)
    resolved_private = private.resolve(strict=False)
    if build_projection_root is None:
        projection_root = Path(
            os.path.commonpath((resolved_ios, resolved_private.parent))
        )
    else:
        candidate = build_projection_root.expanduser().absolute()
        if candidate.is_symlink() or not candidate.is_dir():
            raise ValueError("iOS Pod explicit build projection root is invalid")
        projection_root = candidate.resolve(strict=True)
    unsafe_roots = {
        Path("/"),
        Path.home().resolve(),
        Path(tempfile.gettempdir()).resolve(),
        Path("/tmp").resolve(),
        Path("/private/tmp").resolve(),
    }
    if projection_root in unsafe_roots or not projection_root.is_dir():
        raise ValueError("iOS Pod build projection root is invalid")
    if not (
        resolved_ios.is_relative_to(projection_root)
        and resolved_private.is_relative_to(projection_root)
    ):
        raise ValueError("iOS Pod source and private state must share projection root")
    host = validate_ios_pod_host(dependency_host)
    snapshot = load_verified_ios_pod_capsule(
        snapshot_root=snapshot_root,
        expected_podfile_lock=ios / "Podfile.lock",
        pod_executable=pod_executable,
        resolution_inputs=resolution_inputs,
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=host,
        verified_snapshot=verified_snapshot,
    )
    if (ios / "Pods").exists() or (ios / "Pods").is_symlink():
        raise ValueError("iOS Pod build projection Pods destination must be fresh")
    private.mkdir(parents=True, mode=0o700)
    home = private / "home"
    cache = private / "cache"
    user_home = private / "user-home"
    user_home.mkdir(mode=0o700)
    (user_home / ".config").mkdir(mode=0o700)
    (user_home / ".cache").mkdir(mode=0o700)
    copy_ios_pod_component(
        snapshot,
        component="pods",
        destination=ios / "Pods",
        writable=True,
    )
    copy_ios_pod_component(
        snapshot,
        component="home",
        destination=home,
        writable=True,
    )
    copy_ios_pod_component(
        snapshot,
        component="cache",
        destination=cache,
        writable=True,
    )
    return IosPodProjection(
        snapshot=snapshot,
        ios_root=ios,
        pods_root=ios / "Pods",
        cp_home_dir=home,
        cp_cache_dir=cache,
        private_home=user_home,
        resolution_inputs=tuple(sorted(resolution_inputs.items())),
        upstream_dependency_digest=upstream_dependency_digest,
        dependency_host=host,
        snapshot_root=snapshot_root.expanduser().resolve(strict=True),
        projection_root=projection_root,
    )


def cocoapods_network_denied_command(pod_executable: str | Path) -> list[str]:
    """Return the only admitted install command for a build/launch executor."""

    sandbox = _SANDBOX_EXECUTABLE
    if sandbox.is_symlink() or not sandbox.is_file() or not os.access(sandbox, os.X_OK):
        raise ValueError("iOS Pod network-denial sandbox is unavailable")
    executable = Path(pod_executable).expanduser().resolve(strict=True)
    return [
        str(sandbox),
        "-p",
        _NETWORK_DENIED_PROFILE,
        str(executable),
        "install",
        "--deployment",
        "--no-repo-update",
    ]


def _run_install(
    *,
    command: list[str],
    projection: IosPodProjection,
    environment: Mapping[str, str],
    timeout_seconds: float,
    phase: str,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=projection.ios_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"iOS Pod {phase} offline install execution failed") from error
    if result.returncode != 0:
        raise ValueError(
            f"iOS Pod {phase} offline install failed with exit code {result.returncode}"
        )
    return result


def _build_output_snapshot(
    *,
    projection: IosPodProjection,
    pod_executable: str | Path,
) -> IosPodSnapshot:
    return build_verified_ios_pod_snapshot(
        podfile_lock=projection.ios_root / "Podfile.lock",
        pods_root=projection.pods_root,
        cp_home_dir=projection.cp_home_dir,
        cp_cache_dir=projection.cp_cache_dir,
        pod_executable=pod_executable,
        resolution_inputs=dict(projection.resolution_inputs),
        upstream_dependency_digest=projection.upstream_dependency_digest,
        dependency_host=projection.dependency_host,
    )


def _pods_by_path(snapshot: IosPodSnapshot) -> dict[str, IosPodNode]:
    return {
        node.relative: node
        for node in snapshot.nodes
        if node.relative.startswith("pods/")
        # CocoaPods/Xcode may materialize per-user workspace state during an
        # otherwise byte-stable install. The iOS workspace ignores xcuserdata;
        # it is not dependency payload and must not affect convergence proof.
        and not is_ephemeral_xcode_user_state(node.relative)
    }


def _first_node_drift(
    expected: Mapping[str, IosPodNode],
    actual: Mapping[str, IosPodNode],
) -> str | None:
    for relative in sorted(expected.keys() | actual.keys()):
        before = expected.get(relative)
        after = actual.get(relative)
        if before is None or after is None or before.as_dict() != after.as_dict():
            return relative
    return None


def _project_node(nodes: Mapping[str, IosPodNode]) -> IosPodNode:
    project = nodes.get(_PROJECT_RELATIVE)
    if project is None or project.kind != "file":
        raise ValueError("iOS Pod Pods.xcodeproj project is absent")
    return project


def _allowed_project_roots(
    *,
    projection: IosPodProjection,
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    roots = [
        projection.projection_root,
        Path("/Applications"),
        Path("/Library"),
        Path("/System"),
        Path("/bin"),
        Path("/sbin"),
        Path("/usr"),
        Path("/opt/homebrew"),
    ]
    declared_flutter = environment.get("QWQ_REAL_FLUTTER")
    flutter = declared_flutter or shutil.which(
        "flutter", path=environment.get("PATH", "")
    )
    if flutter:
        executable = Path(flutter).expanduser().resolve(strict=True)
        if executable.name != "flutter" or not executable.is_file():
            raise ValueError("iOS Pod Flutter executable identity is invalid")
        roots.append(executable.parent.parent)
    pub_cache = environment.get("PUB_CACHE")
    if pub_cache:
        cache = Path(pub_cache).expanduser().absolute()
        if not cache.is_relative_to(projection.projection_root):
            raise ValueError("iOS Pod PUB_CACHE is outside build projection root")
        roots.append(cache)
    return tuple(roots)


def _validate_projected_project(
    *,
    projection: IosPodProjection,
    project: IosPodNode,
    environment: Mapping[str, str],
) -> None:
    content, mode = _read_regular_nofollow(
        project.source,
        label="projected Pods.xcodeproj/project.pbxproj",
    )
    if mode != project.mode or _digest_bytes(content) != project.sha256:
        raise ValueError("iOS Pod projected project changed during validation")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("iOS Pod projected project is not UTF-8") from error
    if not all(
        marker in text for marker in ("archiveVersion", "objects", "rootObject")
    ):
        raise ValueError("iOS Pod projected project API structure is invalid")
    forbidden = (projection.snapshot_root, projection.snapshot_root.parent)
    if any(str(path) in text for path in forbidden):
        raise ValueError("iOS Pod projected project references sealed dependency root")
    allowed = _allowed_project_roots(
        projection=projection,
        environment=environment,
    )
    for raw in sorted(set(_ABSOLUTE_PATH.findall(text))):
        path = Path(raw).expanduser().absolute()
        if not any(path == root or path.is_relative_to(root) for root in allowed):
            raise ValueError(
                f"iOS Pod projected project has an external absolute path: {raw}"
            )


def _pods_tree_digest(nodes: Mapping[str, IosPodNode]) -> str:
    entries = [nodes[relative].as_dict() for relative in sorted(nodes)]
    return _digest_bytes(
        _canonical_bytes(
            {
                "schema": IOS_POD_CAPSULE_SCHEMA,
                "component": "pods",
                "entries": entries,
            }
        )
    )


def run_offline_cocoapods_install(
    *,
    projection: IosPodProjection,
    pod_executable: str | Path,
    base_environment: Mapping[str, str],
    timeout_seconds: float = 300.0,
) -> OfflinePodInstallResult:
    """Project once, then prove full byte convergence under OS network denial."""

    command = cocoapods_network_denied_command(pod_executable)
    environment = isolated_cocoapods_environment(
        base=base_environment,
        projection=projection,
    )
    seed_pods = _pods_by_path(projection.snapshot)
    seed_project = _project_node(seed_pods)
    first = _run_install(
        command=command,
        projection=projection,
        environment=environment,
        timeout_seconds=timeout_seconds,
        phase="first",
    )
    projected = _build_output_snapshot(
        projection=projection,
        pod_executable=pod_executable,
    )
    if projected.lock_bytes != projection.snapshot.lock_bytes:
        raise ValueError("iOS Pod first offline install changed Podfile.lock identity")
    projected_pods = _pods_by_path(projected)
    for relative in sorted(seed_pods.keys() | projected_pods.keys()):
        if relative == _PROJECT_RELATIVE:
            continue
        before = seed_pods.get(relative)
        after = projected_pods.get(relative)
        if before is None or after is None or before.as_dict() != after.as_dict():
            raise ValueError(
                "iOS Pod first offline install changed sealed Pods payload outside "
                f"Pods.xcodeproj/project.pbxproj: {relative}"
            )
    projected_project = _project_node(projected_pods)
    _validate_projected_project(
        projection=projection,
        project=projected_project,
        environment=environment,
    )
    second = _run_install(
        command=command,
        projection=projection,
        environment=environment,
        timeout_seconds=timeout_seconds,
        phase="second",
    )
    converged = _build_output_snapshot(
        projection=projection,
        pod_executable=pod_executable,
    )
    if converged.lock_bytes != projection.snapshot.lock_bytes:
        raise ValueError("iOS Pod second offline install changed Podfile.lock identity")
    converged_pods = _pods_by_path(converged)
    drift = _first_node_drift(projected_pods, converged_pods)
    if drift is not None:
        raise ValueError(
            "iOS Pod second offline install did not converge exact Pods component: "
            f"{drift}"
        )
    return OfflinePodInstallResult(
        command=tuple(command),
        second_command=tuple(command),
        first_exit_code=first.returncode,
        second_exit_code=second.returncode,
        output_snapshot=converged,
        stdout=first.stdout,
        stderr=first.stderr,
        second_stdout=second.stdout,
        second_stderr=second.stderr,
        seed_project_digest=seed_project.sha256,
        projected_project_digest=projected_project.sha256,
        converged_tree_digest=_pods_tree_digest(converged_pods),
    )
