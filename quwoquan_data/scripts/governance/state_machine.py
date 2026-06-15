"""Explicit candidate lifecycle with a mandatory human-review publication gate."""
from __future__ import annotations

STATUS_PENDING_REVIEW = "pending_review"
STATUS_PUBLISHED = "published"
STATUS_REJECTED = "rejected"
STATUS_OFFLINE = "offline"

STATUSES = frozenset(
    {
        STATUS_PENDING_REVIEW,
        STATUS_PUBLISHED,
        STATUS_REJECTED,
        STATUS_OFFLINE,
    }
)

DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
DECISION_OFFLINE = "offline"
DECISION_REOPEN = "reopen"

DECISION_TARGETS = {
    DECISION_APPROVE: STATUS_PUBLISHED,
    DECISION_REJECT: STATUS_REJECTED,
    DECISION_OFFLINE: STATUS_OFFLINE,
    DECISION_REOPEN: STATUS_PENDING_REVIEW,
}

ALLOWED_TRANSITIONS = frozenset(
    {
        (STATUS_PENDING_REVIEW, STATUS_PUBLISHED),
        (STATUS_PENDING_REVIEW, STATUS_REJECTED),
        (STATUS_REJECTED, STATUS_PENDING_REVIEW),
        (STATUS_PUBLISHED, STATUS_OFFLINE),
        (STATUS_OFFLINE, STATUS_PUBLISHED),
    }
)


def transition_target(current_status: str, decision: str) -> str:
    if current_status not in STATUSES:
        raise ValueError(f"unknown candidate status: {current_status!r}")
    target = DECISION_TARGETS.get(decision)
    if target is None:
        raise ValueError(f"unknown review decision: {decision!r}")
    if target == current_status:
        return target
    if (current_status, target) not in ALLOWED_TRANSITIONS:
        raise ValueError(f"invalid candidate transition: {current_status} -> {target}")
    return target


__all__ = [
    "STATUS_PENDING_REVIEW",
    "STATUS_PUBLISHED",
    "STATUS_REJECTED",
    "STATUS_OFFLINE",
    "STATUSES",
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DECISION_OFFLINE",
    "DECISION_REOPEN",
    "ALLOWED_TRANSITIONS",
    "transition_target",
]
