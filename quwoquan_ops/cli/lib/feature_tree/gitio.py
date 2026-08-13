"""git 增量与 HEAD 文本读取。"""
from __future__ import annotations

import subprocess

from . import context


def git_changed_paths() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=context.REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    parts = result.stdout.decode("utf-8", errors="replace").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(parts):
        item = parts[index]
        if not item:
            break
        status, path = item[:2], item[3:]
        if status[0] in "RC" or status[1] in "RC":
            index += 1
            path = parts[index] if index < len(parts) else path
        paths.append(path)
        index += 1
    return sorted(set(paths))


def git_head_text(rel: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=context.REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""
