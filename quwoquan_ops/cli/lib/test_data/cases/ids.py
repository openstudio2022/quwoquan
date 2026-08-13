from enum import StrEnum


class AcceptanceCaseId(StrEnum):
    USER_RELATIONSHIP = "user-relationship"
    USER_FOLLOWING_SUBJECT = "user-following-subject"
    USER_GREETING_INBOX = "user-greeting-inbox"
    CONTENT_COMMENTS = "content-comments"
    CONTENT_FOOTPRINT = "content-footprint"
    CONTENT_REACTION = "content-reaction"
    CIRCLE_MEMBERSHIP = "circle-membership"
    CIRCLE_GATHERING = "circle-gathering"
    CIRCLE_PENDING_APPROVAL = "circle-pending-approval"
    CHAT_RECALL = "chat-recall"
    CHAT_GROUP_GOVERNANCE = "chat-group-governance"
    ASSISTANT_PROMPT = "assistant-prompt"
    ASSISTANT_SKILL_SUBSCRIPTION = "assistant-skill-subscription"
    NOTIFICATION_DELIVERY = "notification-delivery"
    RTC_COMPLETED_CALL = "rtc-completed-call"
