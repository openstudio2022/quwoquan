#!/usr/bin/env python3
"""Gate: L2 primer messages must not contradict the Continue button.

If a PrimerMessage tells the user to tap Allow directly while the dialog
uses permissionPrimerContinue (继续), UX breaks. Allowed pattern:
  点「继续」后，请在系统弹窗中选择「允许」
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

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
VALUES = ROOT / "quwoquan_app" / "lib" / "core" / "constants" / "ui_text_constants_values.dart"

FORBIDDEN = re.compile(r"请点[「\"]允许[」\"]")
PRIMER_MESSAGE = re.compile(
    r"static const String (\w*PrimerMessage\w*)\s*=\s*'([^']*)';"
)


def main() -> int:
    if not VALUES.is_file():
        print(f"FAIL: missing {VALUES}")
        return 1
    text = VALUES.read_text(encoding="utf-8")
    violations: list[str] = []
    for name, body in PRIMER_MESSAGE.findall(text):
        if FORBIDDEN.search(body) and "继续" not in body:
            violations.append(f"{name}: {body!r}")
        if FORBIDDEN.search(body) and "系统弹窗" not in body:
            violations.append(
                f"{name}: uses 请点允许 without 系统弹窗 context: {body!r}"
            )
    if violations:
        print("FAIL: primer copy contradicts Continue / system sheet flow:")
        for line in violations:
            print(f"  - {line}")
        return 1
    print("OK: permission primer copy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
