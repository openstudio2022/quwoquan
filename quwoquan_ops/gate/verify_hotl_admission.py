#!/usr/bin/env python3
"""Verify HOTL contract, current fail-closed readback, and read-only CLI surface."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.hotl_admission import contract_failure, inspect, load_contract  # noqa: E402

# write expansion blocker 是否必须在场由动态 S4 准入态派生（objective-execution REQ-003）。
CURRENT_BLOCKERS = (
    "AUTHORITY_PROVIDER_UNAVAILABLE",
    "HUMAN_BOTTLENECK_COHORT_MISSING",
    "CONTROL_PROOF_MISSING",
    "COMMERCIAL_AUTHORITY_NOT_CLOSED",
    "CHECKPOINT_POLICY_UNRESOLVED",
)

_BLOCKER_ERROR_CODES = {
    "RISK_TIER_NOT_ELIGIBLE": "HOTL.RISK_TIER_BLOCKED",
    "AUTHORITY": "HOTL.AUTHORITY_BLOCKED",
    "ROLE_RESPONSIBILITY": "HOTL.AUTHORITY_BLOCKED",
    "SEGREGATION_OF_DUTIES": "HOTL.AUTHORITY_BLOCKED",
    "COHORT": "HOTL.COHORT_BLOCKED",
    "HUMAN_BOTTLENECK": "HOTL.COHORT_BLOCKED",
    "HUMAN_WAIT": "HOTL.COHORT_BLOCKED",
    "HUMAN_CALIBRATION": "HOTL.COHORT_BLOCKED",
    "CONTROL": "HOTL.CONTROL_BLOCKED",
    "REVOKE": "HOTL.CONTROL_BLOCKED",
    "CHECKPOINT": "HOTL.CHECKPOINT_BLOCKED",
    "IMMUTABLE_CHECKPOINT": "HOTL.CHECKPOINT_BLOCKED",
    "RESUME": "HOTL.CHECKPOINT_BLOCKED",
    "HUMAN_OVERRIDE": "HOTL.CHECKPOINT_BLOCKED",
    "COMMERCIAL": "HOTL.COMMERCIAL_BLOCKED",
    "OBJECTIVE_ADMISSION": "HOTL.OBJECTIVE_ADMISSION_BLOCKED",
    "REQUESTED_WRITE": "HOTL.OBJECTIVE_ADMISSION_BLOCKED",
    "WRITE_EXPANSION": "HOTL.OBJECTIVE_ADMISSION_BLOCKED",
    "EVALUATION_IDENTITY": "HOTL.EVALUATION_IDENTITY_FAILED",
    "ACTIVATION": "HOTL.ACTIVATION_BLOCKED",
}


def current_input() -> dict[str, object]:
    return {
        "subject": {
            "subject_id": "current-repository",
            "scope_id": "development-workflow",
            "action_id": "hotl-expansion",
        },
        "risk_tier": "R1",
        "requested_write_concurrency": 1,
        "authority_readback": None,
        "role_responsibility_proof": None,
        "cohort_proof": None,
        "checkpoint_policy": None,
        "control_proofs": [],
        "commercial_authority_readback": None,
        "activation_receipt": None,
    }


def _detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _emit_contract_failure(error: BaseException) -> int:
    failure = contract_failure(_detail(error))
    print(
        "[hotl-admission] GATE_BLOCK: "
        f"code={failure['error_code']} terminal={failure['terminal']} "
        f"recovery={failure['recovery']} detail={failure['detail']}",
        file=sys.stderr,
    )
    return 1


def _error_code_for_blocker(blocker: str) -> str:
    if blocker == "RISK_TIER_NOT_ELIGIBLE":
        return _BLOCKER_ERROR_CODES[blocker]
    for prefix, code in _BLOCKER_ERROR_CODES.items():
        if blocker.startswith(prefix):
            return code
    return "HOTL.CONTRACT_INVALID"


def _descriptor(
    contract: Mapping[str, Any], code: str,
) -> tuple[str, str, str]:
    errors = contract["errors"]
    actual_code = code if code in errors else "HOTL.CONTRACT_INVALID"
    value = errors[actual_code]
    return actual_code, value["terminal"], value["recovery"]


def _emit_issue(
    *, contract: Mapping[str, Any], detail: str, blocker: str | None = None,
    code: str | None = None, stream: Any = sys.stderr, label: str = "GATE_BLOCK",
) -> None:
    actual_code, terminal, recovery = _descriptor(
        contract, code or _error_code_for_blocker(blocker or "INPUT_CONTRACT_INVALID"),
    )
    blocker_text = f" blocker={blocker}" if blocker else ""
    print(
        f"[hotl-admission] {label}: code={actual_code} terminal={terminal} "
        f"recovery={recovery}{blocker_text} detail={detail}",
        file=stream,
    )


def main() -> int:
    try:
        contract = load_contract()
    except Exception as error:
        return _emit_contract_failure(error)

    try:
        readback = inspect(current_input())
    except Exception as error:
        _emit_issue(
            contract=contract,
            code="HOTL.CONTRACT_INVALID",
            detail=f"current evaluator failed: {_detail(error)}",
        )
        return 1

    blockers = readback.get("blockers")
    blocker_values = blockers if isinstance(blockers, list) else []
    if readback.get("status") == "blocked":
        blocker = blocker_values[0] if blocker_values else "INPUT_CONTRACT_INVALID"
        _emit_issue(
            contract=contract,
            detail=str(readback.get("detail") or "current HOTL evaluation is blocked"),
            blocker=blocker,
            code=str(readback.get("error_code") or _error_code_for_blocker(blocker)),
        )
        return 1

    issues: list[tuple[str, str | None, str | None]] = []
    if contract.get("owner_story") != "specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md":
        issues.append(("contract owner story drifted", None, "HOTL.CONTRACT_INVALID"))
    policy = contract["admission_policy"]
    fallback = policy["current_fallback"]
    for field, value in fallback.items():
        if readback.get(field) != value:
            issues.append((f"current readback {field} must match canonical current_fallback", None, "HOTL.CONTRACT_INVALID"))
    if policy.get("allowed_authority_decision_kinds") != ["delivery_authorization"]:
        issues.append(("authority decision kind allowlist drifted", None, "HOTL.CONTRACT_INVALID"))
    activation = policy.get("activation", {})
    if activation.get("provider_available") is not False or activation.get("supplied_receipt_trust") != "audit_only":
        issues.append(("v1 activation provider boundary drifted", None, "HOTL.ACTIVATION_BLOCKED"))

    try:
        from lib.objective_execution import inspect_admission

        expected_s4_status = str(inspect_admission().get("status"))
    except Exception as error:
        _emit_issue(
            contract=contract, code="HOTL.OBJECTIVE_ADMISSION_BLOCKED",
            detail=f"canonical S4 derivation unavailable: {_detail(error)}",
        )
        return 1
    required_blockers = list(CURRENT_BLOCKERS)
    if expected_s4_status != "admitted":
        required_blockers.append("WRITE_EXPANSION_NOT_ADMITTED")
    for blocker in required_blockers:
        if blocker not in blocker_values:
            issues.append(("current readback is missing required fail-closed blocker", blocker, None))
    if readback.get("activation_required") is not True:
        issues.append(("current readback must still require activation", "ACTIVATION_PROVIDER_UNAVAILABLE", None))
    s4 = readback.get("s4_readback")
    if not isinstance(s4, Mapping) or s4.get("status") != expected_s4_status:
        issues.append(("dynamic S4 readback must match canonical branch policy derivation", "OBJECTIVE_ADMISSION_BLOCKED", None))
    try:
        cli = (ROOT / "quwoquan_ops/cli/hotl_admission.py").read_text(encoding="utf-8")
        parser_region = cli[cli.index("def build_parser"):cli.index("def _emit")]
    except Exception as error:
        _emit_issue(
            contract=contract, code="HOTL.CONTRACT_INVALID",
            detail=f"CLI surface could not be inspected: {_detail(error)}",
        )
        return 1
    if 'add_parser("contract")' not in parser_region or 'add_parser("inspect")' not in parser_region:
        issues.append(("CLI must expose contract and inspect", None, "HOTL.CONTRACT_INVALID"))
    if parser_region.count("add_parser(") != 2:
        issues.append(("CLI exposes a mutation or ungoverned command", None, "HOTL.CONTRACT_INVALID"))

    if issues:
        for detail, blocker, code in issues:
            _emit_issue(contract=contract, detail=detail, blocker=blocker, code=code)
        return 1

    for blocker in blocker_values:
        _emit_issue(
            contract=contract,
            detail="canonical current fail-closed blocker",
            blocker=blocker,
            stream=sys.stdout,
            label="EXPECTED_BLOCKER",
        )
    print("[hotl-admission] OK: read-only contract/current fail-closed admission verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
