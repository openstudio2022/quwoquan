"""Validate request-wide Patrol constraints before device discovery."""

from __future__ import annotations

from typing import Any

from .constants import ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN
from .session import (
    _is_account_enforcement_target,
    _is_controlled_edge_fault_target,
    _local_target_for_environment_alias,
)


def static_request_issue(
    args: Any,
    *,
    runtime_env: str,
    api_contract_env: str,
    candidate_digest: str,
) -> str:
    issues: list[str] = []
    if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
        if not _is_controlled_edge_fault_target(args):
            issues.append(
                "controlled edge fault requires the canonical feed recovery Patrol target"
            )
        if _local_target_for_environment_alias(args.env_name) not in {
            "alpha-local",
            "beta-local",
            "gamma-local",
        }:
            issues.append(
                "controlled edge fault accepts only Alpha/Beta/Gamma local targets"
            )
        if len([item for item in args.device_id if str(item).strip()]) != 1:
            issues.append("controlled edge fault requires exactly one explicit device")
    if _is_account_enforcement_target(args):
        if args.dry_run:
            issues.append("account-enforcement Gamma UAT forbids dry-run evidence")
        if runtime_env != "gamma" or api_contract_env != "gamma":
            issues.append(
                "account-enforcement UAT requires Gamma runtime and Gamma API contract"
            )
        if ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN.fullmatch(
            candidate_digest
        ) is None:
            issues.append(
                "account-enforcement UAT requires a canonical immutable candidate digest"
            )
    return "; ".join(issues)
