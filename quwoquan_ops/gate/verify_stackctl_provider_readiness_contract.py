#!/usr/bin/env python3
"""Block removal or reordering of stackctl Provider readiness preflights."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
RUNNER = ROOT / "quwoquan_ops" / "cli" / "provider_conformance_runner.py"


def _function_source(source: str, tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                return segment
    raise ValueError(f"stackctl function is missing: {name}")


def main() -> int:
    source = STACKCTL.read_text(encoding="utf-8")
    runner_source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(STACKCTL))
    issues: list[str] = []

    preflight = _function_source(source, tree, "_run_provider_readiness_preflight")
    for token in (
        'PROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"',
        '"--require-ready"',
        '"provider-readiness.json"',
        '"failureCategories"',
        '"--matrix"',
        '"--capability-id"',
    ):
        if token not in source:
            issues.append(f"stackctl Provider readiness contract missing {token}")
    for token in (
        '"releaseReadiness"',
        'case_result.get("releaseReadiness")',
        "CaseResult must own",
    ):
        if token not in runner_source:
            issues.append(f"Provider runner must derive release receipts from CaseResult: {token}")
    for forbidden in ('"stdout": result.stdout', '"stderr": result.stderr'):
        if forbidden in preflight:
            issues.append(
                "Provider readiness preflight must not persist raw child output "
                f"({forbidden})"
            )

    verify = _function_source(source, tree, "command_verify")
    if 'env_name in {"gamma", "prod"}' not in verify:
        issues.append("release verify must require Provider readiness for gamma and prod")
    if "_run_provider_readiness_preflight(env_name, report_dir)" not in verify:
        issues.append("release verify must invoke the Provider readiness preflight")
    if '"providerReadiness": provider_readiness' not in verify:
        issues.append("release verify report must include sanitized Provider readiness")

    deploy = _function_source(source, tree, "_command_deploy_with_lock")
    preflight_call = deploy.find('_run_provider_readiness_preflight("prod", report_dir)')
    package_action = deploy.find("package_cmd = [")
    if preflight_call < 0:
        issues.append("prod gray-initial deploy must invoke Provider readiness")
    elif package_action < 0 or preflight_call > package_action:
        issues.append("prod Provider readiness must precede package or remote release actions")
    if 'if rollout_stage == "gray-initial":' not in deploy:
        issues.append("prod Provider readiness must be scoped to gray-initial")
    if '"providerReadiness": provider_readiness' not in deploy:
        issues.append("prod deploy report must include sanitized Provider readiness")

    if issues:
        print("[verify_stackctl_provider_readiness_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_stackctl_provider_readiness_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
