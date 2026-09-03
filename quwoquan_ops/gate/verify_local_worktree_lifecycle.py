#!/usr/bin/env python3
"""本地 worktree 生命周期门禁：hooks、实时身份与滞留事实。"""

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
        return [
            f"{policy.failure_code('hooks_not_installed')}: 缺少 hook 目录 {policy.hooks_path}"
        ]
    for name in REQUIRED_HOOKS:
        if not (hook_dir / name).is_file():
            issues.append(
                f"{policy.failure_code('hooks_not_installed')}: "
                f"缺少 hook 文件 {policy.hooks_path}/{name}"
            )
    return issues


def run(*, as_json: bool, require_all_lanes: bool = False) -> int:
    try:
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
    except Exception as exc:  # noqa: BLE001 - 策略不可读即门禁不成立
        print(f"FAIL: OPS.WORKTREE.POLICY_INVALID: {exc}")
        return 2

    issues = _check_hook_files(policy)
    if not inventory.hooks_installed(policy=policy):
        issues.append(
            f"{policy.failure_code('hooks_not_installed')}: core.hooksPath 未指向 "
            f"{policy.hooks_path}；修复：{policy.install_command}"
        )

    summary: dict[str, object]
    try:
        copies = inventory.discover_work_copies(policy=policy)
        issues.extend(
            inventory.validate_worktree_identity(
                copies,
                policy,
                require_all_lanes=require_all_lanes,
                repo_root=ROOT,
            )
        )
        summary = inventory.summarize(copies, policy)
    except inventory.InventoryError as exc:
        # authority 失败是门禁问题，不用空列表冒充「没有 worktree」。
        issues.append(f"{exc.code}: {exc.detail}")
        summary = {"inventoryError": {"code": exc.code, "detail": exc.detail}}
    except Exception as exc:  # noqa: BLE001 - 未知 probe 错误同样 fail-closed
        issues.append(f"{inventory.INVENTORY_UNAVAILABLE}: unexpected inventory failure: {exc}")
        summary = {
            "inventoryError": {
                "code": inventory.INVENTORY_UNAVAILABLE,
                "detail": str(exc),
            }
        }

    rows = summary.get("items") if isinstance(summary, dict) else []
    rows = rows if isinstance(rows, list) else []
    for item in rows:
        if not item.get("overdue"):
            continue
        issues.append(
            f"{policy.failure_code('unmerged_overdue')}: {item['path']} 滞留 "
            f"{item['staleDays']} 天（ahead={item['ahead']} dirty={item['dirty']} "
            f"stash={item['stashes']}）；长期 lane 在 integration/abort 后 "
            "fast-forward resync 到 canonical dev1.0 并保留 worktree；"
            "额外 clone 或废弃副本再由人工决定是否删除"
        )

    if as_json:
        print(
            json.dumps(
                {
                    "issues": issues,
                    "summary": summary,
                    "requireAllLanes": require_all_lanes,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if issues else 0

    if issues:
        print(f"FAIL: 本地 worktree 生命周期发现 {len(issues)} 个问题")
        for issue in issues:
            print(f"  - {issue}")
        return 2

    pending = summary.get("withUnmergedWork") or 0
    total = summary.get("totalWorkCopies") or 0
    lane_mode = "；六条 lane 身份齐备" if require_all_lanes else ""
    print(
        f"PASS: hooks 已安装；工作副本 {total} 个，其中 {pending} 个含未合入工作，"
        f"无超过 {policy.unmerged_reminder_after_days} 天的滞留项{lane_mode}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    parser.add_argument(
        "--require-all-lanes",
        action="store_true",
        help="要求六条 fixed lane 各有一个 clean、与 canonical dev1.0 同 HEAD 的 worktree",
    )
    args = parser.parse_args(argv)
    return run(as_json=args.json, require_all_lanes=args.require_all_lanes)


if __name__ == "__main__":
    raise SystemExit(main())
