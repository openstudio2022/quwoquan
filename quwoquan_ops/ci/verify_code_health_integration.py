#!/usr/bin/env python3
"""Hosted recomputation of Code Health Delta for one exact dev1.0 push range.

在 push 已经发生之后运行：它不能拦住 push，只能让 run 失败并发布 typed fact；
把 fact 纳入 promotion required evidence 归 CI/CD owner。before 必须是 after 的祖先
（dev1.0 只允许快进），零 SHA 或非祖先一律 typed GATE_BLOCK，不猜测范围。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.code_health_evidence import write_fact  # noqa: E402
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta  # noqa: E402
from quwoquan_ops.gate.code_health_delta.render import render_candidate  # noqa: E402

FACT_SCHEMA = "quwoquan.code-health-integration.v1"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_ZERO_SHA = "0" * 40


class IntegrationRangeError(ValueError):
    """Raised when the pushed range cannot be recomputed as one exact fast-forward."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)


def validate_range(repo: Path, *, before: str, after: str) -> None:
    for label, value in (("before", before), ("after", after)):
        if _SHA.fullmatch(value) is None:
            raise IntegrationRangeError("CODE_HEALTH.INTEGRATION_RANGE_INVALID", f"{label} 必须为 40 位 exact SHA")
    if before == _ZERO_SHA:
        raise IntegrationRangeError("CODE_HEALTH.INTEGRATION_RANGE_INVALID", "首个 push 没有 exact before，拒绝猜测复算范围")
    if before == after:
        raise IntegrationRangeError("CODE_HEALTH.INTEGRATION_RANGE_INVALID", "before 与 after 相同，没有可复算的范围")
    for value in (before, after):
        if _git(repo, "cat-file", "-e", f"{value}^{{commit}}").returncode:
            raise IntegrationRangeError("CODE_HEALTH.INTEGRATION_RANGE_INVALID", f"{value} 不是本仓库可解析的 commit")
    if _git(repo, "merge-base", "--is-ancestor", before, after).returncode:
        raise IntegrationRangeError(
            "CODE_HEALTH.INTEGRATION_NOT_FAST_FORWARD",
            "before 不是 after 的祖先；dev1.0 只允许快进，非快进 push 不产生 code-health fact",
        )


def recompute(repo: Path, *, before: str, after: str, policy_path: Path) -> dict[str, Any]:
    validate_range(repo, before=before, after=after)
    report = analyze_delta(repo, base=before, head=after, policy_path=policy_path, mode="full")
    return {
        **report,
        "integration": {"schema": FACT_SCHEMA, "before": before, "after": after, "blocksPush": False},
    }


def blocked_fact(*, before: str, after: str, error: IntegrationRangeError) -> dict[str, Any]:
    return {
        "schema": FACT_SCHEMA, "terminal": "GATE_BLOCK",
        "integration": {"schema": FACT_SCHEMA, "before": before, "after": after, "blocksPush": False},
        "blocker": {"code": error.code, "message": str(error)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="Exact OID of dev1.0 before the push (github.event.before)")
    parser.add_argument("--after", required=True, help="Exact OID of dev1.0 after the push (github.event.after)")
    parser.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--fact-output", type=Path, required=True)
    parser.add_argument("--summary-markdown", type=Path)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        fact = recompute(repo, before=args.before, after=args.after, policy_path=args.policy)
    except IntegrationRangeError as error:
        fact = blocked_fact(before=args.before, after=args.after, error=error)
        write_fact(fact, args.fact_output)
        message = f"# Code Health Integration — GATE_BLOCK\n\n- `{error.code}`: {error}\n"
        if args.summary_markdown is not None:
            args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.summary_markdown.write_text(message, encoding="utf-8")
        print(message)
        print(f"code-health-integration: GATE_BLOCK {error.code}: {error}", file=sys.stderr)
        return 1
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(fact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_fact(fact, args.fact_output)
    markdown = render_candidate(fact)
    if args.summary_markdown is not None:
        args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.summary_markdown.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(
        f"code-health-integration: {fact['terminal']} findings={fact['summary']['findingCount']} "
        f"range={args.before[:12]}..{args.after[:12]} fact={args.fact_output}"
    )
    return 1 if fact["terminal"] == "GATE_BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
