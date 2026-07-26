#!/usr/bin/env python3
"""从 alpha 源生成 test-only Chat App DTO 薄适配器。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "quwoquan_app/runners/alpha/lib/alpha_chat_repository.dart"
TARGET = ROOT / "quwoquan_app/test/support/cloud_services/chat_repository_mock.dart"
HEADER = (
    "// Code generated from runners/alpha/lib/alpha_chat_repository.dart. "
    "DO NOT EDIT.\n"
)


def render() -> str:
    return HEADER + SOURCE.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        actual = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if actual != expected:
            print(
                "chat test adapter is stale; run "
                "python3 quwoquan_app/scripts/chat/generate_chat_test_adapter.py",
                file=sys.stderr,
            )
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(expected, encoding="utf-8")
    print(f"generated {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
