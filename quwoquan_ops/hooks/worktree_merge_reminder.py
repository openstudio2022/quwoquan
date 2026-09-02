#!/usr/bin/env python3
"""未合入工作副本的滞留提醒，并顺带交叉自检 git hooks 安装状态。

角色：hook。由 `quwoquan_ops/hooks/post-commit`（提交后必提醒）与两个执行面的会话
开始事件（按最小间隔去重）调用。

行为语义归属：
`specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md`
的 REQ-002 与 REQ-003。

去重状态是可删除运行输出：丢失后只退化为多提醒一次，不会漏报。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 由 harness 或 git hook 调用时命令行没有 `-B`，import 会在源码树留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

_STATE_RELATIVE = "env/repo/local/worktree-governance/cache/last-reminder.json"
# Cursor 侧的提醒挂在 beforeShellExecution，对每条 shell 命令都会触发，因此它必须能在
# 不启动解释器的情况下判断「还没到点」。sentinel 里只有一个 epoch 数字，读它的 bash 因此
# 不需要知道提醒间隔——间隔仍然只由 worktree_policy.yaml 决定，不产生第二份默认值。
_SENTINEL_RELATIVE = "env/repo/local/worktree-governance/cache/next-reminder-at"


def _output_root() -> Path:
    return Path(os.environ.get("QWQ_OUTPUT_ROOT", str(ROOT / ".qwq_output")))


def _state_path() -> Path:
    return _output_root() / _STATE_RELATIVE


def load_state() -> dict[str, object]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(*, at: int, overdue_paths: list[str], next_at: int) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"at": at, "nextAt": next_at, "overduePaths": sorted(overdue_paths)}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        (_output_root() / _SENTINEL_RELATIVE).write_text(f"{next_at}\n", encoding="utf-8")
    except OSError:
        return


def should_emit(state: dict[str, object], *, reason: str, overdue_paths: list[str], interval_hours: int, now: int) -> bool:
    """提交后必提醒；会话开始按最小间隔去重，但出现新的超期副本时立即提醒。"""
    if reason == "commit":
        return True
    previous_at = state.get("at")
    if not isinstance(previous_at, int):
        return True
    if now - previous_at >= interval_hours * 3600:
        return True
    known = state.get("overduePaths")
    known_set = set(known) if isinstance(known, list) else set()
    return bool(set(overdue_paths) - known_set)


def build_message(summary: dict[str, object], *, hooks_ok: bool, policy) -> str:
    lines: list[str] = []
    if not hooks_ok:
        lines.append(
            f"  ! {policy.failure_code('hooks_not_installed')}  "
            "git hooks 未安装，本仓库的提交与推送门禁当前全部失效"
        )
        lines.append(f"    修复：{policy.install_command}")

    items = summary.get("items")
    rows = items if isinstance(items, list) else []
    for item in rows:
        marker = "  !" if item.get("overdue") else "  -"
        code = f"{policy.failure_code('unmerged_overdue')}  " if item.get("overdue") else ""
        lines.append(
            f"{marker} {code}{item.get('path')}  滞留 {item.get('staleDays')} 天  "
            f"ahead={item.get('ahead')} dirty={item.get('dirty')} stash={item.get('stashes')}"
        )
        if item.get("probeError"):
            lines.append(f"    探测失败：{item.get('probeError')}")

    if not lines:
        return ""

    tail = [
        "  处置：长期 lane 在 integration/abort 后 fast-forward resync 到 canonical dev1.0，",
        "  并保留 worktree 供下轮复用；",
        "  clone 或额外废弃副本是否删除仍由人工决定。",
    ] if rows else []
    return "\n".join(["[worktree] 本地工作副本提醒", *lines, *tail])


def collect(policy) -> tuple[dict[str, object], bool, list[str]]:
    import local_worktree_inventory as inventory

    copies = inventory.discover_work_copies(policy=policy)
    summary = inventory.summarize(copies, policy)
    hooks_ok = inventory.hooks_installed(policy=policy)
    items = summary.get("items")
    rows = items if isinstance(items, list) else []
    overdue = [str(row.get("path")) for row in rows if row.get("overdue")]
    return summary, hooks_ok, overdue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=("git", "codex"), default="git")
    parser.add_argument("--reason", choices=("commit", "session"), default="session")
    args = parser.parse_args(argv)

    try:
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
        summary, hooks_ok, overdue = collect(policy)
    except Exception as exc:  # noqa: BLE001 - 提醒失败不得阻断提交或会话，但必须可见
        _emit(args.harness, f"[worktree] 提醒未生效：{exc}")
        return 0

    now = int(time.time())
    state = load_state()
    if not should_emit(
        state,
        reason=args.reason,
        overdue_paths=overdue,
        interval_hours=policy.reminder_min_interval_hours,
        now=now,
    ):
        return 0

    message = build_message(summary, hooks_ok=hooks_ok, policy=policy)
    save_state(
        at=now,
        overdue_paths=overdue,
        next_at=now + policy.reminder_min_interval_hours * 3600,
    )
    if message:
        _emit(args.harness, message)
    return 0


def _emit(harness: str, message: str) -> None:
    """纯文本给 git hook 与 Cursor 的 bash 投递通道，JSON 给 Codex 的 SessionStart。

    Cursor 没有自己的分支：它的 sessionStart 不支持任何输出字段，提醒改由
    `worktree_session_reminder_gate.sh` 在 beforeShellExecution 上包装本命令的纯文本。
    """
    if harness == "codex":
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}},
                ensure_ascii=False,
            )
        )
        return
    print(message)


if __name__ == "__main__":
    raise SystemExit(main())
