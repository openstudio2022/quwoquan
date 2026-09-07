#!/usr/bin/env python3
"""Clean-candidate adapter binding Code Health Delta to Delivery impact identity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.impact_planner_core import canonical_digest, validate_exact_sha
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.render import render_candidate


def verify_delivery(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    expected_path_digest: str,
    expected_impact_plan_digest: str,
    policy_path: Path | None = None,
) -> tuple[dict[str, Any], Path, str]:
    """Recompute one immutable candidate and bind it to canonical impact identity."""
    repo = repo.resolve()
    base_sha = validate_exact_sha(base_sha, label="base_sha")
    head_sha = validate_exact_sha(head_sha, label="head_sha")
    if not expected_impact_plan_digest.startswith("sha256:"):
        raise ValueError("Delivery impact plan digest is not canonical")
    report = analyze_delta(
        repo,
        base=base_sha,
        head=head_sha,
        policy_path=(policy_path or repo / "quwoquan_ops/policies/code_health_policy.yaml"),
        mode="full",
    )
    if report["changedPathsDigest"] != expected_path_digest:
        raise ValueError("changed-path digest differs from canonical Delivery impact plan")
    identity = canonical_digest(
        {
            "impactPlanDigest": expected_impact_plan_digest,
            "changedPathsDigest": expected_path_digest,
            "policyDigest": report["policyDigest"],
            "implementationDigest": report["implementationDigest"],
            "toolchainDigest": report["evidenceFingerprint"]["digest_payload"]["execution"]["toolchain_digest"],
        }
    )
    fingerprint = report["evidenceFingerprint"]["digest"].removeprefix("sha256:")
    output = repo / ".qwq_output/env/repo/runs/code-health" / fingerprint / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report, output, identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--expected-path-digest", required=True)
    parser.add_argument("--expected-impact-plan-digest", required=True)
    parser.add_argument(
        "--summary-markdown", type=Path,
        help="Also write the Markdown projection (blockers, recovery, debt delta) for the PR step summary",
    )
    args = parser.parse_args()
    try:
        report, output, identity = verify_delivery(
            ROOT,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            expected_path_digest=args.expected_path_digest,
            expected_impact_plan_digest=args.expected_impact_plan_digest,
        )
        markdown = render_candidate(report)
        if args.summary_markdown is not None:
            args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.summary_markdown.write_text(markdown, encoding="utf-8")
        print(markdown, end="")
        print(f"code-health-delivery: {report['terminal']} identity={identity} output={output}")
        return 1 if report["terminal"] == "GATE_BLOCK" else 0
    except Exception as exc:
        print(f"code-health-delivery: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
