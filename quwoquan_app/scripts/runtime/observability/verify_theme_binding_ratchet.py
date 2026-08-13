#!/usr/bin/env python3
"""主题绑定门禁：业务层禁止硬绑单侧主题，`isDark ?` 三元只减不增。

深浅色收敛主线：语义色统一经 `AppColorsFunctional.getColor(isDark, ColorType.*)`、
`AppColors.ios*(context)` 动态色或 Theme 消费；页面不得直接锁定
`AppColors.light.*` / `AppColors.dark.*`（会在另一模式下渲染错误表面），
也不得继续扩散 `isDark ?` 手写三元分支。

- 规则 A（零容忍）：`lib/**`（`design_system` token 定义层除外）出现
  `AppColors.light.` 或 `AppColors.dark.` 即 BLOCK。
- 规则 B（棘轮）：`isDark ?` 三元按文件与 `theme_binding_baseline.json`
  比较，超出即 BLOCK；下降后运行 `--update-baseline` 固化。
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
BASELINE_PATH = Path(__file__).with_name("theme_binding_baseline.json")

_HARD_BINDING = re.compile(r"AppColors\.(?:light|dark)\.")
_ISDARK_TERNARY = re.compile(r"\bisDark\s*\?")


def _business_dart_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(LIB_ROOT.rglob("*.dart")):
        rel = path.relative_to(APP_ROOT).as_posix()
        if rel.startswith("lib/design_system/"):
            continue
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        files.append(path)
    return files


def main() -> int:
    update = "--update-baseline" in sys.argv
    hard_bindings: list[str] = []
    ternary_counts: dict[str, int] = {}

    for path in _business_dart_files():
        rel = path.relative_to(APP_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _HARD_BINDING.search(line):
                hard_bindings.append(f"{rel}:{line_no}: {line.strip()}")
        count = len(_ISDARK_TERNARY.findall(text))
        if count:
            ternary_counts[rel] = count

    if update:
        write_counts(BASELINE_PATH, ternary_counts)
        print(
            f"OK: isDark 三元基线已更新（{sum(ternary_counts.values())} 处 / "
            f"{len(ternary_counts)} 文件）"
        )

    errors: list[str] = []
    if hard_bindings:
        errors.append(
            "业务层禁止硬绑单侧主题（改用 AppColorsFunctional.getColor / "
            "AppColors.ios*(context)）："
        )
        errors.extend(f"  - {hit}" for hit in hard_bindings)

    if not update:
        if not BASELINE_PATH.is_file():
            print(
                "FAIL: 缺少 theme_binding_baseline.json，先运行 --update-baseline 固化存量"
            )
            return 1
        baseline = load_counts(BASELINE_PATH)
        for rel, count in sorted(ternary_counts.items()):
            allowed = baseline.get(rel, 0)
            if count > allowed:
                errors.append(
                    f"  - {rel}: isDark 三元 {count} 处，超出基线 {allowed}；"
                    "新明暗差异请收进 ColorType/主题动态色"
                )

    if errors:
        print("FAIL: 主题绑定门禁未通过：")
        for error in errors:
            print(error)
        return 1
    if not update:
        print(
            f"OK: 业务层无单侧主题硬绑；isDark 三元 "
            f"{sum(ternary_counts.values())} 处未超出基线"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
