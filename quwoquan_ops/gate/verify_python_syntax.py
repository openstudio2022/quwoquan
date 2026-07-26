#!/usr/bin/env python3
"""Compile Python sources in memory without creating source-tree bytecode."""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = (
    ROOT / "quwoquan_data" / "scripts",
    ROOT / "quwoquan_ops" / "cli",
    ROOT / "quwoquan_ops" / "gate",
)


def _python_sources(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    sources: list[Path] = []
    for path in paths:
        if path.is_file():
            sources.append(path)
        elif path.is_dir():
            sources.extend(
                candidate
                for candidate in path.rglob("*.py")
                if "__pycache__" not in candidate.parts
            )
        else:
            sources.append(path)
    return tuple(sorted(set(sources)))


def syntax_issues(paths: tuple[Path, ...]) -> list[str]:
    issues: list[str] = []
    for path in _python_sources(paths):
        if not path.is_file():
            issues.append(f"{path}: Python source file is missing")
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError) as exc:
            issues.append(f"{path}: {exc}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = tuple(args.paths) or DEFAULT_ROOTS
    issues = syntax_issues(paths)
    if issues:
        print("[verify_python_syntax] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_python_syntax] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
