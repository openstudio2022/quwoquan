"""Synchronize, seal and replay Android Gradle dependencies privately."""

from __future__ import annotations

import os
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .android_gradle_capsule import (
    _WRAPPER_FILES,
    AndroidGradleFile,
    AndroidGradleSnapshot,
    _artifact_records,
    _read_regular_nofollow,
    _scan_tree,
    build_android_gradle_snapshot,
    canonical_bytes,
    digest_bytes,
    wrapper_identity,
)
from .dependency_fs import (
    _directory_fd,
    assert_real_directory,
    write_fresh_relative_file,
)
from .dependency_network_command import (
    retry_event,
    run_managed_subprocess,
    transient_network_cause,
)

_CONTROL_PROPERTIES = b"org.gradle.daemon=false\norg.gradle.caching=false\n"
_OFFLINE_INIT = b"""// Canonical App dependency projection: network resolution is forbidden.
gradle.startParameter.offline = true
gradle.startParameter.buildCacheEnabled = false
"""

_GRADLE_NETWORK_MAX_ATTEMPTS = 3
_GRADLE_NETWORK_BACKOFF_SECONDS = (1.0, 2.0)
_GRADLE_PROCESS_TIMEOUT_SECONDS = 20 * 60
_GRADLE_INVOCATION_DEADLINE_SECONDS = 45 * 60

_FLUTTER_GRADLE_WRAPPER_ARTIFACTS = (
    "gradlew",
    "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar",
)


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _exact_regular_file(path: Path, *, label: str) -> tuple[bytes, int]:
    """Read one stable real file and retain its exact permission bits."""

    absolute = _lexical_absolute(path)
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor = _directory_fd(absolute.parent, label=f"{label} parent")
        descriptor = os.open(
            absolute.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(
                f"Android Gradle {label} is not a single-link regular file"
            )
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Android Gradle {label} is unavailable or unsafe") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if identity(before) != identity(after):
        raise ValueError(f"Android Gradle {label} changed during read")
    return bytes(content), stat.S_IMODE(before.st_mode)


def _present_nofollow(path: Path, *, label: str) -> bool:
    absolute = _lexical_absolute(path)
    parent_descriptor = -1
    try:
        parent_descriptor = _directory_fd(absolute.parent, label=f"{label} parent")
        os.stat(absolute.name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Android Gradle {label} cannot be inspected safely") from exc
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
    return True


def materialize_flutter_gradle_wrappers(
    *,
    project_root: Path,
    gradle_roots: Sequence[Path],
    flutter_executable: str | Path,
) -> tuple[dict[str, Any], ...]:
    """Fill Flutter's ignored wrapper tools into one private source projection."""

    repository = _lexical_absolute(project_root)
    try:
        assert_real_directory(repository, label="wrapper projection root")
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Android Gradle wrapper projection root is unavailable or linked"
        ) from exc

    declared_flutter = Path(flutter_executable).expanduser()
    if not declared_flutter.is_absolute():
        raise ValueError("Android Gradle Flutter executable must be absolute")
    try:
        physical_flutter = declared_flutter.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Android Gradle Flutter executable is unavailable") from exc
    _flutter_bytes, flutter_mode = _exact_regular_file(
        physical_flutter, label="Flutter executable"
    )
    if (
        physical_flutter.name != "flutter"
        or physical_flutter.parent.name != "bin"
        or not flutter_mode & 0o111
    ):
        raise ValueError(
            "Android Gradle Flutter executable is not a canonical executable"
        )

    flutter_root = physical_flutter.parent.parent
    artifact_root = flutter_root / "bin/cache/artifacts/gradle_wrapper"
    try:
        assert_real_directory(flutter_root, label="Flutter SDK root")
        assert_real_directory(
            artifact_root, label="Flutter Gradle wrapper artifact root"
        )
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Android Gradle Flutter SDK wrapper artifact root is unavailable or linked"
        ) from exc

    sdk_artifacts = {
        relative: _exact_regular_file(
            artifact_root / relative,
            label=f"Flutter SDK wrapper artifact {relative}",
        )
        for relative in _FLUTTER_GRADLE_WRAPPER_ARTIFACTS
    }
    if not sdk_artifacts["gradlew"][1] & 0o111:
        raise ValueError("Android Gradle Flutter SDK wrapper script is not executable")

    plans: list[tuple[Path, tuple[bytes, int], tuple[str, ...]]] = []
    seen_roots: set[str] = set()
    for gradle_root in gradle_roots:
        target_root = _lexical_absolute(gradle_root)
        if not target_root.is_relative_to(repository):
            raise ValueError("Android Gradle wrapper root escapes the private project")
        relative_root = target_root.relative_to(repository).as_posix()
        if not relative_root or relative_root in seen_roots:
            raise ValueError("Android Gradle wrapper roots are empty or duplicated")
        seen_roots.add(relative_root)
        try:
            assert_real_directory(target_root, label=f"wrapper root {relative_root}")
        except (RuntimeError, ValueError) as exc:
            raise ValueError(
                f"Android Gradle wrapper root is unavailable or linked: {relative_root}"
            ) from exc

        properties = _exact_regular_file(
            target_root / "gradle/wrapper/gradle-wrapper.properties",
            label=f"wrapper properties {relative_root}",
        )
        missing: list[str] = []
        for relative, sdk_identity in sdk_artifacts.items():
            destination = target_root / relative
            if not _present_nofollow(
                destination,
                label=f"projected wrapper artifact {relative_root}/{relative}",
            ):
                missing.append(relative)
                continue
            target_identity = _exact_regular_file(
                destination,
                label=f"projected wrapper artifact {relative_root}/{relative}",
            )
            if target_identity != sdk_identity:
                raise ValueError(
                    "Android Gradle projected wrapper artifact differs from Flutter SDK: "
                    f"{relative_root}/{relative}"
                )
        plans.append((target_root, properties, tuple(missing)))

    if not plans:
        raise ValueError("Android Gradle wrapper roots are empty or duplicated")

    for target_root, _properties, missing in plans:
        for relative in missing:
            content, mode = sdk_artifacts[relative]
            write_fresh_relative_file(
                root=target_root,
                relative=relative,
                content=content,
                mode=mode,
            )

    identities: list[dict[str, Any]] = []
    for target_root, original_properties, _missing in plans:
        relative_root = target_root.relative_to(repository).as_posix()
        current_properties = _exact_regular_file(
            target_root / "gradle/wrapper/gradle-wrapper.properties",
            label=f"wrapper properties {relative_root}",
        )
        if current_properties != original_properties:
            raise ValueError(
                "Android Gradle wrapper properties changed during materialization: "
                f"{relative_root}"
            )
        for relative, sdk_identity in sdk_artifacts.items():
            if (
                _exact_regular_file(
                    target_root / relative,
                    label=f"materialized wrapper artifact {relative_root}/{relative}",
                )
                != sdk_identity
            ):
                raise ValueError(
                    "Android Gradle materialized wrapper artifact identity drifted: "
                    f"{relative_root}/{relative}"
                )
        identities.append(
            wrapper_identity(project_root=repository, gradle_root=target_root)
        )
    return tuple(identities)


