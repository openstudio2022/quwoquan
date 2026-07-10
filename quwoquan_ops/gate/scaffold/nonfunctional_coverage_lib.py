#!/usr/bin/env python3
"""Shared helpers for non-functional test coverage gates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from test_directory_inventory_lib import ROOT, iter_canonical_files


FEATURE_TREE = ROOT / "specs" / "feature-tree"


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def require_path(self, path: Path, label: str) -> None:
        if not path.exists():
            self.add(f"missing {label}: {path.relative_to(ROOT)}")

    def require_any_canonical_test(self, *, label: str, patterns: Iterable[str], minimum: int = 1) -> None:
        matches = canonical_tests_matching(patterns)
        if len(matches) < minimum:
            self.add(f"{label}: expected at least {minimum} canonical test(s), got {len(matches)}")

    def require_any_text(self, *, label: str, roots: Iterable[Path], patterns: Iterable[str]) -> None:
        compiled = [re.compile(pattern, re.I) for pattern in patterns]
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".md", ".yaml", ".yml", ".json", ".py", ".go", ".dart"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if any(pattern.search(text) for pattern in compiled):
                    return
        self.add(f"{label}: no matching governance text found")

    def exit_code(self, ok_message: str) -> int:
        if not self.items:
            print(ok_message)
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}")
        return 1


def canonical_tests_matching(patterns: Iterable[str]) -> list[Path]:
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    matches: list[Path] = []
    for _, path, _ in iter_canonical_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(rel) or pattern.search(text) for pattern in compiled):
            matches.append(path)
    return matches
