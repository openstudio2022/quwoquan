#!/usr/bin/env python3
"""
页面级 A/B/C 治理扫描（与 verify_page_matrix_scan_complete 磁盘集一致，见 scripts/page_disk_scan_paths.py）。

规范：specs/gates/page_abc_governance.md
白名单：specs/gates/page_abc_governance_allowlist.yaml

退出码：
  0 — 成功（报告模式或未启用的 enforce 无未豁免违规）
  1 — enforce 维度存在未豁免违规
  2 — 工具/配置错误（无 lib、白名单 path 非法、互斥参数等）

CI 可选环境变量（由 gate_repo.sh 读取）：GATE_PAGE_ABC_ENFORCE → 映射为 --enforce-a 等。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

from page_disk_scan_paths import matrix_disk_scan_paths

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALLOWLIST = ROOT / "specs/gates/page_abc_governance_allowlist.yaml"

APP = ROOT / "quwoquan_app"
LIB = APP / "lib"

A_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"draftVersion", re.I), "draftVersion"),
    (re.compile(r"\b_fromV\d|fromV\d\b|_fromCurrent|fromCurrentMap\b", re.I), "versioned/Current map parser"),
    (re.compile(r"version\s*==\s*['\"]v\d", re.I), "version==vN"),
    (re.compile(r"RewriteV2|uiProcessTimelineV2", re.I), "*V2 API identifier"),
    (re.compile(r"V2\s*原型|发现页\s*V1", re.I), "comment V1/V2 generation"),
]

B_RIVERPOD_CURRENT_IMPORT = re.compile(
    r"^\s*import\s+['\"]package:flutter_riverpod/current\.dart['\"]"
)

B_BAD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bclass\s+\w*Current\w*"),
    re.compile(r"\bCurrent[A-Z]\w*\b"),
    re.compile(r"\bcurrentPageId\b"),
    re.compile(r"\bfromCurrent[A-Za-z]*\b"),
    re.compile(r"\bonOpenCurrent\w*"),
    re.compile(r"\b_WorksCurrent\w*"),
    re.compile(r"\btrackCurrent\w*"),
    re.compile(r"\b_buildCurrent\w*"),
]

C_DYNAMIC = re.compile(r"\bdynamic\b")
C_MAP = re.compile(r"Map\s*<\s*String\s*,\s*dynamic\s*>")

ALLOWED_EXEMPTION_KEYS = frozenset({"path", "dimensions", "reason", "tracking"})


def disk_scan_paths_sorted() -> list[str]:
    return sorted(matrix_disk_scan_paths(ROOT))


def load_allowlist(
    allowlist_path: Path | None,
    valid_paths: frozenset[str],
) -> tuple[dict[str, frozenset[str]], int]:
    """
    返回 (path -> exempt dimensions set)，第二个返回值为 0 或 2（配置错误）。
    """
    if allowlist_path is None or not allowlist_path.is_file():
        return {}, 0

    if yaml is None:
        print(
            "verify_page_abc_governance: BLOCK: PyYAML required to parse allowlist",
            file=sys.stderr,
        )
        return {}, 2

    raw = yaml.safe_load(allowlist_path.read_text(encoding="utf-8"))
    if raw is None:
        return {}, 0
    if not isinstance(raw, dict):
        print("verify_page_abc_governance: allowlist root must be a mapping", file=sys.stderr)
        return {}, 2

    items = raw.get("exemptions")
    if items is None:
        return {}, 0
    if not isinstance(items, list):
        print("verify_page_abc_governance: exemptions must be a list", file=sys.stderr)
        return {}, 2

    out: dict[str, frozenset[str]] = {}
    for i, ex in enumerate(items):
        if not isinstance(ex, dict):
            print(f"verify_page_abc_governance: exemptions[{i}] must be a mapping", file=sys.stderr)
            return {}, 2
        unknown = set(ex.keys()) - ALLOWED_EXEMPTION_KEYS
        if unknown:
            print(
                f"verify_page_abc_governance: WARN: exemptions[{i}] unknown keys: {sorted(unknown)}",
                file=sys.stderr,
            )
        path = ex.get("path")
        if not isinstance(path, str) or not path.strip():
            print(f"verify_page_abc_governance: exemptions[{i}] missing path", file=sys.stderr)
            return {}, 2
        path = path.strip().replace("\\", "/")
        if path.startswith("quwoquan_app/"):
            path = path[len("quwoquan_app/") :]
        if path not in valid_paths:
            print(
                f"verify_page_abc_governance: allowlist path not in matrix scan set: {path}",
                file=sys.stderr,
            )
            return {}, 2
        dims_raw = ex.get("dimensions")
        if not isinstance(dims_raw, list) or not dims_raw:
            print(f"verify_page_abc_governance: exemptions[{i}] dimensions must be non-empty list", file=sys.stderr)
            return {}, 2
        dims: set[str] = set()
        for d in dims_raw:
            if not isinstance(d, str):
                print(f"verify_page_abc_governance: exemptions[{i}] dimension not string", file=sys.stderr)
                return {}, 2
            du = d.strip().upper()
            if du not in ("A", "B", "C"):
                print(
                    f"verify_page_abc_governance: exemptions[{i}] invalid dimension {d!r}",
                    file=sys.stderr,
                )
                return {}, 2
            dims.add(du)
        reason = ex.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            print(f"verify_page_abc_governance: exemptions[{i}] reason required", file=sys.stderr)
            return {}, 2

        merged = set(out.get(path, frozenset())) | dims
        out[path] = frozenset(merged)

    return out, 0


def analyze_file(rel: str) -> dict:
    path = APP / rel
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    filtered = "\n".join(ln for ln in lines if not B_RIVERPOD_CURRENT_IMPORT.match(ln))

    a_hits: list[str] = []
    for pat, label in A_PATTERNS:
        if pat.search(text):
            a_hits.append(label)

    b_bad = [p.pattern for p in B_BAD_PATTERNS if p.search(filtered)]
    has_riverpod_current = any(B_RIVERPOD_CURRENT_IMPORT.match(ln) for ln in lines)

    c_dyn = len(C_DYNAMIC.findall(text))
    c_map = len(C_MAP.findall(text))

    return {
        "rel": rel,
        "a_hits": sorted(set(a_hits)),
        "b_bad": b_bad,
        "b_riverpod_current_only": bool(has_riverpod_current and not b_bad),
        "c_dyn": c_dyn,
        "c_map": c_map,
    }


def apply_allowlist(
    rows: list[dict],
    exempt: dict[str, frozenset[str]],
) -> tuple[list[dict], list[dict], list[dict]]:
    """返回 (fail_a_rows, fail_b_rows, fail_c_rows) 未豁免。"""
    fail_a: list[dict] = []
    fail_b: list[dict] = []
    fail_c: list[dict] = []
    ex = exempt

    for r in rows:
        rel = r["rel"]
        ed = ex.get(rel, frozenset())
        if r["a_hits"] and "A" not in ed:
            fail_a.append(r)
        if r["b_bad"] and "B" not in ed:
            fail_b.append(r)
        c_tot = r["c_dyn"] + r["c_map"]
        if c_tot > 0 and "C" not in ed:
            fail_c.append(r)

    return fail_a, fail_b, fail_c


def bad_patterns_matched(patterns: list[str]) -> str:
    return "; ".join(patterns[:5]) + ("…" if len(patterns) > 5 else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Page A/B/C governance scan (64-path matrix set).")
    out_group = ap.add_mutually_exclusive_group()
    out_group.add_argument("--markdown", action="store_true", help="print markdown table")
    out_group.add_argument("--json", action="store_true", help="print JSON report")
    out_group.add_argument(
        "--quiet",
        "--summary-only",
        dest="quiet",
        action="store_true",
        help="print one-line summary only",
    )
    ap.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"YAML allowlist (default: {DEFAULT_ALLOWLIST})",
    )
    ap.add_argument("--enforce-a", action="store_true", help="exit 1 if unexempted A hits")
    ap.add_argument("--enforce-b", action="store_true", help="exit 1 if unexempted B hits")
    ap.add_argument("--enforce-c", action="store_true", help="exit 1 if unexempted C hits")
    args = ap.parse_args()

    if not LIB.is_dir():
        print("verify_page_abc_governance: BLOCK: quwoquan_app/lib missing", file=sys.stderr)
        return 2

    paths = disk_scan_paths_sorted()
    if not paths:
        print("verify_page_abc_governance: no paths (missing lib?)", file=sys.stderr)
        return 2

    valid_set = frozenset(paths)
    allow_path = args.allowlist if args.allowlist is not None else DEFAULT_ALLOWLIST
    if args.allowlist is not None and not allow_path.is_file():
        print(f"verify_page_abc_governance: allowlist not found: {allow_path}", file=sys.stderr)
        return 2
    exempt, err = load_allowlist(allow_path if allow_path.is_file() else None, valid_set)
    if err:
        return 2

    rows = [analyze_file(rel) for rel in paths]
    fail_a, fail_b, fail_c = apply_allowlist(rows, exempt)

    raw_fail_a = [r for r in rows if r["a_hits"]]
    raw_fail_b = [r for r in rows if r["b_bad"]]
    raw_fail_c = [r for r in rows if r["c_dyn"] + r["c_map"] > 0]
    riverpod_only = [r for r in rows if r["b_riverpod_current_only"]]

    summary = {
        "paths": len(paths),
        "raw_A": len(raw_fail_a),
        "raw_B": len(raw_fail_b),
        "raw_C": len(raw_fail_c),
        "fail_A": len(fail_a),
        "fail_B": len(fail_b),
        "fail_C": len(fail_c),
        "riverpod_current_import_only": len(riverpod_only),
    }

    if args.json:
        payload = {
            "summary": summary,
            "allowlist": str(allow_path) if allow_path.is_file() else None,
            "files": [],
        }
        for r in rows:
            rel = r["rel"]
            ed = exempt.get(rel, frozenset())
            c_tot = r["c_dyn"] + r["c_map"]
            payload["files"].append(
                {
                    "path": rel,
                    "A_hits": r["a_hits"],
                    "A_exempt": "A" in ed,
                    "B_bad_patterns": len(r["b_bad"]) > 0,
                    "B_exempt": "B" in ed,
                    "C_dynamic": r["c_dyn"],
                    "C_map": r["c_map"],
                    "C_exempt": "C" in ed,
                    "B_riverpod_current_only": r["b_riverpod_current_only"],
                }
            )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.markdown:
        print("| # | 路径 | A | B | C |")
        print("|---:|------|:---:|:---:|:---:|")
        for i, r in enumerate(rows, 1):
            rel = r["rel"]
            ed = exempt.get(rel, frozenset())
            if not r["a_hits"]:
                a_cell = "—"
            else:
                prefix = "⚠ " if "A" in ed else "✓ "
                a_cell = prefix + "; ".join(r["a_hits"])
            if r["b_bad"]:
                b_cell = "⚠ exempt" if "B" in ed else "✓ 待清"
            elif r["b_riverpod_current_only"]:
                b_cell = "△ riverpod/current import"
            else:
                b_cell = "—"
            c_tot = r["c_dyn"] + r["c_map"]
            if c_tot == 0:
                c_cell = "—"
            else:
                c_cell = (
                    f"⚠ dyn {r['c_dyn']}, Map {r['c_map']}"
                    if "C" in ed
                    else f"✓ dyn {r['c_dyn']}, Map {r['c_map']}"
                )
            print(f"| {i} | `{rel}` | {a_cell} | {b_cell} | {c_cell} |")
        print()
        print(
            f"Summary: paths={summary['paths']} raw_A={summary['raw_A']} raw_B={summary['raw_B']} "
            f"raw_C={summary['raw_C']} fail_A={summary['fail_A']} fail_B={summary['fail_B']} "
            f"fail_C={summary['fail_C']} riverpod_current_only={summary['riverpod_current_import_only']}"
        )
    elif args.quiet:
        ok = (
            (not args.enforce_a or summary["fail_A"] == 0)
            and (not args.enforce_b or summary["fail_B"] == 0)
            and (not args.enforce_c or summary["fail_C"] == 0)
        )
        status = "OK" if ok else "FAIL"
        print(
            f"verify_page_abc_governance: {status} paths={summary['paths']} "
            f"raw_A={summary['raw_A']} raw_B={summary['raw_B']} raw_C={summary['raw_C']} "
            f"fail_A={summary['fail_A']} fail_B={summary['fail_B']} fail_C={summary['fail_C']}"
        )
    else:
        for r in rows:
            rel = r["rel"]
            ed = exempt.get(rel, frozenset())
            if r["a_hits"]:
                tag = " (exempt A)" if "A" in ed else ""
                print(f"A\t{rel}\t{', '.join(r['a_hits'])}{tag}")
            if r["b_bad"]:
                tag = " (exempt B)" if "B" in ed else ""
                print(f"B\t{rel}\t{bad_patterns_matched(r['b_bad'])}{tag}")
            c_tot = r["c_dyn"] + r["c_map"]
            if c_tot:
                tag = " (exempt C)" if "C" in ed else ""
                print(f"C\t{rel}\tdynamic={r['c_dyn']} map={r['c_map']}{tag}")
        for r in riverpod_only:
            print(f"B~\t{r['rel']}\tflutter_riverpod/current.dart import only")
        print(
            f"verify_page_abc_governance: paths={summary['paths']} "
            f"raw_A={summary['raw_A']} raw_B={summary['raw_B']} raw_C={summary['raw_C']} "
            f"fail_A={summary['fail_A']} fail_B={summary['fail_B']} fail_C={summary['fail_C']} "
            f"B_riverpod_only={summary['riverpod_current_import_only']}"
        )

    code = 0
    if args.enforce_a and fail_a:
        code = 1
    if args.enforce_b and fail_b:
        code = 1
    if args.enforce_c and fail_c:
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
