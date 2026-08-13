#!/usr/bin/env python3
"""Block removal or reordering of stackctl Provider readiness preflights."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
# stackctl 域拆分后，契约随函数定义位置迁移：
# - command_verify → commands/verify_domain.py
# - _run_provider_readiness_preflight → commands/environment_probe.py
# - _command_deploy_with_lock → commands/deploy_rollout.py
# - --matrix/--capability-id CLI 面 → commands/provider_conformance_domain.py
VERIFY_DOMAIN = ROOT / "quwoquan_ops" / "cli" / "commands" / "verify_domain.py"
ENVIRONMENT_PROBE = ROOT / "quwoquan_ops" / "cli" / "commands" / "environment_probe.py"
DEPLOY_ROLLOUT = ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_rollout.py"
CONFORMANCE_DOMAIN = (
    ROOT / "quwoquan_ops" / "cli" / "commands" / "provider_conformance_domain.py"
)
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
    probe_source = ENVIRONMENT_PROBE.read_text(encoding="utf-8")
    probe_tree = ast.parse(probe_source, filename=str(ENVIRONMENT_PROBE))
    deploy_source = DEPLOY_ROLLOUT.read_text(encoding="utf-8")
    deploy_tree = ast.parse(deploy_source, filename=str(DEPLOY_ROLLOUT))
    conformance_source = CONFORMANCE_DOMAIN.read_text(encoding="utf-8")
    verify_domain_source = VERIFY_DOMAIN.read_text(encoding="utf-8")
    verify_domain_tree = ast.parse(
        verify_domain_source, filename=str(VERIFY_DOMAIN)
    )
    issues: list[str] = []

    preflight = _function_source(
        probe_source, probe_tree, "_run_provider_readiness_preflight"
    )
    if (
        'PROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"'
        not in source
    ):
        issues.append(
            "stackctl Provider readiness contract missing PROVIDER_CONFORMANCE_SCRIPT"
        )
    for token in (
        '"--require-ready"',
        '"provider-readiness.json"',
        '"failureCategories"',
    ):
        if token not in probe_source:
            issues.append(f"environment probe Provider readiness missing {token}")
    for token in ('"--matrix"', '"--capability-id"'):
        if token not in conformance_source:
            issues.append(f"provider conformance CLI surface missing {token}")
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

    verify = _function_source(
        verify_domain_source, verify_domain_tree, "command_verify"
    )
    if 'env_name in {"gamma", "prod"}' not in verify:
        issues.append("release verify must require Provider readiness for gamma and prod")
    if "_run_provider_readiness_preflight(env_name, report_dir)" not in verify:
        issues.append("release verify must invoke the Provider readiness preflight")
    if '"providerReadiness": provider_readiness' not in verify:
        issues.append("release verify report must include sanitized Provider readiness")

    deploy = _function_source(deploy_source, deploy_tree, "_command_deploy_with_lock")
    preflight_call = deploy.find('_run_provider_readiness_preflight("prod", report_dir)')
    release_actions = (
        deploy.find("_materialize_release_evidence_configuration("),
        deploy.find("deploy_result = _stackctl.run("),
    )
    if preflight_call < 0:
        issues.append("prod canary deploy must invoke Provider readiness")
    elif any(action < 0 or preflight_call > action for action in release_actions):
        issues.append("prod Provider readiness must precede package or remote release actions")
    if 'if rollout_stage == "canary":' not in deploy:
        issues.append("prod Provider readiness must be scoped to canary")
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
