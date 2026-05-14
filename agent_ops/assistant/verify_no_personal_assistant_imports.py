#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
CURRENT_DIR = ROOT / "quwoquan_app" / "lib" / "personal_assistant"
SCAN_DIRS = [
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "test",
    ROOT / "quwoquan_app" / "tool",
]
BLOCKED_SNIPPETS = (
    "package:quwoquan_app/personal_assistant/",
    "lib/personal_assistant/",
)


def main() -> int:
    violations: list[str] = []

    if CURRENT_DIR.exists():
        violations.append(
            f"[guard] current directory still exists: {CURRENT_DIR.relative_to(ROOT)}"
        )

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in sorted(p for p in scan_dir.rglob("*") if p.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if any(snippet in line for snippet in BLOCKED_SNIPPETS):
                    violations.append(
                        f"[guard] blocked current path in {path.relative_to(ROOT)}:{line_no}: {line.strip()}"
                    )

    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1

    print("[guard] OK: no personal_assistant imports or lib paths found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
