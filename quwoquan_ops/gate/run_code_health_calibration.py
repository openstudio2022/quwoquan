#!/usr/bin/env python3
"""Backtest Code Health Delta on exact merged-PR candidates and aggregate calibration."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.code_health_delta.calibration import aggregate_calibration
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.policy import load_policy


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _sample(value: str) -> tuple[int, str]:
    number, separator, sha = value.partition("=")
    if not separator or not number.isdigit():
        raise argparse.ArgumentTypeError("sample 必须为 <pr-number>=<merge-sha>")
    return int(number), sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append", type=_sample, required=True)
    parser.add_argument("--reviews", type=Path, help="Optional JSON map: '<pr>:<code>:<path>' -> confirmed|false-positive")
    parser.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        reviews = {} if args.reviews is None else json.loads(args.reviews.read_text(encoding="utf-8"))
        if not isinstance(reviews, dict):
            raise ValueError("reviews 必须为 object")
        policy = load_policy(args.policy)
        samples = []
        for pull_request, merge_sha in args.sample:
            head = _git("rev-parse", "--verify", f"{merge_sha}^{{commit}}")
            parents = _git("rev-list", "--parents", "-n", "1", head).split()
            if len(parents) < 3:
                raise ValueError(f"PR #{pull_request} candidate 不是 merge commit")
            base = parents[1]
            started = time.monotonic()
            report = analyze_delta(ROOT, base=base, head=head, policy_path=args.policy, mode="full")
            duration = round(time.monotonic() - started, 3)
            finding_reviews = []
            for finding in report["findings"]:
                key = f"{pull_request}:{finding['code']}:{finding['path']}"
                if key in reviews:
                    finding_reviews.append({"code": finding["code"], "path": finding["path"], "verdict": reviews[key]})
            samples.append({"pullRequest": pull_request, "durationSeconds": duration, "report": report, "findingReviews": finding_reviews})
            print(f"calibration sample PR #{pull_request}: {report['terminal']} {duration:.3f}s", file=sys.stderr)
        observed_at = datetime.now(timezone.utc)
        aggregate = aggregate_calibration(samples, policy=policy, observed_at=observed_at)
        payload = {**aggregate, "samples": samples}
        output = args.output or ROOT / ".qwq_output/env/repo/runs/code-health/calibration" / aggregate["sampleSetDigest"].removeprefix("sha256:") / "report.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"code-health-calibration: {aggregate['promotion']['recommendation']} samples={aggregate['sampleCount']} output={output}")
        return 0
    except Exception as exc:
        print(f"code-health-calibration: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
