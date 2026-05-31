#!/usr/bin/env python3
"""CLI-first ratchet 门禁：拦截新增的直跑业务入口脚本。

规则：`quwoquan_data/scripts/**/*.py` 含 `if __name__ == "__main__":` 的文件，
必须在 `cli_first_allowlist.txt` 基线内。新增业务能力应实现为
`<command>/handler.py(register_parser)` + `_common/` 逻辑库，经 `qwq-data` 暴露给 skill。

新增直跑脚本 -> FAIL；允许的历史脚本逐步薄壳化（删除 allowlist 行即收敛）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = SCRIPTS_ROOT / "cli_first_allowlist.txt"
_MAIN_RE = re.compile(r"__name__\s*==\s*[\"']__main__[\"']")


def _load_allowlist() -> set[str]:
    entries: set[str] = set()
    if ALLOWLIST.exists():
        for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                entries.add(line)
    return entries


def main() -> None:
    allow = _load_allowlist()
    offenders: list[str] = []
    stale: set[str] = set(allow)
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        rel = path.relative_to(SCRIPTS_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if _MAIN_RE.search(text):
            stale.discard(rel)
            if rel not in allow:
                offenders.append(rel)

    if offenders:
        print("[verify-cli-first] FAILED: new direct-run entry scripts detected", file=sys.stderr)
        for rel in offenders:
            print(f"  - {rel} (wrap as <command>/handler.py + _common/ and expose via qwq-data)", file=sys.stderr)
        sys.exit(1)

    if stale:
        print("[verify-cli-first] NOTE: allowlist entries no longer have __main__ (safe to remove):")
        for rel in sorted(stale):
            print(f"  - {rel}")

    print(f"[verify-cli-first] PASSED ({len(allow)} allowlisted entries)")


if __name__ == "__main__":
    main()
