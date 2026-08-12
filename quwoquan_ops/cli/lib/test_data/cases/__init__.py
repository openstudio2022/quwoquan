"""Source-owned typed acceptance cases.

Case factories live beside the control-plane contract so stackctl can serialize
an explicitly selected set without introducing a capability registry or a test
inventory.
"""

from .canonical import (
    AcceptanceCaseId,
    assistant_prompt_case,
    canonical_acceptance_suite,
    chat_recall_case,
    circle_membership_case,
    content_comments_case,
    notification_delivery_case,
    rtc_completed_call_case,
    user_relationship_case,
)

__all__ = (
    "AcceptanceCaseId",
    "assistant_prompt_case",
    "canonical_acceptance_suite",
    "chat_recall_case",
    "circle_membership_case",
    "content_comments_case",
    "notification_delivery_case",
    "rtc_completed_call_case",
    "user_relationship_case",
)
