"""Review 派发计划的终态分类职责。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NoReturn


def classify_terminal(
    reviewers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    incomplete_roles: list[dict[str, str] | str],
    failed_evidence_ids: list[str],
    cancelled: bool,
    contract_section: Callable[[str], dict[str, Any]],
    refuse: Callable[[str, str], NoReturn],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """把执行缺口归一为契约声明的终态与 typed incomplete roles。"""

    typed: list[dict[str, Any]] = []
    codes: list[str] = []
    reviewer_map = {item["role"]: item for item in reviewers}
    for raw in incomplete_roles:
        if isinstance(raw, str):
            role, separator, reason = raw.partition("=")
            if not separator:
                role, reason = raw, "unspecified"
        else:
            role = str(raw.get("role") or "")
            reason = str(raw.get("reason") or "unspecified")
        reviewer = reviewer_map.get(role)
        if reviewer is None:
            refuse(
                "REVIEW.INVALID_INCOMPLETE_ROLE",
                f"incomplete role 不在本轮 reviewers 中：{role}",
            )
        code = (
            "REVIEW.REQUIRED_REVIEWER_INCOMPLETE"
            if reviewer["required"]
            else "REVIEW.OPTIONAL_REVIEWER_INCOMPLETE"
        )
        typed.append(
            {
                "role": role,
                "required": reviewer["required"],
                "reason": reason,
                "code": code,
            }
        )
        codes.append(code)

    evidence_ids = {item["id"] for item in evidence}
    invalid_evidence = [item for item in failed_evidence_ids if item not in evidence_ids]
    if invalid_evidence:
        refuse(
            "REVIEW.INVALID_EVIDENCE_RESULT",
            "失败 evidence 不在本轮计划中：" + ", ".join(invalid_evidence),
        )
    if failed_evidence_ids:
        codes.append("REVIEW.EVIDENCE_FAILED")
    if cancelled:
        codes.append("REVIEW.CANCELLED")

    unique_codes = list(dict.fromkeys(codes))
    terminal_contract = contract_section("terminal_codes")
    unknown_codes = [code for code in unique_codes if code not in terminal_contract]
    if unknown_codes:
        refuse(
            "REVIEW.TERMINAL_CONTRACT_INVALID",
            "terminal code 未注册：" + ", ".join(unknown_codes),
        )
    status = "READY"
    if any(
        (terminal_contract.get(code) or {}).get("severity") == "GATE_BLOCK"
        for code in unique_codes
    ):
        status = "GATE_BLOCK"
    elif any(
        (terminal_contract.get(code) or {}).get("severity") == "PR_WARN"
        for code in unique_codes
    ):
        status = "PR_WARN"
    return typed, {
        "status": status,
        "codes": unique_codes,
        "failed_evidence": list(dict.fromkeys(failed_evidence_ids)),
    }


__all__ = ["classify_terminal"]
