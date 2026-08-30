#!/usr/bin/env python3
"""Run the canonical Human-Agent Delivery representative-path eval gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.human_agent_delivery.eval_runner import run_eval  # noqa: E402


def main() -> int:
    report = run_eval()
    print(json.dumps({
        "status": report["status"], "fixture_count": report["fixture_count"],
        "family_counts": report["family_counts"], "machine_score": report["machine_score"],
        "passed_checks": report["passed_checks"],
        "hard_invariant_denominator": report["hard_invariant_denominator"],
        "human_calibration": report["human_calibration"]["status"],
    }, ensure_ascii=False, sort_keys=True))
    if report["status"] != "pass":
        for failure in report["failed_checks"]:
            print(f"[human-agent-delivery-eval] FAIL {failure}", file=sys.stderr)
        return 1
    print("[human-agent-delivery-eval] OK: deterministic representative paths satisfy all hard invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