@dataclass(frozen=True, slots=True)
class GradleInvocation:
    gradle_root: Path
    tasks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AndroidGradleSyncResult:
    snapshot: AndroidGradleSnapshot
    online_results: tuple[subprocess.CompletedProcess[str], ...]
    offline_results: tuple[subprocess.CompletedProcess[str], ...]


def canonical_android_uat_gradle_invocations(
    project_root: Path,
) -> tuple[GradleInvocation, GradleInvocation]:
    """Return both real APK and instrumentation builds used by canonical UAT."""

    repository = project_root.expanduser().absolute()
    return (
        GradleInvocation(
            gradle_root=repository / "quwoquan_app/android",
            tasks=(
                ":app:assembleNonprodDebug",
                ":app:assembleNonprodDebugAndroidTest",
            ),
        ),
        GradleInvocation(
            gradle_root=repository / "quwoquan_app/test_host/patrol/android",
            tasks=(":app:assembleDebug", ":app:assembleDebugAndroidTest"),
        ),
    )


def _fresh_directory(path: Path, *, label: str) -> Path:
    target = path.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ValueError(f"Android Gradle {label} must be fresh")
    target.mkdir(parents=True, mode=0o700)
    return target


def _copy_regular(source: Path, destination: Path, *, writable: bool) -> None:
    content, mode = _read_regular_nofollow(source, label=f"sync file {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Android Gradle dependency copy made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    destination.chmod((0o755 if mode & 0o111 else 0o644) if writable else mode)


def _write_generated(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Android Gradle metadata write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o444)


def _copy_dependency_subtree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"Android Gradle dependency source is missing: {source}")
    for path in sorted(source.rglob("*")):
        node = path.lstat()
        relative = path.relative_to(source)
        target = destination / relative
        if stat.S_ISDIR(node.st_mode) and not path.is_symlink():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            continue
        if path.name.endswith((".lock", ".lck", ".part", ".tmp")):
            continue
        if not stat.S_ISREG(node.st_mode) or path.is_symlink() or node.st_nlink != 1:
            raise ValueError(
                "Android Gradle sync cache contains a symlink, hardlink or special node"
            )
        _copy_regular(path, target, writable=False)


