#!/usr/bin/env python3
"""按当前 worktree 布局选择要启动的 App 树。

dispatcher `flutter` 与 `run.sh` wrapper 都遵守"启动当前所站的那棵树"；cwd 不在任何
本 App 树内时，不再静默退回 wrapper 自身所在树，而是枚举同一仓库（bare/common dir）
下的全部 linked worktree：显式 `--worktree <目录|分支>` 直接命中，TTY 下数字选择，
非 TTY 以 typed blocker 要求显式选择。只读 `git worktree list --porcelain`，不解析
第二份配置，也不写任何状态。

作为 CLI 使用时输出选中树的 `run.sh` 绝对路径（供 bash wrapper `exec`）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ENTRYPOINT_BLOCKER = "APP.LAUNCH.workspace_entrypoint_inactive"
WORKTREE_OPTION = "--worktree"


class WorktreeSelectionError(RuntimeError):
    """无法唯一确定要启动的 App 树。"""


class AppWorktree:
    """一棵含本 App 的 worktree。

    不用 dataclass：本模块由 dispatcher 按物理路径 exec_module 加载而不注册进
    sys.modules，Python 3.9 的 dataclass 字段处理会据此崩溃。
    """

    __slots__ = ("root", "branch")

    def __init__(self, root: Path, branch: str) -> None:
        self.root = root
        self.branch = branch

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, AppWorktree)
            and other.root == self.root
            and other.branch == self.branch
        )

    def __hash__(self) -> int:
        return hash((self.root, self.branch))

    def __repr__(self) -> str:
        return f"AppWorktree(root={self.root!r}, branch={self.branch!r})"

    @property
    def app_dir(self) -> Path:
        return self.root / "quwoquan_app"

    @property
    def run_sh(self) -> Path:
        return self.app_dir / "run.sh"

    @property
    def label(self) -> str:
        return f"{self.root.name} [{self.branch or 'detached'}]"


def is_app_root(candidate: Path) -> bool:
    run_sh = candidate / "run.sh"
    return (
        run_sh.is_file()
        and not run_sh.is_symlink()
        and (candidate / "pubspec.yaml").is_file()
        and (candidate.parent / "quwoquan_ops/cli/stackctl.py").is_file()
    )


def app_root_containing(cwd: Path) -> Path | None:
    """cwd 所在的本 App 树（quwoquan_app 目录）；不在任何树内返回 None。"""
    current = cwd.absolute()
    while True:
        if is_app_root(current):
            return current
        nested = current / "quwoquan_app"
        if is_app_root(nested):
            return nested
        parent = current.parent
        if parent == current:
            return None
        current = parent


def list_app_worktrees(anchor_repo_root: Path) -> list[AppWorktree]:
    """枚举与 anchor 同仓的全部 worktree 中含本 App 的树（按 git 输出顺序）。"""
    completed = subprocess.run(
        ["git", "-C", str(anchor_repo_root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise WorktreeSelectionError(
            f"git worktree list failed for {anchor_repo_root}: {completed.stderr.strip()}"
        )
    worktrees: list[AppWorktree] = []
    root: Path | None = None
    branch = ""
    for line in [*completed.stdout.splitlines(), ""]:
        if line.startswith("worktree "):
            root = Path(line[len("worktree "):].strip())
            branch = ""
        elif line.startswith("branch "):
            branch = line[len("branch "):].strip().removeprefix("refs/heads/")
        elif line == "":
            if root is not None and is_app_root(root / "quwoquan_app"):
                worktrees.append(AppWorktree(root=root.resolve(), branch=branch))
            root = None
            branch = ""
    return worktrees


def _match_explicit(candidates: list[AppWorktree], explicit: str) -> AppWorktree:
    wanted = explicit.strip()
    if not wanted:
        raise WorktreeSelectionError(f"{WORKTREE_OPTION} requires a directory or branch")
    wanted_path = Path(wanted).expanduser()
    matches = [
        candidate
        for candidate in candidates
        if candidate.root.name == wanted
        or candidate.branch == wanted
        or candidate.branch == f"lane/{wanted}"
        or (wanted_path.is_absolute() and wanted_path.resolve() == candidate.root)
    ]
    if len(matches) == 1:
        return matches[0]
    labels = ", ".join(candidate.label for candidate in candidates)
    if not matches:
        raise WorktreeSelectionError(
            f"{WORKTREE_OPTION} {wanted!r} matches no App worktree; available: {labels}"
        )
    raise WorktreeSelectionError(
        f"{WORKTREE_OPTION} {wanted!r} is ambiguous; available: {labels}"
    )


def select_worktree(
    candidates: list[AppWorktree],
    *,
    explicit: str = "",
    interactive: bool,
    prompt_stream=sys.stderr,
    input_stream=sys.stdin,
) -> AppWorktree:
    if not candidates:
        raise WorktreeSelectionError("no App worktree is available")
    if explicit:
        return _match_explicit(candidates, explicit)
    if len(candidates) == 1:
        return candidates[0]
    if not interactive:
        labels = ", ".join(candidate.label for candidate in candidates)
        raise WorktreeSelectionError(
            "multiple App worktrees are available and the terminal is not interactive; "
            f"pass {WORKTREE_OPTION} <directory|branch>: {labels}"
        )
    print("[launcher] 当前目录不在任何 App 工作树内，请选择要启动的工作树：", file=prompt_stream)
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}) {candidate.label}  {candidate.root}", file=prompt_stream)
    print("编号: ", end="", file=prompt_stream, flush=True)
    answer = input_stream.readline().strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(candidates):
        raise WorktreeSelectionError(f"invalid worktree choice {answer!r}")
    return candidates[int(answer) - 1]


def resolve_launch_app_dir(
    *,
    cwd: Path,
    anchor_app_dir: Path,
    explicit: str = "",
    interactive: bool,
) -> Path:
    """返回要启动的 quwoquan_app 目录。

    显式 `--worktree` 优先；否则 cwd 所在树；否则枚举 worktree（单树自动、多树选择）。
    """
    anchor_repo_root = anchor_app_dir.parent
    if explicit:
        return select_worktree(
            list_app_worktrees(anchor_repo_root), explicit=explicit, interactive=interactive
        ).app_dir
    located = app_root_containing(cwd)
    if located is not None:
        return located
    try:
        candidates = list_app_worktrees(anchor_repo_root)
    except WorktreeSelectionError:
        # anchor 不在 git 仓库内（例如被整目录复制的 launcher）：没有第二棵树可选，
        # 唯一可启动的就是 anchor 自身所在树。
        candidates = []
    if not candidates:
        return anchor_app_dir
    return select_worktree(candidates, interactive=interactive).app_dir


def strip_worktree_option(arguments: list[str]) -> tuple[str, list[str]]:
    """从参数中摘出 `--worktree <value>` / `--worktree=<value>`，返回 (value, 其余参数)。"""
    explicit = ""
    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token == WORKTREE_OPTION:
            if index + 1 >= len(arguments):
                raise WorktreeSelectionError(f"{WORKTREE_OPTION} requires a directory or branch")
            explicit = arguments[index + 1]
            index += 2
            continue
        if token.startswith(WORKTREE_OPTION + "="):
            explicit = token.split("=", 1)[1]
            index += 1
            continue
        remaining.append(token)
        index += 1
    return explicit, remaining


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-app-dir", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(WORKTREE_OPTION, dest="worktree", default="")
    arguments = parser.parse_args(argv[1:])
    interactive = sys.stdin.isatty() and sys.stderr.isatty()
    try:
        app_dir = resolve_launch_app_dir(
            cwd=Path(arguments.cwd),
            anchor_app_dir=Path(arguments.anchor_app_dir).resolve(),
            explicit=arguments.worktree,
            interactive=interactive,
        )
    except WorktreeSelectionError as error:
        print(f"GATE_BLOCK: {ENTRYPOINT_BLOCKER}: {error}", file=sys.stderr)
        return 2
    print(app_dir / "run.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
