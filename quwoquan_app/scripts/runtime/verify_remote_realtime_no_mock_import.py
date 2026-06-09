#!/usr/bin/env python3
"""
阻断 remote realtime 实现重新依赖 chat/mock 或 realtime/mock 目录。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "services"
    / "realtime"
    / "remote_realtime_connection_delegate.dart"
)

FORBIDDEN = re.compile(
    r"""import\s+['"]package:quwoquan_app/cloud/services/(?:chat|realtime)/mock/"""
)


def main() -> int:
    if not TARGET.is_file():
        print(f"verify_remote_realtime_no_mock_import: skip (missing {TARGET})")
        return 0

    text = TARGET.read_text(encoding="utf-8")
    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if FORBIDDEN.search(line):
            violations.append(
                f"  {TARGET.relative_to(ROOT)}:{line_no}: {line.strip()}"
            )

    if violations:
        print(
            "verify_remote_realtime_no_mock_import: FAIL — remote realtime "
            "must not import mock packages:\n" + "\n".join(violations),
            file=sys.stderr,
        )
        return 1

    print("verify_remote_realtime_no_mock_import: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
