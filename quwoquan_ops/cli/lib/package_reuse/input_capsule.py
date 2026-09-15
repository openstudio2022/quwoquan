"""部署输入枚举与只读 content-addressed input capsule（逐字迁自原单文件）。

``ROOT`` 经包属性（``_pkg.``）消费，保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
import argparse
import shutil
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import quwoquan_ops.cli.lib.package_reuse as _pkg

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    COCOAPODS_ENVIRONMENT_KEYS,
    AppDependencyToolchainError,
    cocoapods_identity_from_environment,
    resolve_cocoapods_identity,
)

from .constants import (
    _CAPSULE_ENTRY_FIELDS,
    _CAPSULE_FIELDS,
    PACKAGE_INPUT_CAPSULE_SCHEMA,
)
from .dependency_bundle_capsule import (
    VerifiedDependencySnapshots,
    copy_dependency_bundle_to_capsule,
    load_managed_dependency_snapshots,
    verify_dependency_bundle_capsule,
)
from .dependency_bundle import AppDependencyBundle, load_active_dependency_bundle
from .ios_pod_inputs import (
    IOS_POD_DEPENDENCY_LOGICAL_PATHS,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from .dependency_fs import remove_private_tree
from .dependency_network_command import (
    process_group_cleanup_grace,
    remaining_managed_deadline_seconds,
    run_managed_subprocess,
)
from .pub_cache_capsule import dependency_required


def _digest_record(
    entries: Iterable[tuple[str, str, bytes]],
) -> tuple[str, int]:
    """Digest logical path, entry kind and bytes without relying on mtimes."""

    digest = hashlib.sha256()
    count = 0
    for logical_path, kind, content in entries:
        path_bytes = logical_path.encode("utf-8")
        kind_bytes = kind.encode("ascii")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(kind_bytes).to_bytes(8, "big"))
        digest.update(kind_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        count += 1
    return f"sha256:{digest.hexdigest()}", count


def _path_entry(path: Path) -> tuple[str, bytes]:
    if path.is_symlink():
        return "symlink", os.readlink(path).encode("utf-8")
    if path.is_file():
        return "file", path.read_bytes()
    if not path.exists():
        return "missing", b""
    raise ValueError(f"deployment input is not a file or symlink: {path}")


def _normalized_input_roots(values: Sequence[str]) -> list[str]:
    roots = sorted({str(value).strip() for value in values if str(value).strip()})
    if not roots:
        raise ValueError("deployment input closure is empty")
    for value in roots:
        path = Path(value)
        if not path.is_absolute() and (
            not path.parts or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("deployment input closure path is unsafe")
    return roots


def _enumerated_deployment_inputs(
    roots: Sequence[str],
) -> tuple[list[str], list[tuple[str, Path, str]]]:
    normalized_roots = _normalized_input_roots(roots)
    repo_roots = [value for value in normalized_roots if not Path(value).is_absolute()]
    external_roots = [
        Path(value) for value in normalized_roots if Path(value).is_absolute()
    ]
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *repo_roots,
        ],
        cwd=_pkg.ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot enumerate managed deployment inputs"
            + (f": {detail}" if detail else "")
        )
    entries: list[tuple[str, Path, str]] = []
    for encoded in sorted(value for value in result.stdout.split(b"\0") if value):
        relative = os.fsdecode(encoded)
        path = _pkg.ROOT / relative
        # ``git ls-files --cached`` also reports tracked files deleted from the
        # live worktree.  A package capsule represents the bytes that actually
        # exist at capture time; keeping a deleted index entry here makes an
        # unrelated deletion fail before the real compiler can decide whether
        # that path is required.  The deletion is still reflected by the tree
        # digest (the bytes are absent) and by workspaceStatusDigest.
        if not path.exists() and not path.is_symlink():
            continue
        entries.append((relative, path, f"repo/{relative}"))
    for index, path in enumerate(external_roots):
        if path.exists() or path.is_symlink():
            entries.append(
                (
                    f"external:{path}",
                    path,
                    f"external/{index:04d}-{hashlib.sha256(str(path).encode()).hexdigest()}",
                )
            )
    if not entries:
        raise ValueError("managed deployment input set is empty")
    return normalized_roots, entries


def _safe_capsule_source(path: Path, *, logical_path: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"deployment input is unavailable: {logical_path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        resolved = path.resolve(strict=True)
        if logical_path.startswith("external:"):
            raise ValueError(
                f"external deployment input symlink is forbidden: {logical_path}"
            )
        if not resolved.is_relative_to(_pkg.ROOT.resolve()):
            raise ValueError(
                f"deployment input symlink escapes repository: {logical_path}"
            )
        return metadata
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"deployment input is not a regular file or safe symlink: {logical_path}"
        )
    if not logical_path.startswith("external:"):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(_pkg.ROOT.resolve()):
            raise ValueError(f"deployment input escapes repository: {logical_path}")
    return metadata


def _copy_regular_capsule_input(
    source: Path,
    destination: Path,
    *,
    logical_path: str,
) -> tuple[bytes, int]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("package input capsule requires O_NOFOLLOW")
    descriptor = os.open(
        source,
        os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"deployment input is not regular: {logical_path}")
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(
                f"deployment input changed during capsule copy: {logical_path}"
            )
    finally:
        os.close(descriptor)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
    output = os.open(destination, flags, 0o700)
    try:
        view = memoryview(content)
        while view:
            written = os.write(output, view)
            if written <= 0:
                raise OSError("package capsule write made no progress")
            view = view[written:]
        os.fsync(output)
        copied = os.fstat(output)
    finally:
        os.close(output)
    if (before.st_dev, before.st_ino) == (copied.st_dev, copied.st_ino):
        raise ValueError(f"package capsule hardlink is forbidden: {logical_path}")
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    os.chmod(destination, mode, follow_symlinks=False)
    return bytes(content), mode


def _capsule_identity_payload(
    *,
    roots: Sequence[str],
    input_digest: str,
    input_count: int,
) -> dict[str, object]:
    return {
        "deploymentInputRoots": list(roots),
        "deploymentInputDigest": input_digest,
        "deploymentInputFileCount": input_count,
    }


def _baseline_id(identity: dict[str, object]) -> str:
    encoded = json.dumps(
        identity,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


_DEPENDENCY_LOAD_TIMEOUT_ENV = "QWQ_PACKAGE_DEPENDENCY_LOAD_TIMEOUT_SECONDS"
_DEPENDENCY_LOAD_TIMEOUT_DEFAULT_SECONDS = 900
_MANAGED_RESULT_SCHEMA = "stackctl-package-capsule-managed-result.v1"
_MANAGED_REQUEST_MAX_BYTES = 128 * 1024 * 1024
_MANAGED_CONTROL_DIRECTORY_MODE = 0o700
_MANAGED_CONTROL_FILE_MODE = 0o600


class PackageDependencyInputTimeoutError(ValueError):
    """Typed finite blocker after a managed process group is killed and reaped."""

    code = "OPS.PACKAGE.dependency_input_timeout"


class PackageDependencyDonorIntegrityError(ValueError):
    """A canonically complete, identity-matching donor failed clone/CAS."""

    code = "OPS.PACKAGE.dependency_donor_integrity"


def _dependency_load_timeout_seconds() -> int:
    raw = str(os.environ.get(_DEPENDENCY_LOAD_TIMEOUT_ENV) or "").strip()
    if not raw:
        return _DEPENDENCY_LOAD_TIMEOUT_DEFAULT_SECONDS
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{_DEPENDENCY_LOAD_TIMEOUT_ENV} must be an integer") from error
    if value < 1 or value > 3600:
        raise ValueError(f"{_DEPENDENCY_LOAD_TIMEOUT_ENV} must be between 1 and 3600")
    return value


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _dependency_manifest_payloads(bundle: AppDependencyBundle) -> dict[str, object]:
    manifests = dict(bundle.component_manifests)
    android_wrapper = manifests["androidGradle"]
    android = android_wrapper.get("dependency")
    if not isinstance(android, Mapping):
        android = android_wrapper
    return {
        "dependency:dart-pub-cache-v2": manifests["productionPub"],
        "dependency:patrol-host-dart-pub-cache-v1": manifests["patrolPub"],
        IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PRODUCTION_HOST]: manifests[
            "productionIosPods"
        ],
        IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PATROL_HOST]: manifests[
            "patrolIosPods"
        ],
        "dependency:android-gradle-v1": dict(android),
    }


def _current_cocoapods_manifest_identity() -> dict[str, object]:
    try:
        present = {
            key
            for key in COCOAPODS_ENVIRONMENT_KEYS
            if str(os.environ.get(key) or "").strip()
        }
        identity = (
            cocoapods_identity_from_environment(os.environ)
            if present
            else resolve_cocoapods_identity(
                search_path=str(os.environ.get("PATH") or "")
            )
        )
    except AppDependencyToolchainError as error:
        raise ValueError(str(error)) from error
    return identity.physical.as_dict()


def _assert_current_cocoapods_identity(
    manifests: Mapping[str, object],
) -> None:
    current = _current_cocoapods_manifest_identity()
    for logical in (
        IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PRODUCTION_HOST],
        IOS_POD_DEPENDENCY_LOGICAL_PATHS[IOS_POD_PATROL_HOST],
    ):
        manifest = manifests.get(logical)
        if not isinstance(manifest, Mapping) or manifest.get("cocoaPods") != current:
            raise ValueError(
                "APP.DEPENDENCY.cocoapods_mixed: active iOS dependency "
                "manifest differs from current CocoaPods identity"
            )


def _capsule_dependency_payloads(
    capsule_root: Path, manifest: Mapping[str, object]
) -> dict[str, object] | None:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return None
    result: dict[str, object] = {}
    for raw in entries:
        if not isinstance(raw, Mapping):
            return None
        logical = str(raw.get("logicalPath") or "")
        if not logical.startswith("dependency:"):
            continue
        relative = Path(str(raw.get("capsulePath") or ""))
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            return None
        try:
            value = json.loads((capsule_root / relative).read_bytes())
        except (OSError, TypeError, UnicodeError, json.JSONDecodeError):
            return None
        result[logical] = value
    return result


def _completed_capsule_candidates(capsule_root: Path) -> list[Path]:
    candidate_parent = capsule_root.parent.parent
    if candidate_parent.is_symlink() or not candidate_parent.is_dir():
        return []
    found: list[tuple[int, str, Path]] = []
    for candidate in candidate_parent.iterdir():
        if candidate == capsule_root.parent or candidate.name.startswith("."):
            continue
        try:
            metadata = candidate.lstat()
            candidate_manifest = candidate / "manifest.json"
            old_capsule = candidate / "input-capsule"
            manifest_metadata = candidate_manifest.lstat()
        except OSError:
            continue
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or candidate.is_symlink()
            or not stat.S_ISREG(manifest_metadata.st_mode)
            or candidate_manifest.is_symlink()
            or old_capsule.is_symlink()
            or not old_capsule.is_dir()
        ):
            continue
        found.append((manifest_metadata.st_mtime_ns, candidate.name, old_capsule))
    return [item[2] for item in sorted(found, reverse=True)]


def _matching_dependency_capsules(
    *, capsule_root: Path, expected: Mapping[str, object]
) -> list[tuple[Path, list[dict[str, object]]]]:
    matches: list[tuple[Path, list[dict[str, object]]]] = []
    for old_capsule in _completed_capsule_candidates(capsule_root):
        try:
            manifest = _read_capsule_manifest(old_capsule)
            dependency_payloads = _capsule_dependency_payloads(old_capsule, manifest)
        except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
            continue
        if dependency_payloads != expected:
            continue
        # From this point the donor claims the exact current dependency identity.
        # Any completion/integrity failure is evidence, never a cache miss.
        try:
            candidate_manifest = json.loads(
                (old_capsule.parent / "manifest.json").read_text(encoding="utf-8")
            )
            if not isinstance(candidate_manifest, dict):
                raise ValueError("deployment candidate manifest is not an object")
            validated_candidate = _pkg.validate_candidate_manifest(
                candidate_manifest,
                expected_environment=str(candidate_manifest.get("environment") or ""),
                expected_target=str(candidate_manifest.get("target") or ""),
                require_full=True,
                candidate_root=old_capsule.parent,
                purpose="self_verify",
            )
            if validated_candidate.get("baselineId") != manifest.get("baselineId"):
                raise ValueError("dependency donor candidate baseline binding drifted")
            raw_entries = manifest.get("entries")
            if not isinstance(raw_entries, list):
                raise ValueError("dependency donor capsule entries are invalid")
            records = [
                dict(item)
                for item in raw_entries
                if isinstance(item, Mapping)
                and str(item.get("logicalPath") or "").startswith("dependency:")
            ]
            if len(records) != len(expected):
                raise ValueError("dependency donor marker set is incomplete")
        except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise PackageDependencyDonorIntegrityError(
                f"{PackageDependencyDonorIntegrityError.code}: identity-matching "
                f"donor {old_capsule.parent.name} is not a canonical completed candidate"
            ) from error
        matches.append((old_capsule, records))
    return matches


def _managed_control_root(staging: Path, operation: str) -> Path:
    parent = staging.parent
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / (
        f".{staging.name}.{operation}.{os.getpid()}.{uuid.uuid4().hex}.control"
    )
    root.mkdir(mode=_MANAGED_CONTROL_DIRECTORY_MODE)
    os.chmod(root, _MANAGED_CONTROL_DIRECTORY_MODE)
    return root


def _write_private_managed_request(path: Path, encoded: bytes) -> None:
    if len(encoded) > _MANAGED_REQUEST_MAX_BYTES:
        raise ValueError("managed package capsule request exceeds bounded size")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, _MANAGED_CONTROL_FILE_MODE)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("managed package capsule request write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, _MANAGED_CONTROL_FILE_MODE)
    finally:
        os.close(descriptor)


def _validated_control_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("managed package capsule control root is unsafe")
    metadata = path.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != _MANAGED_CONTROL_DIRECTORY_MODE
    ):
        raise ValueError("managed package capsule control root identity mismatch")
    return path


def _read_private_managed_request(
    *, request_path: Path, control_root: Path, declared_digest: str
) -> Mapping[str, object]:
    root = _validated_control_root(control_root)
    if (
        not request_path.is_absolute()
        or request_path.parent != root
        or request_path.name != "request.json"
    ):
        raise ValueError("managed package capsule request path escapes control root")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(request_path, flags)
    except OSError as error:
        raise ValueError("managed package capsule request file is unsafe") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != _MANAGED_CONTROL_FILE_MODE
            or metadata.st_size < 2
            or metadata.st_size > _MANAGED_REQUEST_MAX_BYTES
        ):
            raise ValueError("managed package capsule request file identity mismatch")
        remaining = metadata.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("managed package capsule request was truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("managed package capsule request grew during read")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ):
            raise ValueError("managed package capsule request changed during read")
    finally:
        os.close(descriptor)
    encoded = b"".join(chunks)
    actual_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if declared_digest != actual_digest:
        raise ValueError("managed package capsule request digest mismatch")
    try:
        request = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("managed package capsule request JSON is invalid") from error
    if not isinstance(request, Mapping) or request.get("schema") != _MANAGED_RESULT_SCHEMA:
        raise ValueError("managed package capsule request is invalid")
    operation = str(request.get("operation") or "")
    staging = Path(str(request.get("staging") or ""))
    result_path = Path(str(request.get("resultPath") or ""))
    if (
        operation not in {
            "load-active",
            "materialize-active",
            "clone-verify-dependencies",
            "verify-full",
        }
        or not staging.is_absolute()
        or staging.parent != root.parent
        or not root.name.startswith(f".{staging.name}.{operation}.")
        or not result_path.is_absolute()
        or result_path != root / "result.json"
    ):
        raise ValueError("managed package capsule request attempt binding mismatch")
    request_path.unlink()
    return request


def _run_capsule_managed_operation(
    operation: str,
    *,
    staging: Path,
    timeout: float,
    source_capsule: Path | None = None,
    records: Sequence[Mapping[str, object]] = (),
    expected_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    timeout = remaining_managed_deadline_seconds(timeout)
    control_root = _managed_control_root(staging, operation)
    request_path = control_root / "request.json"
    result_path = control_root / "result.json"
    request = {
        "schema": _MANAGED_RESULT_SCHEMA,
        "operation": operation,
        "repoRoot": str(_pkg.ROOT.expanduser().absolute()),
        "staging": str(staging.expanduser().absolute()),
        "sourceCapsule": str(source_capsule.expanduser().absolute())
        if source_capsule is not None
        else None,
        "records": [dict(item) for item in records],
        "expectedSnapshot": dict(expected_snapshot)
        if expected_snapshot is not None
        else None,
        "resultPath": str(result_path),
    }
    encoded_request = _canonical_json_bytes(request)
    request_digest = "sha256:" + hashlib.sha256(encoded_request).hexdigest()
    command = [
        sys.executable,
        "-B",
        "-c",
        (
            "from quwoquan_ops.cli.lib.package_reuse.input_capsule import "
            "_managed_main; raise SystemExit(_managed_main())"
        ),
        "--managed-request-path",
        str(request_path),
        "--managed-control-root",
        str(control_root),
        "--managed-request-digest",
        request_digest,
    ]
    try:
        _write_private_managed_request(request_path, encoded_request)
        try:
            completed = run_managed_subprocess(
                command,
                cwd=_pkg.ROOT,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": os.pathsep.join(
                        filter(
                            None,
                            (
                                str(Path(__file__).resolve().parents[4]),
                                os.environ.get("PYTHONPATH", ""),
                            ),
                        )
                    ),
                },
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                on_stderr=lambda chunk: print(
                    chunk, end="", file=sys.stderr, flush=True
                ),
            )
        except subprocess.TimeoutExpired as error:
            raise PackageDependencyInputTimeoutError(
                f"{PackageDependencyInputTimeoutError.code}: {operation} exceeded "
                f"the remaining {timeout:g}s package deadline; all owned process groups "
                f"killed and reaped; cleanupGrace={process_group_cleanup_grace()}"
            ) from error
        try:
            encoded = result_path.read_bytes()
            result = json.loads(encoded)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"managed package capsule {operation} result is missing"
            ) from error
        if (
            not isinstance(result, dict)
            or result.get("schema") != _MANAGED_RESULT_SCHEMA
            or result.get("operation") != operation
            or result.get("staging") != request["staging"]
            or result.get("requestDigest") != request_digest
            or set(result)
            != {
                "schema",
                "operation",
                "staging",
                "requestDigest",
                "status",
                "payload",
            }
        ):
            raise ValueError(
                f"managed package capsule {operation} result identity mismatch"
            )
        if completed.returncode != 0 or result.get("status") != "ok":
            payload = result.get("payload")
            detail = payload.get("detail") if isinstance(payload, Mapping) else None
            raise ValueError(
                f"managed package capsule {operation} failed: {detail or 'unknown'}"
            )
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"managed package capsule {operation} payload is invalid")
        return payload
    finally:
        request_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
        try:
            control_root.rmdir()
        except FileNotFoundError:
            pass


def _write_managed_result(
    request: Mapping[str, object], *, status: str, payload: Mapping[str, object]
) -> None:
    result_path = Path(str(request["resultPath"]))
    temporary = result_path.with_name(f".{result_path.name}.{os.getpid()}.tmp")
    value = {
        "schema": _MANAGED_RESULT_SCHEMA,
        "operation": request["operation"],
        "staging": request["staging"],
        "requestDigest": request["requestDigest"],
        "status": status,
        "payload": dict(payload),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, _MANAGED_CONTROL_FILE_MODE)
    try:
        encoded = _canonical_json_bytes(value)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("managed package capsule result write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(result_path)


def _managed_child(request: Mapping[str, object]) -> int:
    operation = str(request.get("operation") or "")
    staging = Path(str(request.get("staging") or ""))
    repo_root = Path(str(request.get("repoRoot") or ""))
    _pkg.ROOT = repo_root
    print(f"[package-capsule-stage] {operation}: started", file=sys.stderr, flush=True)
    try:
        if operation == "load-active":
            bundle = load_active_dependency_bundle(repo_root=repo_root)
            manifests = _dependency_manifest_payloads(bundle)
            _assert_current_cocoapods_identity(manifests)
            payload = {"manifests": manifests}
        elif operation == "materialize-active":
            snapshots = load_managed_dependency_snapshots(repo_root=repo_root)
            payload = {
                "records": copy_dependency_bundle_to_capsule(
                    snapshots=snapshots, capsule_root=staging
                )
            }
        elif operation == "clone-verify-dependencies":
            source = Path(str(request.get("sourceCapsule") or "")) / "dependencies"
            destination = staging / "dependencies"
            if source.is_symlink() or not source.is_dir() or destination.exists():
                raise ValueError("reusable package dependency tree is unsafe")
            if sys.platform == "darwin":
                subprocess.run(
                    ["/bin/cp", "-cRP", str(source), str(destination)], check=True
                )
            else:
                shutil.copytree(source, destination, symlinks=True)
            raw_records = request.get("records")
            if not isinstance(raw_records, list):
                raise ValueError("reusable dependency records are invalid")
            verify_dependency_bundle_capsule(
                capsule_root=staging,
                manifest_entries=[
                    dict(item) for item in raw_records if isinstance(item, Mapping)
                ],
            )
            payload = {"records": raw_records}
        elif operation == "verify-full":
            raw_expected = request.get("expectedSnapshot")
            if not isinstance(raw_expected, Mapping):
                raise ValueError("expected package snapshot is invalid")
            verified = verify_package_input_capsule(
                staging, expected_snapshot=dict(raw_expected)
            )
            payload = {
                "baselineId": verified["baselineId"],
                "deploymentInputDigest": verified["deploymentInputDigest"],
            }
        else:
            raise ValueError("managed package capsule operation is unknown")
    except BaseException as error:
        _write_managed_result(
            request,
            status="error",
            payload={"detail": f"{error.__class__.__name__}: {error}"},
        )
        print(f"[package-capsule-stage] {operation}: failed", file=sys.stderr, flush=True)
        return 2
    _write_managed_result(request, status="ok", payload=payload)
    print(f"[package-capsule-stage] {operation}: completed", file=sys.stderr, flush=True)
    return 0


def _managed_main() -> int | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--managed-request-path")
    parser.add_argument("--managed-control-root")
    parser.add_argument("--managed-request-digest")
    args, unknown = parser.parse_known_args()
    values = (
        args.managed_request_path,
        args.managed_control_root,
        args.managed_request_digest,
    )
    if not any(values):
        return None
    if unknown or not all(values):
        raise ValueError("managed package capsule arguments are invalid")
    request = _read_private_managed_request(
        request_path=Path(args.managed_request_path),
        control_root=Path(args.managed_control_root),
        declared_digest=str(args.managed_request_digest),
    )
    request = dict(request)
    request["requestDigest"] = str(args.managed_request_digest)
    return _managed_child(request)


def materialize_package_input_capsule(
    roots: Sequence[str],
    *,
    capsule_root: Path,
) -> dict[str, object]:
    """Copy one source closure into a read-only, content-addressed capsule."""

    normalized_roots, source_entries = _enumerated_deployment_inputs(roots)
    dependencies_required = dependency_required(_pkg.ROOT, normalized_roots)
    active_manifests: dict[str, object] | None = None
    timeout = _dependency_load_timeout_seconds()
    capsule_root = capsule_root.expanduser()
    if (
        not capsule_root.is_absolute()
        or capsule_root.exists()
        or capsule_root.is_symlink()
    ):
        raise ValueError("package input capsule root must be a new absolute path")
    capsule_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{capsule_root.name}.", dir=str(capsule_root.parent))
    )
    published = False
    try:
        if dependencies_required:
            print(
                f"[package-capsule-stage] load-active: dispatch timeout={timeout}s",
                file=sys.stderr,
                flush=True,
            )
            active_payload = _run_capsule_managed_operation(
                "load-active", staging=staging, timeout=timeout
            )
            raw_manifests = active_payload.get("manifests")
            if not isinstance(raw_manifests, dict):
                raise ValueError("managed active dependency manifests are invalid")
            active_manifests = raw_manifests
        records: list[dict[str, object]] = []
        digest_entries: list[tuple[str, str, bytes]] = []
        for logical_path, source, relative in source_entries:
            metadata = _safe_capsule_source(source, logical_path=logical_path)
            destination = staging / relative
            if stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(target)
                content = target.encode("utf-8")
                kind = "symlink"
                mode = 0
            else:
                content, mode = _copy_regular_capsule_input(
                    source,
                    destination,
                    logical_path=logical_path,
                )
                kind = "file"
            digest_entries.append((logical_path, kind, content))
            records.append(
                {
                    "logicalPath": logical_path,
                    "capsulePath": relative,
                    "kind": kind,
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                    "mode": mode,
                }
            )
        if active_manifests is not None:
            dependency_records: list[dict[str, object]] | None = None
            for reused_capsule, candidate_records in _matching_dependency_capsules(
                capsule_root=capsule_root,
                expected=active_manifests,
            ):
                print(
                    "[package-capsule-stage] clone-verify-dependencies: dispatch "
                    f"source={reused_capsule.parent.name} timeout={timeout}s",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    payload = _run_capsule_managed_operation(
                        "clone-verify-dependencies",
                        staging=staging,
                        source_capsule=reused_capsule,
                        records=candidate_records,
                        timeout=timeout,
                    )
                except PackageDependencyInputTimeoutError:
                    raise
                except (OSError, TypeError, UnicodeError, ValueError) as error:
                    if (staging / "dependencies").exists():
                        remove_private_tree(staging / "dependencies")
                    raise PackageDependencyDonorIntegrityError(
                        f"{PackageDependencyDonorIntegrityError.code}: "
                        f"identity-matching donor {reused_capsule.parent.name} "
                        "failed clone or component CAS"
                    ) from error
                raw_records = payload.get("records")
                if not isinstance(raw_records, list):
                    raise ValueError("managed cloned dependency records are invalid")
                dependency_records = [
                    dict(item) for item in raw_records if isinstance(item, Mapping)
                ]
                break
            if dependency_records is None:
                print(
                    "[package-capsule-stage] materialize-active: dispatch "
                    f"timeout={timeout}s",
                    file=sys.stderr,
                    flush=True,
                )
                payload = _run_capsule_managed_operation(
                    "materialize-active", staging=staging, timeout=timeout
                )
                raw_records = payload.get("records")
                if not isinstance(raw_records, list):
                    raise ValueError("managed dependency records are invalid")
                dependency_records = [
                    dict(item) for item in raw_records if isinstance(item, Mapping)
                ]
            for record in dependency_records:
                marker_path = staging / str(record["capsulePath"])
                content = marker_path.read_bytes()
                digest_entries.append((str(record["logicalPath"]), "file", content))
                records.append(record)
        input_digest, input_count = _digest_record(digest_entries)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_pkg.ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        source_revision = revision.stdout.strip()
        if revision.returncode != 0 or len(source_revision) != 40:
            raise ValueError("cannot resolve workspace source revision")
        repo_roots = [
            value for value in normalized_roots if not Path(value).is_absolute()
        ]
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v2",
                "-z",
                "--untracked-files=all",
                "--",
                *repo_roots,
            ],
            cwd=_pkg.ROOT,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0:
            raise ValueError("cannot resolve workspace index/worktree state")
        identity = _capsule_identity_payload(
            roots=normalized_roots,
            input_digest=input_digest,
            input_count=input_count,
        )
        baseline_id = _baseline_id(identity)
        manifest = {
            "schema": PACKAGE_INPUT_CAPSULE_SCHEMA,
            "baselineId": baseline_id,
            "sourceRevision": source_revision,
            "workspaceStatusDigest": "sha256:"
            + hashlib.sha256(status.stdout).hexdigest(),
            **identity,
            "entries": records,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        head = staging / "repo/.git/HEAD"
        head.parent.mkdir(parents=True, exist_ok=True)
        head.write_text(source_revision + "\n", encoding="ascii")
        os.chmod(head, 0o444)
        # Dependency writers/clone verification already seal their own trees.
        # Rewalking ~65k dependency nodes here would add another unbounded
        # metadata pass in the parent process.  Seal only parent-owned source
        # trees; final managed full verification still checks every entry.
        for owned_root in (staging / "repo", staging / "external"):
            if not owned_root.exists():
                continue
            for directory in sorted(
                (
                    path
                    for path in owned_root.rglob("*")
                    if path.is_dir() and not path.is_symlink()
                ),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                os.chmod(directory, 0o555)
            os.chmod(owned_root, 0o555)
        os.chmod(staging / "manifest.json", 0o444)
        os.chmod(staging, 0o555)
        staging.replace(capsule_root)
        published = True
        try:
            print(
                f"[package-capsule-stage] verify-full: dispatch timeout={timeout}s",
                file=sys.stderr,
                flush=True,
            )
            verified_payload = _run_capsule_managed_operation(
                "verify-full",
                staging=capsule_root,
                expected_snapshot=manifest,
                timeout=timeout,
            )
            if (
                verified_payload.get("baselineId") != manifest["baselineId"]
                or verified_payload.get("deploymentInputDigest")
                != manifest["deploymentInputDigest"]
            ):
                raise ValueError("managed full capsule verification identity mismatch")
        except BaseException:
            remove_private_tree(capsule_root)
            published = False
            raise
        return {**manifest, "capsuleRoot": str(capsule_root)}
    finally:
        if not published and staging.exists():
            remove_private_tree(staging)


def _read_capsule_manifest(capsule_root: Path) -> dict[str, object]:
    if capsule_root.is_symlink() or not capsule_root.is_dir():
        raise ValueError("package input capsule root is missing or unsafe")
    path = capsule_root / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("package input capsule manifest is missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _CAPSULE_FIELDS:
        raise ValueError("package input capsule manifest fields mismatch")
    if value.get("schema") != PACKAGE_INPUT_CAPSULE_SCHEMA:
        raise ValueError("package input capsule schema mismatch")
    return value


@dataclass(frozen=True, slots=True)
class VerifiedPackageInputCapsule:
    manifest: dict[str, object]
    dependency_snapshots: VerifiedDependencySnapshots | None


def _verify_package_input_capsule(
    capsule_root: Path,
    *,
    expected_snapshot: dict[str, object] | None = None,
) -> VerifiedPackageInputCapsule:
    """Verify capsule bytes once and retain current-process dependency CAS."""

    manifest = _read_capsule_manifest(capsule_root)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("package input capsule entry set is empty")
    entries: list[tuple[str, str, bytes]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _CAPSULE_ENTRY_FIELDS:
            raise ValueError("package input capsule entry fields mismatch")
        relative = Path(str(raw.get("capsulePath") or ""))
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            raise ValueError("package input capsule path is unsafe")
        path = capsule_root / relative
        kind = str(raw.get("kind") or "")
        declared_mode = raw.get("mode")
        if declared_mode.__class__ is not int:
            raise ValueError("package input capsule entry mode is invalid")
        if kind == "file":
            if declared_mode not in {0o444, 0o555}:
                raise ValueError("package input capsule entry mode is invalid")
        elif kind == "symlink":
            if declared_mode != 0:
                raise ValueError("package input capsule entry mode is invalid")
        else:
            raise ValueError("package input capsule entry kind is invalid")
        metadata = path.lstat()
        if kind == "file":
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise ValueError("package input capsule file kind drifted")
            content = path.read_bytes()
            if stat.S_IMODE(metadata.st_mode) != declared_mode:
                raise ValueError("package input capsule file mode drifted")
        elif kind == "symlink":
            if not stat.S_ISLNK(metadata.st_mode):
                raise ValueError("package input capsule symlink kind drifted")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(capsule_root.resolve()):
                raise ValueError("package input capsule symlink escapes capsule")
            content = os.readlink(path).encode("utf-8")
        declared_size = raw.get("size")
        if (
            isinstance(declared_size, bool)
            or not isinstance(declared_size, int)
            or declared_size < 0
        ):
            raise ValueError("package input capsule entry size is invalid")
        if (
            declared_size != len(content)
            or raw.get("digest") != "sha256:" + hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("package input capsule entry CAS mismatch")
        entries.append((str(raw.get("logicalPath") or ""), kind, content))
    app_lock = capsule_root / "repo/quwoquan_app/pubspec.lock"
    dependency_entries = [
        item
        for item in raw_entries
        if str(item.get("logicalPath") or "").startswith("dependency:")
    ]
    dependency_snapshots: VerifiedDependencySnapshots | None = None
    if app_lock.exists():
        dependency_snapshots = verify_dependency_bundle_capsule(
            capsule_root=capsule_root,
            manifest_entries=raw_entries,
        )
    elif dependency_entries or (capsule_root / "dependencies").exists():
        raise ValueError("App dependency capsule exists without App pubspec.lock")
    digest, count = _digest_record(entries)
    identity = _capsule_identity_payload(
        roots=_normalized_input_roots(list(manifest.get("deploymentInputRoots") or [])),
        input_digest=digest,
        input_count=count,
    )
    if (
        digest != manifest.get("deploymentInputDigest")
        or count != manifest.get("deploymentInputFileCount")
        or _baseline_id(identity) != manifest.get("baselineId")
    ):
        raise ValueError("package input capsule identity CAS mismatch")
    if expected_snapshot is not None:
        for field in (
            "baselineId",
            "sourceRevision",
            "workspaceStatusDigest",
            "deploymentInputRoots",
            "deploymentInputDigest",
            "deploymentInputFileCount",
        ):
            if expected_snapshot.get(field) != manifest.get(field):
                raise ValueError(f"package input capsule {field} mismatch")
    return VerifiedPackageInputCapsule(
        manifest=manifest,
        dependency_snapshots=dependency_snapshots,
    )


def verify_package_input_capsule(
    capsule_root: Path,
    *,
    expected_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    """Verify capsule bytes only; never re-read the mutable workspace."""

    return _verify_package_input_capsule(
        capsule_root,
        expected_snapshot=expected_snapshot,
    ).manifest


def verify_package_input_capsule_with_dependencies(
    capsule_root: Path,
    *,
    expected_snapshot: dict[str, object] | None = None,
) -> VerifiedPackageInputCapsule:
    """Verify once and expose fresh dependency snapshots to the same process."""

    return _verify_package_input_capsule(
        capsule_root,
        expected_snapshot=expected_snapshot,
    )


if __name__ == "__main__":
    _managed_exit = _managed_main()
    if _managed_exit is not None:
        raise SystemExit(_managed_exit)
