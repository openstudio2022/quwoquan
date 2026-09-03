"""Private five-component network sync used by ``app-dependency-sync``."""

from __future__ import annotations

import json
import os
import re
import urllib.request
import stat
import subprocess
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from quwoquan_ops.cli.commands.app_dependency_sync_ios import (
    assert_ios_generated_metadata as _assert_ios_generated_metadata,
)
from quwoquan_ops.cli.commands.app_dependency_sync_projection import project
from quwoquan_ops.cli.lib.app_dependency_sync_diagnostics import (
    dependency_failure_cause,
    redact_dependency_failure_text,
    write_private_log as _write_private_log,
)
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    resolve_cocoapods_executable,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_component import (
    load_android_gradle_component,
    write_android_gradle_component,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_store import (
    canonical_android_uat_gradle_invocations,
    materialize_flutter_gradle_wrappers,
    synchronize_android_gradle_dependencies,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    remove_private_tree,
    write_fresh_relative_file,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_network_command import (
    retry_event,
    run_managed_subprocess,
    transient_network_cause,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_capsule import (
    build_verified_ios_pod_snapshot,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_inputs import (
    IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
    IOS_PODFILE_RELATIVES,
    ios_pod_resolution_inputs,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_projection import (
    materialize_ios_pod_projection,
    run_offline_cocoapods_install,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_store import (
    load_verified_ios_pod_capsule,
    write_ios_pod_capsule,
)
from quwoquan_ops.cli.lib.package_reuse.native_dependency_inputs import (
    native_resolution_input_paths,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_cache import (
    PATROL_HOST_RELATIVE,
    build_patrol_pub_cache_snapshot,
    patrol_resolution_input_paths,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_store import (
    load_patrol_pub_cache_snapshot_at,
    write_patrol_pub_cache_snapshot,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import (
    _canonical_bytes,
    _digest_bytes,
    _lock_model,
    build_pub_cache_snapshot,
    copy_snapshot_tree_with_lock,
    is_canonical_pub_cache_transient,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_store import (
    build_sync_manifest,
    load_pub_cache_snapshot_at,
    pub_resolution_input_paths,
)


from quwoquan_ops.cli.commands.app_dependency_sync_pub_fallback import (
    PUBLIC_PUB_MIRROR as _PUBLIC_PUB_MIRROR,
    public_pub_origin_archive_fallback as _public_pub_origin_archive_fallback_impl,
)


def _public_pub_origin_archive_fallback(
    *, app_dir: Path, pub_cache: Path, log_path: Path
) -> bool:
    """Retain the builder hook while delegating archive validation/extraction."""

    return _public_pub_origin_archive_fallback_impl(
        app_dir=app_dir,
        pub_cache=pub_cache,
        log_path=log_path,
        urlopen=urllib.request.urlopen,
    )


_SYNC_TIMEOUT_SECONDS = 900
_SYNC_NETWORK_MAX_ATTEMPTS = 3
_SYNC_NETWORK_DEADLINE_SECONDS = 45 * 60
_PROXY_KEYS = {
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
}
_BASE_ENVIRONMENT_KEYS = {
    "ANDROID_HOME",
    "ANDROID_SDK_ROOT",
    "CI",
    "DEVELOPER_DIR",
    "FLUTTER_ROOT",
    "JAVA_HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "SDKROOT",
    "TERM",
    "TMPDIR",
    "TOOLCHAINS",
}
def private_environment(
    *, home: Path, pub_cache: Path | None, hosted_url: str | None
) -> dict[str, str]:
    private_home = home.expanduser().absolute()
    private_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    config, cache = private_home / "xdg-config", private_home / "xdg-cache"
    config.mkdir(mode=0o700, exist_ok=True)
    cache.mkdir(mode=0o700, exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in _BASE_ENVIRONMENT_KEYS or key.startswith("LC_")
    }
    for key in _PROXY_KEYS | {
        "CP_HOME_DIR",
        "CP_CACHE_DIR",
        "COCOAPODS_HOME",
        "COCOAPODS_REPOS_DIR",
        "GRADLE_HOME",
        "GRADLE_USER_HOME",
        "GIT_CONFIG_GLOBAL",
        "PUB_CACHE",
        "PUB_HOSTED_URL",
        "SSH_AUTH_SOCK",
    }:
        environment.pop(key, None)
    environment.update(
        {
            "HOME": str(private_home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_CACHE_HOME": str(cache),
            "FLUTTER_SWIFT_PACKAGE_MANAGER": IOS_FLUTTER_SWIFT_PACKAGE_MANAGER,
            "FLUTTER_SUPPRESS_ANALYTICS": "true",
            "COCOAPODS_DISABLE_STATS": "true",
            "COCOAPODS_SKIP_UPDATE_MESSAGE": "true",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": environment.get("LANG") or "en_US.UTF-8",
            "PATH": environment.get("PATH") or "/usr/bin:/bin",
        }
    )
    if pub_cache is not None:
        environment["PUB_CACHE"] = str(pub_cache.expanduser().absolute())
    if hosted_url is not None:
        environment["PUB_HOSTED_URL"] = hosted_url
    return environment


def _run_checked(
    *,
    command: list[str],
    cwd: Path,
    environment: Mapping[str, str],
    log_path: Path,
    phase: str,
    retry_transient_network: bool = False,
    public_hosted_upstream: bool = False,
) -> subprocess.CompletedProcess[str]:
    attempts = _SYNC_NETWORK_MAX_ATTEMPTS if retry_transient_network else 1
    started_at = time.monotonic()
    failures: list[tuple[str, BaseException | None]] = []
    terminal_failure: tuple[str, BaseException | None] | None = None
    log_entries: list[str] = []
    for attempt in range(attempts):
        remaining = _SYNC_NETWORK_DEADLINE_SECONDS - (time.monotonic() - started_at)
        if remaining <= 0:
            break
        try:
            completed = run_managed_subprocess(
                command,
                cwd=cwd,
                env=dict(environment),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=min(_SYNC_TIMEOUT_SECONDS, remaining),
                check=False,
            )
            output = completed.stdout or ""
        except subprocess.TimeoutExpired as exc:
            output = str(exc.output or "")
            failures.append((output, exc))
            cause = "process_timeout"
        else:
            if completed.returncode == 0:
                if failures:
                    log_entries.append(
                        retry_event(attempt=attempt + 1, result="success")
                    )
                else:
                    log_entries.append(output)
                _write_private_log(
                    log_path,
                    redact_dependency_failure_text("\n".join(log_entries)),
                )
                return completed
            failures.append((output, None))
            cause = transient_network_cause(output)
            if (
                cause is None
                and public_hosted_upstream
                and "package not available (authorization failed)" in output.lower()
            ):
                # pub.flutter-io.cn 是公开 hosted mirror，不存在 package 凭据。
                # 其 archive upstream 403/5xx 会被 Dart Pub 折叠成该固定文案；
                # 仅对这个钉定公共 mirror 视作暂态，私有 hosted auth 仍立即阻断。
                cause = "public_hosted_upstream_unavailable"
            if not retry_transient_network or cause is None:
                terminal_failure = (output, None)
                break
        if attempt + 1 < attempts:
            remaining = _SYNC_NETWORK_DEADLINE_SECONDS - (time.monotonic() - started_at)
            delay = min(float(1 << attempt), max(0.0, remaining))
            log_entries.append(
                retry_event(
                    attempt=attempt + 1,
                    result="transient_failure",
                    cause=cause,
                    backoff=delay,
                )
            )
            if delay:
                time.sleep(delay)
    if not failures:
        raise ValueError(
            f"APP.DEPENDENCY.sync_timeout: {phase} exceeded network deadline"
        )
    selected_output, selected_error = terminal_failure or failures[0]
    _write_private_log(
        log_path,
        redact_dependency_failure_text(
            "\n".join([*log_entries, selected_output])
        ),
    )
    if selected_error is not None:
        raise ValueError(
            f"APP.DEPENDENCY.sync_timeout: {phase} exceeded {_SYNC_TIMEOUT_SECONDS}s"
        ) from selected_error
    tail = "\n".join(selected_output.splitlines()[-20:])
    raise ValueError(
        f"APP.DEPENDENCY.sync_failed: {phase} failed" + (f"\n{tail}" if tail else "")
    )


def run_pub_get(
    *,
    flutter: str,
    app_dir: Path,
    pub_cache: Path,
    hosted_url: str,
    offline: bool,
    log_path: Path,
    private_home: Path | None = None,
) -> None:
    environment = private_environment(
        home=private_home or app_dir.parent / "flutter-home",
        pub_cache=pub_cache,
        hosted_url=hosted_url,
    )
    command = [flutter, "pub", "get"]
    if offline:
        command.append("--offline")
    command.extend(["--enforce-lockfile", "--no-example"])
    try:
        _run_checked(
            command=command,
            cwd=app_dir,
            environment=environment,
            log_path=log_path,
            phase=f"Pub {'offline validation' if offline else 'network sync'}",
            retry_transient_network=not offline,
            public_hosted_upstream=(
                not offline and hosted_url == _PUBLIC_PUB_MIRROR
            ),
        )
    except ValueError as error:
        if (
            offline
            or hosted_url != _PUBLIC_PUB_MIRROR
            or "Package not available (authorization failed)" not in str(error)
            or not _public_pub_origin_archive_fallback(
                app_dir=app_dir, pub_cache=pub_cache, log_path=log_path
            )
        ):
            raise
        _write_private_log(
            log_path.with_name(f"{log_path.stem}-origin-fallback{log_path.suffix}"),
            retry_event(
                attempt=1,
                result="origin_fallback",
                cause="public_mirror_archive_unavailable",
            ),
        )




def _remove_pub_online_transients(cache_root: Path) -> None:
    """在 sealing 前移除 Pub online-only metadata，不触碰 locked package bytes。"""

    for relative in ("hosted/pub.flutter-io.cn/.cache", "_temp", "log", "README.md"):
        path = cache_root / relative
        if path.is_symlink():
            raise ValueError("APP.DEPENDENCY.pub_online_transient_unsafe")
        if path.is_dir():
            remove_private_tree(path)
        elif path.exists():
            path.unlink()


def _resolution_input_paths(repo_root: Path) -> set[Path]:
    root = repo_root.expanduser().absolute()
    paths = {
        *pub_resolution_input_paths(root),
        *patrol_resolution_input_paths(root),
        *native_resolution_input_paths(root),
        root / "quwoquan_app/pubspec.lock",
        root / PATROL_HOST_RELATIVE / "pubspec.lock",
    }
    for host in (IOS_POD_PRODUCTION_HOST, IOS_POD_PATROL_HOST):
        paths.update(
            ios_pod_resolution_inputs(repo_root=root, dependency_host=host).values()
        )
    return paths


def _exact_source_file(path: Path, *, label: str) -> tuple[bytes, int]:
    before = path.stat(follow_symlinks=False)
    content, _normalized_mode = read_regular_nofollow(path, label=label)
    after = path.stat(follow_symlinks=False)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or identity(before) != identity(after)
    ):
        raise ValueError(f"APP.DEPENDENCY.live_source_unsafe: {label}")
    return content, stat.S_IMODE(before.st_mode)


def _resolution_seal(repo_root: Path) -> dict[str, tuple[bytes, int]]:
    root = repo_root.expanduser().absolute()
    return {
        path.relative_to(root).as_posix(): _exact_source_file(
            path, label=f"sync source {path.relative_to(root).as_posix()}"
        )
        for path in sorted(_resolution_input_paths(root))
    }


def resolution_seal(repo_root: Path) -> dict[str, tuple[bytes, int]]:
    """Public intra-command live seal hook retained separately from projection checks."""

    return _resolution_seal(repo_root)


def assert_live_resolution_seal(
    *, repo_root: Path, expected: Mapping[str, tuple[bytes, int]]
) -> None:
    root = repo_root.expanduser().absolute()
    current_paths = {
        path.relative_to(root).as_posix() for path in _resolution_input_paths(root)
    }
    if current_paths != set(expected):
        raise ValueError("APP.DEPENDENCY.live_source_set_drift")
    for relative, sealed in expected.items():
        actual = _exact_source_file(
            root / relative, label=f"live sync source {relative}"
        )
        if actual != sealed:
            raise ValueError(f"APP.DEPENDENCY.live_source_drift: {relative}")


def _assert_resolution_seal(
    *, projection_root: Path, expected: Mapping[str, tuple[bytes, int]]
) -> None:
    for relative, sealed in expected.items():
        content, _normalized_mode = read_regular_nofollow(
            projection_root / relative, label=f"projected sync source {relative}"
        )
        metadata = (projection_root / relative).stat(follow_symlinks=False)
        actual = content, stat.S_IMODE(metadata.st_mode)
        if actual != sealed:
            raise ValueError(f"APP.DEPENDENCY.source_projection_drift: {relative}")


def _locked_host(lock_path: Path) -> str:
    _encoded, _digest, packages = _lock_model(lock_path)
    hosts = {item["url"] for item in packages}
    if len(hosts) != 1:
        raise ValueError("APP.DEPENDENCY.pub_host_set_invalid")
    return hosts.pop()


def _clear_flutter_metadata(host_root: Path) -> None:
    dart_tool = host_root / ".dart_tool"
    if dart_tool.exists() or dart_tool.is_symlink():
        remove_private_tree(dart_tool)
    for name in (".flutter-plugins", ".flutter-plugins-dependencies", ".packages"):
        path = host_root / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("APP.DEPENDENCY.generated_flutter_metadata_unsafe")
        path.unlink(missing_ok=True)


def _verify_pub_replay(
    *, snapshot: Any, lock_path: Path, cache_root: Path, host_root: Path
) -> None:
    """Accept only Pub's host-bound active-root marker beyond the sealed CAS."""

    rebuilt = build_pub_cache_snapshot(lock_path=lock_path, cache_root=cache_root)
    if rebuilt.manifest != snapshot.manifest:
        raise ValueError("APP.DEPENDENCY.pub_offline_replay_drift")
    expected_files = {item.relative for item in snapshot.files}
    expected_directories = set(snapshot.directories)
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in cache_root.rglob("*"):
        relative = path.relative_to(cache_root).as_posix()
        if path.is_dir() and not path.is_symlink():
            actual_directories.add(relative)
        else:
            actual_files.add(relative)
    if expected_files - actual_files or expected_directories - actual_directories:
        raise ValueError("APP.DEPENDENCY.pub_offline_replay_missing_cas_bytes")
    extra_files = actual_files - expected_files
    extra_directories = actual_directories - expected_directories
    if len(extra_files) != 1:
        raise ValueError("APP.DEPENDENCY.pub_offline_replay_extra_bytes")
    marker_relative = extra_files.pop()
    marker_parts = marker_relative.split("/")
    if (
        len(marker_parts) != 3
        or marker_parts[0] != "active_roots"
        or not re.fullmatch(r"[0-9a-f]{2}", marker_parts[1])
        or not re.fullmatch(r"[0-9a-f]{62}", marker_parts[2])
        or extra_directories != {"active_roots", f"active_roots/{marker_parts[1]}"}
    ):
        raise ValueError("APP.DEPENDENCY.pub_offline_replay_extra_bytes")
    marker, _mode = read_regular_nofollow(
        cache_root / marker_relative, label="Pub replay active-root marker"
    )
    try:
        payload = json.loads(marker)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("APP.DEPENDENCY.pub_active_root_marker_invalid") from exc
    expected_marker = {
        "package_config": (host_root / ".dart_tool/package_config.json").as_uri()
    }
    if payload != expected_marker:
        raise ValueError("APP.DEPENDENCY.pub_active_root_marker_invalid")


def _seal_directories(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    root.chmod(0o555)


def _expected_flutter(context: BuildContext) -> dict[str, str]:
    return {
        "flutterVersion": context.source_identity["flutterVersion"],
        "flutterCommandResolutionDigest": context.source_identity[
            "flutterCommandResolutionDigest"
        ],
    }


def _write_production_pub(
    *, context: BuildContext, projection_root: Path, snapshot: Any
) -> Path:
    target = context.generation_root / "productionPub"
    target.mkdir(mode=0o700)
    copy_snapshot_tree_with_lock(
        snapshot,
        target / "pub",
        lock_path=projection_root / "quwoquan_app/pubspec.lock",
        writable=False,
    )
    write_fresh_relative_file(
        root=target,
        relative="manifest.json",
        content=snapshot.encoded_sync_manifest,
        mode=0o444,
    )
    loaded = load_pub_cache_snapshot_at(
        repo_root=projection_root,
        snapshot_root=target,
        expected_flutter=_expected_flutter(context),
    )
    if loaded.manifest != snapshot.manifest:
        raise ValueError("APP.DEPENDENCY.production_pub_write_drift")
    _seal_directories(target)
    return target


def _pub_state_root(projection_root: Path, component_name: str) -> Path:
    if component_name not in {"productionPub", "patrolPub"}:
        raise ValueError("APP.DEPENDENCY.pub_component_invalid")
    root = projection_root.expanduser().absolute()
    state = root / ".dependency-sync/pub" / component_name
    if not state.is_relative_to(root):
        raise ValueError("APP.DEPENDENCY.pub_state_projection_escape")
    return state


def _build_pub_components(
    *, context: BuildContext, projection_root: Path
) -> tuple[dict[str, Path], dict[str, Path], dict[str, str]]:
    flutter = str(context.flutter_identity.get("executable") or "")
    if not flutter:
        raise ValueError("APP.DEPENDENCY.flutter_executable_missing")
    specs = (
        ("productionPub", projection_root / "quwoquan_app", False),
        ("patrolPub", projection_root / PATROL_HOST_RELATIVE, True),
    )
    roots: dict[str, Path] = {}
    replays: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for name, host_root, patrol in specs:
        lock = host_root / "pubspec.lock"
        hosted_url = _locked_host(lock)
        base = _pub_state_root(projection_root, name)
        online = base / "online-cache"
        online.mkdir(parents=True, mode=0o700)
        context.progress.begin("pub-online-resolution")
        run_pub_get(
            flutter=flutter,
            app_dir=host_root,
            pub_cache=online,
            hosted_url=hosted_url,
            offline=False,
            log_path=context.process_root / f"{name}-online.log",
            private_home=base / "online-home",
        )
        _remove_pub_online_transients(online)
        try:
            dependency = build_pub_cache_snapshot(
                lock_path=lock,
                cache_root=online,
                admitted_extra=is_canonical_pub_cache_transient,
            )
        except ValueError as error:
            raise ValueError(
                f"APP.DEPENDENCY.pub_online_snapshot_invalid: {error}"
            ) from error
        if patrol:
            snapshot = build_patrol_pub_cache_snapshot(
                repo_root=projection_root,
                cache_root=online,
                flutter_identity=context.flutter_identity,
            )
            if snapshot.manifest != dependency.manifest:
                raise ValueError("APP.DEPENDENCY.patrol_pub_online_scan_drift")
            root = write_patrol_pub_cache_snapshot(
                snapshot=snapshot,
                destination=context.generation_root / name,
                repo_root=projection_root,
            )
        else:
            manifest = build_sync_manifest(
                repo_root=projection_root,
                snapshot=dependency,
                flutter_identity=context.flutter_identity,
            )
            snapshot = replace(
                dependency,
                sync_manifest=manifest,
                encoded_sync_manifest=_canonical_bytes(manifest),
            )
            root = _write_production_pub(
                context=context, projection_root=projection_root, snapshot=snapshot
            )
        _clear_flutter_metadata(host_root)
        replay = base / "replay-cache"
        copy_snapshot_tree_with_lock(
            snapshot,
            replay,
            lock_path=lock,
            writable=True,
            admitted_extra=is_canonical_pub_cache_transient,
        )
        context.progress.begin("pub-offline-replay")
        run_pub_get(
            flutter=flutter,
            app_dir=host_root,
            pub_cache=replay,
            hosted_url=hosted_url,
            offline=True,
            log_path=context.process_root / f"{name}-offline.log",
            private_home=base / "offline-home",
        )
        _verify_pub_replay(
            snapshot=snapshot,
            lock_path=lock,
            cache_root=replay,
            host_root=host_root,
        )
        read_regular_nofollow(
            host_root / ".flutter-plugins-dependencies",
            label=f"{name} fresh Flutter plugin metadata",
        )
        roots[name], replays[name] = root, replay
        digests[name] = _digest_bytes(_canonical_bytes(snapshot.sync_manifest))
    return roots, replays, digests


def _pod_environment(
    *, state_root: Path, pub_cache: Path, hosted_url: str, pod: str
) -> tuple[dict[str, str], Path, Path]:
    home, cache = state_root / "pod-home", state_root / "pod-cache"
    home.mkdir(parents=True, mode=0o700)
    cache.mkdir(mode=0o700)
    environment = private_environment(
        home=state_root / "user-home",
        pub_cache=pub_cache,
        hosted_url=hosted_url,
    )
    environment.update(
        {
            "CP_HOME_DIR": str(home),
            "CP_CACHE_DIR": str(cache),
            "COCOAPODS_HOME": str(home),
            "PATH": os.pathsep.join(
                [str(Path(pod).parent), environment.get("PATH", "")]
            ).rstrip(os.pathsep),
        }
    )
    return environment, home, cache


def _build_ios_component(
    *,
    context: BuildContext,
    projection_root: Path,
    pod: str,
    host: str,
    pub_cache: Path,
    upstream_digest: str,
) -> Path:
    app_root = (
        projection_root / "quwoquan_app"
        if host == IOS_POD_PRODUCTION_HOST
        else projection_root / PATROL_HOST_RELATIVE
    )
    ios_root = projection_root / IOS_PODFILE_RELATIVES[host].parent
    state = context.work_root / "ios-online" / host
    environment, cp_home, cp_cache = _pod_environment(
        state_root=state,
        pub_cache=pub_cache,
        hosted_url=_locked_host(app_root / "pubspec.lock"),
        pod=pod,
    )
    flutter = str(context.flutter_identity.get("executable") or "")
    if not flutter:
        raise ValueError("APP.DEPENDENCY.flutter_executable_missing")
    environment["QWQ_REAL_FLUTTER"] = flutter
    environment["FLUTTER_ROOT"] = str(
        Path(flutter).expanduser().resolve(strict=True).parent.parent
    )
    config_command = [
        flutter,
        "build",
        "ios",
        "--config-only",
        "--no-codesign",
        "--no-pub",
    ]
    if host == IOS_POD_PRODUCTION_HOST:
        config_command.extend(["--flavor", "nonprod"])
    config_command.extend(["-t", "lib/main.dart"])
    _run_checked(
        command=config_command,
        cwd=app_root,
        environment=environment,
        log_path=context.process_root / f"{host}-ios-config.log",
        phase=f"{host} iOS Flutter config",
        retry_transient_network=True,
    )
    context.progress.begin("pods-online-resolution")
    _run_checked(
        command=[pod, "install", "--deployment"],
        cwd=ios_root,
        environment=environment,
        log_path=context.process_root / f"{host}-pod-online.log",
        phase=f"{host} CocoaPods network sync",
        retry_transient_network=True,
    )
    _assert_ios_generated_metadata(app_root)
    inputs = ios_pod_resolution_inputs(repo_root=projection_root, dependency_host=host)
    snapshot = build_verified_ios_pod_snapshot(
        podfile_lock=ios_root / "Podfile.lock",
        pods_root=ios_root / "Pods",
        cp_home_dir=cp_home,
        cp_cache_dir=cp_cache,
        pod_executable=pod,
        resolution_inputs=inputs,
        upstream_dependency_digest=upstream_digest,
        dependency_host=host,
    )
    name = "productionIosPods" if host == IOS_POD_PRODUCTION_HOST else "patrolIosPods"
    target = write_ios_pod_capsule(snapshot, context.generation_root / name)
    remove_private_tree(ios_root / "Pods")
    projection = materialize_ios_pod_projection(
        snapshot_root=target,
        ios_root=ios_root,
        private_state_root=projection_root / ".dependency-sync" / f"ios-{host}",
        pod_executable=pod,
        resolution_inputs=inputs,
        upstream_dependency_digest=upstream_digest,
        dependency_host=host,
        build_projection_root=projection_root,
    )
    context.progress.begin("pods-offline-replay")
    try:
        replay = run_offline_cocoapods_install(
            projection=projection,
            pod_executable=pod,
            base_environment=environment,
            timeout_seconds=_SYNC_TIMEOUT_SECONDS,
        )
    except ValueError as error:
        raise ValueError(
            f"APP.DEPENDENCY.ios_pod_offline_replay_failed: {error}"
        ) from error
    write_fresh_relative_file(
        root=context.process_root,
        relative=f"{host}-pod-offline-evidence.json",
        content=_canonical_bytes(replay.evidence_manifest),
        mode=0o600,
    )
    _write_private_log(
        context.process_root / f"{host}-pod-offline.log",
        redact_dependency_failure_text(
            replay.stdout + replay.stderr + replay.second_stdout + replay.second_stderr
        ),
    )
    return target


from quwoquan_ops.cli.commands.app_dependency_sync_trust import (
    validated_runtime_trust_root as _validated_runtime_trust_root,
)


def _build_android_component(
    *,
    context: BuildContext,
    projection_root: Path,
    pub_replays: Mapping[str, Path],
    pub_digests: Mapping[str, str],
    trust_root: Path,
    trust_sensitive_values: tuple[str, ...] = (),
) -> Path:
    for name, host in (
        ("productionPub", projection_root / "quwoquan_app"),
        ("patrolPub", projection_root / PATROL_HOST_RELATIVE),
    ):
        read_regular_nofollow(
            host / ".dart_tool/package_config.json",
            label=f"{name} replay package config",
        )
        assert_real_directory(pub_replays[name], label=f"{name} replay cache")
    environment = private_environment(
        home=context.work_root / "android-user-home",
        pub_cache=None,
        hosted_url=None,
    )
    environment.update(
        {
            "QWQ_APP_BUILD_PROFILE": "nonprod",
            "QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT": str(trust_root),
        }
    )
    invocations = canonical_android_uat_gradle_invocations(projection_root)
    gradle_roots = [item.gradle_root for item in invocations]
    flutter = str(context.flutter_identity.get("executable") or "")
    if not flutter:
        raise ValueError("APP.DEPENDENCY.flutter_executable_missing")
    context.progress.begin("gradle-wrapper-materialization")
    materialize_flutter_gradle_wrappers(
        project_root=projection_root,
        gradle_roots=gradle_roots,
        flutter_executable=flutter,
    )
    context.progress.begin("gradle-online-resolution")
    try:
        result = synchronize_android_gradle_dependencies(
            project_root=projection_root,
            online_home=context.work_root / "android/online-home",
            sealed_tree=context.work_root / "android/sealed-tree",
            replay_tree=context.work_root / "android/replay-tree",
            gradle_roots=gradle_roots,
            invocations=invocations,
            environment=environment,
        )
    except subprocess.CalledProcessError as exc:
        output = redact_dependency_failure_text(
            exc.stdout or exc.output or "",
            sensitive_values=trust_sensitive_values or (str(trust_root),),
        )
        _write_private_log(
            context.process_root / "android-gradle-failed.log",
            output,
        )
        tail = "\n".join(output.splitlines()[-20:])
        raise ValueError(
            "APP.DEPENDENCY.android_sync_failed: "
            f"cause={dependency_failure_cause(exc)}" + (f"\n{tail}" if tail else "")
        ) from exc
    context.progress.begin("gradle-offline-replay")
    for phase, results in (
        ("online", result.online_results),
        ("offline", result.offline_results),
    ):
        for index, completed in enumerate(results):
            _write_private_log(
                context.process_root / f"android-{phase}-{index}.log",
                redact_dependency_failure_text(
                    completed.stdout or "",
                    sensitive_values=trust_sensitive_values or (str(trust_root),),
                ),
            )
    original_invocations = canonical_android_uat_gradle_invocations(context.repo_root)
    return write_android_gradle_component(
        project_root=context.repo_root,
        snapshot=result.snapshot,
        invocations=original_invocations,
        upstream_dependency_digests=pub_digests,
        destination=context.generation_root / "androidGradle",
    )


def _verify_components(
    *,
    context: BuildContext,
    projection_root: Path,
    roots: Mapping[str, Path],
    pod: str,
    pub_digests: Mapping[str, str],
) -> None:
    expected_flutter = _expected_flutter(context)
    load_pub_cache_snapshot_at(
        repo_root=projection_root,
        snapshot_root=roots["productionPub"],
        expected_flutter=expected_flutter,
    )
    load_patrol_pub_cache_snapshot_at(
        repo_root=projection_root,
        snapshot_root=roots["patrolPub"],
        expected_flutter=expected_flutter,
    )
    for name, host in (
        ("productionIosPods", IOS_POD_PRODUCTION_HOST),
        ("patrolIosPods", IOS_POD_PATROL_HOST),
    ):
        ios_root = projection_root / IOS_PODFILE_RELATIVES[host].parent
        load_verified_ios_pod_capsule(
            snapshot_root=roots[name],
            expected_podfile_lock=ios_root / "Podfile.lock",
            pod_executable=pod,
            resolution_inputs=ios_pod_resolution_inputs(
                repo_root=projection_root, dependency_host=host
            ),
            upstream_dependency_digest=pub_digests[
                "productionPub" if host == IOS_POD_PRODUCTION_HOST else "patrolPub"
            ],
            dependency_host=host,
        )
    load_android_gradle_component(
        project_root=context.repo_root,
        component_root=roots["androidGradle"],
        invocations=canonical_android_uat_gradle_invocations(context.repo_root),
        upstream_dependency_digests=pub_digests,
    )


def build_dependency_components(
    context: BuildContext, *, trust_root: Path
) -> Mapping[str, Path]:
    """Network-resolve, offline-replay, seal and reread all five components."""

    validated_trust_root, trust_sensitive_values = _validated_runtime_trust_root(
        trust_root, repo_root=context.repo_root
    )
    context.progress.begin("toolchain-resolution")
    pod = resolve_cocoapods_executable(
        str(os.environ.get("QWQ_COCOAPODS_EXECUTABLE") or "")
    )
    context.progress.begin("live-source-seal")
    sealed_sources = resolution_seal(context.repo_root)
    projection_root = context.work_root / "source-projection"
    context.progress.begin("source-projection")
    project(context.repo_root, projection_root)
    _assert_resolution_seal(projection_root=projection_root, expected=sealed_sources)
    context.progress.begin("pub-resolution-replay")
    roots, pub_replays, pub_digests = _build_pub_components(
        context=context, projection_root=projection_root
    )
    context.progress.begin("ios-resolution-replay")
    for name, host in (
        ("productionIosPods", IOS_POD_PRODUCTION_HOST),
        ("patrolIosPods", IOS_POD_PATROL_HOST),
    ):
        pub_name = "productionPub" if host == IOS_POD_PRODUCTION_HOST else "patrolPub"
        roots[name] = _build_ios_component(
            context=context,
            projection_root=projection_root,
            pod=pod,
            host=host,
            pub_cache=pub_replays[pub_name],
            upstream_digest=pub_digests[pub_name],
        )
    context.progress.begin("android-resolution-replay")
    roots["androidGradle"] = _build_android_component(
        context=context,
        projection_root=projection_root,
        pub_replays=pub_replays,
        pub_digests=pub_digests,
        trust_root=validated_trust_root,
        trust_sensitive_values=trust_sensitive_values,
    )
    context.progress.begin("source-projection-readback")
    _assert_resolution_seal(projection_root=projection_root, expected=sealed_sources)
    context.progress.begin("component-readback")
    _verify_components(
        context=context,
        projection_root=projection_root,
        roots=roots,
        pod=pod,
        pub_digests=pub_digests,
    )
    return roots
