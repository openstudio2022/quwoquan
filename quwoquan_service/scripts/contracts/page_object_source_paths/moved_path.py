"""定位搬迁后的页面：git 重命名链、同名候选与 entry_widget 收窄。

``git`` 重命名链是最权威证据；其次是 ``lib/**`` 内同名文件唯一匹配。
定位不唯一时一律返回人工裁决项，绝不猜测。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .models import (
    APP_DIR_NAME,
    GIT_RENAME_MAX_HOPS,
    ManualDecision,
    SourcePathFix,
)


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _rename_target_in_commit(
    repository_root: Path, commit: str, old_path: str
) -> str | None:
    """在单个提交的完整 diff 里找 ``old_path`` 的重命名落点。

    不能用 ``git log --diff-filter=R -- <old_path>``：pathspec 会把新路径从 diff
    中裁掉，重命名对就配不上，结果永远为空。必须先定位删除该路径的提交，再看那
    个提交的**全量** ``--name-status``。
    """

    shown = _run_git(
        repository_root,
        ["show", "-M", "--name-status", "--format=", commit],
    )
    for line in shown.splitlines():
        if not line.startswith("R"):
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        _, old, new = fields
        if old == old_path:
            return new
    return None


def git_rename_target(repository_root: Path, relative_from_root: str) -> str | None:
    """沿 git 重命名链正向追一个已消失的路径，返回磁盘上存在的落点。

    链上任一跳落地即返回；追不到磁盘存在的文件则返回 ``None``，把决定权交回
    文件名匹配或人工裁决，绝不返回猜测值。
    """

    current = relative_from_root
    visited = {current}
    for _ in range(GIT_RENAME_MAX_HOPS):
        commit = _run_git(
            repository_root,
            ["log", "--diff-filter=D", "--format=%H", "-1", "--", current],
        ).strip()
        if not commit:
            return None
        target = _rename_target_in_commit(repository_root, commit, current)
        if target is None or target in visited:
            return None
        visited.add(target)
        current = target
        if (repository_root / current).is_file():
            return current
    return None


def _dart_library_text(source: Path) -> str:
    text = source.read_text(encoding="utf-8", errors="ignore")
    chunks = [text]
    for match in re.finditer(r"^\s*part\s+['\"]([^'\"]+)['\"]\s*;", text, re.MULTILINE):
        part = (source.parent / match.group(1)).resolve()
        if part.is_file():
            chunks.append(part.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def defines_entry_widget(source: Path, entry_widget: str) -> bool:
    pattern = re.compile(rf"\bclass\s+{re.escape(entry_widget)}\b")
    return bool(pattern.search(_dart_library_text(source)))


def lib_basename_candidates(app_root: Path, source_path: str) -> list[str]:
    """按文件名在 ``lib/**`` 全树收集候选，返回 App 相对路径。"""

    lib_root = app_root / "lib"
    if not lib_root.is_dir():
        return []
    basename = Path(source_path).name
    return sorted(
        candidate.relative_to(app_root).as_posix()
        for candidate in lib_root.rglob(basename)
        if candidate.is_file()
    )


def references_widget(source: Path, entry_widget: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(entry_widget)}\b")
    return bool(pattern.search(source.read_text(encoding="utf-8", errors="ignore")))


def resolve_moved_path(
    repository_root: Path,
    app_root: Path,
    *,
    page_id: str,
    field_name: str,
    old_path: str,
    entry_widget: str,
    widget_predicate: Callable[[Path, str], bool],
    excluded_paths: frozenset[str],
    missing_reason: str,
) -> SourcePathFix | ManualDecision:
    """定位一个已失效路径的新位置；不唯一即返回人工裁决项，绝不猜测。

    ``git`` 重命名链是最权威证据；其次是 ``lib/**`` 内同名文件唯一匹配。
    ``entry_widget`` 只用来收窄候选（页面必须**定义**它，装配证据必须**引用**它），
    不用来放宽任何判定。
    """

    candidates = [
        candidate
        for candidate in lib_basename_candidates(app_root, old_path)
        if candidate not in excluded_paths
    ]

    rename_target = git_rename_target(repository_root, f"{APP_DIR_NAME}/{old_path}")
    rename_candidate: str | None = None
    if rename_target and rename_target.startswith(f"{APP_DIR_NAME}/lib/"):
        relative = rename_target[len(APP_DIR_NAME) + 1 :]
        if relative not in excluded_paths:
            rename_candidate = relative

    if entry_widget:
        matched = [
            candidate
            for candidate in candidates
            if widget_predicate(app_root / candidate, entry_widget)
        ]
        if matched:
            candidates = matched
        elif candidates:
            return ManualDecision(
                page_id=page_id,
                field_name=field_name,
                old_path=old_path,
                reason=(
                    f"同名候选均与 entry_widget {entry_widget} 无关，"
                    "文件可能已被拆分或改名，需人工裁决"
                ),
                candidates=tuple(candidates),
            )

    if rename_candidate and rename_candidate in candidates:
        return SourcePathFix(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            new_path=rename_candidate,
            method="git_rename",
        )
    if len(candidates) == 1:
        return SourcePathFix(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            new_path=candidates[0],
            method="lib_basename_unique",
        )
    if not candidates:
        return ManualDecision(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            reason=missing_reason,
        )
    return ManualDecision(
        page_id=page_id,
        field_name=field_name,
        old_path=old_path,
        reason="lib/** 下存在多个同名候选且 git 重命名链无法唯一定位，需人工裁决",
        candidates=tuple(candidates),
    )
