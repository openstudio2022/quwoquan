#!/usr/bin/env python3
"""阻断 production realtime 重新引入 Mock、fixture 或运行时模式切换。"""

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
REALTIME_ROOT = (
    ROOT / "quwoquan_app" / "lib" / "cloud" / "services" / "realtime"
)

FORBIDDEN = re.compile(
    r"""(?:
        import\s+['"][^'"]*(?:/mock/|quwoquan_cloud_mock|contract_fixture_runtime_loader)
        |appDataSourceModeProvider
        |cloudRepositoryImplForMode
        |MockRealtime
    )""",
    re.VERBOSE,
)


def main() -> int:
    violations: list[str] = []
    for target in sorted(REALTIME_ROOT.rglob("*.dart")):
        text = target.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                violations.append(
                    f"  {target.relative_to(ROOT)}:{line_no}: {line.strip()}"
                )

    if violations:
        print(
            "verify_remote_realtime_no_mock_import: FAIL — production "
            "realtime must be Remote-only:\n" + "\n".join(violations),
            file=sys.stderr,
        )
        return 1

    print("verify_remote_realtime_no_mock_import: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