def _copy_wrapper_inputs(
    *,
    project_root: Path,
    gradle_roots: Sequence[Path],
    destination: Path,
) -> None:
    repository = project_root.expanduser().absolute()
    for gradle_root in gradle_roots:
        root = gradle_root.expanduser().absolute()
        if not root.is_relative_to(repository):
            raise ValueError("Android Gradle wrapper root escapes the project")
        relative_root = root.relative_to(repository)
        for relative_file in _WRAPPER_FILES:
            _copy_regular(
                root / relative_file,
                destination / relative_root / relative_file,
                writable=False,
            )


def _write_closure_metadata(tree_root: Path) -> None:
    files = _scan_tree_without_required_metadata(tree_root)
    artifacts = _artifact_records(files)
    components = sorted({item["coordinate"] for item in artifacts})
    verification = [
        {
            "coordinate": item["coordinate"],
            "file": item["file"],
            "sha256": item["sha256"],
            "size": item["size"],
        }
        for item in artifacts
    ]
    _write_generated(
        tree_root / "metadata/resolution-lock.json",
        canonical_bytes(
            {
                "schema": "stackctl-android-gradle-resolution-lock.v1",
                "components": components,
            }
        ),
    )
    _write_generated(
        tree_root / "metadata/verification-metadata.json",
        canonical_bytes(
            {
                "schema": "stackctl-android-gradle-verification-metadata.v1",
                "artifacts": verification,
            }
        ),
    )


def _scan_tree_without_required_metadata(
    tree_root: Path,
) -> tuple[AndroidGradleFile, ...]:
    scratch = tree_root / "metadata"
    scratch.mkdir(parents=True, exist_ok=True)
    placeholders = (
        scratch / "resolution-lock.json",
        scratch / "verification-metadata.json",
    )
    for path, schema in zip(
        placeholders,
        (
            "stackctl-android-gradle-resolution-lock.v1",
            "stackctl-android-gradle-verification-metadata.v1",
        ),
        strict=True,
    ):
        _write_generated(path, canonical_bytes({"schema": schema}))
    try:
        return _scan_tree(tree_root)
    finally:
        for path in placeholders:
            path.unlink(missing_ok=True)


def _assert_wrapper_archives(
    *,
    project_root: Path,
    tree_root: Path,
    gradle_roots: Sequence[Path],
) -> None:
    for gradle_root in gradle_roots:
        identity = wrapper_identity(
            project_root=project_root,
            gradle_root=gradle_root,
        )
        archive_name = identity["distributionUrl"].rsplit("/", 1)[-1]
        matches = list((tree_root / "home/wrapper/dists").glob(f"*/*/{archive_name}"))
        if len(matches) != 1:
            raise ValueError(
                f"Android Gradle wrapper archive is missing or duplicated: {archive_name}"
            )
        content, _mode = _read_regular_nofollow(
            matches[0],
            label=f"wrapper archive {archive_name}",
        )
        if digest_bytes(content) != f"sha256:{identity['distributionSha256']}":
            raise ValueError(
                f"Android Gradle wrapper archive digest drifted: {archive_name}"
            )


