#!/usr/bin/env python3
"""
助手 / App 搜索 弱类型棘轮门禁（与 specs/gates/assistant_search_weak_typing_governance.md 一致）。

口径（手写助手，排除生成体目录）：
  - bucket assistant_handwritten: quwoquan_app/lib/assistant/**/*.dart
    排除 **/assistant/generated/** 与 *.g.dart
  - bucket core_search_repository: 单文件 search_repository.dart

指标（每个 bucket，与基线比较）：
  - map_string_dynamic: 字面量 `Map<String, dynamic>`（含空格变体）
  - dynamic_keyword: 词边界 `dynamic`（含泛型/形参等）

辅助信息（仅 `--json` 输出，不参与基线比较）：
  - map_string_object_optional: 字面量 `Map<String, Object?>`（含空格变体）

行为：
  - 默认：与 specs/gates/assistant_search_weak_typing_baseline.json 比较，
    任一指标 **严格大于** 基线 → exit 1（回归）。
  - --write-baseline：用当前扫描覆盖基线文件（有意收口或 bump 基线时用）。

退出码：0 成功；1 回归或基线缺失；2 参数/IO 错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "quwoquan_app" / "lib"
DEFAULT_BASELINE = ROOT / "specs" / "gates" / "assistant_search_weak_typing_baseline.json"

MAP_RE = re.compile(r"Map<String,\s*dynamic>")
MAP_OBJECT_OPT_RE = re.compile(r"Map<String,\s*Object\?>")
DYNAMIC_RE = re.compile(r"\bdynamic\b")

SEARCH_REPO_FILE = LIB / "core" / "services" / "search_repository.dart"


@dataclass
class BucketCounts:
    map_string_dynamic: int
    dynamic_keyword: int


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _scan_assistant_handwritten_files() -> tuple[BucketCounts, int]:
    """Single pass: ratchet counts + informational `Map<String, Object?>` count."""
    m = d = mo = 0
    base = LIB / "assistant"
    if not base.is_dir():
        return BucketCounts(0, 0), 0
    for path in base.rglob("*.dart"):
        if path.name.endswith(".g.dart"):
            continue
        try:
            rel = path.relative_to(LIB)
        except ValueError:
            continue
        if "generated" in rel.parts:
            continue
        text = _read_text(path)
        m += len(MAP_RE.findall(text))
        d += len(DYNAMIC_RE.findall(text))
        mo += len(MAP_OBJECT_OPT_RE.findall(text))
    return BucketCounts(map_string_dynamic=m, dynamic_keyword=d), mo


def scan_assistant_handwritten() -> BucketCounts:
    counts, _ = _scan_assistant_handwritten_files()
    return counts


def _scan_search_repository_files() -> tuple[BucketCounts, int]:
    if not SEARCH_REPO_FILE.is_file():
        return BucketCounts(0, 0), 0
    text = _read_text(SEARCH_REPO_FILE)
    return (
        BucketCounts(
            map_string_dynamic=len(MAP_RE.findall(text)),
            dynamic_keyword=len(DYNAMIC_RE.findall(text)),
        ),
        len(MAP_OBJECT_OPT_RE.findall(text)),
    )


def scan_search_repository() -> BucketCounts:
    counts, _ = _scan_search_repository_files()
    return counts


def current_snapshot() -> dict[str, dict[str, int]]:
    a = scan_assistant_handwritten()
    s = scan_search_repository()
    return {
        "assistant_handwritten": asdict(a),
        "core_search_repository": asdict(s),
    }


def snapshot_for_json() -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """One pass per tree/file: ratchet buckets + informational metrics."""
    a_counts, amo = _scan_assistant_handwritten_files()
    s_counts, smo = _scan_search_repository_files()
    buckets = {
        "assistant_handwritten": asdict(a_counts),
        "core_search_repository": asdict(s_counts),
    }
    info = {
        "assistant_handwritten": {"map_string_object_optional": amo},
        "core_search_repository": {"map_string_object_optional": smo},
    }
    return buckets, info


def load_baseline(path: Path) -> dict[str, dict[str, int]] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    buckets = raw.get("buckets")
    if not isinstance(buckets, dict):
        return None
    out: dict[str, dict[str, int]] = {}
    for k, v in buckets.items():
        if isinstance(v, dict) and all(
            isinstance(v.get(x), int) for x in ("map_string_dynamic", "dynamic_keyword")
        ):
            out[str(k)] = {
                "map_string_dynamic": int(v["map_string_dynamic"]),
                "dynamic_keyword": int(v["dynamic_keyword"]),
            }
    return out if out else None


def regressions(
    baseline: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> list[str]:
    msgs: list[str] = []
    all_keys = sorted(set(baseline) | set(current))
    for key in all_keys:
        b = baseline.get(key, {"map_string_dynamic": 0, "dynamic_keyword": 0})
        c = current.get(key, {"map_string_dynamic": 0, "dynamic_keyword": 0})
        for metric in ("map_string_dynamic", "dynamic_keyword"):
            if c[metric] > b[metric]:
                msgs.append(
                    f"{key}.{metric}: baseline={b[metric]} current={c[metric]} (regression +{c[metric] - b[metric]})"
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
        help="Print current snapshot JSON (buckets + informational_metrics) to stdout",
    )
    args = ap.parse_args()
    baseline_path: Path = args.baseline

    if args.json:
        buckets, info = snapshot_for_json()
        print(
            json.dumps(
                {
                    "version": 1,
                    "buckets": buckets,
                    "informational_metrics": info,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    current = current_snapshot()

    if args.write_baseline:
        payload = {
            "version": 1,
            "buckets": current,
            "notes": "Ratchet: any increase in map_string_dynamic or dynamic_keyword per bucket fails CI until baseline is intentionally updated.",
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
            "Run: python3 scripts/verify_assistant_search_weak_typing_ratchet.py --write-baseline",
            file=sys.stderr,
        )
        return 1

    bad = regressions(baseline, current)
    if bad:
        print("assistant/search weak typing RATCHET FAIL (metrics increased):", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nIf the increase is intentional, update the baseline with --write-baseline in a dedicated commit.",
            file=sys.stderr,
        )
        return 1

    print(
        "verify_assistant_search_weak_typing_ratchet: ok (no regression vs baseline)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
