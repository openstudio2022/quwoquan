#!/usr/bin/env python3
"""Verify workflow contract closure, parity semantics, and fail-closed PRE routing."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.workflow_resolution import load_contract, validate_contract  # noqa: E402

EXPECTED_WORKFLOWS = (
    "explore", "prd", "design", "dev", "continue", "plan-next", "review", "commit",
    "environment-ops", "content-production", "incident-inspection", "distill",
)


def _detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _issue(detail: str, *, code: str = "WFR.CONTRACT_INVALID") -> str:
    return f"[workflow-resolution] GATE_BLOCK: code={code} terminal=hold recovery=repair_canonical_workflow_resolution_contract detail={detail}"


def main() -> int:
    issues: list[str] = []
    try:
        contract = load_contract()
        validate_contract(contract)
    except Exception as error:
        print(_issue(_detail(error)), file=sys.stderr)
        return 1
    try:
        human = yaml.safe_load((ROOT / "quwoquan_ops/policies/human_agent_delivery_contract.yaml").read_text(encoding="utf-8"))
        binding = human["workflow_interaction_binding"]
    except Exception as error:
        binding = None
        issues.append(f"human interaction binding unavailable: {_detail(error)}")
    try:
        registry = yaml.safe_load((ROOT / ".agents/skills/review/references/registry.yaml").read_text(encoding="utf-8"))
        registry_workflows = registry["workflows"]
    except Exception as error:
        registry_workflows = None
        issues.append(f"review registry unavailable: {_detail(error)}")
    if isinstance(binding, Mapping):
        if tuple(binding.get("required_skills", [])) != tuple(sorted(EXPECTED_WORKFLOWS)):
            issues.append("human interaction required_skills must equal canonical workflow closed set")
        if set(binding.get("bindings", {})) != set(EXPECTED_WORKFLOWS):
            issues.append("human interaction bindings must equal canonical workflow closed set")
    if isinstance(registry_workflows, Mapping) and tuple(registry_workflows) != EXPECTED_WORKFLOWS:
        issues.append("review registry workflows must equal canonical workflow closed set/order")
    for workflow in EXPECTED_WORKFLOWS:
        skill = ROOT / contract["workflows"][workflow]["skill_ref"]
        try:
            text = skill.read_text(encoding="utf-8")
        except OSError as error:
            issues.append(f"skill unavailable: {workflow}: {_detail(error)}")
            continue
        if f"name: {workflow}" not in text or "metadata:\n  kind: workflow" not in text:
            issues.append(f"skill metadata drifted: {workflow}")
        definition = contract["workflows"][workflow]
        command = definition["canonical_command"]
        metadata_region = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
        declared_command = f"command: {command}" in metadata_region
        if definition["automatic_only"]:
            if definition["host_explicit_entry_available"] is not False or declared_command:
                issues.append(f"automatic-only workflow host policy drifted: {workflow}")
        elif definition["host_explicit_entry_available"] is not True or not declared_command:
            issues.append(f"explicit workflow metadata command drifted: {workflow}")
        expected_digest = "sha256:" + hashlib.sha256(skill.read_bytes()).hexdigest()
        if len(expected_digest) != 71:
            issues.append(f"skill digest failed: {workflow}")
    adapter_ref = contract["host_projections"]["neutral_adapter"]
    adapter = ROOT / adapter_ref
    if not adapter.is_file() or adapter.is_symlink():
        issues.append(f"neutral host adapter unavailable: {adapter_ref}")
    cursor = contract["host_projections"]["cursor"]
    for workflow in cursor["explicit_workflows"]:
        shell = ROOT / cursor["explicit_shell_root"] / f"{workflow}.md"
        if not shell.is_file():
            issues.append(f"Cursor command shell missing: {workflow}")
            continue
        shell_text = shell.read_text(encoding="utf-8")
        required = (
            "quwoquan_ops/cli/workflow_host_adapter.py",
            f"--canonical-command /{workflow}",
            "--manifest-ref <repo-relative-manifest.json>",
            "--expected-target <target>",
            f".agents/skills/{workflow}/SKILL.md",
            "verification valid",
        )
        if any(marker not in shell_text for marker in required):
            issues.append(f"Cursor command shell does not prove resolver-before-PRE wiring: {workflow}")
    if cursor["arbitrary_message_intercept_available"] is not False or cursor["natural_discovery_status"] != "unproven":
        issues.append("Cursor arbitrary natural-message interception must remain unproven")
    codex = contract["host_projections"]["codex"]
    if codex["native_explicit_entry_available"] is not False or codex["natural_discovery_status"] != "unproven":
        issues.append("Codex native discovery must remain unproven")
    if contract["smoke_protocol"]["status"] != "OPEN":
        issues.append("real Cursor/Codex discovery smoke must remain OPEN until host evidence exists")
    if issues:
        for issue in issues:
            print(_issue(issue), file=sys.stderr)
        return 1
    print("[workflow-resolution] OK: contract/skills/human-binding/review-registry closure verified; real Cursor/Codex discovery remains OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
