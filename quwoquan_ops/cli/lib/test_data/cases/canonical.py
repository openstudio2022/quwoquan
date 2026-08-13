"""Governed release composition without central business assertions.

Each service owns its runner and factory.  This module only fixes the release
Journey ordering used by ``stackctl test-data-request``.
"""

from __future__ import annotations

from ..api import CaseRef
from .assistant_service import assistant_prompt_case, assistant_skill_subscription_case
from .chat_service import chat_group_governance_case, chat_recall_case
from .circle_service import (
    circle_gathering_case,
    circle_membership_case,
    circle_pending_approval_case,
)
from .content_service import (
    content_comments_case,
    content_footprint_case,
    content_reaction_case,
)
from .notification_service import notification_delivery_case
from .rtc_service import rtc_completed_call_case
from .user_service import (
    user_following_subject_case,
    user_greeting_inbox_case,
    user_relationship_case,
)


def canonical_acceptance_suite() -> tuple[CaseRef[object], ...]:
    return (
        user_relationship_case(),
        user_following_subject_case(),
        user_greeting_inbox_case(),
        content_comments_case(),
        content_reaction_case(),
        content_footprint_case(),
        circle_membership_case(),
        circle_gathering_case(),
        circle_pending_approval_case(),
        chat_recall_case(),
        chat_group_governance_case(),
        assistant_prompt_case(),
        assistant_skill_subscription_case(),
        notification_delivery_case(),
        rtc_completed_call_case(),
    )


__all__ = ("canonical_acceptance_suite",)
