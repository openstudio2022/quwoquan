#!/usr/bin/env python3
"""本地工作副本生命周期门禁：hooks 安装自检 + 未合入滞留判定。

角色：gate。由 `make verify-local-worktree-lifecycle`（挂在 `make gate` 上）与
`commit_gate_select.py` 的 static checks 调用。

行为语义归属：
`specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md`
的 REQ-002、REQ-003、REQ-004。

这道门必须留在聚合门禁上而不是只挂 pre-commit：hooks 失效时 pre-commit 恰好不会
运行，而那正是最需要发现问题的时刻。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

REQUIRED_HOOKS = ("pre-commit", "pre-push", "post-commit")


def _check_hook_files(policy) -> list[str]:
    issues: list[str] = []
    hook_dir = ROOT / policy.hooks_path
    if not hook_dir.is_dir():
        issues.append(f"{policy.failure_code('hooks_not_installed')}: 缺少 hook 目录 {policy.hooks_path}")
        return issues
    for name in REQUIRED_HOOKS:
        target = hook_dir / name
        if not target.is_file():
            issues.append(f"{policy.failure_code('hooks_not_installed')}: 缺少 hook 文件 {policy.hooks_path}/{name}")
    return issues


def run(*, as_json: bool) -> int:
    try:
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
    except Exception as exc:  # noqa: BLE001 - 策略不可读即门禁不成立，fail-closed
        print(f"FAIL: OPS.WORKTREE.POLICY_INVALID: {exc}")
        return 2

    issues = _check_hook_files(policy)

    if not inventory.hooks_installed(policy=policy):
        issues.append(
            f"{policy.failure_code('hooks_not_installed')}: core.hooksPath 未指向 {policy.hooks_path}；"
            f"提交与推送门禁当前全部失效。修复：{policy.install_command}"
        )

    copies = inventory.discover_work_copies(policy=policy)
    summary = inventory.summarize(copies, policy)
    rows = summary["items"] if isinstance(summary.get("items"), list) else []
    for item in rows:
        if not item.get("overdue"):
            continue
        issues.append(
            f"{policy.failure_code('unmerged_overdue')}: {item['path']} 滞留 {item['staleDays']} 天"
            f"（ahead={item['ahead']} dirty={item['dirty']} stash={item['stashes']}）；"
            "合回 dev1.0 后删除该副本，或确认无用后直接删除该目录"
        )

    if as_json:
        print(json.dumps({"issues": issues, "summary": summary}, ensure_ascii=False, indent=2))
        return 2 if issues else 0

    if issues:
        print(f"FAIL: 本地工作副本生命周期发现 {len(issues)} 个问题")
        for issue in issues:
            print(f"  - {issue}")
        return 2

    pending = summary.get("withUnmergedWork") or 0
    total = summary.get("totalWorkCopies") or 0
    print(
        f"PASS: hooks 已安装；工作副本 {total} 个，其中 {pending} 个含未合入工作，"
        f"无超过 {policy.unmerged_reminder_after_days} 天的滞留项"
    )
    for item in rows:
        print(f"  - {item['path']} 滞留 {item['staleDays']} 天 ahead={item['ahead']} dirty={item['dirty']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    args = parser.parse_args(argv)
    return run(as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
