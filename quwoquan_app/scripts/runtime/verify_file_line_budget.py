#!/usr/bin/env python3
"""R03 文件行数预算门禁（ratchet：只降不升）。

军规 R03：单文件 >1000 行为 GATE_BLOCK。本脚本把当前所有 >1000 行业务源登记进
allowlist 冻结基线，之后任何文件超过其登记上限、或新出现未登记的 >1000 行文件即 fail。

扫描范围：
  - quwoquan_app/lib/**/*.dart
  - quwoquan_service/**/*.go
  - quwoquan_data/scripts/**/*.py

排除（生成物 / l10n / 测试 / mock / vendor）：
  - *.g.dart / *.g.go / *_test.go / __pycache__
  - quwoquan_app/lib/l10n/app_localizations*.dart
  - 任意 mock / generated / vendor / test / tests / runtime / runs 目录段

allowlist：quwoquan_ops/policies/gates/file_line_budget_allowlist.yaml
  block_threshold: 1000
  allow:
    - path: <repo-relative>
      max_lines: <int>          # ratchet 上限：current 必须 <= 此值
      reason: <str>

更新基线（清理后或刻意登记新债时）：
  python3 quwoquan_app/scripts/runtime/verify_file_line_budget.py --write-baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST_PATH = ROOT / "quwoquan_ops" / "policies" / "gates" / "file_line_budget_allowlist.yaml"
DEFAULT_BLOCK_THRESHOLD = 1000

SCAN_ROOTS = [
    (ROOT / "quwoquan_app" / "lib", "*.dart"),
    (ROOT / "quwoquan_service", "*.go"),
    (ROOT / "quwoquan_data" / "scripts", "*.py"),
]

# 排除的目录段（任意一段命中即排除）。
EXCLUDE_DIR_SEGMENTS = {
    "mock",
    "generated",
    "vendor",
    "test",
    "tests",
    ".dart_tool",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    ".qwq_test_venv",
    "runtime",
    "runs",
    "dist",
}


def is_excluded(rel: str, name: str) -> bool:
    if name.endswith(".g.dart") or name.endswith(".g.go"):
        return True
    if name.endswith("_test.go"):
        return True
    if rel.startswith("quwoquan_app/lib/l10n/app_localizations"):
        return True
    parts = set(Path(rel).parts)
    if parts & EXCLUDE_DIR_SEGMENTS:
        return True
    return False


def scan() -> dict[str, int]:
    """返回受管文件 -> 行数（仅记录 > block_threshold 的，减少噪声）。"""
    result: dict[str, int] = {}
    for base, pattern in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if is_excluded(rel, path.name):
                continue
            try:
                n = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
            except OSError:
                continue
            result[rel] = n
    return result


def load_allowlist() -> dict:
    if not ALLOWLIST_PATH.is_file():
        return {}
    data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}
    return data


def reason_for(rel: str) -> str:
    if "pageflip" in rel or rel.endswith("article_read_only_book_deck.dart"):
        return "pageflip-locked (受 11/12 号几何规则严管，专项后置，禁止本轮拆分)"
    if rel.startswith("quwoquan_data/scripts/"):
        return "data-oversized-budget (CLI-first 模块拆分，后续逐步降)"
    if rel.endswith(".go"):
        return "go-oversized-budget (同 package 多文件拆分，后续逐步降)"
    return "oversized-budget (子 widget / part / extension 拆分，后续逐步降)"


def write_baseline() -> int:
    counts = scan()
    threshold = DEFAULT_BLOCK_THRESHOLD
    over = {rel: n for rel, n in counts.items() if n > threshold}
    allow = [
        {"path": rel, "max_lines": n, "reason": reason_for(rel)}
        for rel, n in sorted(over.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    payload = {
        "_comment": (
            "R03 文件行数预算（ratchet 只降不升）。由 verify_file_line_budget.py "
            "--write-baseline 生成。清理后请重跑收紧基线；新增超标即门禁 BLOCK。"
        ),
        "governance": {
            "owner": "repository-architecture",
            "reason": "超过行数红线的存量文件只减不增",
            "expires_when": "allow 为空时删除本文件",
        },
        "block_threshold": threshold,
        "allow": allow,
    }
    ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_PATH.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8",
    )
    print(
        f"verify_file_line_budget: wrote baseline entries={len(allow)} "
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
            f"verify_file_line_budget: BLOCK: missing {ALLOWLIST_PATH} "
            f"(run with --write-baseline once)",
            file=sys.stderr,
        )
        return 2

    data = load_allowlist()
    threshold = int(data.get("block_threshold", DEFAULT_BLOCK_THRESHOLD))
    allow_entries = data.get("allow", []) or []
    budget: dict[str, int] = {}
    for entry in allow_entries:
        if isinstance(entry, dict) and "path" in entry:
            budget[str(entry["path"])] = int(entry.get("max_lines", threshold))

    counts = scan()
    violations: list[str] = []

    # 1) 任何 > threshold 的文件必须登记且不超上限（ratchet）。
    for rel, n in sorted(counts.items()):
        if n <= threshold:
            continue
        if rel not in budget:
            violations.append(
                f"  NEW oversized {rel}: {n} > {threshold} 且未登记 allowlist"
            )
        elif n > budget[rel]:
            violations.append(
                f"  RATCHET {rel}: {n} > 登记上限 {budget[rel]}（只能降不能升）"
            )

    # 2) allowlist 中已降到阈值以下的死条目（提示清理，不阻断）。
    stale = [rel for rel in budget if counts.get(rel, 0) <= threshold]

    if violations:
        print(
            "verify_file_line_budget: BLOCK: R03 文件行数预算违规：",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "  修复：拆分文件降到登记上限以下，或清理后 --write-baseline 收紧基线。",
            file=sys.stderr,
        )
        return 1

    msg = (
        f"verify_file_line_budget: ok managed>{threshold}="
        f"{sum(1 for n in counts.values() if n > threshold)} "
        f"allow={len(budget)}"
    )
    if stale:
        msg += f" (可清理 {len(stale)} 条已达标登记: {', '.join(sorted(stale)[:3])}...)"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
