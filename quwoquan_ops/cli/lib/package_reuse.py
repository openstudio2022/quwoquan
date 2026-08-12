"""以当前部署输入和完整 runtime package 摘要判定 package 是否可复用。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import uuid4

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    RELEASE_INPUT_CLASSIFICATIONS,
    RUNTIME_CANDIDATE_TYPE,
    validate_candidate_manifest,
)
from quwoquan_ops.cli.lib.output_paths import (
    PACKAGE_ROOT_OVERRIDE_ENV,
    active_deployment_candidate,
    app_deployment_package_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)

ROOT = Path(__file__).resolve().parents[3]
FINGERPRINT_NAME = "package-fingerprint.json"
FINGERPRINT_SCHEMA = "stackctl-package-reuse-fingerprint"
PACKAGE_INPUT_CAPSULE_SCHEMA = "stackctl-package-input-capsule.v1"
PACKAGE_INPUT_CAPSULE_DIRECTORY = "input-capsule"
CURRENTNESS_TIMEOUT_SECONDS = 10.0
PACKAGE_VALIDATION_PURPOSES = frozenset({"self_verify", "currentness"})
_FINGERPRINT_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "candidateType",
        "includeServices",
        "servicePackages",
        "reportRef",
        "baselineId",
        "sourceRevision",
        "workspaceStatusDigest",
        "deploymentInputs",
        "packageContent",
        "releaseInputClassification",
        "contractGraphDigest",
        "graphqlReadRegistry",
    }
)
_DIGEST_FIELDS = frozenset({"digest", "fileCount"})
_DEPLOYMENT_INPUT_FIELDS = frozenset({"roots", "capsuleRef", *_DIGEST_FIELDS})
_CAPSULE_FIELDS = frozenset(
    {
        "schema",
        "baselineId",
        "sourceRevision",
        "workspaceStatusDigest",
        "deploymentInputRoots",
        "deploymentInputDigest",
        "deploymentInputFileCount",
        "entries",
    }
)
_CAPSULE_ENTRY_FIELDS = frozenset(
    {"logicalPath", "capsulePath", "kind", "digest", "size", "mode"}
)


class _UnsafeFingerprintPath(ValueError):
    pass


def _fingerprint_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError(
            "package fingerprint persistence requires O_NOFOLLOW/O_DIRECTORY"
        )
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _fingerprint_file_flags(*, write: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("package fingerprint persistence requires O_NOFOLLOW")
    access = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY
    return access | nofollow | getattr(os, "O_CLOEXEC", 0)


def _absolute_fingerprint_path(path: Path) -> Path:
    expanded = path.expanduser()
    candidate = expanded if expanded.is_absolute() else Path.cwd() / expanded
    normalized = Path(os.path.abspath(candidate))
    if len(normalized.parts) > 1 and normalized.parts[1] in {"tmp", "var"}:
        remainder = normalized.parts[2:]
        alias = Path(normalized.anchor) / normalized.parts[1]
        if alias.is_symlink():
            target = os.readlink(alias)
            expected = f"private/{normalized.parts[1]}"
            if target != expected:
                raise _UnsafeFingerprintPath(
                    f"package fingerprint system path alias is unsafe: {alias}"
                )
            normalized = (Path(normalized.anchor) / target).joinpath(*remainder)
    if not normalized.is_absolute() or not normalized.name:
        raise _UnsafeFingerprintPath("package fingerprint path is unsafe")
    return normalized


def _open_fingerprint_parent(
    path: Path,
    *,
    create: bool,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = _absolute_fingerprint_path(path)
    descriptor = os.open(absolute.anchor, _fingerprint_directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        for part in absolute.parent.parts[1:]:
            try:
                child = os.open(
                    part,
                    _fingerprint_directory_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(
                        part,
                        _fingerprint_directory_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise _UnsafeFingerprintPath(
                        f"package fingerprint parent is unsafe: {part}"
                    ) from exc
            except OSError as exc:
                raise _UnsafeFingerprintPath(
                    f"package fingerprint parent is a symlink or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise _UnsafeFingerprintPath(
                    f"package fingerprint parent is not a directory: {part}"
                )
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_fingerprint_parent(
    path: Path,
    *,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptor, identities = _open_fingerprint_parent(path, create=False)
    os.close(descriptor)
    if identities != expected:
        raise _UnsafeFingerprintPath(
            "package fingerprint parent changed during persistence"
        )


def _fingerprint_entry_info(
    parent_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _UnsafeFingerprintPath(
            f"package fingerprint entry is unsafe: {name}"
        ) from exc


def _atomic_write_fingerprint(path: Path, encoded: bytes) -> None:
    absolute = _absolute_fingerprint_path(path)
    parent_descriptor, identities = _open_fingerprint_parent(
        absolute,
        create=True,
    )
    legacy_temporary = f".{absolute.name}.tmp"
    temporary = f".{absolute.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    expected_identity: tuple[int, int] | None = None
    try:
        if _fingerprint_entry_info(parent_descriptor, legacy_temporary) is not None:
            raise _UnsafeFingerprintPath(
                "package fingerprint legacy temporary path is occupied"
            )
        current = _fingerprint_entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint final path is a symlink or non-regular file"
            )
        descriptor = os.open(
            temporary,
            _fingerprint_file_flags(write=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("package fingerprint temporary write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint temporary path is not a regular file"
            )
        expected_identity = (info.st_dev, info.st_ino)
        os.close(descriptor)
        descriptor = -1

        _revalidate_fingerprint_parent(absolute, expected=identities)
        if _fingerprint_entry_info(parent_descriptor, legacy_temporary) is not None:
            raise _UnsafeFingerprintPath(
                "package fingerprint legacy temporary path is occupied"
            )
        current = _fingerprint_entry_info(parent_descriptor, absolute.name)
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise _UnsafeFingerprintPath(
                "package fingerprint final path is a symlink or non-regular file"
            )
        os.replace(
            temporary,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_exists = False
        os.fsync(parent_descriptor)
        _revalidate_fingerprint_parent(absolute, expected=identities)
        final_descriptor = os.open(
            absolute.name,
            _fingerprint_file_flags(write=False),
            dir_fd=parent_descriptor,
        )
        try:
            final_info = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_info.st_mode)
                or expected_identity != (final_info.st_dev, final_info.st_ino)
            ):
                raise _UnsafeFingerprintPath(
                    "package fingerprint changed after atomic write"
                )
        finally:
            os.close(final_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def fingerprint_path(env_name: str, target_name: str) -> Path:
    return app_deployment_package_dir(env_name, target=target_name) / FINGERPRINT_NAME


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


def _enumerated_deployment_inputs(
    roots: Sequence[str],
) -> tuple[list[str], list[tuple[str, Path, str]]]:
    normalized_roots = _normalized_input_roots(roots)
    repo_roots = [
        value for value in normalized_roots if not Path(value).is_absolute()
    ]
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
        cwd=ROOT,
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
        path = ROOT / relative
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
        if not resolved.is_relative_to(ROOT.resolve()):
            raise ValueError(f"deployment input symlink escapes repository: {logical_path}")
        return metadata
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"deployment input is not a regular file or safe symlink: {logical_path}"
        )
    if not logical_path.startswith("external:"):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(ROOT.resolve()):
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
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ValueError(f"deployment input changed during capsule copy: {logical_path}")
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


def materialize_package_input_capsule(
    roots: Sequence[str],
    *,
    capsule_root: Path,
) -> dict[str, object]:
    """Copy one source closure into a read-only, content-addressed capsule."""

    normalized_roots, source_entries = _enumerated_deployment_inputs(roots)
    capsule_root = capsule_root.expanduser()
    if not capsule_root.is_absolute() or capsule_root.exists() or capsule_root.is_symlink():
        raise ValueError("package input capsule root must be a new absolute path")
    capsule_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{capsule_root.name}.", dir=str(capsule_root.parent))
    )
    published = False
    try:
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
        input_digest, input_count = _digest_record(digest_entries)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
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
            cwd=ROOT,
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
        for directory in sorted(
            (path for path in staging.rglob("*") if path.is_dir() and not path.is_symlink()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o555)
        os.chmod(staging / "manifest.json", 0o444)
        os.chmod(staging, 0o555)
        staging.replace(capsule_root)
        published = True
        return {**manifest, "capsuleRoot": str(capsule_root)}
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


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


def verify_package_input_capsule(
    capsule_root: Path,
    *,
    expected_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    """Verify capsule bytes only; never re-read the mutable workspace."""

    manifest = _read_capsule_manifest(capsule_root)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("package input capsule entry set is empty")
    entries: list[tuple[str, str, bytes]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _CAPSULE_ENTRY_FIELDS:
            raise ValueError("package input capsule entry fields mismatch")
        relative = Path(str(raw.get("capsulePath") or ""))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("package input capsule path is unsafe")
        path = capsule_root / relative
        kind = str(raw.get("kind") or "")
        metadata = path.lstat()
        if kind == "file":
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise ValueError("package input capsule file kind drifted")
            content = path.read_bytes()
            mode = 0o555 if metadata.st_mode & 0o111 else 0o444
            if metadata.st_mode & 0o222 or int(raw.get("mode") or -1) != mode:
                raise ValueError("package input capsule file is writable or mode drifted")
        elif kind == "symlink":
            if not stat.S_ISLNK(metadata.st_mode):
                raise ValueError("package input capsule symlink kind drifted")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(capsule_root.resolve()):
                raise ValueError("package input capsule symlink escapes capsule")
            content = os.readlink(path).encode("utf-8")
        else:
            raise ValueError("package input capsule entry kind is invalid")
        if (
            int(raw.get("size") or -1) != len(content)
            or raw.get("digest") != "sha256:" + hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("package input capsule entry CAS mismatch")
        entries.append((str(raw.get("logicalPath") or ""), kind, content))
    digest, count = _digest_record(entries)
    identity = _capsule_identity_payload(
        roots=_normalized_input_roots(
            list(manifest.get("deploymentInputRoots") or [])
        ),
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
    return manifest


def deployment_input_roots(
    env_name: str,
    target_name: str,
    service_packages: Sequence[str],
    *,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
) -> list[str]:
    """Return the declared source closure actually read by runtime packaging."""

    expected_target = "prod-hosted" if env_name == "prod" else f"{env_name}-local"
    if target_name != expected_target:
        raise ValueError("deployment input closure target/environment mismatch")
    _normalized_service_packages(service_packages)
    roots = {
        # Current Dockerfiles use COPY . . from this build context. Until that
        # context is narrowed, the entire service tree is a real image input.
        "quwoquan_service",
        "quwoquan_service/.dockerignore",
        "quwoquan_service/go.mod",
        "quwoquan_service/go.sum",
        "quwoquan_service/generated/contract_graph.json",
        "quwoquan_service/contracts/metadata",
        "quwoquan_service/tools/codegen_graphql_read_registry",
        "quwoquan_service/scripts/runtime/packaging",
        "quwoquan_app/configs/default/app_runtime.yaml",
        f"quwoquan_app/configs/{env_name}/app_runtime.yaml",
        "quwoquan_app/config/schema.yaml",
        "quwoquan_app/scripts/env/build_app_env_package.sh",
        "quwoquan_app/scripts/env/print_app_env_dart_defines.py",
        "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        "quwoquan_ops/cli/stackctl.py",
        "quwoquan_ops/cli/legal_static.py",
        "quwoquan_ops/cli/print_local_port_profile.py",
        "quwoquan_ops/cli/render_runtime_config.py",
        "quwoquan_ops/cli/lib",
        "quwoquan_ops/environments/domain_governance.yaml",
        "quwoquan_ops/environments/local_env_port_manifest.yaml",
        "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
        "quwoquan_ops/environments/compose/object-storage-lifecycle.json",
        "quwoquan_ops/environments/gamma/local/Caddyfile",
        "quwoquan_ops/environments/external_provider_bindings.yaml",
        "quwoquan_ops/external/livekit/base/livekit.yaml",
        *(f"quwoquan_ops/environments/{name}/runtime.yaml" for name in ("alpha", "beta", "gamma", "prod")),
    }
    for value in (release_attestation, rollback_release_attestation):
        normalized = str(value or "").strip()
        if normalized:
            roots.add(str(Path(normalized).expanduser().absolute()))
    return sorted(roots)


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


def deployment_input_digest(
    roots: Sequence[str],
    *,
    timeout_seconds: float | None = None,
) -> tuple[str, int]:
    """Digest tracked/untracked bytes in the declared package source closure."""

    _normalized_roots, source_entries = _enumerated_deployment_inputs(roots)
    deadline = (
        time.monotonic() + timeout_seconds
        if timeout_seconds is not None and timeout_seconds > 0
        else None
    )

    def entries() -> Iterable[tuple[str, str, bytes]]:
        for logical_path, path, _relative in source_entries:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("deployment input currentness check timed out")
            kind, content = _path_entry(path)
            yield logical_path, kind, content

    return _digest_record(entries())


def workspace_snapshot(
    *,
    deployment_roots: Sequence[str],
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Return one identity bound only to the declared deployment closure."""

    normalized_roots = _normalized_input_roots(deployment_roots)
    repo_roots = [value for value in normalized_roots if not Path(value).is_absolute()]

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or len(source_revision) != 40:
        raise ValueError("cannot resolve workspace source revision")
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
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        detail = status.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot resolve workspace index/worktree state"
            + (f": {detail}" if detail else "")
        )
    input_digest, input_count = deployment_input_digest(
        normalized_roots,
        timeout_seconds=timeout_seconds,
    )
    status_digest = "sha256:" + hashlib.sha256(status.stdout).hexdigest()
    identity_payload = {
        "deploymentInputRoots": normalized_roots,
        "deploymentInputDigest": input_digest,
        "deploymentInputFileCount": input_count,
    }
    return {
        **identity_payload,
        "sourceRevision": source_revision,
        "workspaceStatusDigest": status_digest,
        "baselineId": _baseline_id(identity_payload),
    }


