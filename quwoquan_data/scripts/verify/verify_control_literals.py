#!/usr/bin/env python3
"""Enforce single owners for Data execution control literals."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from core.paths import DATA_ROOT, REPO_ROOT
from verify.control_literal_text import text_control_literal_issues


SCRIPTS_ROOT = DATA_ROOT / "scripts"
_POLICY_ARGUMENT = re.compile(
    r"(?:timeout|timeout_seconds|retry_limit|max_retries|max_workers|concurrency|stagger_seconds|backoff_seconds)$",
    re.IGNORECASE,
)
_RETIRED_PHASE = re.compile(r"\b(?:canary|m[1-3]|h10k)\b", re.IGNORECASE)
_RETIRED_TASK_TOKEN = re.compile(r"(?:two[_ -]?province|rolloutMilestone)", re.IGNORECASE)
_RETIRED_TASK_IDENTIFIER = re.compile(
    r"(?:two_?province|rollout_?milestone)", re.IGNORECASE
)


def source_control_literal_issues(source: str, *, label: str) -> list[str]:
    """Check a Python module without encoding task-specific baselines.

    Numeric defaults on control arguments are rejected so active modules expose
    timeouts and retry budgets at their call boundary instead of hiding them.
    Protocol payloads may retain numeric data; this check only covers control parameters.
    """
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        return [f"{label}:{exc.lineno}: invalid Python syntax"]
    issues: list[str] = []
    docstrings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and _RETIRED_TASK_IDENTIFIER.search(node.id):
            issues.append(
                f"{label}:{node.lineno}: retired task-specific control identifier {node.id!r}"
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings and (
                _RETIRED_PHASE.search(node.value) or _RETIRED_TASK_TOKEN.search(node.value)
            ):
                issues.append(
                    f"{label}:{node.lineno}: retired task-specific control literal {node.value!r}"
                )
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = [*node.args.posonlyargs, *node.args.args]
        defaults = [None] * (len(arguments) - len(node.args.defaults)) + list(node.args.defaults)
        pairs = [*zip(arguments, defaults), *zip(node.args.kwonlyargs, node.args.kw_defaults)]
        for argument, default in pairs:
            if (
                default is not None
                and isinstance(default, ast.Constant)
                and isinstance(default.value, (int, float))
                and _POLICY_ARGUMENT.search(argument.arg)
            ):
                issues.append(
                    f"{label}:{node.lineno}: {argument.arg} numeric default must be explicit at the call boundary"
                )
    issues.extend(text_control_literal_issues(source, label=label))
    return issues


def control_literal_issues() -> list[str]:
    issues: list[str] = []
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        if (
            path == Path(__file__).resolve()
            or "__pycache__" in path.parts
            or "generated" in path.parts
            or "verify" in path.parts
        ):
            continue
        issues.extend(
            source_control_literal_issues(
                path.read_text(encoding="utf-8"),
                label=path.relative_to(REPO_ROOT).as_posix(),
            )
        )
    return issues


def main() -> int:
    issues = control_literal_issues()
    if issues:
        print("[verify_control_literals] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_control_literals] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
