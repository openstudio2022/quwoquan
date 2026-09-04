"""Explicit network sync for the immutable App hosted-Pub dependency capsule."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)
from quwoquan_app.scripts.device.build_launcher_handoff import (
    materialize_runtime_config_trust_envelope,
)
from quwoquan_ops.cli.commands import app_dependency_sync_builder as _builder
from quwoquan_ops.cli.lib.app_dependency_sync_process_result import (
    PROCESS_RESULT_SCHEMA as _PROCESS_RESULT_SCHEMA,
    atomic_process_result as _atomic_process_result,
    process_result_payload as _process_result_payload,
)
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.lib.host_locks import (
    HostLockBusyError,
    acquire_host_lock_bounded,
    app_dependency_sync_lock_path,
)
from quwoquan_ops.cli.lib.patrol_execution_lock import patrol_execution_lock_path
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
    load_launch_manifest_contract,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import decode_keyring
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_component import (
    ANDROID_GRADLE_SYNC_SCHEMA,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA,
    APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA,
    APP_DEPENDENCY_COMPONENTS,
    component_declaration,
    managed_dependency_bundle_root,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_publish import (
    publish_dependency_bundle_activation,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
    remove_private_tree,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_capsule import (
    IOS_POD_CAPSULE_SCHEMA,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_inputs import (
    IOS_NATIVE_DEPENDENCY_MODE,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from quwoquan_ops.cli.lib.package_reuse.native_dependency_inputs import (
    native_resolution_input_identity,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_cache import (
    PATROL_PUB_SYNC_MANIFEST_SCHEMA,
    patrol_resolution_input_identity,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import (
    PUB_CACHE_SYNC_MANIFEST_SCHEMA,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_store import (
    resolution_input_identity,
)

_LOCK_TIMEOUT_SECONDS = 10 * 60
_LOCK_PROGRESS_INTERVAL_SECONDS = 30
_LOCK_OWNER_WORKTREE = Path(__file__).resolve().parents[3]
_SOURCE_IDENTITY_FIELDS = {
    "flutterVersion",
    "flutterCommandResolutionDigest",
    "productionPubResolutionInputDigest",
    "patrolPubResolutionInputDigest",
    "nativeResolutionInputDigest",
}


class _ActivePointerCommitState(Enum):
    """Fresh active-pointer readback after an attempted commit."""

    SELECTS_ATTEMPT = "selects_attempt"
    SELECTS_OTHER = "selects_other"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class _PublicationProgress:
    """In-process phase evidence retained when a publisher raises."""

    active_write_started: bool = False


@dataclass(slots=True)
class DependencyBuildProgress:
    """Process-only phase marker; never participates in publication identity."""

    current_phase: str = "component-build"
    on_begin: Callable[[str], None] | None = None

    def begin(self, phase: str) -> None:
        if not phase or not all(character.islower() or character.isdigit() or character == "-" for character in phase):
            raise ValueError("APP.DEPENDENCY.process_phase_invalid")
        self.current_phase = phase
        if self.on_begin is not None:
            self.on_begin(phase)


@dataclass(frozen=True, slots=True)
class DependencyComponentBuildContext:
    """Attempt-owned inputs exposed to an injectable five-component builder."""

    repo_root: Path
    attempt_id: str
    work_root: Path
    process_root: Path
    generation_root: Path
    flutter_identity: Mapping[str, str]
    source_identity: Mapping[str, str]
    progress: DependencyBuildProgress = field(default_factory=DependencyBuildProgress)


ComponentBuilder = Callable[[DependencyComponentBuildContext], Mapping[str, Path]]
BundlePublisher = Callable[..., tuple[dict[str, Any], dict[str, Any], Path, Path]]


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    subparsers.add_parser(
        "app-dependency-sync",
        help=(
            "explicitly fetch, replay, and atomically activate the five locked "
            "App dependency components"
        ),
    )


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int) -> None:
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("App dependency sync receipt write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        parent = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def _sync_lock(
    *, on_wait: Callable[[str, float], None] | None = None
) -> Any:
    """Serialize dependency sync and the shared Flutter build workspace."""

    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    held = []
    try:
        for path, resource in (
            (app_dependency_sync_lock_path(), "flutter-cocoapods-gradle"),
            (patrol_execution_lock_path(), "flutter-build-workspace"),
        ):
            held.append(
                acquire_host_lock_bounded(
                    path,
                    timeout_seconds=max(0.0, deadline - time.monotonic()),
                    poll_seconds=1.0,
                    fields={"resource": resource},
                    worktree_path=_LOCK_OWNER_WORKTREE,
                    on_wait=on_wait,
                )
            )
        yield tuple(held)
    except HostLockBusyError as exc:
        raise ValueError(
            "APP.DEPENDENCY.sync_lock_timeout: "
            f"timeoutSeconds={_LOCK_TIMEOUT_SECONDS}; {exc}"
        ) from exc
    finally:
        for lock in reversed(held):
            lock.close()


def _project(repo_root: Path, destination: Path) -> Path:
    return _builder.project(repo_root, destination)


def _run_pub_get(
    *,
    flutter: str,
    app_dir: Path,
    pub_cache: Path,
    hosted_url: str,
    offline: bool,
    log_path: Path,
    private_home: Path | None = None,
) -> None:
    _builder.run_pub_get(
        flutter=flutter,
        app_dir=app_dir,
        pub_cache=pub_cache,
        hosted_url=hosted_url,
        offline=offline,
        log_path=log_path,
        private_home=private_home,
    )


def _source_identity(
    *, repo_root: Path, flutter_identity: Mapping[str, str]
) -> dict[str, str]:
    production = resolution_input_identity(repo_root)
    patrol = patrol_resolution_input_identity(repo_root)
    native = native_resolution_input_identity(repo_root)
    return {
        "flutterVersion": str(flutter_identity.get("flutterVersion") or ""),
        "flutterCommandResolutionDigest": str(
            flutter_identity.get("commandResolutionDigest")
            or flutter_identity.get("flutterCommandResolutionDigest")
            or ""
        ),
        "productionPubResolutionInputDigest": str(production["resolutionInputDigest"]),
        "patrolPubResolutionInputDigest": str(patrol["resolutionInputDigest"]),
        "nativeResolutionInputDigest": str(native["nativeResolutionInputDigest"]),
    }


def _validated_source_identity(value: Mapping[str, str]) -> dict[str, str]:
    normalized = {str(key): str(item) for key, item in value.items()}
    if (
        set(normalized) != _SOURCE_IDENTITY_FIELDS
        or not normalized["flutterVersion"]
        or any(
            not normalized[field].startswith("sha256:")
            for field in _SOURCE_IDENTITY_FIELDS - {"flutterVersion"}
        )
    ):
        raise ValueError("APP.DEPENDENCY.source_identity_incomplete")
    return normalized


def _build_dependency_components(
    context: DependencyComponentBuildContext,
    *,
    trust_root: Path,
) -> Mapping[str, Path]:
    return _builder.build_dependency_components(context, trust_root=trust_root)


@contextlib.contextmanager
def _attempt_android_runtime_trust(
    repo_root: Path, *, attempt_id: str, cleanup_warnings: list[str]
) -> Any:
    """Own one private nonprod trust envelope for the default native builder."""

    try:
        signing = prepare_local_app_runtime_config_signing(repo_root)
        keyring = decode_keyring(signing.trusted_public_keys_path.read_bytes())
        envelope = build_runtime_config_trust_envelope("nonprod", keyring)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_authority_unavailable: "
            f"cause={_builder.dependency_failure_cause(exc)}"
        ) from exc
    directory = tempfile.mkdtemp(
        prefix=f"qwq-app-dependency-runtime-trust.{attempt_id}."
    )
    root = Path(directory).resolve(strict=True)
    primary_error: BaseException | None = None
    try:
        repository = repo_root.expanduser().resolve(strict=True)
        if root == repository or root.is_relative_to(repository):
            raise ValueError(
                "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
                "attempt trust must stay outside the repository"
            )
        root.chmod(0o700)
        root_metadata = root.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
        ):
            raise ValueError(
                "APP.DEPENDENCY.android_runtime_trust_permissions_invalid: "
                "attempt root must be 0700"
            )
        trust_directory = root / "qwq_runtime"
        trust_directory.mkdir(mode=0o700)
        trust_path = trust_directory / "runtime-config-trust.json"
        try:
            materialize_runtime_config_trust_envelope(
                envelope,
                str(trust_path),
                load_launch_manifest_contract(),
            )
        except (OSError, TypeError, UnicodeError, ValueError) as exc:
            raise ValueError(
                "APP.DEPENDENCY.android_runtime_trust_materialization_failed: "
                f"cause={_builder.dependency_failure_cause(exc)}"
            ) from exc
        read_regular_nofollow(trust_path, label="attempt Android runtime trust")
        trust_metadata = trust_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(trust_metadata.st_mode)
            or trust_metadata.st_nlink != 1
            or stat.S_IMODE(trust_metadata.st_mode) != 0o600
        ):
            raise ValueError(
                "APP.DEPENDENCY.android_runtime_trust_permissions_invalid: "
                "trust envelope must be a single-link 0600 file"
            )
        yield root
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            remove_private_tree(root)
        except (OSError, ValueError) as exc:
            cause = _builder.dependency_failure_cause(exc)
            if primary_error is not None:
                cleanup_warnings.append(
                    "APP.DEPENDENCY.android_runtime_trust_cleanup_warning: "
                    f"cause={cause}"
                )
            else:
                raise ValueError(
                    "APP.DEPENDENCY.android_runtime_trust_cleanup_failed: "
                    f"cause={cause}"
                ) from exc


def _read_component_manifest(*, name: str, root: Path) -> dict[str, Any]:
    try:
        encoded, _mode = read_regular_nofollow(
            root / "manifest.json", label=f"{name} sync manifest"
        )
        value = json.loads(encoded)
    except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"APP.DEPENDENCY.component_manifest_invalid: {name}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"APP.DEPENDENCY.component_manifest_invalid: {name}")
    return value


def _validate_component_bindings(
    *,
    manifests: Mapping[str, Mapping[str, Any]],
    declarations: Mapping[str, Mapping[str, Any]],
    source_identity: Mapping[str, str],
) -> None:
    expected_schemas = {
        "productionPub": PUB_CACHE_SYNC_MANIFEST_SCHEMA,
        "patrolPub": PATROL_PUB_SYNC_MANIFEST_SCHEMA,
        "productionIosPods": IOS_POD_CAPSULE_SCHEMA,
        "patrolIosPods": IOS_POD_CAPSULE_SCHEMA,
        "androidGradle": ANDROID_GRADLE_SYNC_SCHEMA,
    }
    for name, schema in expected_schemas.items():
        if manifests[name].get("schema") != schema:
            raise ValueError(f"APP.DEPENDENCY.component_binding_invalid: {name} schema")
    flutter_fields = {
        "flutterVersion": source_identity["flutterVersion"],
        "flutterCommandResolutionDigest": source_identity[
            "flutterCommandResolutionDigest"
        ],
    }
    pub_sources = {
        "productionPub": source_identity["productionPubResolutionInputDigest"],
        "patrolPub": source_identity["patrolPubResolutionInputDigest"],
    }
    for name, resolution_digest in pub_sources.items():
        manifest = manifests[name]
        if (
            any(
                manifest.get(field) != expected
                for field, expected in flutter_fields.items()
            )
            or manifest.get("resolutionInputDigest") != resolution_digest
        ):
            raise ValueError(f"APP.DEPENDENCY.component_binding_invalid: {name} source")
    pub_manifest_digests = {
        name: str(declarations[name]["manifestDigest"])
        for name in ("productionPub", "patrolPub")
    }
    ios_bindings = {
        "productionIosPods": (
            IOS_POD_PRODUCTION_HOST,
            pub_manifest_digests["productionPub"],
        ),
        "patrolIosPods": (
            IOS_POD_PATROL_HOST,
            pub_manifest_digests["patrolPub"],
        ),
    }
    for name, (host, upstream_digest) in ios_bindings.items():
        manifest = manifests[name]
        if (
            manifest.get("dependencyHost") != host
            or manifest.get("nativeDependencyMode") != IOS_NATIVE_DEPENDENCY_MODE
            or manifest.get("upstreamDependencyDigest") != upstream_digest
        ):
            raise ValueError(
                f"APP.DEPENDENCY.component_binding_invalid: {name} upstream"
            )
    android = manifests["androidGradle"]
    if (
        android.get("nativeResolutionInputDigest")
        != source_identity["nativeResolutionInputDigest"]
        or android.get("upstreamDependencyDigests") != pub_manifest_digests
    ):
        raise ValueError(
            "APP.DEPENDENCY.component_binding_invalid: androidGradle upstream"
        )


def _component_declarations(
    *,
    context: DependencyComponentBuildContext,
    component_roots: Mapping[str, Path],
) -> dict[str, dict[str, Any]]:
    if set(component_roots) != set(APP_DEPENDENCY_COMPONENTS):
        raise ValueError("APP.DEPENDENCY.component_set_incomplete")
    active_root = context.generation_root.parent.parent
    assert_real_directory(active_root, label="dependency bundle active root")
    assert_real_directory(
        context.generation_root.parent, label="dependency bundle snapshots root"
    )
    assert_real_directory(
        context.generation_root, label="dependency bundle generation root"
    )
    manifests: dict[str, dict[str, Any]] = {}
    declarations: dict[str, dict[str, Any]] = {}
    seen: set[Path] = set()
    for name in APP_DEPENDENCY_COMPONENTS:
        root = Path(component_roots[name]).expanduser().absolute()
        expected = context.generation_root / name
        if root != expected or root in seen:
            raise ValueError(f"APP.DEPENDENCY.component_cross_attempt: {name}")
        seen.add(root)
        assert_real_directory(root, label=f"{name} generation root")
        manifest = _read_component_manifest(name=name, root=root)
        manifests[name] = manifest
        declarations[name] = component_declaration(
            snapshot_ref=root.relative_to(active_root),
            manifest=manifest,
        )
    _validate_component_bindings(
        manifests=manifests,
        declarations=declarations,
        source_identity=context.source_identity,
    )
    return declarations


def _publish_dependency_generation(
    *,
    publisher: BundlePublisher,
    output: Path,
    active_root: Path,
    attempt_id: str,
    source_identity: Mapping[str, str],
    components: Mapping[str, Mapping[str, Any]],
    progress: _PublicationProgress,
    before_active_write: Callable[[], None],
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    def atomic_json(path: Path, value: dict[str, Any]) -> None:
        if path == active_root / "active.json":
            before_active_write()
            progress.active_write_started = True
        _atomic_json(path, value, mode=0o600)

    return publisher(
        output_root=output,
        active_root=active_root,
        attempt_id=attempt_id,
        source_identity=source_identity,
        components=components,
        atomic_json=atomic_json,
    )


def _cleanup_attempt_root(root: Path | None, warnings: list[str]) -> None:
    if root is None or not root.exists():
        return
    try:
        remove_private_tree(root)
    except (OSError, ValueError) as exc:
        warnings.append(
            "APP.DEPENDENCY.cleanup_warning: "
            f"cause={_builder.dependency_failure_cause(exc)}"
        )


def _active_pointer_commit_state(
    *, path: Path, attempt_id: str
) -> _ActivePointerCommitState:
    """Tri-state a fresh no-follow read before deciding generation cleanup."""

    try:
        encoded, _mode = read_regular_nofollow(
            path, label="dependency bundle active commit readback"
        )
        value = json.loads(encoded)
    except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        return _ActivePointerCommitState.UNKNOWN
    if (
        not isinstance(value, dict)
        or value.get("schema") != APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA
    ):
        return _ActivePointerCommitState.UNKNOWN
    observed_attempt = value.get("attemptId")
    if (
        not isinstance(observed_attempt, str)
        or not observed_attempt
        or any(character not in "0123456789abcdef" for character in observed_attempt)
    ):
        return _ActivePointerCommitState.UNKNOWN
    if observed_attempt == attempt_id:
        return _ActivePointerCommitState.SELECTS_ATTEMPT
    return _ActivePointerCommitState.SELECTS_OTHER


def command_app_dependency_sync(
    args: argparse.Namespace,
    *,
    component_builder: ComponentBuilder | None = None,
    publisher: BundlePublisher | None = None,
) -> dict[str, Any]:
    """Build all five closures, persist receipt v3, then switch active v2."""

    del args
    repo_root = Path(__file__).resolve().parents[3]
    attempt_id = uuid.uuid4().hex
    work_root: Path | None = None
    generation_root: Path | None = None
    process_root: Path | None = None
    active_path: Path | None = None
    active_committed = False
    active_commit_ambiguous = False
    active_commit_cause = ""
    failed_phase = "initialization"
    failure_cause = ""
    outcome: dict[str, Any] | None = None
    cleanup_warnings: list[str] = []
    sensitive_failure_values: list[str] = []
    output = output_root().expanduser().absolute()
    process_root = output / "env/repo/local/app-dependency-sync/process" / attempt_id
    try:
        process_base = process_root.parent
        process_base.mkdir(parents=True, exist_ok=True, mode=0o700)
        assert_real_directory(process_base, label="dependency sync process base")
        process_base.chmod(0o700)
        process_root.mkdir(mode=0o700)
        assert_real_directory(process_root, label="dependency sync process root")
        process_root.chmod(0o700)

        last_wait_progress_at = -_LOCK_PROGRESS_INTERVAL_SECONDS

        def emit_progress(
            phase: str,
            *,
            state: str = "running",
            holder: str = "",
            remaining_seconds: float | None = None,
        ) -> None:
            fields = [
                "[app-dependency-sync]",
                f"attemptId={attempt_id}",
                f"phase={phase}",
                f"state={state}",
            ]
            if remaining_seconds is not None:
                fields.append(f"remainingSeconds={max(0, int(remaining_seconds))}")
            if holder:
                fields.append(f"holder={holder}")
            print(" ".join(fields), file=sys.stderr, flush=True)

        def wait_progress(holder: str, remaining_seconds: float) -> None:
            nonlocal last_wait_progress_at
            elapsed = _LOCK_TIMEOUT_SECONDS - remaining_seconds
            if (
                last_wait_progress_at < 0
                or elapsed - last_wait_progress_at >= _LOCK_PROGRESS_INTERVAL_SECONDS
                or remaining_seconds <= 0
            ):
                emit_progress(
                    "dependency-sync-lock",
                    state="waiting",
                    holder=holder,
                    remaining_seconds=remaining_seconds,
                )
                last_wait_progress_at = elapsed

        emit_progress("initialization")
        failed_phase = "live-source-seal"
        emit_progress("live-source-seal")
        live_source_seal = _builder.resolution_seal(repo_root)
        failed_phase = "dependency-sync-lock"
        emit_progress("dependency-sync-lock", state="acquiring")
        with _sync_lock(on_wait=wait_progress):
            emit_progress("dependency-sync-lock", state="acquired")
            failed_phase = "toolchain-identity"
            emit_progress("toolchain-identity")
            try:
                flutter_identity = resolved_flutter_identity(dict(os.environ))
            except FacadeError as exc:
                raise ValueError(
                    f"APP.DEPENDENCY.flutter_identity_invalid: {exc}"
                ) from exc
            source_identity = _validated_source_identity(
                _source_identity(
                    repo_root=repo_root,
                    flutter_identity=flutter_identity,
                )
            )
            active_root = managed_dependency_bundle_root().absolute()
            active_path = active_root / "active.json"
            work_root = active_root / "work" / attempt_id
            work_root.mkdir(parents=True, mode=0o700)
            snapshots_root = active_root / "snapshots"
            snapshots_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            assert_real_directory(
                snapshots_root, label="dependency bundle snapshots root"
            )
            generation_root = snapshots_root / attempt_id
            if generation_root.exists() or generation_root.is_symlink():
                raise ValueError("APP.DEPENDENCY.attempt_identity_collision")
            generation_root.mkdir(mode=0o700)
            progress = DependencyBuildProgress(on_begin=emit_progress)
            context = DependencyComponentBuildContext(
                repo_root=repo_root,
                attempt_id=attempt_id,
                work_root=work_root,
                process_root=process_root,
                generation_root=generation_root,
                flutter_identity=dict(flutter_identity),
                source_identity=source_identity,
                progress=progress,
            )
            failed_phase = progress.current_phase
            if component_builder is None:
                with _attempt_android_runtime_trust(
                    repo_root,
                    attempt_id=attempt_id,
                    cleanup_warnings=cleanup_warnings,
                ) as trust_root:
                    sensitive_failure_values.append(str(trust_root))
                    roots = _build_dependency_components(
                        context, trust_root=trust_root
                    )
            else:
                roots = component_builder(context)
            failed_phase = "live-source-readback"
            emit_progress("live-source-readback")
            _builder.assert_live_resolution_seal(
                repo_root=repo_root,
                expected=live_source_seal,
            )
            try:
                current_flutter = resolved_flutter_identity(dict(os.environ))
            except FacadeError as exc:
                raise ValueError(
                    f"APP.DEPENDENCY.flutter_identity_invalid: {exc}"
                ) from exc
            current_source = _validated_source_identity(
                _source_identity(
                    repo_root=repo_root,
                    flutter_identity=current_flutter,
                )
            )
            if current_source != source_identity:
                raise ValueError("APP.DEPENDENCY.source_identity_drift_during_sync")
            failed_phase = "component-readback"
            emit_progress("component-readback")
            components = _component_declarations(
                context=context,
                component_roots=roots,
            )
            publication_progress = _PublicationProgress()
            failed_phase = "publication"
            emit_progress("publication")
            try:
                published = _publish_dependency_generation(
                    publisher=publisher or publish_dependency_bundle_activation,
                    output=output,
                    active_root=active_root,
                    attempt_id=attempt_id,
                    source_identity=source_identity,
                    components=components,
                    progress=publication_progress,
                    before_active_write=lambda: _builder.assert_live_resolution_seal(
                        repo_root=repo_root,
                        expected=live_source_seal,
                    ),
                )
                if not isinstance(published, tuple) or len(published) != 4:
                    raise ValueError("APP.DEPENDENCY.publisher_result_invalid")
                receipt, active, receipt_path, published_active_path = published
                expected_receipt_path = (
                    output
                    / "env/repo/runs/app-dependency-sync"
                    / attempt_id
                    / "report.json"
                )
                if (
                    not isinstance(receipt, Mapping)
                    or not isinstance(active, Mapping)
                    or not isinstance(receipt_path, Path)
                    or not isinstance(published_active_path, Path)
                    or receipt.get("schema")
                    != APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA
                    or active.get("schema") != APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA
                    or receipt.get("attemptId") != attempt_id
                    or active.get("attemptId") != attempt_id
                    or receipt_path != expected_receipt_path
                    or published_active_path != active_path
                ):
                    raise ValueError("APP.DEPENDENCY.publisher_result_invalid")
                commit_state = _active_pointer_commit_state(
                    path=active_path,
                    attempt_id=attempt_id,
                )
                if commit_state is not _ActivePointerCommitState.SELECTS_ATTEMPT:
                    raise ValueError(
                        "APP.DEPENDENCY.activation_readback_invalid: "
                        f"readback={commit_state.value}"
                    )
                _builder.assert_live_resolution_seal(
                    repo_root=repo_root,
                    expected=live_source_seal,
                )
            except (
                OSError,
                RuntimeError,
                TypeError,
                UnicodeError,
                ValueError,
                json.JSONDecodeError,
                subprocess.SubprocessError,
            ) as exc:
                # The atomic rename may already have committed even when its
                # directory fsync or the injectable publisher acknowledgement
                # fails. Decide while still holding the sync lock, and never
                # delete a generation selected by the freshly read pointer.
                commit_state = None
                if publication_progress.active_write_started:
                    commit_state = _active_pointer_commit_state(
                        path=active_path, attempt_id=attempt_id
                    )
                if commit_state in {
                    _ActivePointerCommitState.SELECTS_ATTEMPT,
                    _ActivePointerCommitState.UNKNOWN,
                }:
                    active_commit_ambiguous = True
                    active_commit_cause = _builder.dependency_failure_cause(exc)
                    raise ValueError(
                        "APP.DEPENDENCY.activation_commit_ambiguous: "
                        f"readback={commit_state.value}; "
                        "generation preserved"
                    ) from exc
                raise
            active_committed = True
            failed_phase = "post-publication-live-source-readback"
            emit_progress("post-publication-live-source-readback")
            _builder.assert_live_resolution_seal(
                repo_root=repo_root,
                expected=live_source_seal,
            )
            _cleanup_attempt_root(work_root, cleanup_warnings)
        emit_progress("completed")
        outcome = {
            "exitCode": 0,
            "summary": "App dependency sync completed",
            "details": [
                f"attemptId={attempt_id}",
                *(
                    f"{name}.treeDigest={components[name]['treeDigest']}"
                    for name in APP_DEPENDENCY_COMPONENTS
                ),
                f"receipt={receipt_path}",
                f"active={active_path}",
                *cleanup_warnings,
            ],
            "receipt": receipt,
            "activation": {
                "status": "committed",
                "activeRef": active_path.relative_to(output).as_posix(),
                "attemptId": attempt_id,
            },
        }
    except (
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        failure_cause = _builder.dependency_failure_cause(exc)
        if 'progress' in locals() and failed_phase == "component-build":
            failed_phase = progress.current_phase
        seal_failure: BaseException | None = None
        if 'live_source_seal' in locals():
            try:
                _builder.assert_live_resolution_seal(
                    repo_root=repo_root,
                    expected=live_source_seal,
                )
            except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as seal_exc:
                seal_failure = seal_exc
        if not active_committed:
            _cleanup_attempt_root(work_root, cleanup_warnings)
        if not active_committed and not active_commit_ambiguous:
            _cleanup_attempt_root(generation_root, cleanup_warnings)
        detail = _builder.redact_dependency_failure_text(
            str(exc) or type(exc).__name__,
            sensitive_values=tuple(sensitive_failure_values),
        )
        if not detail.startswith("APP.DEPENDENCY"):
            detail = (
                "APP.DEPENDENCY.sync_blocked: "
                f"cause={failure_cause}; detail={detail}"
            )
        details = [
            detail,
            *(
                [f"cause={active_commit_cause}"]
                if active_commit_ambiguous
                else []
            ),
            *cleanup_warnings,
        ]
        if seal_failure is not None:
            details.append(
                _builder.redact_dependency_failure_text(
                    str(seal_failure) or type(seal_failure).__name__,
                    sensitive_values=tuple(sensitive_failure_values),
                )
            )
        outcome = {
            "exitCode": 2,
            "summary": "App dependency sync blocked",
            "details": details,
        }
    result_ref = (process_root / "result.json").relative_to(output).as_posix()
    outcome_details = outcome.setdefault("details", [])
    if not any(str(item).startswith("attemptId=") for item in outcome_details):
        outcome_details.append(f"attemptId={attempt_id}")
    outcome_details.append(f"processResult={result_ref}")
    if process_root is not None:
        try:
            process_result = _process_result_payload(
                attempt_id=attempt_id,
                outcome=outcome,
                failed_phase=failed_phase,
                cause=failure_cause,
                output=output,
                process_root=process_root,
                sensitive_values=tuple(sensitive_failure_values),
                redact=_builder.redact_dependency_failure_text,
            )
            _atomic_process_result(process_root / "result.json", process_result)
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as exc:
            result_warning = (
                "APP.DEPENDENCY.process_result_write_warning: "
                f"cause={_builder.dependency_failure_cause(exc)}"
            )
            outcome.setdefault("details", []).append(result_warning)
    return outcome