def workspace_drift_details(
    start: dict[str, object],
    end: dict[str, object],
) -> list[str]:
    """Return report-safe evidence when package inputs change mid-flight."""

    closure_fields = (
        "deploymentInputRoots",
        "deploymentInputDigest",
        "deploymentInputFileCount",
    )
    if all(start.get(field) == end.get(field) for field in closure_fields):
        return []
    return [
        "workspace changed while package was being materialized",
        f"startBaselineId={start.get('baselineId', '')}",
        f"endBaselineId={end.get('baselineId', '')}",
        f"startSourceRevision={start.get('sourceRevision', '')}",
        f"endSourceRevision={end.get('sourceRevision', '')}",
        (
            "startWorkspaceStatusDigest="
            f"{start.get('workspaceStatusDigest', '')}"
        ),
        (
            "endWorkspaceStatusDigest="
            f"{end.get('workspaceStatusDigest', '')}"
        ),
        (
            "startDeploymentInputDigest="
            f"{start.get('deploymentInputDigest', '')}"
        ),
        (
            "endDeploymentInputDigest="
            f"{end.get('deploymentInputDigest', '')}"
        ),
    ]


def _expected_service_packages() -> list[str]:
    service_root = ROOT / "quwoquan_service" / "services"
    services = sorted(
        path.name for path in service_root.iterdir() if path.is_dir()
    )
    if (
        ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "config"
        / "schema.yaml"
    ).is_file():
        services.append("platform-ops-service")
    if not services:
        raise ValueError("canonical service package set is empty")
    return sorted(services)


