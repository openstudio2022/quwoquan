"""Source-owned typed acceptance cases.

Case factories live beside the control-plane contract so stackctl can serialize
an explicitly selected set without introducing a capability registry or a test
inventory.
"""

from .assistant_service import (
    AssistantPromptCase,
    AssistantSkillSubscriptionCase,
    assistant_prompt_case,
    assistant_skill_subscription_case,
)
from .canonical import canonical_acceptance_suite
from .chat_service import (
    ChatGroupGovernanceCase,
    ChatRecallCase,
    chat_group_governance_case,
    chat_recall_case,
)
from .circle_service import (
    CircleGatheringCase,
    CircleMembershipCase,
    CirclePendingApprovalCase,
    circle_gathering_case,
    circle_membership_case,
    circle_pending_approval_case,
)
from .content_service import (
    ContentCommentsCase,
    ContentFootprintCase,
    ContentReactionCase,
    content_comments_case,
    content_footprint_case,
    content_reaction_case,
)
from .ids import AcceptanceCaseId
from .notification_service import NotificationDeliveryCase, notification_delivery_case
from .rtc_service import RtcCompletedCallCase, rtc_completed_call_case
from .user_service import (
    UserFollowingSubjectCase,
    UserGreetingInboxCase,
    UserRelationshipCase,
    user_following_subject_case,
    user_greeting_inbox_case,
    user_relationship_case,
)

__all__ = (
    "AcceptanceCaseId",
    "AssistantPromptCase",
    "AssistantSkillSubscriptionCase",
    "ChatGroupGovernanceCase",
    "ChatRecallCase",
    "CircleGatheringCase",
    "CircleMembershipCase",
    "CirclePendingApprovalCase",
    "ContentCommentsCase",
    "ContentFootprintCase",
    "ContentReactionCase",
    "NotificationDeliveryCase",
    "RtcCompletedCallCase",
    "UserFollowingSubjectCase",
    "UserGreetingInboxCase",
    "UserRelationshipCase",
    "assistant_prompt_case",
    "assistant_skill_subscription_case",
    "canonical_acceptance_suite",
    "chat_group_governance_case",
    "chat_recall_case",
    "circle_gathering_case",
    "circle_membership_case",
    "circle_pending_approval_case",
    "content_comments_case",
    "content_footprint_case",
    "content_reaction_case",
    "notification_delivery_case",
    "rtc_completed_call_case",
    "user_following_subject_case",
    "user_greeting_inbox_case",
    "user_relationship_case",
)
