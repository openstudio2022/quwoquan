#!/usr/bin/env python3
"""Render CI timing summary against shared PR gate budgets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET_FILE = REPO_ROOT / "deploy" / "shared" / "pr_gate_timing_budgets.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-key", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument(
        "--budget-file",
        default=str(DEFAULT_BUDGET_FILE),
    )
    parser.add_argument("--critical-path-seconds", type=int, required=True)
    parser.add_argument("--phase", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--write-step-summary", action="store_true")
    return parser.parse_args()


def parse_key_value(item: str) -> Tuple[str, int]:
    if "=" not in item:
        raise ValueError("expected key=value, got {0!r}".format(item))
    key, raw_value = item.split("=", 1)
    return key.strip(), int(float(raw_value.strip() or "0"))


def load_budget(path: Path, gate_key: str) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    gates = payload.get("gates") or {}
    if gate_key not in gates:
        raise KeyError("gate budget not found: {0}".format(gate_key))
    gate = dict(gates[gate_key])
    gate["totalBudgetSeconds"] = int(payload.get("totalBudgetSeconds", 0) or 0)
    return gate


def format_seconds(value: int) -> str:
    minutes, seconds = divmod(max(int(value), 0), 60)
    if minutes == 0:
        return "{0}s".format(seconds)
    return "{0}m {1:02d}s".format(minutes, seconds)


def render_markdown(
    *,
    title: str,
    gate_key: str,
    gate_budget: Dict[str, Any],
    critical_path_seconds: int,
    phases: List[Tuple[str, int]],
    notes: List[str],
) -> str:
    budget_seconds = int(gate_budget.get("budgetSeconds", 0) or 0)
    critical_definition = str(gate_budget.get("criticalPath", "")).strip()
    status = "within_budget" if critical_path_seconds <= budget_seconds else "over_budget"
    delta = critical_path_seconds - budget_seconds
    phase_budgets = gate_budget.get("phaseBudgetsSeconds") or {}

    lines = [
        "## {0}".format(title or gate_key),
        "",
        "- budget: `{0}`".format(format_seconds(budget_seconds)),
        "- critical path: `{0}`".format(format_seconds(critical_path_seconds)),
        "- budget status: `{0}`".format(status),
        "- delta: `{0}`".format(
            (
                ("+" if delta > 0 else "-") + format_seconds(abs(delta))
                if delta
                else "0s"
            )
        ),
    ]
    if critical_definition:
        lines.append("- critical path definition: `{0}`".format(critical_definition))
    if phases:
        lines.append("- phases:")
        for key, seconds in phases:
            budget = phase_budgets.get(key)
            suffix = ""
            if isinstance(budget, int):
                suffix = " (budget {0})".format(format_seconds(budget))
            lines.append(
                "  - `{0}`: {1}{2}".format(key, format_seconds(seconds), suffix)
            )
    for note in notes:
        if note.strip():
            lines.append("- note: {0}".format(note.strip()))
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    budget_path = Path(args.budget_file)
    if not budget_path.is_absolute():
        budget_path = REPO_ROOT / budget_path
    phases = [parse_key_value(item) for item in args.phase]
    gate_budget = load_budget(budget_path, args.gate_key)
    markdown = render_markdown(
        title=args.title.strip() or args.gate_key,
        gate_key=args.gate_key,
        gate_budget=gate_budget,
        critical_path_seconds=args.critical_path_seconds,
        phases=phases,
        notes=args.note,
    )
    print(markdown)
    if args.write_step_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
