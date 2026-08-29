#!/usr/bin/env python3
"""Gate: L2 primer messages must not contradict the Continue button.

If a PrimerMessage tells the user to tap Allow directly while the dialog
uses permissionPrimerContinue (继续), UX breaks. Allowed pattern:
  点「继续」后，请在系统弹窗中选择「允许」
"""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
COPY_DIR = ROOT / "quwoquan_app" / "lib" / "l10n" / "copy"

FORBIDDEN = re.compile(r"请点[「\"]允许[」\"]")
PRIMER_MESSAGE = re.compile(
    r"static const String (\w*PrimerMessage\w*)\s*=\s*'([^']*)';"
)


def main() -> int:
    if not COPY_DIR.is_dir():
        print(f"FAIL: missing copy dir {COPY_DIR}")
        return 1
    violations: list[str] = []
    primer_count = 0
    for dart_file in sorted(COPY_DIR.rglob("*.dart")):
        text = dart_file.read_text(encoding="utf-8")
        for name, body in PRIMER_MESSAGE.findall(text):
            primer_count += 1
            if FORBIDDEN.search(body) and "继续" not in body:
                violations.append(f"{dart_file.name}:{name}: {body!r}")
            if FORBIDDEN.search(body) and "系统弹窗" not in body:
                violations.append(
                    f"{dart_file.name}:{name}: "
                    f"uses 请点允许 without 系统弹窗 context: {body!r}"
                )
    if primer_count == 0:
        # 零匹配意味着扫描目标失效（常量迁移/改名），门禁必须显式红而非静默通过。
        print(f"FAIL: no *PrimerMessage* constants found under {COPY_DIR}")
        return 1
    if violations:
        print("FAIL: primer copy contradicts Continue / system sheet flow:")
        for line in violations:
            print(f"  - {line}")
        return 1
    print(f"OK: permission primer copy ({primer_count} constants)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
