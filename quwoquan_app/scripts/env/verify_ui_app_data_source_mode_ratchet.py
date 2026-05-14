#!/usr/bin/env python3
"""
UI 层 AppDataSourceMode / appDataSourceModeProvider 引用棘轮（见 mock_data_cloud_integration_policy.md）。

扫描：quwoquan_app/lib/ui/**/*.dart
豁免（不计入）：开发者设置页须保留数据源切换 UI。

指标（单 bucket `ui`）：
  - mock_enum_hits: 非注释行中子串 `AppDataSourceMode.mock` 出现次数
  - provider_hits: 非注释行中子串 `appDataSourceModeProvider` 出现次数

行为：与 specs/gates/ui_app_data_source_mode_baseline.json 比较，任一指标严格大于基线 → exit 1。
--write-baseline：覆盖基线（有意收口或 bump 时用）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "quwoquan_app" / "lib"
UI_ROOT = LIB / "ui"
DEFAULT_BASELINE = ROOT / "specs" / "gates" / "ui_app_data_source_mode_baseline.json"

# Paths relative to lib/ — excluded from ratchet (permanent carve-out).
EXEMPT_REL = frozenset(
    {
        "ui/settings/pages/developer_settings_page.dart",
    }
)


def _is_comment_or_doc_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("//") or s.startswith("/*") or s.startswith("*")


def _scan_ui_tree() -> tuple[int, int]:
    mock_hits = 0
    provider_hits = 0
    if not UI_ROOT.is_dir():
        return 0, 0
    for path in sorted(UI_ROOT.rglob("*.dart")):
        try:
            rel = path.relative_to(LIB).as_posix()
        except ValueError:
            continue
        if rel in EXEMPT_REL:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if _is_comment_or_doc_line(line):
                continue
            mock_hits += line.count("AppDataSourceMode.mock")
            provider_hits += line.count("appDataSourceModeProvider")
    return mock_hits, provider_hits


def current_buckets() -> dict[str, dict[str, int]]:
    m, p = _scan_ui_tree()
    return {"ui": {"mock_enum_hits": m, "provider_hits": p}}


def load_baseline(path: Path) -> dict[str, dict[str, int]] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    buckets = raw.get("buckets")
    if not isinstance(buckets, dict):
        return None
    out: dict[str, dict[str, int]] = {}
    ui = buckets.get("ui")
    if isinstance(ui, dict) and all(
        isinstance(ui.get(k), int) for k in ("mock_enum_hits", "provider_hits")
    ):
        out["ui"] = {
            "mock_enum_hits": int(ui["mock_enum_hits"]),
            "provider_hits": int(ui["provider_hits"]),
        }
    return out if out else None


def regressions(
    baseline: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> list[str]:
    msgs: list[str] = []
    metrics = ("mock_enum_hits", "provider_hits")
    all_keys = sorted(set(baseline) | set(current))
    for key in all_keys:
        b = baseline.get(key, {m: 0 for m in metrics})
        c = current.get(key, {m: 0 for m in metrics})
        for metric in metrics:
            bv = int(b.get(metric, 0))
            cv = int(c.get(metric, 0))
            if cv > bv:
                msgs.append(
                    f"{key}.{metric}: baseline={bv} current={cv} (regression +{cv - bv})"
                )
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to baseline JSON",
    )
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite baseline file with current counts",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print current snapshot JSON to stdout",
    )
    args = ap.parse_args()
    baseline_path: Path = args.baseline

    current = current_buckets()

    if args.json:
        print(
            json.dumps(
                {"version": 1, "buckets": current},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.write_baseline:
        payload = {
            "version": 1,
            "buckets": current,
            "exempt_paths_relative_to_lib": sorted(EXEMPT_REL),
            "notes": "Ratchet: mock_enum_hits or provider_hits must not increase vs baseline until intentionally updated.",
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote baseline: {baseline_path}", file=sys.stderr)
        return 0

    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(
            f"ERROR: missing or invalid baseline: {baseline_path}\n"
            "Run: python3 scripts/verify_ui_app_data_source_mode_ratchet.py --write-baseline",
            file=sys.stderr,
        )
        return 1

    bad = regressions(baseline, current)
    if bad:
        print(
            "ui_app_data_source_mode RATCHET FAIL (metrics increased):",
            file=sys.stderr,
        )
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nIf the increase is intentional, update the baseline with --write-baseline in a dedicated commit.",
            file=sys.stderr,
        )
        return 1

    print(
        "verify_ui_app_data_source_mode_ratchet: ok (no regression vs baseline)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
