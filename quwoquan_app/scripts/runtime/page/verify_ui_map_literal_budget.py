#!/usr/bin/env python3
"""App UI 层 `Map<String, dynamic>` 零容忍门禁。

UI 层由三处组成，页面、壳层与设计系统都不得用弱类型 Map 承载展示模型：
  lib/service/**/presentation/**  对象级页面与展示模型
  lib/runtime/shell/**            应用壳
  lib/design_system/**            设计系统

存量债务已于预算基线 `expires_when` 条件（计数归零）达成时清零，基线文件随之
退役。本门禁自此零容忍：任何命中即 exit 1 并逐条列出。任一扫描根缺失 →
exit 2：目录被搬走而计数静默归零，会让门禁在债务重新出现时显示为绿。
"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

import re

ROOT = REPO_ROOT
APP_LIB = ROOT / "quwoquan_app" / "lib"
UI_SCAN_ROOTS = (
    APP_LIB / "service",
    APP_LIB / "runtime" / "shell",
    APP_LIB / "design_system",
)
PRESENTATION_SEGMENT = "presentation"
MAP_RE = re.compile(r"Map<String,\s*dynamic>")


def missing_scan_roots() -> list[Path]:
    return [root for root in UI_SCAN_ROOTS if not root.is_dir()]


def _is_ui_file(path: Path) -> bool:
    if path.name.endswith(".g.dart"):
        return False
    # service/ 下只有对象的 presentation 层属于 UI；application/domain/adapters
    # 的弱类型由各自的分层门禁负责。
    if path.is_relative_to(APP_LIB / "service"):
        return PRESENTATION_SEGMENT in path.parts
    return True


def find_ui_hits() -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for root in UI_SCAN_ROOTS:
        for path in sorted(root.rglob("*.dart")):
            if not _is_ui_file(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for _ in MAP_RE.finditer(line):
                    hits.append((path, line_number, line.strip()))
    return hits


def main() -> int:
    missing = missing_scan_roots()
    if missing:
        joined = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        print(
            f"verify_ui_map_literal_budget: BLOCK: missing UI scan root(s) {joined} "
            f"(update UI_SCAN_ROOTS after moving UI code; a silent zero count hides debt)",
            file=sys.stderr,
        )
        return 2

    hits = find_ui_hits()
    if hits:
        print(
            f"verify_ui_map_literal_budget: FAIL: {len(hits)} ui "
            f"Map<String,dynamic> occurrence(s); the UI layer is zero-tolerance — "
            f"decode at the JSON boundary and project into a typed presentation model",
            file=sys.stderr,
        )
        for path, line_number, line in hits:
            print(
                f"  - {path.relative_to(ROOT)}:{line_number}: {line}",
                file=sys.stderr,
            )
        return 1

    print("verify_ui_map_literal_budget: ok ui Map<String,dynamic> count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
