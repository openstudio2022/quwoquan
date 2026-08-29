#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root, require_scan_root  # noqa: E402

ROOT = repository_root()
SERVICE_ROOT = require_scan_root(
    ROOT / "quwoquan_service" / "services", "relationship-error-code-gate services"
)

CHECK_PATHS = [
    SERVICE_ROOT / "user-service",
    SERVICE_ROOT / "chat-service",
    SERVICE_ROOT / "rtc-service",
]

# 只拦截关系门禁相关的第二真相源，不误伤普通字符串检查。
RELATION_ERROR_HINTS = (
    "not_mutual",
    "mutual",
    "blocked",
    "persona_handle_taken",
    "nickname_taken",
    "retired persona",
    "empty persona should be deleted directly",
    "switch to another persona",
    "must be retired",
    "primary",
    "last",
)


def scan_file(path: Path) -> list[str]:
    failures: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return failures

    for line_no, line in enumerate(text.splitlines(), start=1):
        if "strings.Contains(err.Error()," not in line:
            continue
        if any(hint in line for hint in RELATION_ERROR_HINTS):
            failures.append(
                f"{path.relative_to(ROOT)}:{line_no}: "
                "relationship/error gate must not branch on err.Error() text; "
                "use generated AppError code or NormalizeError(err).Code instead"
            )
    return failures


def main() -> int:
    failures: list[str] = []
    for base in CHECK_PATHS:
        for path in base.rglob("*.go"):
            failures.extend(scan_file(path))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("verify_relationship_error_code_gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