def _normalized_service_packages(values: Sequence[str]) -> list[str]:
    normalized = sorted(str(value).strip() for value in values)
    if (
        not normalized
        or any(not value for value in normalized)
        or len(normalized) != len(set(normalized))
    ):
        raise ValueError("service package identity set is invalid")
    return normalized


def _candidate_service_packages(candidate_root: Path) -> list[str]:
    root = candidate_root / "packages" / "services"
    if not root.is_dir():
        raise ValueError("candidate service package root is missing")
    values = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.is_symlink()
    )
    return _normalized_service_packages(values)


def _package_roots(
    env_name: str,
    target_name: str,
    service_packages: Sequence[str],
    *,
    candidate_root: Path | None = None,
) -> list[tuple[str, Path]]:
    if candidate_root is not None:
        package_root = candidate_root / "packages"
        roots = [
            ("app", package_root / "app"),
            ("runtime-shared", package_root / "runtime-shared"),
        ]
        legal_static = package_root / "legal-static"
        if legal_static.is_dir():
            roots.append(("legal-static", legal_static))
        roots.extend(
            (f"services/{service}", package_root / "services" / service)
            for service in service_packages
        )
        return roots

    roots = [
        (
            "app",
            app_deployment_package_dir(env_name, target=target_name),
        ),
        (
            "runtime-shared",
            runtime_shared_deployment_package_dir(
                env_name,
                target=target_name,
            ),
        ),
    ]
    legal_static = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static.is_dir():
        roots.append(("legal-static", legal_static))
    roots.extend(
        (
            f"services/{service}",
            service_deployment_package_dir(
                env_name,
                service,
                target=target_name,
            ),
        )
        for service in service_packages
    )
    return roots


