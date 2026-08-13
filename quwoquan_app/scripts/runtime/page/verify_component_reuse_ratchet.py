#!/usr/bin/env python3
"""组件复用棘轮门禁：页面私有空态/骨架实现只减不增。

组件收敛主线：空态统一走 `design_system/feedback/app_empty_state.dart` 的
`AppEmptyState`（错误态 `AppPageErrorState`、加载态 `AppRequestFeedback` 同属
反馈层三态积木）；页面不得再新增私有 `_XxxEmptyState` / `XxxSkeleton` 轮子。

- 扫描 `lib/**`（`design_system` 除外）的 `class ..EmptyState` / `class ..Skeleton..`；
- 与 `component_reuse_baseline.json` 按文件比较，超出即 BLOCK；
- 下降后运行 `--update-baseline` 固化（基线只减不增）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT
from _common.ratchet_baseline import load_counts, write_counts

LIB_ROOT = APP_ROOT / "lib"
BASELINE_PATH = Path(__file__).with_name("component_reuse_baseline.json")

_PRIVATE_WHEEL = re.compile(
    r"class\s+_?\w*(?:EmptyState|Skeleton)\w*\s+extends\s"
)


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(LIB_ROOT.rglob("*.dart")):
        rel = path.relative_to(APP_ROOT).as_posix()
        if rel.startswith("lib/design_system/"):
            continue
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        count = len(_PRIVATE_WHEEL.findall(path.read_text(encoding="utf-8")))
        if count:
            counts[rel] = count
    return counts


def main() -> int:
    update = "--update-baseline" in sys.argv
    counts = scan()
    if update:
        write_counts(BASELINE_PATH, counts)
        print(
            f"OK: 组件复用基线已更新（私有空态/骨架 {sum(counts.values())} 个 / "
            f"{len(counts)} 文件）"
        )
        return 0

    if not BASELINE_PATH.is_file():
        print("FAIL: 缺少 component_reuse_baseline.json，先运行 --update-baseline")
        return 1
    baseline = load_counts(BASELINE_PATH)

    errors: list[str] = []
    for rel, count in sorted(counts.items()):
        allowed = baseline.get(rel, 0)
        if count > allowed:
            errors.append(
                f"{rel}: 私有空态/骨架 {count} 个，超出基线 {allowed}；"
                "空态请使用 design_system 的 AppEmptyState"
            )
    if errors:
        print("FAIL: 组件复用棘轮未通过（禁止新增私有空态/骨架轮子）：")
        for error in errors:
            print(f"  - {error}")
        return 1
    total_now = sum(counts.values())
    total_baseline = sum(baseline.values())
    suffix = (
        f"（基线 {total_baseline}，已下降；可运行 --update-baseline 固化战果）"
        if total_now < total_baseline
        else ""
    )
    print(f"OK: 私有空态/骨架未超出基线（{total_now} 个）{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
