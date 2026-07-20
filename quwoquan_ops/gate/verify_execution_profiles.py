#!/usr/bin/env python3
"""Prevent profile fallback and retired tier/gate entrypoints from returning."""
from __future__ import annotations

import sys
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TARGET_ACCEPTANCE = (
    ROOT
    / "specs"
    / "feature-tree"
    / "discovery-content"
    / "object-homepage-coverage-scaling"
    / "zhejiang-sichuan-province-coverage"
    / "acceptance.yaml"
)
ACTIVE_PATHS = (
    ROOT / "Makefile",
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "quwoquan_data" / "AGENTS.md",
    ROOT / "quwoquan_ops" / "AGENTS.md",
    ROOT / ".cursor" / "commands" / "deploy.md",
    ROOT / ".cursor" / "commands" / "infra.md",
    ROOT / ".cursor" / "rules" / "03-testing.mdc",
    ROOT / ".cursor" / "rules" / "07-ios-native-ux.mdc",
    ROOT / ".cursor" / "skills" / "environment-ops" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "quwoquan-data-content" / "SKILL.md",
    ROOT / ".github" / "workflows" / "deploy-prod-auto.yml",
    ROOT / "specs" / "03_TESTING_STRATEGY.md",
    ROOT / "specs" / "02_IOS_NATIVE_FRONTEND_UX_SPEC.md",
    ROOT / "specs" / "product" / "2026H1-positioning-refactor" / "90-integration-acceptance.md",
    ROOT / "docs" / "agent_context_contract.md",
    ROOT / "docs" / "agent_command_simulation_matrix.md",
    ROOT / "docs" / "codex_workflow.md",
    ROOT / "quwoquan_ops" / "cli" / "stackctl.py",
)
RETIRED_TOKENS = ("gate" + "-full", "--" + "tier")
RETIRED_PROD_ENVIRONMENT_PATTERNS = (
    re.compile(r"--env-name\s+prod-gray"),
    re.compile(r"environment-smoke-prod-gray"),
)
ALLOWED_PROFILES = {"baseline", "smoke", "integration", "release"}


def _evidence_entries(document: object) -> list[dict[str, object]]:
    if not isinstance(document, dict):
        return []
    entries: list[dict[str, object]] = []
    for group in ("contract_acceptance", "sit_acceptance", "gwt_acceptance"):
        for item in (document.get(group) or {}).values():
            if not isinstance(item, dict):
                continue
            evidence = item.get("test_evidence") or {}
            if not isinstance(evidence, dict):
                continue
            for bucket in ("primary", "supporting"):
                for entry in evidence.get(bucket) or []:
                    if isinstance(entry, dict):
                        entries.append(entry)
    return entries


def main() -> int:
    issues: list[str] = []
    for path in ACTIVE_PATHS:
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_TOKENS:
            if token in text:
                issues.append(f"retired entrypoint {token!r} remains in {path.relative_to(ROOT)}")
        if path.name == "Makefile":
            for pattern in RETIRED_PROD_ENVIRONMENT_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        "production UAT must use env=prod plus rolloutStage, "
                        "not a prod-gray environment alias"
                    )
    document = yaml.safe_load(TARGET_ACCEPTANCE.read_text(encoding="utf-8"))
    entries = _evidence_entries(document)
    if not entries:
        issues.append("two-province acceptance has no test evidence")
    for entry in entries:
        profile = entry.get("execution_profile")
        if profile not in ALLOWED_PROFILES:
            issues.append(f"two-province test evidence has invalid execution_profile {profile!r}")
    if issues:
        print("[verify_execution_profiles] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_execution_profiles] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
