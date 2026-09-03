"""Synchronize, seal and replay Android Gradle dependencies privately."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

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
    assert_real_directory,
    read_regular_nofollow,
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
_FLUTTER_WRAPPER_CACHE_RELATIVE = Path("bin/cache/artifacts/gradle_wrapper")
_FLUTTER_WRAPPER_STAMP_RELATIVE = Path("bin/cache/gradle_wrapper.stamp")
_FLUTTER_WRAPPER_VERSION_RELATIVE = Path("bin/internal/gradle_wrapper.version")
_FLUTTER_SDK_IDENTITY_RELATIVE = Path("bin/cache/flutter.version.json")
_FLUTTER_WRAPPER_VERSION = re.compile(
    r"flutter_infra_release/gradle-wrapper/[0-9a-f]{40}/gradle-wrapper\.tgz\Z"
)
_FLUTTER_IDENTITY_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FLUTTER_WRAPPER_ARTIFACT_FILES = (
    "gradlew",
    "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar",
)


@dataclass(frozen=True, slots=True)
class GradleInvocation:
    gradle_root: Path
    tasks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AndroidGradleSyncResult:
    snapshot: AndroidGradleSnapshot
    online_results: tuple[subprocess.CompletedProcess[str], ...]
    offline_results: tuple[subprocess.CompletedProcess[str], ...]


def _flutter_sdk_root(flutter_executable: Path) -> Path:
    executable = flutter_executable.expanduser().absolute()
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            "Android Gradle wrapper Flutter executable is unavailable"
        ) from exc
    if resolved != executable:
        raise ValueError("Android Gradle wrapper Flutter executable is linked")
    if resolved.name != "flutter" or resolved.parent.name != "bin":
        raise ValueError("Android Gradle wrapper Flutter executable layout is invalid")
    root = resolved.parent.parent
    try:
        _content, mode = read_regular_nofollow(
            resolved, label="Flutter SDK executable"
        )
        assert_real_directory(root, label="Flutter SDK root")
    except (RuntimeError, ValueError) as exc:
        raise ValueError("Android Gradle wrapper Flutter SDK root is unsafe") from exc
    if not mode & 0o111:
        raise ValueError("Android Gradle wrapper Flutter executable is not executable")
    return root


def _flutter_wrapper_artifact(
    flutter_root: Path,
    *,
    expected_flutter_identity: Mapping[str, str],
) -> dict[str, tuple[bytes, int]]:
    try:
        sdk_identity, _identity_mode = read_regular_nofollow(
            flutter_root / _FLUTTER_SDK_IDENTITY_RELATIVE,
            label="Flutter SDK identity metadata",
        )
        version, _version_mode = read_regular_nofollow(
            flutter_root / _FLUTTER_WRAPPER_VERSION_RELATIVE,
            label="Flutter Gradle wrapper artifact version",
        )
        stamp, _stamp_mode = read_regular_nofollow(
            flutter_root / _FLUTTER_WRAPPER_STAMP_RELATIVE,
            label="Flutter Gradle wrapper artifact stamp",
        )
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Android Gradle wrapper official Flutter artifact is unavailable"
        ) from exc
    try:
        payload = json.loads(sdk_identity.decode("utf-8", errors="strict"))
        version_value = version.decode("utf-8", errors="strict").strip()
        stamp_value = stamp.decode("utf-8", errors="strict").strip()
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Android Gradle wrapper official Flutter artifact metadata is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "Android Gradle wrapper official Flutter artifact metadata is invalid"
        )
    actual_identity = {
        key: str(payload.get(key) or "").strip()
        for key in (
            "frameworkVersion",
            "frameworkRevision",
            "engineRevision",
            "dartSdkVersion",
            "channel",
        )
    }
    expected_version = str(
        expected_flutter_identity.get("flutterVersion")
        or expected_flutter_identity.get("frameworkVersion")
        or ""
    ).strip()
    expected_digest = str(
        expected_flutter_identity.get("commandResolutionDigest")
        or expected_flutter_identity.get("flutterCommandResolutionDigest")
        or ""
    ).strip()
    actual_digest = digest_bytes(canonical_bytes(actual_identity))
    if (
        not expected_version
        or _FLUTTER_IDENTITY_DIGEST.fullmatch(expected_digest) is None
        or actual_identity["frameworkVersion"] != expected_version
        or actual_digest != expected_digest
    ):
        raise ValueError(
            "Android Gradle wrapper current pinned Flutter SDK identity drifted"
        )
    if (
        _FLUTTER_WRAPPER_VERSION.fullmatch(version_value) is None
        or stamp_value != version_value
    ):
        raise ValueError(
            "Android Gradle wrapper official Flutter artifact identity is unsealed"
        )

    source_root = flutter_root / _FLUTTER_WRAPPER_CACHE_RELATIVE
    try:
        assert_real_directory(source_root, label="Flutter Gradle wrapper artifact root")
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Android Gradle wrapper official Flutter artifact is unavailable"
        ) from exc
    artifact: dict[str, tuple[bytes, int]] = {}
    for relative in _FLUTTER_WRAPPER_ARTIFACT_FILES:
        try:
            content, mode = read_regular_nofollow(
                source_root / relative,
                label=f"Flutter Gradle wrapper artifact {relative}",
            )
        except (RuntimeError, ValueError) as exc:
            raise ValueError(
                "Android Gradle wrapper official Flutter artifact is unavailable"
            ) from exc
        if relative == "gradlew" and not mode & 0o111:
            raise ValueError(
                "Android Gradle wrapper official Flutter script is not executable"
            )
        artifact[relative] = content, mode
    return artifact


def materialize_flutter_gradle_wrappers(
    *,
    project_root: Path,
    gradle_roots: Sequence[Path],
    flutter_executable: Path,
    expected_flutter_identity: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """Inject only the pinned Flutter SDK's sealed artifact into fresh hosts."""

    repository = project_root.expanduser().absolute()
    try:
        if repository.resolve(strict=True) != repository:
            raise ValueError("linked project root")
        assert_real_directory(repository, label="Android Gradle wrapper project root")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("Android Gradle wrapper project root is unsafe") from exc
    flutter_root = _flutter_sdk_root(flutter_executable)
    artifact = _flutter_wrapper_artifact(
        flutter_root,
        expected_flutter_identity=expected_flutter_identity,
    )
    roots: list[Path] = []
    targets: list[tuple[str, str]] = []
    seen_roots: set[Path] = set()
    for gradle_root in gradle_roots:
        root = gradle_root.expanduser().absolute()
        if not root.is_relative_to(repository):
            raise ValueError("Android Gradle wrapper root escapes the project")
        try:
            if root.resolve(strict=True) != root:
                raise ValueError("linked Gradle root")
            assert_real_directory(root, label="Android Gradle wrapper host root")
            read_regular_nofollow(
                root / "gradle/wrapper/gradle-wrapper.properties",
                label="Android Gradle wrapper properties",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Android Gradle wrapper host root is unsafe") from exc
        if root in seen_roots:
            raise ValueError("Android Gradle wrapper host root is duplicated")
        seen_roots.add(root)
        relative_root = root.relative_to(repository).as_posix()
        roots.append(root)
        for artifact_relative in artifact:
            target = root / artifact_relative
            try:
                target.lstat()
            except FileNotFoundError:
                pass
            else:
                raise ValueError(
                    f"Android Gradle wrapper bootstrap target is not fresh: "
                    f"{relative_root}/{artifact_relative}"
                )
            targets.append(
                (artifact_relative, f"{relative_root}/{artifact_relative}")
            )

    for artifact_relative, target_relative in targets:
        content, mode = artifact[artifact_relative]
        write_fresh_relative_file(
            root=repository, relative=target_relative, content=content, mode=mode
        )
    if _flutter_wrapper_artifact(
        flutter_root,
        expected_flutter_identity=expected_flutter_identity,
    ) != artifact:
        raise ValueError("Android Gradle wrapper official Flutter artifact drifted")
    for root in roots:
        for artifact_relative, expected in artifact.items():
            actual = read_regular_nofollow(
                root / artifact_relative,
                label=f"injected Android Gradle wrapper {artifact_relative}",
            )
            if actual != expected:
                raise ValueError("Android Gradle wrapper injected artifact drifted")
    return tuple(
        wrapper_identity(project_root=repository, gradle_root=root) for root in roots
    )


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
