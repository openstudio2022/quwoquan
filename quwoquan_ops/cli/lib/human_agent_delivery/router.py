"""Pure Human-Agent Delivery role router and hard-gate evaluators."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .contract import closed_values, load_contract, namespace_values, typed_blocker


def _route_table() -> dict[tuple[str, str], dict[str, Any]]:
    return {(item["stage"], item["decision_kind"]): item for item in load_contract()["router"]}


def route(
    stage: str,
    decision_kind: str,
    *,
    current_role: str | None = None,
    actor_authenticated: bool = True,
    role_present: bool = True,
    timed_out: bool = False,
    scope_valid: bool = True,
    evidence_fresh: bool = True,
    hard_gates: Sequence[Mapping[str, Any]] = (),
    risk_categories: Sequence[str] = (),
    sod_policy: str | None = None,
    role_actor_ids: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return only required role, no-human-needed, or one typed blocker."""
    if stage not in closed_values("delivery_stage"):
        return typed_blocker("HAD.UNKNOWN_STAGE", detail=stage)
    if decision_kind not in closed_values("decision_kind"):
        return typed_blocker("HAD.UNKNOWN_DECISION_KIND", detail=decision_kind)
    entry = _route_table().get((stage, decision_kind))
    if entry is None:
        return typed_blocker("HAD.ROUTE_NOT_FOUND", detail=f"{stage}+{decision_kind}")
    required_role = entry["accountable_role"]
    if required_role is None:
        return {"result": "no_human_needed"}
    if current_role in namespace_values("review_role") or (current_role or "").startswith("review."):
        return typed_blocker("HAD.REVIEW_ROLE_FORBIDDEN", terminal=entry["default_terminal"])
    if current_role is not None and current_role != required_role:
        return typed_blocker(
            "HAD.WRONG_HUMAN_ROLE",
            detail=f"required={required_role}, actual={current_role}",
            terminal=entry["default_terminal"],
        )
    for failed, code in (
        (not actor_authenticated, "HAD.IDENTITY_UNKNOWN"),
        (not role_present, "HAD.ROLE_ABSENT"),
        (timed_out, "HAD.ROLE_TIMEOUT"),
        (not scope_valid, "HAD.SCOPE_INVALID"),
        (not evidence_fresh, "HAD.EVIDENCE_EXPIRED"),
    ):
        if failed:
            return typed_blocker(code, terminal=entry["default_terminal"])
    failed_gates = [
        gate for gate in hard_gates
        if gate.get("passed") is not True or gate.get("evidence_fresh") is not True
    ]
    if failed_gates:
        return typed_blocker(
            "HAD.HARD_GATE_FAILED",
            detail=",".join(str(gate.get("gate_id") or "unknown") for gate in failed_gates),
            terminal=entry["default_terminal"],
        )
    contract = load_contract()
    policies = contract["sod_policies"]
    risk_policy = contract["risk_sod_policy"]
    unknown_risks = sorted(set(risk_categories) - set(risk_policy["classifications"]))
    if unknown_risks:
        return typed_blocker("HAD.SOD_FAILED", detail=f"unknown risk categories={unknown_risks}")
    required_by_risk = {risk_policy["classifications"][risk] for risk in risk_categories}
    effective_sod_policy = sod_policy or risk_policy["default"]
    if "independent-principal-required" in required_by_risk:
        effective_sod_policy = "independent-principal-required"
    if effective_sod_policy not in policies:
        return typed_blocker("HAD.SOD_FAILED", detail=f"unknown policy={effective_sod_policy}")
    required_principal_roles = [required_role, *entry["hard_veto_roles"]]
    actors = role_actor_ids or {}
    if policies[effective_sod_policy]["distinct_authenticated_actors_required"]:
        identities = [actors.get(role) for role in required_principal_roles]
        if any(not identity for identity in identities) or len(set(identities)) != len(identities):
            return typed_blocker(
                "HAD.SOD_FAILED",
                detail="independent principal roles require distinct authenticated actors",
                terminal=entry["default_terminal"],
            )
    return {
        "result": "required_role",
        "role": required_role,
        "hard_veto_roles": list(entry["hard_veto_roles"]),
        "default_terminal": entry["default_terminal"],
    }


def legal_option_ids(
    options: Sequence[Mapping[str, Any]],
    hard_gates: Sequence[Mapping[str, Any]],
    *,
    majority_option_ids: Iterable[str] = (),
) -> tuple[str, ...]:
    """Hard gates remove options before preferences; votes cannot re-add them."""
    del majority_option_ids
    option_ids = {str(option["option_id"]) for option in options}
    blocked: set[str] = set()
    for gate in hard_gates:
        if gate.get("passed") is not True or gate.get("evidence_fresh") is not True:
            blocked.update(str(value) for value in gate.get("option_ids", ()))
    return tuple(sorted(option_ids - blocked))


def stable_option_order(options: Sequence[Mapping[str, Any]], seed: str) -> tuple[dict[str, Any], ...]:
    """Stable order without process-global random state."""
    return tuple(
        dict(option)
        for option in sorted(
            options,
            key=lambda option: (
                hashlib.sha256(f"{seed}\0{option['option_id']}".encode("utf-8")).digest(),
                str(option["option_id"]),
            ),
        )
    )


def balanced_permutations(options: Sequence[Mapping[str, Any]], seed: str) -> tuple[tuple[dict[str, Any], ...], ...]:
    """Return cyclic rotations so every option occupies every position once."""
    base = stable_option_order(options, seed)
    return tuple(base[index:] + base[:index] for index in range(len(base)))
