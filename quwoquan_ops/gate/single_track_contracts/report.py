"""Inventory report, exact-fingerprint ratchet, and CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import ownership, scanner
from .baseline import (
    DEFAULT_BASELINE,
    BaselineError,
    evaluate_ratchet,
    repository_revision,
    write_baseline,
)
from .constants import ROOT
from .scanner import Finding, Inventory

# Stable patch surface consumed by local contracts.
iter_files = scanner.iter_files
scan_file = scanner.scan_file
scan_versioned_golden_assets = scanner.scan_versioned_golden_assets


def write_inventory(inv: Inventory, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Single-track contract inventory", "", "## Counts", ""]
    for key in sorted(inv.counts):
        lines.append(f"- {key}: {inv.counts[key]}")
    lines.extend(["", "## Findings", ""])
    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for finding in inv.findings:
        by_cat[finding.category].append(finding)
    for cat in sorted(by_cat):
        lines.extend([f"### {cat}", ""])
        for item in by_cat[cat][:200]:
            lines.append(f"- `{item.path}`: {item.detail}")
        if len(by_cat[cat]) > 200:
            lines.append(f"- ... {len(by_cat[cat]) - 200} more")
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_path.with_suffix(".json").write_text(
        json.dumps(
            {"counts": dict(inv.counts), "total": sum(inv.counts.values())},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _configure_scan_root(root: Path) -> None:
    """Point every root-derived scanner authority at one read-only repository."""
    scanner.ROOT = root
    ownership.CONTRACT_GRAPH_PATH = root / "quwoquan_service/generated/contract_graph.json"
    ownership.CONTRACT_OBJECT_SOURCE_ROOT = root / "quwoquan_service"
    ownership._contract_graph_object_segments.cache_clear()
    ownership._contract_object_source_dirs.cache_clear()
    ownership._recommendation_identity_object_segments.cache_clear()


def _scan(root: Path) -> Inventory:
    _configure_scan_root(root)
    inv = Inventory()
    for path in iter_files():
        scan_file(path, inv)
    scan_versioned_golden_assets(inv)
    return inv


def _inventory_label(out_path: Path, root: Path) -> str:
    try:
        return out_path.relative_to(root).as_posix()
    except ValueError:
        return str(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to scan (primarily for explicit baseline maintenance)",
    )
    parser.add_argument("--inventory-out", default=None)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="explicitly replace --baseline from the inventory scanned at --root",
    )
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not (root / ".git").exists():
        parser.error(f"--root is not a repository worktree: {root}")
    baseline_path = args.baseline.expanduser().resolve()
    out_path = (
        Path(args.inventory_out).expanduser().resolve()
        if args.inventory_out
        else root / ".qwq_output/env/repo/runs/single-track-inventory.md"
    )
    inv = _scan(root)
    write_inventory(inv, out_path)
    total = sum(inv.counts.values())
    print(
        f"[single-track] inventory={_inventory_label(out_path, root)} "
        f"total_findings={total}"
    )
    for key in sorted(inv.counts):
        print(f"  {key}: {inv.counts[key]}")

    if args.write_baseline:
        try:
            write_baseline(
                inv,
                baseline_path,
                baseline_revision=repository_revision(root),
            )
        except BaselineError as error:
            print(f"[single-track] GATE_BLOCK: {error}", file=sys.stderr)
            return 2
        print(
            f"[single-track] WROTE baseline={baseline_path} findings={total}"
        )
        return 0

    if not baseline_path.exists():
        if total == 0:
            print("[single-track] OK: zero findings; no ratchet baseline needed")
            return 0
        print(
            "[single-track] GATE_BLOCK: findings remain and exact-fingerprint "
            f"baseline is missing: {baseline_path}",
            file=sys.stderr,
        )
        return 2
    try:
        result = evaluate_ratchet(inv, baseline_path)
    except BaselineError as error:
        print(f"[single-track] GATE_BLOCK: {error}", file=sys.stderr)
        return 2

    reduced_findings = 0
    for reduction in result.reductions:
        before_after = reduction.rsplit("count=", 1)[-1]
        before, after = (int(value) for value in before_after.split("->"))
        reduced_findings += before - after
    print(
        "[single-track] ratchet "
        f"baseline_findings={result.baseline_total} "
        f"baseline_identities={result.baseline_identity_count} "
        f"remaining_findings={result.current_total} "
        f"remaining_identities={result.current_identity_count} "
        f"reductions={reduced_findings} "
        f"reduced_identities={len(result.reductions)} "
        f"additions={len(result.failures)}"
    )
    if not result.failures:
        if result.baseline_total == 0:
            print("[single-track] OK: zero baseline and zero current findings")
        else:
            print("[single-track] OK: exact-fingerprint debt did not grow")
        return 0
    print(
        "[single-track] GATE_BLOCK: new or increased exact fingerprints",
        file=sys.stderr,
    )
    for failure in result.failures[:40]:
        print(f"  {failure}", file=sys.stderr)
    if len(result.failures) > 40:
        print(f"  ... {len(result.failures) - 40} more identities", file=sys.stderr)
    return 1
