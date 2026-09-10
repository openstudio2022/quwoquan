"""独立发布仓的只读身份与扫描边界；不创建仓、不猜旧池。"""
from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

CANONICAL_ROOTS = frozenset({"entities", "posts", "creators", "tags"})
REPOSITORY_FILES = frozenset({"repository.json", ".gitignore"})
REPOSITORY_DIRECTORIES = frozenset({".git", "releases"})


class PublishRepositoryError(ValueError):
    """根缺失、身份漂移与非法文件分别可诊断。"""


def _regular_root(root: Path) -> Path:
    absolute = root.expanduser().absolute()
    if ".." in absolute.parts:
        raise PublishRepositoryError("DATA.REPOSITORY.PATH_INVALID")
    for part in (*reversed(absolute.parents), absolute):
        if part.is_symlink():
            raise PublishRepositoryError(f"DATA.REPOSITORY.SYMLINK: {part}")
    if not absolute.is_dir():
        raise PublishRepositoryError(f"DATA.REPOSITORY.MISSING: {absolute}")
    return absolute


def require_publish_repository(root: Path, *, expected_repository_id: str | None = None) -> dict[str, Any]:
    from core.paths import REPO_ROOT
    from core.schema import assert_valid

    absolute = _regular_root(root)
    if absolute == REPO_ROOT or REPO_ROOT in absolute.parents:
        raise PublishRepositoryError("DATA.REPOSITORY.SOURCE_WORKTREE_FORBIDDEN")
    marker = absolute / "repository.json"
    if marker.is_symlink():
        raise PublishRepositoryError("DATA.REPOSITORY.SYMLINK: repository.json")
    if not marker.is_file():
        raise PublishRepositoryError("DATA.REPOSITORY.MISSING: repository.json")
    try:
        document = json.loads(marker.read_bytes())
        assert_valid(document, "publish", "repository")
    except (ValueError, TypeError) as exc:
        raise PublishRepositoryError("DATA.REPOSITORY.IDENTITY_INVALID") from exc
    if expected_repository_id is not None and document["repositoryId"] != expected_repository_id:
        raise PublishRepositoryError("DATA.REPOSITORY.IDENTITY_MISMATCH")
    git_dir = absolute / ".git"
    if git_dir.is_symlink():
        raise PublishRepositoryError("DATA.REPOSITORY.SYMLINK: .git")
    if not git_dir.is_dir():
        raise PublishRepositoryError("DATA.REPOSITORY.GIT_ROOT_REQUIRED: 独立仓不得是 linked worktree")
    return document


def repository_sidecar_root(root: Path) -> Path:
    require_publish_repository(root)
    sidecar = root.expanduser().absolute() / ".git" / "qwq-publish"
    if sidecar.is_symlink():
        raise PublishRepositoryError("DATA.REPOSITORY.SYMLINK: shared sidecar")
    if sidecar.exists() and not sidecar.is_dir():
        raise PublishRepositoryError("DATA.REPOSITORY.SIDECAR_INVALID")
    return sidecar


def canonical_files(root: Path) -> tuple[Path, ...]:
    """只遍历声明的对象根；拒绝未知根，不把 Git 对象算进发布摘要。"""
    require_publish_repository(root)
    for entry in root.iterdir():
        if entry.is_symlink():
            raise PublishRepositoryError(f"DATA.REPOSITORY.SYMLINK: {entry.name}")
        expected_directory = entry.name in CANONICAL_ROOTS | REPOSITORY_DIRECTORIES
        expected_file = entry.name in REPOSITORY_FILES
        if not ((expected_directory and entry.is_dir()) or (expected_file and entry.is_file())):
            raise PublishRepositoryError(f"DATA.REPOSITORY.ROOT_ENTRY_INVALID: {entry.name}")
    return tuple(path for name in sorted(CANONICAL_ROOTS) for path in _object_files(root / name))


def _object_files(base: Path) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in sorted(base.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise PublishRepositoryError(f"DATA.REPOSITORY.SYMLINK: {path}")
        if stat.S_ISREG(mode):
            result.append(path)
        elif not stat.S_ISDIR(mode):
            raise PublishRepositoryError(f"DATA.REPOSITORY.SPECIAL_FILE: {path}")
    return tuple(result)
