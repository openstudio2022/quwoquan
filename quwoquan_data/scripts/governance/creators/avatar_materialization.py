"""Create-once persistence and atomic creator projection for avatar governance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

import yaml
from content.release.canonical import creator_projection
from content.release.canonical.creator_commercial_closure import (
    creator_commercial_closure_issues,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)


class CreatorAvatarError(ValueError):
    """The requested avatar cannot be proven or persisted canonically."""


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _create_once(path: Path, body: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != body:
            raise CreatorAvatarError(f"immutable artifact drift: {path}")
        return False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return True


def _remove_created(path: Path, body: bytes, *, stop: Path) -> None:
    """Roll back only bytes created by this invocation, never pre-existing CAS."""

    if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
        return
    path.unlink()
    parent = path.parent
    while parent != stop and stop in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _replace_bytes_if_unchanged(path: Path, before: bytes, after: bytes) -> None:
    if path.read_bytes() != before:
        raise CreatorAvatarError(f"concurrent creator profile change detected: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(after)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_avatar_asset(
    profile_path: Path,
    avatar_asset: Mapping[str, object],
) -> tuple[bytes, bytes, bool]:
    before = profile_path.read_bytes()
    try:
        profile = yaml.safe_load(before.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CreatorAvatarError(
            f"creator profile unreadable: {profile_path}: {exc}"
        ) from exc
    if not isinstance(profile, dict):
        raise CreatorAvatarError(f"creator profile must be an object: {profile_path}")
    existing = profile.get("avatarAsset")
    if existing is not None:
        if existing != dict(avatar_asset):
            raise CreatorAvatarError(
                f"creator profile already binds a different immutable avatar: {profile_path}"
            )
        return before, before, False
    block = yaml.safe_dump(
        {"avatarAsset": dict(avatar_asset)},
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    after = before.rstrip() + b"\n" + block
    _replace_bytes_if_unchanged(profile_path, before, after)
    return before, after, True


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return ""
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CreatorAvatarError(f"creator projection contains symlink: {path}")
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _assert_replaceable_projection(target: Path) -> None:
    if not target.exists():
        return
    allowed = {
        "_creator.json",
        "profile.json",
        "assets.refs.json",
        "works.refs.ndjson",
    }
    for path in target.rglob("*"):
        if path.is_symlink():
            raise CreatorAvatarError(f"creator projection contains symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(target)
        if relative.parts[0] == "rights_snapshots" and path.suffix == ".json":
            continue
        if len(relative.parts) != 1 or relative.name not in allowed:
            raise CreatorAvatarError(f"creator projection owns unexpected file: {path}")


def _project_creator(creator_ref: str, *, publish_root: Path) -> bool:
    creators_root = publish_root / "creators"
    creators_root.mkdir(parents=True, exist_ok=True)
    target = creators_root / creator_ref
    _assert_replaceable_projection(target)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{creator_ref}.avatar.", dir=creators_root)
    )
    backup = creators_root / f".{creator_ref}.backup.{os.getpid()}"
    failed = creators_root / f".{creator_ref}.failed.{os.getpid()}"
    had_target = target.is_dir()
    try:
        creator_projection.project_creator_object(creator_ref, staging)
        if had_target and _tree_digest(target) == _tree_digest(staging):
            return False
        if backup.exists() or failed.exists():
            raise CreatorAvatarError("stale creator projection swap artifact exists")
        if had_target:
            os.replace(target, backup)
        os.replace(staging, target)
        issues = creator_commercial_closure_issues(
            publish_root,
            creator_refs=[creator_ref],
        )
        if issues:
            raise CreatorAvatarError(
                f"projected creator commercial closure failed: {issues}"
            )
        if backup.is_dir():
            shutil.rmtree(backup)
        return True
    except (OSError, ValueError, ObjectTransactionError):
        if target.is_dir() and backup.is_dir():
            os.replace(target, failed)
            os.replace(backup, target)
            shutil.rmtree(failed, ignore_errors=True)
        elif target.is_dir() and not had_target:
            shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def persist_creator_avatar(
    *,
    creator_ref: str,
    profile_path: Path,
    publish_root: Path,
    creator_pool_root: Path,
    object_key: str,
    derivative_body: bytes,
    rights_ref: str,
    rights_document: Mapping[str, object],
    avatar_asset: Mapping[str, object],
) -> dict[str, bool]:
    """Persist immutable bytes/evidence, then update and project one profile."""

    cas_path = publish_root / object_key
    rights_path = creator_pool_root / rights_ref
    rights_body = _json_bytes(rights_document)
    cas_created = False
    rights_created = False
    try:
        cas_created = _create_once(cas_path, derivative_body)
        rights_created = _create_once(rights_path, rights_body)
    except (OSError, ValueError) as exc:
        if cas_created:
            _remove_created(cas_path, derivative_body, stop=publish_root)
        if rights_created:
            _remove_created(rights_path, rights_body, stop=creator_pool_root)
        if isinstance(exc, CreatorAvatarError):
            raise
        raise CreatorAvatarError(
            f"avatar immutable artifact write failed: {exc}"
        ) from exc
    before = b""
    after = b""
    profile_changed = False
    try:
        before, after, profile_changed = _append_avatar_asset(
            profile_path, avatar_asset
        )
        projection_changed = _project_creator(creator_ref, publish_root=publish_root)
    except (OSError, ValueError, ObjectTransactionError) as exc:
        if profile_changed and profile_path.read_bytes() == after:
            _replace_bytes_if_unchanged(profile_path, after, before)
        if cas_created:
            _remove_created(cas_path, derivative_body, stop=publish_root)
        if rights_created:
            _remove_created(rights_path, rights_body, stop=creator_pool_root)
        if isinstance(exc, CreatorAvatarError):
            raise
        raise CreatorAvatarError(f"creator avatar projection failed: {exc}") from exc
    return {
        "cas": cas_created,
        "rights": rights_created,
        "profile": profile_changed,
        "projection": projection_changed,
    }


__all__ = [
    "CreatorAvatarError",
    "persist_creator_avatar",
]
