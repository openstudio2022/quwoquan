"""Pure commercial, production campaign, and outcome state rules."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contract import load_contract, typed_blocker
from .router import legal_option_ids

try:
    from lib.objective_execution.admission import inspect_admission
except ImportError:  # package import path used by repository tests
    from quwoquan_ops.cli.lib.objective_execution.admission import inspect_admission


def commercial_option_is_legal(
    status: str,
    *,
    hard_gates: Sequence[Mapping[str, Any]],
    limited_scope_reversible: bool = False,
    policy_allows_limited_scope: bool = False,
) -> bool:
    if status not in load_contract()["closed_sets"]["commercial_readiness_status"]:
        return False
    legal = legal_option_ids(
        [{"option_id": "go"}, {"option_id": "limited_go"}, {"option_id": "hold"}, {"option_id": "abort"}],
        hard_gates,
    )
    if status not in legal:
        return False
    if status == "limited_go":
        return limited_scope_reversible and policy_allows_limited_scope
    return True


def advance_campaign(
    approval: Mapping[str, Any],
    *,
    current_stage: str,
    technical_gate_passed: bool,
    stop_predicate: bool = False,
    constraints_changed: bool = False,
    resume_requested: bool = False,
    rollback_authorized: bool = False,
) -> dict[str, Any]:
    policy = load_contract()["production_policy"]
    stages = policy["technical_gate_stages"]
    if constraints_changed or resume_requested:
        return typed_blocker("HAD.CAMPAIGN_REAPPROVAL_REQUIRED")
    if current_stage not in stages:
        return typed_blocker("HAD.CONTRACT_INVALID", detail=f"unknown campaign stage={current_stage}")
    if stop_predicate:
        status = "rolled_back" if rollback_authorized else "paused"
        return {"status": status, "approval_id": approval["decision_id"], "next_stage": None}
    if not technical_gate_passed:
        return {"status": "paused", "approval_id": approval["decision_id"], "next_stage": None}
    index = stages.index(current_stage)
    if index == len(stages) - 1:
        return {"status": "released", "approval_id": approval["decision_id"], "next_stage": None}
    return {"status": "executing", "approval_id": approval["decision_id"], "next_stage": stages[index + 1]}


def production_concurrency_policy() -> dict[str, Any]:
    """Project dynamic Objective execution admission without duplicating branch facts."""
    admission = inspect_admission()
    return {
        "s4_admission": admission["status"],
        "write_concurrency": admission["write_concurrency"],
    }


def transition_inconclusive_outcome(
    *,
    extension_policy: Mapping[str, Any] | None,
    extensions_used: int,
) -> dict[str, Any]:
    required = load_contract()["outcome_policy"]["extension_requires_prefrozen"]
    if not extension_policy or any(field not in extension_policy for field in required):
        return {"outcome": "inconclusive", "observation_state": "clarify", "extensions_used": extensions_used}
    max_extensions = extension_policy["max_extensions"]
    if not isinstance(max_extensions, int) or extensions_used >= max_extensions:
        return {"outcome": "inconclusive", "observation_state": "escalated", "extensions_used": extensions_used}
    return {
        "outcome": "inconclusive",
        "observation_state": "observing",
        "transition": ["observing", "paused", "observing"],
        "extensions_used": extensions_used + 1,
    }


def accept_outcome(outcome: str) -> dict[str, Any]:
    """Accept only the contract three outcome terminals."""
    if outcome not in load_contract()["closed_sets"]["outcome_status"]:
        return typed_blocker("HAD.CONTRACT_INVALID", detail=f"unknown outcome={outcome}")
    return {"outcome": outcome, "observation_state": "accepted"}
