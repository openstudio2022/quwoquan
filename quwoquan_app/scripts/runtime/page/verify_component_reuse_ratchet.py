#!/usr/bin/env python3
"""组件复用零缺口门禁：页面禁止私有空态/骨架轮子。

组件收敛主线：空态统一走 `design_system/feedback/app_empty_state.dart` 的
`AppEmptyState`（错误态 `AppPageErrorState`、加载态 `AppRequestFeedback` 同属
反馈层三态积木），骨架统一消费 `AppSkeleton*` 原语。

- 扫描 `lib/**`（`design_system` 除外）的 `class ..EmptyState` / `class ..Skeleton..`；
- 类体已消费统一原语（`AppEmptyState` / `AppSkeleton*`）的页面形状组合类
  不算轮子：骨架行形状必须匹配各页内容布局，组合类正是原语的合法消费形态，
  轮子的判据是「自绘空态结构 / 自绘 shimmer 与灰块」；
- 存量已于基线归零后转为零缺口门：任何命中即 BLOCK，不存在 allowlist。
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

LIB_ROOT = APP_ROOT / "lib"

_PRIVATE_WHEEL = re.compile(
    r"class\s+_?\w*(?:EmptyState|Skeleton)\w*\s+extends\s"
)
_UNIFIED_PRIMITIVES = re.compile(r"\bApp(?:EmptyState|Skeleton\w*)\b")


def _wheel_count(text: str) -> int:
    """统计真轮子：命中命名模式且类体未消费统一原语的类。

    类体按下一个 top-level `class ` 声明（或文件尾）切段；段内出现
    `AppEmptyState` / `AppSkeleton*` 即视为原语组合类，不计数。
    """

    count = 0
    matches = list(_PRIVATE_WHEEL.finditer(text))
    boundaries = [match.start() for match in re.finditer(r"^class\s", text, re.M)]
    for match in matches:
        end = len(text)
        for boundary in boundaries:
            if boundary > match.start():
                end = boundary
                break
        body = text[match.start() : end]
        if not _UNIFIED_PRIMITIVES.search(body):
            count += 1
    return count


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(LIB_ROOT.rglob("*.dart")):
        rel = path.relative_to(APP_ROOT).as_posix()
        if rel.startswith("lib/design_system/"):
            continue
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        count = _wheel_count(path.read_text(encoding="utf-8"))
        if count:
            counts[rel] = count
    return counts


def main() -> int:
    counts = scan()
    if counts:
        print("FAIL: 发现私有空态/骨架轮子（零缺口门，禁止新增）：")
        for rel, count in sorted(counts.items()):
            print(
                f"  - {rel}: {count} 个；空态用 AppEmptyState"
                "（区块轻空态用 dense 密度），骨架消费 AppSkeleton* 原语"
            )
        return 1
    print("OK: 无私有空态/骨架轮子（零缺口）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
