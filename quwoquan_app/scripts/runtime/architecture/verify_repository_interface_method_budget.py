#!/usr/bin/env python3
"""R02 Repository 接口方法数预算门禁（零容忍）。

军规 R02：单 interface ≤10 方法。本脚本统计每个 `abstract class *Repository` 的顶层成员
声明数；伞组合接口（body 为空、仅 implements N 个窄接口）自然计 0。

超过阈值（10）的接口一律 BLOCK，不接受登记豁免。ContentRepository 已拆成 6 个 ≤10
子接口，是达标模板。

扫描范围：
  - quwoquan_app/lib/**/*.dart
  - packages/*/lib/**/*.dart
"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re
import sys
from pathlib import Path

ROOT = REPO_ROOT
METHOD_THRESHOLD = 10

SCAN_DIRS = [
    ROOT / "quwoquan_app" / "lib",
    ROOT / "packages",
]

CLASS_RE = re.compile(r"\babstract\s+class\s+(\w*Repository)\b")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_comments(text: str) -> str:
    text = BLOCK_COMMENT_RE.sub("", text)
    out_lines = []
    for line in text.splitlines():
        idx = line.find("//")
        if idx != -1:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def count_members(body: str) -> int:
    """统计 class body 顶层（深度0）以 ; 结束的成员声明数。"""
    depth = 0
    count = 0
    has_token_since_semicolon = False
    for ch in body:
        if ch in "([{":
            depth += 1
            has_token_since_semicolon = True
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            if has_token_since_semicolon:
                count += 1
            has_token_since_semicolon = False
        elif not ch.isspace():
            has_token_since_semicolon = True
    return count


def extract_body(text: str, brace_open_idx: int) -> str:
    depth = 0
    for i in range(brace_open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace_open_idx + 1 : i]
    return ""


def scan() -> list[tuple[str, str, int]]:
    """返回 (interface_name, repo_relative_path, member_count)。"""
    found: list[tuple[str, str, int]] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.dart"):
            if path.name.endswith(".g.dart") or not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            text = strip_comments(raw)
            rel = path.relative_to(ROOT).as_posix()
            for m in CLASS_RE.finditer(text):
                name = m.group(1)
                brace = text.find("{", m.end())
                if brace == -1:
                    continue
                body = extract_body(text, brace)
                found.append((name, rel, count_members(body)))
    return found


def main() -> int:
    violations = [
        f"  {name} ({rel}): {n} 方法 > {METHOD_THRESHOLD}"
        for name, rel, n in sorted(scan())
        if n > METHOD_THRESHOLD
    ]

    if violations:
        print(
            "verify_repository_interface_method_budget: BLOCK: R02 接口方法数违规：",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "  修复：按 ContentRepository 模板拆窄接口。",
            file=sys.stderr,
        )
        return 1

    print(
        f"verify_repository_interface_method_budget: ok threshold={METHOD_THRESHOLD}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