def seal_android_gradle_home(
    *,
    project_root: Path,
    gradle_user_home: Path,
    destination: Path,
    gradle_roots: Sequence[Path],
) -> AndroidGradleSnapshot:
    """Extract only dependency-bearing bytes from one fresh private home."""

    source = gradle_user_home.expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Android Gradle sync home is not a real directory")
    target = _fresh_directory(destination, label="sealed destination")
    _copy_wrapper_inputs(
        project_root=project_root,
        gradle_roots=gradle_roots,
        destination=target / "wrappers",
    )
    _copy_dependency_subtree(
        source / "wrapper/dists",
        target / "home/wrapper/dists",
    )
    _copy_dependency_subtree(
        source / "caches/modules-2",
        target / "home/caches/modules-2",
    )
    _write_generated(target / "home/gradle.properties", _CONTROL_PROPERTIES)
    _write_generated(target / "home/init.d/qwq-offline.gradle", _OFFLINE_INIT)
    _write_closure_metadata(target)
    _assert_wrapper_archives(
        project_root=project_root,
        tree_root=target,
        gradle_roots=gradle_roots,
    )
    snapshot = build_android_gradle_snapshot(
        project_root=project_root,
        tree_root=target,
        gradle_roots=gradle_roots,
    )
    for directory in sorted(
        (item for item in target.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    target.chmod(0o555)
    return snapshot


def copy_android_gradle_snapshot(
    snapshot: AndroidGradleSnapshot,
    destination: Path,
    *,
    project_root: Path,
    gradle_roots: Sequence[Path],
) -> Path:
    target = _fresh_directory(destination, label="projection home")
    for item in snapshot.files:
        _copy_regular(item.source, target / item.relative, writable=True)
    rebuilt = build_android_gradle_snapshot(
        project_root=project_root,
        tree_root=target,
        gradle_roots=gradle_roots,
    )
    if rebuilt.manifest != snapshot.manifest:
        raise ValueError("Android Gradle projected dependency CAS drifted")
    return target / "home"


def write_android_gradle_capsule(
    snapshot: AndroidGradleSnapshot,
    *,
    destination_tree: Path,
    manifest_path: Path,
    project_root: Path,
    gradle_roots: Sequence[Path],
) -> None:
    """Write one immutable package-input tree and prove its complete CAS."""

    target = _fresh_directory(destination_tree, label="capsule tree")
    manifest_target = manifest_path.expanduser().absolute()
    if manifest_target.exists() or manifest_target.is_symlink():
        raise ValueError("Android Gradle capsule manifest destination must be fresh")
    for item in snapshot.files:
        _copy_regular(item.source, target / item.relative, writable=False)
    _write_generated(manifest_target, snapshot.encoded_manifest)
    rebuilt = build_android_gradle_snapshot(
        project_root=project_root,
        tree_root=target,
        gradle_roots=gradle_roots,
    )
    encoded, _mode = _read_regular_nofollow(
        manifest_target,
        label="written capsule manifest",
    )
    if rebuilt.manifest != snapshot.manifest or encoded != snapshot.encoded_manifest:
        raise ValueError("Android Gradle written capsule CAS drifted")
    for directory in sorted(
        (item for item in target.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    target.chmod(0o555)


def _failure_output(error: subprocess.CalledProcessError) -> str:
    output = error.output
    if output is None:
        output = error.stderr
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output or "")


def _bounded_timeout_failure(
    error: subprocess.TimeoutExpired,
    *,
    command: Sequence[str],
) -> subprocess.CalledProcessError:
    output = error.output
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    detail = str(output or "")
    if detail and not detail.endswith("\n"):
        detail += "\n"
    detail += "Android Gradle process exceeded its bounded timeout.\n"
    return subprocess.CalledProcessError(
        returncode=124,
        cmd=list(command),
        output=detail,
    )


def _run_gradle_invocation(
    *,
    command: list[str],
    root: Path,
    environment: Mapping[str, str],
    offline: bool,
) -> subprocess.CompletedProcess[str]:
    attempts = 1 if offline else _GRADLE_NETWORK_MAX_ATTEMPTS
    started_at = time.monotonic()
    first_failure: subprocess.CalledProcessError | None = None
    events: list[str] = []
    for attempt_index in range(attempts):
        remaining = _GRADLE_INVOCATION_DEADLINE_SECONDS - (
            time.monotonic() - started_at
        )
        if remaining <= 0:
            if first_failure is not None:
                raise first_failure
            raise subprocess.CalledProcessError(
                returncode=124,
                cmd=command,
                output="Android Gradle invocation exceeded its wall-clock deadline.\n",
            )
        process_timeout = min(_GRADLE_PROCESS_TIMEOUT_SECONDS, remaining)
        try:
            completed = run_managed_subprocess(
                command,
                cwd=root,
                env=environment,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=process_timeout,
            )
        except subprocess.TimeoutExpired as error:
            failure = _bounded_timeout_failure(error, command=command)
            cause = "process_timeout"
        except subprocess.CalledProcessError as error:
            failure = error
            cause = transient_network_cause(_failure_output(failure))
        else:
            if not events:
                return completed
            output = "\n".join(
                [
                    *events,
                    retry_event(attempt=attempt_index + 1, result="success"),
                ]
            )
            return subprocess.CompletedProcess(
                completed.args,
                completed.returncode,
                stdout=output,
                stderr=completed.stderr,
            )
        if first_failure is None:
            first_failure = failure
        if offline:
            raise failure
        if cause is None:
            raise failure
        if attempt_index + 1 >= attempts:
            break
        remaining = _GRADLE_INVOCATION_DEADLINE_SECONDS - (
            time.monotonic() - started_at
        )
        if remaining <= 0:
            raise first_failure
        delay = min(_GRADLE_NETWORK_BACKOFF_SECONDS[attempt_index], remaining)
        events.append(
            retry_event(
                attempt=attempt_index + 1,
                result="transient_failure",
                cause=cause,
                backoff=delay,
            )
        )
        time.sleep(delay)
    if first_failure is None:  # pragma: no cover - the loop always runs at least once
        raise RuntimeError("Android Gradle invocation did not run")
    raise first_failure


def run_gradle_invocations(
    *,
    project_root: Path,
    gradle_user_home: Path,
    invocations: Sequence[GradleInvocation],
    offline: bool,
    environment: Mapping[str, str] | None = None,
) -> list[subprocess.CompletedProcess[str]]:
    """Run the exact build tasks with a private home; replay requires offline."""

    if not invocations:
        raise ValueError("Android Gradle invocation set is empty")
    home = gradle_user_home.expanduser().absolute()
    repository = project_root.expanduser().absolute()
    if home == Path.home() / ".gradle":
        raise ValueError("Android Gradle global cache fallback is forbidden")
    env = dict(os.environ if environment is None else environment)
    env["GRADLE_USER_HOME"] = str(home)
    env.pop("GRADLE_HOME", None)
    results: list[subprocess.CompletedProcess[str]] = []
    for invocation in invocations:
        root = invocation.gradle_root.expanduser().absolute()
        if not root.is_relative_to(repository) or not invocation.tasks:
            raise ValueError("Android Gradle invocation escapes project or has no task")
        wrapper_identity(project_root=repository, gradle_root=root)
        command = [str(root / "gradlew"), "--no-daemon", "--stacktrace"]
        if offline:
            command.append("--offline")
        command.extend(invocation.tasks)
        results.append(
            _run_gradle_invocation(
                command=command,
                root=root,
                environment=env,
                offline=offline,
            )
        )
    return results


def synchronize_android_gradle_dependencies(
    *,
    project_root: Path,
    online_home: Path,
    sealed_tree: Path,
    replay_tree: Path,
    gradle_roots: Sequence[Path],
    invocations: Sequence[GradleInvocation],
    environment: Mapping[str, str] | None = None,
) -> AndroidGradleSyncResult:
    """Network sync once, seal it, then replay the same closure offline."""

    network_home = _fresh_directory(online_home, label="online sync home")
    online = run_gradle_invocations(
        project_root=project_root,
        gradle_user_home=network_home,
        invocations=invocations,
        offline=False,
        environment=environment,
    )
    snapshot = seal_android_gradle_home(
        project_root=project_root,
        gradle_user_home=network_home,
        destination=sealed_tree,
        gradle_roots=gradle_roots,
    )
    replay_home = copy_android_gradle_snapshot(
        snapshot,
        replay_tree,
        project_root=project_root,
        gradle_roots=gradle_roots,
    )
    offline = run_gradle_invocations(
        project_root=project_root,
        gradle_user_home=replay_home,
        invocations=invocations,
        offline=True,
        environment=environment,
    )
    return AndroidGradleSyncResult(
        snapshot=snapshot,
        online_results=tuple(online),
        offline_results=tuple(offline),
    )
