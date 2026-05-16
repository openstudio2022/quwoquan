#!/usr/bin/env python3
"""
verify_route_and_context_semantic.py

Scans quwoquan_app/lib for hardcoded route/context literals that should come from
metadata/codegen outputs.
"""

from __future__ import annotations

import os
import re
import sys


RULES: list[tuple[re.Pattern[str], str, tuple[str, ...]]] = [
    (
        re.compile(r"context\.(?:go|push)\(\s*['\"][^'\"]+['\"]"),
        "导航跳转应引用 AppRoutePaths builder/常量，禁止 context.go('/...') / context.push('/...') 字面量",
        ("quwoquan_app/lib/app", "quwoquan_app/lib/ui", "quwoquan_app/lib/components"),
    ),
    (
        re.compile(r"\bpath:\s*['\"]/"),
        "GoRoute path 应引用 metadata/codegen 常量，禁止 path: '/...' 字面量",
        ("quwoquan_app/lib/app",),
    ),
    (
        re.compile(r"Uri\s*\(\s*path:\s*['\"]/"),
        "路由 Uri path 应引用 AppRoutePaths builder，禁止 Uri(path: '/...') 字面量",
        ("quwoquan_app/lib/app", "quwoquan_app/lib/ui", "quwoquan_app/lib/components"),
    ),
    (
        re.compile(r"context:\s*['\"][^'\"]+['\"]"),
        "CloudResponseDecoder.context 应引用生成常量，禁止 context: '...' 字面量",
        ("quwoquan_app/lib/cloud",),
    ),
]

EXCLUDE_SUBSTRINGS = [
    "/generated/",
    "/mock/",
    "_test.dart",
]


def should_skip(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(token in normalized for token in EXCLUDE_SUBSTRINGS)


def rule_applies(path: str, scopes: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(scope) for scope in scopes)


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    lib_root = os.path.join(repo_root, "quwoquan_app", "lib")
    violations: list[tuple[str, int, str, str]] = []

    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, repo_root).replace("\\", "/")
            if should_skip(rel):
                continue
            with open(path, encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    for pattern, hint, scopes in RULES:
                        if not rule_applies(rel, scopes):
                            continue
                        if pattern.search(line):
                            violations.append((rel, line_no, stripped, hint))
                            break

    if not violations:
        return 0

    for rel, line_no, line, hint in violations:
        print(f"{rel}:{line_no}: {hint}")
        print(f"  {line}")
    print(
        "\nverify_route_and_context_semantic: route/context 必须消费 metadata/codegen 唯一源",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
