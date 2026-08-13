"""inventory 报告落盘、CLI 参数与 main 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from .constants import ROOT
from .scanner import (
    Finding,
    Inventory,
    iter_files,
    scan_file,
    scan_versioned_golden_assets,
)


def write_inventory(inv: Inventory, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Single-track contract inventory",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(inv.counts):
        lines.append(f"- {key}: {inv.counts[key]}")
    lines.extend(["", "## Findings", ""])
    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for finding in inv.findings:
        by_cat[finding.category].append(finding)
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for item in by_cat[cat][:200]:
            lines.append(f"- `{item.path}`: {item.detail}")
        if len(by_cat[cat]) > 200:
            lines.append(f"- ... {len(by_cat[cat]) - 200} more")
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "counts": dict(inv.counts),
        "total": sum(inv.counts.values()),
    }
    summary_path = out_path.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory-out",
        default=str(
            ROOT / ".qwq_output/env/repo/runs/single-track-inventory.md"
        ),
    )
    args = parser.parse_args()

    inv = Inventory()
    for path in iter_files():
        scan_file(path, inv)
    scan_versioned_golden_assets(inv)

    out_path = Path(args.inventory_out).resolve()
    write_inventory(inv, out_path)

    total = sum(inv.counts.values())
    try:
        inventory_label = out_path.relative_to(ROOT).as_posix()
    except ValueError:
        inventory_label = str(out_path)
    print(
        f"[single-track] inventory={inventory_label} "
        f"total_findings={total}"
    )
    for key in sorted(inv.counts):
        print(f"  {key}: {inv.counts[key]}")

    if total == 0:
        print("[single-track] OK: zero dual-track / versioned-contract findings")
        return 0

    print("[single-track] FAIL: dual-track or versioned-contract residue remains", file=sys.stderr)
    for finding in inv.findings[:40]:
        print(f"  {finding.category}: {finding.path}: {finding.detail}", file=sys.stderr)
    if total > 40:
        print(f"  ... {total - 40} more (see inventory)", file=sys.stderr)
    return 1