def package_content_digest(
    env_name: str,
    target_name: str,
    *,
    service_packages: Sequence[str],
    candidate_root: Path | None = None,
) -> tuple[str, int]:
    def entries() -> Iterable[tuple[str, str, bytes]]:
        for logical_root, root in _package_roots(
            env_name,
            target_name,
            service_packages,
            candidate_root=candidate_root,
        ):
            if not root.is_dir():
                raise ValueError(f"package root is missing: {root}")
            paths = []
            for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
                relative = path.relative_to(root).as_posix()
                if logical_root == "app" and relative == FINGERPRINT_NAME:
                    continue
                if path.is_dir() and not path.is_symlink():
                    continue
                paths.append((relative, path))
            if not paths:
                raise ValueError(f"package root has no payload files: {root}")
            for relative, path in paths:
                kind, content = _path_entry(path)
                yield f"{logical_root}/{relative}", kind, content

    return _digest_record(entries())


def write_package_fingerprint(
    env_name: str,
    target_name: str,
    *,
    report_dir: str,
    include_services: bool,
    details: list[str],
    release_input_classification: str,
    contract_graph_digest: str,
    graphql_read_registry: dict[str, object],
    service_packages: Sequence[str] | None = None,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    expected_snapshot: dict[str, object] | None = None,
    candidate_root: Path | None = None,
) -> Path:
    del details
    if not str(report_dir).strip():
        raise ValueError("package fingerprint requires a report reference")
    if not include_services:
        raise ValueError("runtime package fingerprint requires all services")
    if release_input_classification not in RELEASE_INPUT_CLASSIFICATIONS:
        raise ValueError("package fingerprint releaseInputClassification is invalid")
    if (
        not isinstance(contract_graph_digest, str)
        or len(contract_graph_digest) != 71
        or not contract_graph_digest.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in contract_graph_digest[7:]
        )
    ):
        raise ValueError("package fingerprint contractGraphDigest is invalid")
    packages = _normalized_service_packages(
        service_packages
        if service_packages is not None
        else _expected_service_packages()
    )
    roots = deployment_input_roots(
        env_name,
        target_name,
        packages,
        release_attestation=release_attestation,
        rollback_release_attestation=rollback_release_attestation,
    )
    snapshot = expected_snapshot or workspace_snapshot(deployment_roots=roots)
    snapshot_roots = _normalized_input_roots(
        list(snapshot.get("deploymentInputRoots") or roots)
    )
    if snapshot_roots != roots:
        raise ValueError("package snapshot deployment input closure mismatch")
    input_digest = str(snapshot["deploymentInputDigest"])
    input_count = int(snapshot["deploymentInputFileCount"])
    selected_candidate_root = (
        candidate_root
        if candidate_root is not None
        else app_deployment_package_dir(env_name, target=target_name).parent.parent
    )
    verify_package_input_capsule(
        selected_candidate_root / PACKAGE_INPUT_CAPSULE_DIRECTORY,
        expected_snapshot=snapshot,
    )
    content_digest, content_count = package_content_digest(
        env_name,
        target_name,
        service_packages=packages,
        candidate_root=candidate_root,
    )
    path = fingerprint_path(env_name, target_name)
    payload = {
        "schema": FINGERPRINT_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "candidateType": RUNTIME_CANDIDATE_TYPE,
        "includeServices": True,
        "servicePackages": packages,
        "reportRef": str(report_dir),
        "baselineId": snapshot["baselineId"],
        "sourceRevision": snapshot["sourceRevision"],
        "workspaceStatusDigest": snapshot["workspaceStatusDigest"],
        "deploymentInputs": {
            "roots": snapshot_roots,
            "capsuleRef": PACKAGE_INPUT_CAPSULE_DIRECTORY,
            "digest": input_digest,
            "fileCount": input_count,
        },
        "packageContent": {
            "digest": content_digest,
            "fileCount": content_count,
        },
        "releaseInputClassification": release_input_classification,
        "contractGraphDigest": contract_graph_digest,
        "graphqlReadRegistry": graphql_read_registry,
    }
    _atomic_write_fingerprint(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    return path


def _digest_payload(
    value: object,
    *,
    fields: frozenset[str],
    label: str,
) -> tuple[str, int]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} contract fields mismatch")
    digest = value.get("digest")
    file_count = value.get("fileCount")
    if (
        not isinstance(digest, str)
        or len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        raise ValueError(f"{label} digest is invalid")
    if (
        not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count <= 0
    ):
        raise ValueError(f"{label} fileCount is invalid")
    return digest, file_count


def can_reuse_package(
    env_name: str,
    target_name: str,
    *,
    include_services: bool = True,
    required_services: list[str] | None = None,
    purpose: str = "self_verify",
    currentness_timeout_seconds: float = CURRENTNESS_TIMEOUT_SECONDS,
    candidate_root: Path | None = None,
) -> tuple[bool, str]:
    if not include_services:
        return False, "runtime package reuse requires all services"
    if purpose not in PACKAGE_VALIDATION_PURPOSES:
        return False, "runtime package validation purpose is invalid"

    override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV, "").strip()
    active_candidate: dict[str, str] | None
    if candidate_root is None:
        if override:
            return (
                False,
                (
                    "deployment package root override is forbidden for active "
                    "candidate reuse"
                ),
            )
        try:
            active_candidate = active_deployment_candidate(target_name)
        except ValueError as exc:
            return False, f"active candidate rejected: {exc}"
        if active_candidate is None:
            return False, f"missing active candidate: {target_name}"
        active_root = str(active_candidate.get("candidateDir") or "").strip()
        if not active_root:
            return False, "active candidate rejected: candidateDir is missing"
        selected_candidate_root = Path(active_root)
    else:
        active_candidate = None
        selected_candidate_root = Path(candidate_root).expanduser()
        if not selected_candidate_root.is_absolute():
            return False, "explicit candidate root must be absolute"
        if override:
            override_root = Path(override).expanduser()
            if not override_root.is_absolute():
                return False, "deployment package root override must be absolute"
            if override_root != selected_candidate_root / "packages":
                return (
                    False,
                    (
                        "deployment package root override does not match explicit "
                        "candidate root"
                    ),
                )

    path = selected_candidate_root / "packages" / "app" / FINGERPRINT_NAME
    if not path.is_file():
        return False, f"missing fingerprint: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != _FINGERPRINT_FIELDS:
            raise ValueError("fingerprint contract fields mismatch")
        if payload.get("schema") != FINGERPRINT_SCHEMA:
            raise ValueError("fingerprint schema mismatch")
        if payload.get("environment") != env_name:
            raise ValueError("fingerprint environment mismatch")
        if payload.get("target") != target_name:
            raise ValueError("fingerprint target mismatch")
        if payload.get("candidateType") != RUNTIME_CANDIDATE_TYPE:
            raise ValueError("fingerprint candidateType mismatch")
        if (
            not isinstance(payload.get("includeServices"), bool)
            or payload.get("includeServices") is not True
        ):
            raise ValueError("fingerprint includeServices mismatch")
        report_ref = payload.get("reportRef")
        if not isinstance(report_ref, str) or not report_ref.strip():
            raise ValueError("fingerprint reportRef is invalid")
        classification = payload.get("releaseInputClassification")
        if classification not in RELEASE_INPUT_CLASSIFICATIONS:
            raise ValueError("fingerprint releaseInputClassification is invalid")
        contract_graph_digest = payload.get("contractGraphDigest")
        if (
            not isinstance(contract_graph_digest, str)
            or len(contract_graph_digest) != 71
            or not contract_graph_digest.startswith("sha256:")
            or any(
                character not in "0123456789abcdef"
                for character in contract_graph_digest[7:]
            )
        ):
            raise ValueError("fingerprint contractGraphDigest is invalid")
        graphql_read_registry = payload.get("graphqlReadRegistry")
        if not isinstance(graphql_read_registry, dict):
            raise ValueError("fingerprint graphqlReadRegistry is invalid")
        if (
            active_candidate is not None
            and payload.get("baselineId") != active_candidate["baselineId"]
        ):
            raise ValueError("fingerprint active candidate mismatch")
        raw_packages = payload.get("servicePackages")
        if not isinstance(raw_packages, list) or any(
            not isinstance(value, str) for value in raw_packages
        ):
            raise ValueError("fingerprint servicePackages is invalid")
        packages = (
            _normalized_service_packages(raw_packages)
        )
        expected_packages = (
            _normalized_service_packages(required_services)
            if required_services is not None
            else packages
        )
        if packages != expected_packages:
            raise ValueError("fingerprint servicePackages mismatch")
        if packages != _candidate_service_packages(selected_candidate_root):
            raise ValueError("fingerprint servicePackages mismatch")

        deployment_inputs = payload.get("deploymentInputs")
        expected_input_digest, expected_input_count = _digest_payload(
            deployment_inputs,
            fields=_DEPLOYMENT_INPUT_FIELDS,
            label="deploymentInputs",
        )
        declared_roots = deployment_inputs.get("roots")
        if not isinstance(declared_roots, list) or any(
            not isinstance(value, str) for value in declared_roots
        ):
            raise ValueError("deploymentInputs roots mismatch")
        normalized_roots = _normalized_input_roots(declared_roots)
        if declared_roots != normalized_roots:
            raise ValueError("deploymentInputs roots are not canonical")
        if deployment_inputs.get("capsuleRef") != PACKAGE_INPUT_CAPSULE_DIRECTORY:
            raise ValueError("deploymentInputs capsuleRef mismatch")
        capsule_manifest = verify_package_input_capsule(
            selected_candidate_root / PACKAGE_INPUT_CAPSULE_DIRECTORY,
        )
        if (
            capsule_manifest.get("baselineId") != payload.get("baselineId")
            or capsule_manifest.get("sourceRevision") != payload.get("sourceRevision")
            or capsule_manifest.get("workspaceStatusDigest")
            != payload.get("workspaceStatusDigest")
            or capsule_manifest.get("deploymentInputRoots") != normalized_roots
            or capsule_manifest.get("deploymentInputDigest") != expected_input_digest
            or capsule_manifest.get("deploymentInputFileCount") != expected_input_count
        ):
            raise ValueError("deployment input capsule fingerprint binding mismatch")
        if purpose == "currentness":
            snapshot = workspace_snapshot(
                deployment_roots=normalized_roots,
                timeout_seconds=currentness_timeout_seconds,
            )
            actual_input_digest = str(snapshot["deploymentInputDigest"])
            actual_input_count = int(snapshot["deploymentInputFileCount"])
            if (
                actual_input_digest != expected_input_digest
                or actual_input_count != expected_input_count
            ):
                raise ValueError("deployment input digest mismatch")

        expected_content_digest, expected_content_count = _digest_payload(
            payload.get("packageContent"),
            fields=_DIGEST_FIELDS,
            label="packageContent",
        )
        actual_content_digest, actual_content_count = package_content_digest(
            env_name,
            target_name,
            service_packages=packages,
            candidate_root=selected_candidate_root,
        )
        if (
            actual_content_digest != expected_content_digest
            or actual_content_count != expected_content_count
        ):
            raise ValueError("package content digest mismatch")
        candidate_manifest_path = selected_candidate_root / "manifest.json"
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
        validated_candidate = validate_candidate_manifest(
            candidate_manifest,
            expected_environment=env_name,
            expected_target=target_name,
            require_full=True,
            candidate_root=selected_candidate_root,
            purpose=purpose,
            currentness_timeout_seconds=currentness_timeout_seconds,
        )
        manifest_bindings = {
            "baselineId": payload["baselineId"],
            "sourceRevision": payload["sourceRevision"],
            "workspaceStatusDigest": payload["workspaceStatusDigest"],
            "workspaceDigest": expected_input_digest,
            "packageDigest": expected_content_digest,
            "releaseInputClassification": classification,
            "contractGraphDigest": contract_graph_digest,
            "graphqlReadRegistry": graphql_read_registry,
        }
        for field, expected in manifest_bindings.items():
            if validated_candidate.get(field) != expected:
                raise ValueError(f"deployment candidate {field} mismatch")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return False, f"fingerprint rejected: {exc}"
    return (
        True,
        f"reuse ok fingerprint={path} reportRef={payload['reportRef']}",
    )
