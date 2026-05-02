#!/usr/bin/env python3
"""会话 B：退场术语治理扫描。"""

from __future__ import annotations

import argparse
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

RETIRED_TERMS = (
    "".join(("leg", "acy")),
    "".join(("Leg", "acy")),
    "".join(("LEG", "ACY")),
    chr(0x9057) + chr(0x7559),
    chr(0x65E7) + chr(0x7248),
    chr(0x5386) + chr(0x53F2),
)


def scan_file(path: Path) -> dict:
    rel = path.relative_to(APP).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    hits: list[str] = []
    lower = raw.lower()
    for term in RETIRED_TERMS:
        if term.lower() in lower:
            hits.append("retired-term")
    return {
        "rel": rel,
        "hits": sorted(set(hits)),
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
        help="exit 1 if any retired term matches",
    )
    args = ap.parse_args()

    files: list[Path] = []
    for root in SCAN_ROOTS:
        files.extend(iter_dart_files(root))
    # de-dupe
    files = sorted(set(files))

    rows = [scan_file(p) for p in files]
    bad = [r for r in rows if r["hits"]]

    if args.markdown:
        print("| 路径 | 命中 |")
        print("|------|------|")
        for r in rows:
            if not r["hits"]:
                continue
            h = ", ".join(r["hits"]) if r["hits"] else "—"
            print(f"| `{r['rel']}` | {h} |")
        print()
        print(
            f"Summary: files_scanned={len(files)} "
            f"retired_term_files={len(bad)}"
        )
    else:
        for r in bad:
            print(f"RETIRED_TERM\t{r['rel']}\t{', '.join(r['hits'])}")
        print(
            f"verify_session_b_current_governance: files={len(files)} "
            f"retired_terms={len(bad)}"
        )

    code = 0
    if args.enforce and bad:
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
