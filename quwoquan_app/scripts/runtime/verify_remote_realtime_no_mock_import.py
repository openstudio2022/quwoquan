#!/usr/bin/env python3
"""阻断 production realtime 重新引入 Mock、fixture 或运行时模式切换。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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
