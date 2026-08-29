"""Owner-private lifecycle checks for the IDE VM-service auth URI file."""

from __future__ import annotations

import os
import stat
from pathlib import Path

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
WORKSPACE_ENTRYPOINT_BLOCKER = "APP.LAUNCH.workspace_entrypoint_inactive"


class VmServiceInfoSecurityError(ValueError):
    """The IDE VM-service projection no longer satisfies its trust boundary."""


def _blocked(detail: str) -> VmServiceInfoSecurityError:
    return VmServiceInfoSecurityError(f"{WORKSPACE_ENTRYPOINT_BLOCKER}: {detail}")


def _owner_is_current_user(owner: int) -> bool:
    return owner == os.geteuid()


def ensure_private_directory(path: Path) -> None:
    """Create or tighten one owner directory without following a final symlink."""

    try:
        path.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE, exist_ok=True)
        observed = path.lstat()
    except OSError as error:
        raise _blocked(f"unable to prepare private directory {path}: {error}") from error
    if not stat.S_ISDIR(observed.st_mode):
        raise _blocked(f"private directory must be a non-symlink directory: {path}")
    if not _owner_is_current_user(observed.st_uid):
        raise _blocked(f"private directory owner is not the current user: {path}")
    try:
        path.chmod(PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
        secured = path.lstat()
    except OSError as error:
        raise _blocked(f"unable to secure private directory {path}: {error}") from error
    if (
        not stat.S_ISDIR(secured.st_mode)
        or not _owner_is_current_user(secured.st_uid)
        or stat.S_IMODE(secured.st_mode) != PRIVATE_DIRECTORY_MODE
        or (secured.st_dev, secured.st_ino) != (observed.st_dev, observed.st_ino)
    ):
        raise _blocked(f"private directory must remain owner-only 0700: {path}")


def create_private_vm_service_info_file(path: Path) -> None:
    """Exclusively pre-create an empty owner regular file with mode 0600."""

    ensure_private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    except OSError as error:
        raise _blocked(
            f"VM service info file could not be pre-created securely: {error}"
        ) from error
    try:
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or not _owner_is_current_user(observed.st_uid)
            or stat.S_IMODE(observed.st_mode) != PRIVATE_FILE_MODE
        ):
            raise _blocked(
                "VM service info file must be owner regular non-symlink 0600"
            )
    finally:
        os.close(descriptor)
    validate_private_vm_service_info_file(path)


def workspace_projection_vm_service_allowed_root(
    *,
    source_capsule_manifest: Path,
    projection_root: Path,
    output_root: Path,
) -> Path:
    """Derive the original runs root from one verified workspace projection."""

    manifest = source_capsule_manifest.expanduser().absolute()
    projection = projection_root.expanduser().absolute()
    output = output_root.expanduser().absolute()
    try:
        resolved_manifest = manifest.resolve(strict=True)
        resolved_projection = projection.resolve(strict=True)
        resolved_output = output.resolve(strict=True)
    except OSError as error:
        raise _blocked(f"workspace projection handoff is unavailable: {error}") from error
    attempt_root = resolved_manifest.parent.parent
    expected_runs_root = resolved_output / "env/repo/runs"
    if (
        manifest.is_symlink()
        or not manifest.is_file()
        or resolved_manifest != manifest
        or resolved_manifest.name != "manifest.json"
        or resolved_manifest.parent.name != "input-capsule"
        or attempt_root.parent != expected_runs_root
        or resolved_projection != attempt_root / "repo"
        or resolved_projection != projection
        or resolved_output != output
        or projection.is_symlink()
        or not projection.is_dir()
    ):
        raise _blocked(
            "workspace projection does not bind one original output runs root"
        )
    return expected_runs_root


def validate_private_vm_service_info_file(
    path: Path,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Fail closed unless ``path`` remains an owner regular 0600 attempt file."""

    if not path.is_absolute():
        raise _blocked("VM service info path must be absolute")
    if allowed_root is not None:
        try:
            resolved_parent = path.parent.resolve(strict=True)
            resolved_parent.relative_to(allowed_root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise _blocked(
                "VM service info path must be attempt-scoped under "
                ".qwq_output/env/repo/runs"
            ) from error
    try:
        parent = path.parent.lstat()
        observed = path.lstat()
    except FileNotFoundError as error:
        raise _blocked("VM service info file must be pre-created") from error
    except OSError as error:
        raise _blocked(f"VM service info file is unreadable: {error}") from error
    if (
        not stat.S_ISDIR(parent.st_mode)
        or not _owner_is_current_user(parent.st_uid)
        or stat.S_IMODE(parent.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        raise _blocked("VM service info attempt directory must be owner-only 0700")
    if not stat.S_ISREG(observed.st_mode):
        raise _blocked("VM service info file must be a regular non-symlink file")
    if not _owner_is_current_user(observed.st_uid):
        raise _blocked("VM service info file owner is not the current user")
    if stat.S_IMODE(observed.st_mode) != PRIVATE_FILE_MODE:
        raise _blocked("VM service info file mode must remain 0600")
    return path
