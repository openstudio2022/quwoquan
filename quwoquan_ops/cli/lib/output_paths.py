"""The only local output-root contract.

``.qwq_output`` contains only redacted run evidence, observability records,
process records and disposable caches. Deployment packages, rendered
configuration and certificate exports are outside the repository output tree;
configuration/network truth stays in domain deploy assets and Ops environment
manifests.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".qwq_output"
DEFAULT_DEPLOY_WORK_ROOT = Path.home() / ".cache" / "quwoquan" / "deploy"
DEPLOY_ENVS = frozenset({"alpha", "beta", "gamma", "prod"})
ENV_SEGMENTS = DEPLOY_ENVS | {"repo"}
DEFAULT_DEPLOY_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
ACTIVE_CANDIDATE_SCHEMA = "stackctl-active-deployment-candidate"
PACKAGE_ROOT_OVERRIDE_ENV = "QWQ_DEPLOY_PACKAGE_ROOT_OVERRIDE"
_BASELINE_ID = re.compile(r"sha256:[0-9a-f]{64}")


class _UnsafeActiveCandidatePath(ValueError):
    """The active-candidate pointer cannot be accessed without following links."""


def _secure_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError(
            "active candidate verification requires O_NOFOLLOW/O_DIRECTORY"
        )
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _secure_file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("active candidate verification requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _open_directory_chain(
    path: Path,
    *,
    label: str,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Open every absolute directory segment without following symbolic links."""
    absolute = path.expanduser().absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise _UnsafeActiveCandidatePath(f"{label} parent path is unsafe")
    anchor = Path(absolute.anchor)
    try:
        descriptor = os.open(anchor, _secure_directory_flags())
    except OSError as exc:
        raise _UnsafeActiveCandidatePath(
            f"{label} filesystem root is unavailable"
        ) from exc
    identities: list[tuple[int, int]] = []
    try:
        root_info = os.fstat(descriptor)
        identities.append((root_info.st_dev, root_info.st_ino))
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part,
                    _secure_directory_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                raise
            except OSError as exc:
                raise _UnsafeActiveCandidatePath(
                    f"{label} parent is a symlink or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeActiveCandidatePath(
                    f"{label} parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_directory_chain(
    path: Path,
    *,
    label: str,
    expected_identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_directory_chain(path, label=label)
    os.close(descriptor)
    if identities != expected_identities:
        raise _UnsafeActiveCandidatePath(f"{label} parent changed during access")


def _read_secure_json_object(path: Path, *, label: str) -> dict[str, Any] | None:
    try:
        parent_descriptor, parent_identities = _open_directory_chain(
            path.parent,
            label=label,
        )
    except FileNotFoundError:
        return None
    descriptor = -1
    try:
        try:
            before = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeActiveCandidatePath(
                f"{label} is a symlink or non-regular file"
            )
        try:
            descriptor = os.open(
                path.name,
                _secure_file_flags(write=False),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeActiveCandidatePath(
                f"{label} is a symlink or unreadable"
            ) from exc
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if not stat.S_ISREG(opened.st_mode) or identity != (
            before.st_dev,
            before.st_ino,
        ):
            raise _UnsafeActiveCandidatePath(f"{label} changed during access")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            encoded = handle.read()
        _revalidate_directory_chain(
            path.parent,
            label=label,
            expected_identities=parent_identities,
        )
        after = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != identity:
            raise _UnsafeActiveCandidatePath(f"{label} changed during access")
    except FileNotFoundError as exc:
        raise _UnsafeActiveCandidatePath(f"{label} changed during access") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be an object")
    return payload


def _atomic_write_secure_json_object(
    path: Path,
    payload: dict[str, Any],
    *,
    label: str,
) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    parent_descriptor, parent_identities = _open_directory_chain(
        path.parent,
        label=label,
    )
    temporary = f".{path.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        try:
            current = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeActiveCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        current_identity = (
            (current.st_dev, current.st_ino) if current is not None else None
        )
        descriptor = os.open(
            temporary,
            _secure_file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _revalidate_directory_chain(
            path.parent,
            label=label,
            expected_identities=parent_identities,
        )
        try:
            latest = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            latest = None
        if latest is not None and not stat.S_ISREG(latest.st_mode):
            raise _UnsafeActiveCandidatePath(
                f"{label} final path is a symlink or non-regular file"
            )
        latest_identity = (
            (latest.st_dev, latest.st_ino) if latest is not None else None
        )
        if latest_identity != current_identity:
            raise _UnsafeActiveCandidatePath(
                f"{label} final path changed before activation"
            )
        os.replace(
            temporary,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_exists = False
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def safe_segment(value: str, *, fallback: str = "run") -> str:
    text = str(value or "").strip().replace("/", "-").replace("\\", "-")
    return text if text and text not in {".", ".."} else fallback


def output_root() -> Path:
    return Path(os.environ.get("QWQ_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _deployment_segment(value: str, *, label: str, fallback: str = "") -> str:
    text = str(value or "").strip() or fallback
    candidate = Path(text)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or candidate.is_absolute()
        or len(candidate.parts) != 1
    ):
        raise ValueError(f"deployment {label} must be one safe path segment: {value!r}")
    return text


def _require_external_deployment_base(base: Path) -> None:
    repository_root = ROOT.resolve()
    repository_output_root = output_root().expanduser().resolve()
    if _is_within(base, repository_root):
        raise ValueError(
            "QWQ_DEPLOY_WORK_ROOT must be outside the repository source tree"
        )
    if _is_within(base, repository_output_root) or _is_within(
        repository_output_root,
        base,
    ):
        raise ValueError(
            "QWQ_DEPLOY_WORK_ROOT must be outside QWQ_OUTPUT_ROOT and must not overlap it; "
            ".qwq_output cannot contain deployment configuration or payloads"
        )


def _require_target_scoped_path(path: Path, *, target_root: Path) -> Path:
    candidate = target_root
    try:
        relative_parts = path.relative_to(target_root).parts
    except ValueError as exc:
        raise ValueError(
            f"deployment path escapes target-scoped workspace {target_root}: {path}"
        ) from exc
    for part in relative_parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(
                "deployment path cannot traverse a symbolic link: "
                f"{candidate}"
            )
    resolved = path.resolve()
    if not _is_within(resolved, target_root):
        raise ValueError(
            f"deployment path escapes target-scoped workspace {target_root}: {path}"
        )
    return resolved


def deployment_target_path_in_work_root(
    work_root: str | Path,
    target: str,
    *segments: str,
) -> Path:
    """Return a validated target path below an explicit external workspace."""
    base = Path(work_root).expanduser().resolve()
    _require_external_deployment_base(base)
    target_segment = _deployment_segment(target, label="target", fallback="local")
    target_root = (base / target_segment).resolve()
    if not _is_within(target_root, base):
        raise ValueError(
            "deployment target cannot escape explicit deployment workspace: "
            f"{target_root}"
        )
    _require_external_deployment_base(target_root)
    normalized_segments = tuple(
        _deployment_segment(segment, label="path segment")
        for segment in segments
    )
    candidate = target_root.joinpath(*normalized_segments)
    return _require_target_scoped_path(candidate, target_root=target_root)


def deployment_target_path(target: str, *segments: str) -> Path:
    """Return a real path below exactly one validated deployment target."""
    return deployment_target_path_in_work_root(
        deployment_work_root(target).parent,
        target,
        *segments,
    )


def resolve_deployment_target_path(
    configured_path: str | Path | None,
    *,
    target: str,
    segments: tuple[str, ...],
) -> Path:
    """Accept only the canonical resolver-derived path for a deployment output."""
    expected = deployment_target_path(target, *segments)
    if configured_path is None or not str(configured_path).strip():
        return expected
    configured = Path(configured_path).expanduser().resolve()
    if configured != expected:
        raise ValueError(
            "deployment output must resolve to its target-scoped workspace: "
            f"expected {expected}, got {configured}"
        )
    return expected


def remove_deployment_tree(target: str, *segments: str) -> Path:
    """Remove only a resolver-derived non-symlink deployment directory."""
    if not segments:
        raise ValueError("refusing to remove a deployment target root")
    if segments[0] == "packages":
        package_root = deployment_package_root(env_for_target(target), target=target)
        path = package_root.joinpath(*segments[1:])
        _require_target_scoped_path(path, target_root=deployment_work_root(target))
    else:
        path = deployment_target_path(target, *segments)
    if path.exists():
        shutil.rmtree(path)
    return path


def env_for_target(target: str) -> str:
    target = str(target or "").strip()
    for env in sorted(DEPLOY_ENVS):
        if target == env or target.startswith(f"{env}-"):
            return env
    raise ValueError(f"cannot resolve environment from target {target!r}")


def normalize_env(env_name: str, *, target: str = "") -> str:
    env_name = str(env_name or "").strip()
    if env_name in DEPLOY_ENVS:
        return env_name
    if not env_name and target:
        return env_for_target(target)
    raise ValueError(f"unknown environment {env_name!r}; expected one of {sorted(DEPLOY_ENVS)}")


def run_evidence_dir(parent: Path, command_name: str, target: str) -> Path:
    """Return a collision-resistant directory for one immutable command run.

    A second-resolution timestamp is not a run identity: concurrent read-only
    inspections used to resolve to the same directory and could overwrite each
    other's evidence.  Keep the sortable UTC prefix, add microseconds for
    readability, and use a random run identity so independent processes never
    intentionally share an evidence directory.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_identity = uuid4().hex
    return parent / (
        f"{stamp}-{run_identity}-{safe_segment(command_name)}-"
        f"{safe_segment(target, fallback='local')}"
    )


def env_root(env_name: str) -> Path:
    return output_root() / "env" / normalize_env(env_name)


def env_runs_root(env_name: str) -> Path:
    return env_root(env_name) / "runs"


def env_run_dir(env_name: str, command_name: str, *, target: str = "local") -> Path:
    return run_evidence_dir(
        env_runs_root(normalize_env(env_name, target=target)),
        command_name,
        target,
    )


def env_observability_root(env_name: str) -> Path:
    return env_root(env_name) / "observability"


def env_observability_run_dir(env_name: str, run_id: str) -> Path:
    return env_observability_root(env_name) / safe_segment(run_id)


def env_local_root(env_name: str) -> Path:
    return env_root(env_name) / "local"


def target_local_dir(target: str) -> Path:
    return env_local_root(env_for_target(target)) / safe_segment(target, fallback="local")


def target_process_dir(target: str) -> Path:
    return target_local_dir(target) / "process"


def target_cache_dir(target: str) -> Path:
    return target_local_dir(target) / "cache"


def _deployment_base_root() -> Path:
    configured = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    base = Path(configured).expanduser() if configured else DEFAULT_DEPLOY_WORK_ROOT
    resolved_base = base.resolve()
    _require_external_deployment_base(resolved_base)
    return resolved_base


def deployment_work_root(target: str) -> Path:
    """Return the real, external workspace for exactly one deployment target."""
    target_segment = _deployment_segment(target, label="target", fallback="local")
    resolved_base = _deployment_base_root()
    target_root = (resolved_base / target_segment).resolve()
    if not _is_within(target_root, resolved_base):
        raise ValueError(
            "deployment target cannot escape QWQ_DEPLOY_WORK_ROOT via a symbolic link"
        )
    _require_external_deployment_base(target_root)
    return target_root


def deployment_target_for_env(env_name: str, *, target: str = "") -> str:
    """Resolve the only deployment workspace target allowed for an environment."""
    env = normalize_env(env_name)
    requested = str(target or os.environ.get("QWQ_DEPLOY_TARGET", "")).strip()
    if not requested:
        return DEFAULT_DEPLOY_TARGET_BY_ENV[env]
    if env_for_target(requested) != env:
        raise ValueError(
            f"deployment target {requested!r} does not belong to environment {env!r}"
        )
    return _deployment_segment(
        requested,
        label="target",
        fallback=DEFAULT_DEPLOY_TARGET_BY_ENV[env],
    )


def deployment_package_root(env_name: str, *, target: str = "") -> Path:
    """Return only the staging or atomically activated candidate package root."""
    target_name = deployment_target_for_env(env_name, target=target)
    override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV, "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        _require_target_scoped_path(path, target_root=deployment_work_root(target_name))
        if path.name != "packages":
            raise ValueError("deployment package root override must end in packages")
        return path
    active = active_deployment_candidate(target_name)
    if active is None:
        # Read-only callers receive the historical location only until the first
        # atomic candidate is activated. stackctl up/verify separately reject it.
        return deployment_target_path(target_name, "packages")
    return deployment_candidate_dir(target_name, str(active["baselineId"])) / "packages"


def deployment_candidate_dir(target: str, baseline_id: str) -> Path:
    """Return the immutable full-runtime candidate for one baseline digest."""
    baseline = str(baseline_id or "").strip()
    if _BASELINE_ID.fullmatch(baseline) is None:
        raise ValueError("deployment baselineId must be sha256")
    return deployment_target_path(
        target,
        "candidates",
        "runtime-full",
        baseline.replace(":", "-"),
    )


def active_candidate_manifest_path(target: str) -> Path:
    target_segment = _deployment_segment(target, label="target", fallback="local")
    unresolved_target_root = _deployment_base_root() / target_segment
    resolved_target_root = deployment_work_root(target)
    if unresolved_target_root != resolved_target_root:
        raise _UnsafeActiveCandidatePath(
            "active deployment candidate parent cannot be a symbolic link"
        )
    return unresolved_target_root / "active-runtime-candidate.json"


def _load_full_deployment_candidate(
    target: str,
    baseline_id: str,
) -> dict[str, Any]:
    # Delayed import avoids the output_paths -> deployment_candidate_manifest ->
    # output_paths module initialization cycle while retaining the one canonical
    # full-candidate validator.
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
        load_candidate_manifest,
    )

    payload = load_candidate_manifest(
        env_for_target(target),
        target,
        baseline_id,
        require_full=True,
    )
    if (
        payload.get("candidateType") != "runtime-full"
        or payload.get("target") != target
        or payload.get("baselineId") != baseline_id
    ):
        raise ValueError("deployment candidate manifest identity mismatch")
    return payload


def _active_deployment_candidate_descriptor(
    target: str,
) -> dict[str, str] | None:
    """Securely read the active pointer without re-reading candidate payloads."""

    path = active_candidate_manifest_path(target)
    payload = _read_secure_json_object(
        path,
        label="active deployment candidate",
    )
    if payload is None:
        return None
    required = {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("active deployment candidate fields mismatch")
    baseline = str(payload.get("baselineId") or "")
    expected = deployment_candidate_dir(target, baseline)
    candidate_dir = payload.get("candidateDir")
    if (
        payload.get("schema") != ACTIVE_CANDIDATE_SCHEMA
        or payload.get("candidateType") != "runtime-full"
        or payload.get("target") != target
        or not isinstance(candidate_dir, str)
        or candidate_dir != str(expected)
    ):
        raise ValueError("active deployment candidate identity mismatch")
    return {
        "schema": ACTIVE_CANDIDATE_SCHEMA,
        "candidateType": "runtime-full",
        "target": target,
        "baselineId": baseline,
        "candidateDir": str(expected),
    }


def active_deployment_candidate_snapshot(target: str) -> dict[str, Any] | None:
    """Fix one fully validated candidate for a complete runtime operation.

    The active pointer is parsed exactly once.  Every caller that needs Provider,
    observability or OCI identity can derive it from the returned manifest and
    candidate directory without consulting a later active pointer.
    """

    descriptor = _active_deployment_candidate_descriptor(target)
    if descriptor is None:
        return None
    manifest = _load_full_deployment_candidate(
        target,
        descriptor["baselineId"],
    )
    return {**descriptor, "manifest": manifest}


def active_deployment_candidate(target: str) -> dict[str, str] | None:
    """Read and validate the only activated package candidate for a target."""

    snapshot = active_deployment_candidate_snapshot(target)
    if snapshot is None:
        return None
    return {
        key: str(snapshot[key])
        for key in (
            "schema",
            "candidateType",
            "target",
            "baselineId",
            "candidateDir",
        )
    }


def assert_active_deployment_candidate_snapshot(
    snapshot: dict[str, Any],
) -> None:
    """Fail closed if the active pointer no longer selects a fixed snapshot."""

    required = {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
        "manifest",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != required:
        raise ValueError("fixed deployment candidate snapshot fields mismatch")
    target = str(snapshot.get("target") or "")
    current = _active_deployment_candidate_descriptor(target)
    expected = {
        key: snapshot[key]
        for key in (
            "schema",
            "candidateType",
            "target",
            "baselineId",
            "candidateDir",
        )
    }
    if current != expected:
        raise ValueError("active deployment candidate changed during operation")


def activate_deployment_candidate(target: str, baseline_id: str) -> Path:
    """Atomically publish one already-complete candidate as the active input."""
    candidate = deployment_candidate_dir(target, baseline_id)
    try:
        _load_full_deployment_candidate(target, baseline_id)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"cannot activate invalid full candidate: {exc}") from exc
    path = active_candidate_manifest_path(target)
    payload = {
        "schema": ACTIVE_CANDIDATE_SCHEMA,
        "candidateType": "runtime-full",
        "target": target,
        "baselineId": baseline_id,
        "candidateDir": str(candidate),
    }
    _atomic_write_secure_json_object(
        path,
        payload,
        label="active deployment candidate",
    )
    return path


def app_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "app"


def service_deployment_package_dir(
    env_name: str,
    service: str,
    *,
    target: str = "",
) -> Path:
    return (
        deployment_package_root(env_name, target=target)
        / "services"
        / _deployment_segment(service, label="service", fallback="service")
    )


def legal_static_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "legal-static"


def runtime_shared_deployment_package_dir(
    env_name: str,
    *,
    target: str = "",
) -> Path:
    return deployment_package_root(env_name, target=target) / "runtime-shared"


def portal_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "ops-portal"


def web_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    """Return the only home of the immutable public Web package for one target.

    Unlike app/service/legal packages, the Web package is not a member of a
    runtime candidate: `stackctl package --kind web` builds it in its own
    standalone root, it carries its own content digest plus a `current` pointer,
    and CI produces it in a separate job from the runtime shard.  Routing it
    through `deployment_package_root` made the writer follow the standalone
    override while every reader resolved the active candidate instead, so the
    package was always written where nobody looked for it.
    """
    target_name = deployment_target_for_env(env_name, target=target)
    return deployment_target_path(
        target_name,
        "standalone-packages",
        "web",
        "packages",
        "public-web",
    )


def deployment_render_dir(
    env_name: str,
    *,
    target: str = "",
    name: str = "",
) -> Path:
    target_name = deployment_target_for_env(env_name, target=target)
    segments = ("rendered",)
    if name:
        segments += (_deployment_segment(name, label="render name"),)
    return deployment_target_path(target_name, *segments)


def certificate_export_dir(target: str) -> Path:
    """Host path for target-scoped public DNS-01 certificate material."""
    return deployment_target_path(target, "certificates")


def repo_root() -> Path:
    return output_root() / "env" / "repo"


def repo_runs_root() -> Path:
    return repo_root() / "runs"


def repo_run_dir(command_name: str, *, target: str = "repo") -> Path:
    return run_evidence_dir(repo_runs_root(), command_name, target)


def repo_local_dir(name: str) -> Path:
    return repo_root() / "local" / safe_segment(name, fallback="workspace") / "process"


def data_root() -> Path:
    return output_root() / "data"


def data_tasks_root() -> Path:
    return data_root() / "tasks"


def data_releases_root() -> Path:
    return data_root() / "releases"


def data_local_root() -> Path:
    return data_root() / "local"


def env_data_release_run_dir(env_name: str, release_id: str, run_id: str) -> Path:
    return env_runs_root(env_name) / "data-release" / safe_segment(release_id, fallback="release") / safe_segment(run_id)
