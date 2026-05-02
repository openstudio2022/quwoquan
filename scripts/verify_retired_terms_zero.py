#!/usr/bin/env python3
"""Fail when retired terminology appears in repository text files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".dart_tool",
    "build",
    "node_modules",
    ".idea",
    ".vscode",
    ".venv",
}

TEXT_SUFFIXES = {
    ".arb",
    ".dart",
    ".go",
    ".gradle",
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".mdc",
    ".mjs",
    ".properties",
    ".py",
    ".rb",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_NAMES = {
    "Makefile",
    "Podfile",
}

TERMS = (
    "".join(("leg", "acy")),
    "".join(("Leg", "acy")),
    "".join(("LEG", "ACY")),
    chr(0x9057) + chr(0x7559),
    chr(0x65E7) + chr(0x7248),
    chr(0x5386) + chr(0x53F2),
)


def is_scannable(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.is_file() and (
        path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES
    )


def main() -> int:
    violations: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not is_scannable(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lower = text.lower()
        if any(term.lower() in lower for term in TERMS):
            violations.append(path.relative_to(ROOT).as_posix())

    if violations:
        print("verify_retired_terms_zero: FAIL")
        for rel in violations:
            print(f"  - {rel}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
