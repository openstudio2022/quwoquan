#!/usr/bin/env python3
"""
会话 B：业务 Legacy 治理扫描（lib/ui、lib/cloud/services、lib/cloud/runtime、lib/core）。

排除：import 'package:flutter_riverpod/legacy.dart' 单独统计，可选 --enforce-riverpod-legacy-zero。

用法（仓库根）:
  python3 scripts/verify_session_b_legacy_governance.py
  python3 scripts/verify_session_b_legacy_governance.py --markdown
  python3 scripts/verify_session_b_legacy_governance.py --enforce
  python3 scripts/verify_session_b_legacy_governance.py --enforce --enforce-riverpod-legacy-zero
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "quwoquan_app"
LIB = APP / "lib"

SCAN_ROOTS = [
    LIB / "ui",
    LIB / "cloud" / "services",
    LIB / "cloud" / "runtime",
    LIB / "core",
]

RIVERPOD_LEGACY_IMPORT = re.compile(
    r"^\s*import\s+['\"]package:flutter_riverpod/legacy\.dart['\"];?\s*$"
)

# Lines to skip for "business legacy" (riverpod package path only)
def filter_riverpod_import_lines(text: str) -> str:
    return "\n".join(
        ln for ln in text.splitlines() if not RIVERPOD_LEGACY_IMPORT.match(ln)
    )


PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\blegacyPageId\b"), "legacyPageId"),
    (re.compile(r"\b_fromLegacyMap\b|fromLegacyMap\b"), "fromLegacyMap"),
    (re.compile(r"\bfromLegacy[A-Za-z]*\b"), "fromLegacy*"),
    (re.compile(r"\bclass\s+\w*Legacy\w*"), "class...Legacy"),
    (re.compile(r"\b_Legacy[A-Za-z]\w*"), "_Legacy*"),
    (re.compile(r"\bonOpenLegacy\w*"), "onOpenLegacy*"),
    (re.compile(r"\btrackLegacy\w*"), "trackLegacy*"),
    (re.compile(r"\b_buildLegacy\w*"), "_buildLegacy*"),
    (re.compile(r"\b_WorksLegacy\w*"), "_WorksLegacy*"),
    (re.compile(r"\blegacyUrl\b"), "legacyUrl"),
    (re.compile(r"['\"]legacy_sheet['\"]"), "'legacy_sheet' string"),
    (re.compile(r"['\"]legacy_content['\"]"), "'legacy_content' string"),
    (re.compile(r"profileId:\s*['\"]legacy['\"]"), "profileId: 'legacy'"),
    (re.compile(r"\bhasLegacyStructuredPages\b"), "hasLegacyStructuredPages"),
    (re.compile(r"\blegacyArticleFallbackData\b"), "legacyArticleFallbackData"),
    (re.compile(r"\blegacyDocumentFallbackRate\b"), "legacyDocumentFallback metric"),
    (re.compile(r"\btrackLegacyDocumentFallback\b"), "trackLegacyDocumentFallback"),
    (re.compile(r"\bassistantEntryAskLegacy\b"), "assistantEntryAskLegacy"),
    (re.compile(r"\bshareLegacyFallbackNotice\b"), "shareLegacyFallbackNotice"),
    (re.compile(r"\b_LegacyContentDataService\b"), "_LegacyContentDataService"),
    (re.compile(r"LegacyDataService"), "LegacyDataService"),
    (re.compile(r"\b_legacyRelationTier\b"), "_legacyRelationTier"),
    (re.compile(r"\bfromLegacyRelationship\b"), "fromLegacyRelationship"),
    (re.compile(r"\blegacyHasChatRecords\b"), "legacyHasChatRecords"),
    (re.compile(r"\bfromLegacyScope\b"), "fromLegacyScope"),
]


def scan_file(path: Path) -> dict:
    rel = path.relative_to(APP).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    filtered = filter_riverpod_import_lines(raw)
    hits: list[str] = []
    for pat, label in PATTERNS:
        if pat.search(filtered):
            hits.append(label)
    riverpod_legacy_lines = sum(
        1 for ln in raw.splitlines() if RIVERPOD_LEGACY_IMPORT.match(ln)
    )
    return {
        "rel": rel,
        "hits": sorted(set(hits)),
        "riverpod_legacy_imports": riverpod_legacy_lines,
    }


def iter_dart_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.dart"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument(
        "--enforce",
        action="store_true",
        help="exit 1 if any business-legacy pattern matches",
    )
    ap.add_argument(
        "--enforce-riverpod-legacy-zero",
        action="store_true",
        help="exit 1 if any flutter_riverpod/legacy.dart import remains",
    )
    args = ap.parse_args()

    files: list[Path] = []
    for root in SCAN_ROOTS:
        files.extend(iter_dart_files(root))
    # de-dupe
    files = sorted(set(files))

    rows = [scan_file(p) for p in files]
    bad = [r for r in rows if r["hits"]]
    riverpod_total = sum(r["riverpod_legacy_imports"] for r in rows)
    riverpod_files = [r for r in rows if r["riverpod_legacy_imports"]]

    if args.markdown:
        print("| 路径 | 业务 Legacy 命中 | riverpod/legacy import |")
        print("|------|------------------|------------------------|")
        for r in rows:
            if not r["hits"] and r["riverpod_legacy_imports"] == 0:
                continue
            h = ", ".join(r["hits"]) if r["hits"] else "—"
            rp = str(r["riverpod_legacy_imports"]) if r["riverpod_legacy_imports"] else "—"
            print(f"| `{r['rel']}` | {h} | {rp} |")
        print()
        print(
            f"Summary: files_scanned={len(files)} "
            f"business_legacy_files={len(bad)} "
            f"riverpod_legacy_import_lines={riverpod_total} "
            f"riverpod_legacy_files={len(riverpod_files)}"
        )
    else:
        for r in bad:
            print(f"LEGACY\t{r['rel']}\t{', '.join(r['hits'])}")
        for r in riverpod_files:
            print(f"RIVERPOD_LEGACY\t{r['rel']}\timports={r['riverpod_legacy_imports']}")
        print(
            f"verify_session_b_legacy_governance: files={len(files)} "
            f"business_legacy={len(bad)} riverpod_import_lines={riverpod_total}"
        )

    code = 0
    if args.enforce and bad:
        code = 1
    if args.enforce_riverpod_legacy_zero and riverpod_total > 0:
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
