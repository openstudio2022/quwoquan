#!/usr/bin/env python3
"""R02 Repository 接口方法数预算门禁（ratchet：只降不升）。

军规 R02：单 interface ≤10 方法。本脚本统计每个 `abstract class *Repository` 的顶层成员
声明数；伞组合接口（body 为空、仅 implements N 个窄接口）自然计 0，免登记。

超过阈值（10）的接口必须登记进 allowlist 并冻结当前方法数；之后只能降不能升，新增
超标接口即 fail。ContentRepository 已拆成 6 个 ≤10 子接口，是达标模板。

扫描范围：
  - quwoquan_app/lib/**/*.dart
  - packages/*/lib/**/*.dart

allowlist：specs/gates/repository_interface_method_budget_allowlist.yaml
  method_threshold: 10
  allow:
    - interface: ChatRepository
      path: <repo-relative>
      max_methods: <int>
      reason: <str>

更新基线：
  python3 quwoquan_app/scripts/runtime/verify_repository_interface_method_budget.py --write-baseline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST_PATH = (
    ROOT / "specs" / "gates" / "repository_interface_method_budget_allowlist.yaml"
)
DEFAULT_METHOD_THRESHOLD = 10

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


def load_allowlist() -> dict:
    if not ALLOWLIST_PATH.is_file():
        return {}
    return yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}


def write_baseline() -> int:
    threshold = DEFAULT_METHOD_THRESHOLD
    over = [
        (name, rel, n)
        for (name, rel, n) in scan()
        if n > threshold
    ]
    over.sort(key=lambda t: (-t[2], t[0]))
    allow = [
        {
            "interface": name,
            "path": rel,
            "max_methods": n,
            "reason": "oversized-interface-legacy (按 ContentRepository 模板拆窄接口，后续逐步降)",
        }
        for (name, rel, n) in over
    ]
    payload = {
        "_comment": (
            "R02 Repository 接口方法数预算（ratchet 只降不升）。由 "
            "verify_repository_interface_method_budget.py --write-baseline 生成。"
            "ContentRepository 已拆 6 个 ≤10 子接口为达标模板；超标接口登记后只能降。"
        ),
        "method_threshold": threshold,
        "allow": allow,
    }
    ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_PATH.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8",
    )
    print(
        f"verify_repository_interface_method_budget: wrote baseline entries={len(allow)} "
        f"threshold={threshold} -> {ALLOWLIST_PATH}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    if args.write_baseline:
        return write_baseline()

    if not ALLOWLIST_PATH.is_file():
        print(
            f"verify_repository_interface_method_budget: BLOCK: missing {ALLOWLIST_PATH} "
            f"(run with --write-baseline once)",
            file=sys.stderr,
        )
        return 2

    data = load_allowlist()
    threshold = int(data.get("method_threshold", DEFAULT_METHOD_THRESHOLD))
    budget: dict[str, int] = {}
    for entry in data.get("allow", []) or []:
        if isinstance(entry, dict) and "interface" in entry:
            budget[str(entry["interface"])] = int(entry.get("max_methods", threshold))

    violations: list[str] = []
    for name, rel, n in sorted(scan()):
        if n <= threshold:
            continue
        if name not in budget:
            violations.append(
                f"  NEW oversized interface {name} ({rel}): {n} 方法 > {threshold} 且未登记"
            )
        elif n > budget[name]:
            violations.append(
                f"  RATCHET {name} ({rel}): {n} > 登记上限 {budget[name]}（只能降不能升）"
            )

    if violations:
        print(
            "verify_repository_interface_method_budget: BLOCK: R02 接口方法数违规：",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "  修复：按 ContentRepository 模板拆窄接口，或清理后 --write-baseline 收紧基线。",
            file=sys.stderr,
        )
        return 1

    print(
        f"verify_repository_interface_method_budget: ok over-threshold-allowed={len(budget)} "
        f"threshold={threshold}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
