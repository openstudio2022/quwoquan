#!/usr/bin/env python3
"""[薄壳] 兼容旧入口：委托 `qwq-data verify`。逻辑已沉到 _common.post_verify。

默认 scope=current（仅当前 schema 的 posts 根）；如需全树审计用 --scope all。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from verify.gate import gate_verify  # noqa: E402


def main() -> None:
    scope = "all" if "--all" in sys.argv else "current"
    roots, issues = gate_verify(scope=scope)
    if issues:
        print(f"[verify-quwoquan-data-post-packages] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues[:200]:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print(f"[verify-quwoquan-data-post-packages] PASSED (roots={len(roots)}, scope={scope})")


if __name__ == "__main__":
    main()
