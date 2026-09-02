#!/usr/bin/env python3
"""Verify Objective execution contract, dynamic admission, and bounded CLI wiring."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.objective_execution import inspect_admission, load_contract  # noqa: E402
from lib.objective_execution.contract import (  # noqa: E402
    admission_readback_contract,
    emergency_contract_invalid_terminal,
    validate_admission_readback,
)


def _detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _terminal_line(
    *, code: str, terminal: str, recovery: str, detail: str,
    reason: str | None = None,
) -> str:
    reason_field = f" reason={reason}" if reason else ""
    return (
        "[objective-execution] GATE_BLOCK: "
        f"code={code} terminal={terminal}{reason_field} "
        f"recovery={recovery} detail={detail}"
    )


def _contract_failure(error: BaseException) -> int:
    failure = emergency_contract_invalid_terminal(_detail(error))
    print(
        _terminal_line(
            code=failure["code"],
            terminal=failure["terminal"],
            recovery=failure["recovery"],
            detail=failure["detail"],
        ),
        file=sys.stderr,
    )
    return 1


def _canonical_error(
    contract: Mapping[str, Any], code: str, *, detail: str,
    reason: str | None = None,
) -> str:
    descriptor = contract["errors"][code]
    return _terminal_line(
        code=code,
        terminal=descriptor["terminal"],
        recovery=descriptor["recovery"],
        detail=detail,
        reason=reason,
    )


def _issue_line(
    issue: str,
    *,
    contract: Mapping[str, Any],
    admission: Mapping[str, Any] | None,
) -> str:
    if admission is not None and admission.get("status") == "blocked":
        return _canonical_error(
            contract,
            "OEX.ADMISSION_BLOCKED",
            detail=issue,
            reason=str(admission.get("reason") or ""),
        )
    return _canonical_error(
        contract,
        "OEX.CONTRACT_INVALID",
        detail=issue,
    )


def main() -> int:
    try:
        contract = load_contract()
    except Exception as error:
        return _contract_failure(error)

    admission: dict[str, Any] | None = None
    issues: list[str] = []
    try:
        descriptor = admission_readback_contract()
    except Exception as error:
        descriptor = None
        issues.append(f"public admission descriptor unavailable: {_detail(error)}")
    try:
        inspected_admission = inspect_admission()
        admission = validate_admission_readback(inspected_admission)
    except Exception as error:
        issues.append(f"canonical admission inspection failed: {_detail(error)}")

    if contract["owner_story"] != "specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md":
        issues.append("contract owner story drifted")
    if contract.get("schema_version") != 2:
        issues.append("Objective execution contract must be strict schema v2")
    if contract.get("closed_sets", {}).get("admission_status") != [
        "admitted", "not_admitted", "blocked",
    ]:
        issues.append("Objective v2 admission_status closed set drifted")
    graph = contract.get("transition_graph", {})
    if graph.get("graph_version") != 1 or graph.get("reducer_version") != 1:
        issues.append("Objective transition graph/reducer version drifted")
    commands = contract.get("commands", {})
    execution = commands.get("execute_authorized_effect", {})
    if execution.get("pending_identity_match") != "exact_command_envelope_digest" or execution.get("empty_effect_id_readback_allowed") is not False:
        issues.append("Objective pending command/effect identity contract drifted")
    journal = contract.get("journal", {})
    if journal.get("event_chain_authority") is not True or journal.get("derived_drift_terminal") != "OEX.JOURNAL_RECOVERY_REQUIRED":
        issues.append("Objective crash-recovery authority contract drifted")
    trust = journal.get("storage_trust", {})
    if (
        journal.get("event_atomic_write") != "private_staging_fsync_exclusive_publish_fsync_directory"
        or journal.get("exclusive_publish", {}).get("overwrite_fallback_allowed") is not False
        or trust.get("directory_mode") != "0700"
        or trust.get("file_mode") != "0600"
        or trust.get("public_lease_bypass_argument") != "forbidden"
        or trust.get("path_identity") != "retained_dirfd_and_inode"
    ):
        issues.append("Objective journal trusted storage contract drifted")
    required_errors = {"OEX.JOURNAL_RECOVERY_REQUIRED", "OEX.TRANSITION_INVALID", "OEX.PENDING_COMMAND_CONFLICT", "OEX.EFFECT_IDENTITY_CONFLICT"}
    if not required_errors.issubset(contract.get("errors", {})):
        issues.append("Objective P0 typed errors are incomplete")
    if descriptor != contract.get("admission", {}).get("readback_contract"):
        issues.append("public admission descriptor must project the Objective owner contract")
    if admission is not None:
        if admission["status"] == "blocked":
            issues.append("dynamic Objective admission inspection is blocked")
        elif descriptor is not None:
            admitted_policy = descriptor["statuses"]["admitted"]
            expected_admitted = {
                "status": "admitted",
                "stage": descriptor["stage"],
                "write_concurrency": admitted_policy["write_concurrency"],
                "persistent_lane_allowed": admitted_policy["persistent_lane_allowed"],
                "reason": admitted_policy["reason"],
                "terminal": admitted_policy["terminal"],
            }
            if any(admission.get(field) != value for field, value in expected_admitted.items()):
                issues.append("current branch policy must derive the canonical admitted readback")

    try:
        human = yaml.safe_load(
            (ROOT / "quwoquan_ops/policies/human_agent_delivery_contract.yaml").read_text(encoding="utf-8")
        )
    except Exception as error:
        human = None
        issues.append(f"Human-Agent contract unavailable: {_detail(error)}")
    production = human.get("production_policy") if isinstance(human, dict) else None
    if not isinstance(production, dict):
        issues.append("Human-Agent production policy is missing")
    else:
        for forbidden in ("s4_admission", "write_concurrency", "temporary_branch_bypass"):
            if forbidden in production:
                issues.append(f"Human-Agent contract duplicates Objective admission fact: {forbidden}")
    try:
        cli = (ROOT / "quwoquan_ops/cli/objective_execution.py").read_text(encoding="utf-8")
    except Exception as error:
        cli = ""
        issues.append(f"Objective CLI unavailable: {_detail(error)}")
    if "append_event" in cli or "execute-authorized-effect" in cli or "effect_adapter" in cli:
        issues.append("thin local CLI must not expose journal/effect mutation")
    if issues:
        for issue in issues:
            print(
                _issue_line(issue, contract=contract, admission=admission),
                file=sys.stderr,
            )
        return 1
    print("[objective-execution] OK: contract/admission/CLI single-track verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
