"""Text-level half of the control-literal gate.

AST checks live in ``verify_control_literals``.  Version, legacy-workflow, and
provider-query scans intentionally live here so the entrypoint remains a
small orchestration module under the repository file budget.
"""
from __future__ import annotations

import re


LEGACY_PATTERNS = (
    re.compile(r"publish/v\d+"),
    re.compile(r"publish_" + r"version_root|publish_" + r"active_version"),
    re.compile(r"chuan" + r"xi", re.IGNORECASE),
    re.compile(
        r"四川旅行_" + r"v" + "5|泰国旅行_" + r"v" + "5|"
        r"欧洲旅行_" + r"v" + "5|_v" + "5\\b"
    ),
)
VERSIONED_CONTRACT_PATTERN = re.compile(
    r"\b(?:quwoquan_(?:data|service)|quwoquan\.[A-Za-z0-9_.-]+)"
    r"[A-Za-z0-9_.-]*(?:/[0-9]+|\.v[0-9]+)\b"
)
VERSIONED_POLICY_PATTERN = re.compile(
    r"\b(?:encyclopedia-primary|execution-source-qualification|"
    r"execution-model-readiness)-v[0-9]+\b"
)
VERSION_FIELD_PATTERN = re.compile(
    r"(?:[\"'](?:schemaVersion|contractVersion)[\"']\s*:|"
    r"^(?:\s*)(?:schemaVersion|contractVersion)\s*:)",
    re.IGNORECASE,
)
RETIRED_WORKFLOW_TOKENS = (
    "abandoned" + "Objects",
    "abandonedContent" + "Objects",
    "replacement" + "Objects",
    "partialDelivery" + "Reports",
    "targetSetChange" + "Events",
    "targetSetInvalidated" + "Stages",
    "targetSetRequiresRerun" + "From",
    "allowContentQuota" + "Shortfall",
    "allowQuota" + "Shortfall",
    "allowMinEntity" + "Shortfall",
    "best_effort_with_reasoned" + "_rejects",
    "partial_with_replacement" + "_report",
)


def text_control_literal_issues(text: str, *, label: str) -> list[str]:
    """Return legacy/version/control-literal violations without parsing code."""
    issues: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if VERSION_FIELD_PATTERN.search(line):
            issues.append(
                f"{label}:{lineno}: explicit contract version field is forbidden; "
                "current data contracts are single-track"
            )
        if VERSIONED_CONTRACT_PATTERN.search(line) or VERSIONED_POLICY_PATTERN.search(line):
            issues.append(
                f"{label}:{lineno}: versioned data contract is forbidden; use the single unversioned contract"
            )
        if any(pattern.search(line) for pattern in LEGACY_PATTERNS):
            issues.append(f"{label}:{lineno}: retired regional/version hardcode")
        if label.startswith("quwoquan_data/scripts/governance/") and re.search(
            r"\[timeout:\d+\]",
            line,
        ):
            issues.append(f"{label}:{lineno}: provider query timeout belongs to runtime policy")
        for token in RETIRED_WORKFLOW_TOKENS:
            if token in line:
                issues.append(
                    f"{label}:{lineno}: retired mutable-target/partial-delivery contract {token}"
                )
    return issues


__all__ = ["RETIRED_WORKFLOW_TOKENS", "text_control_literal_issues"]
