from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..api import BusinessObjectRef, CapabilityKey, CapabilityRef, OutputRef
from .common import AcceptanceActorSet, ActorRole


class MessageStatus(StrEnum):
    SENT = "sent"
    RECALLED = "recalled"


@dataclass(frozen=True)
class DirectConversationWithMessagesParams:
    actors: OutputRef[AcceptanceActorSet]
    sender_role: ActorRole
    receiver_role: ActorRole
    message_count: int
    recalled_message_index: int | None = None

    def __post_init__(self) -> None:
        if self.sender_role is self.receiver_role:
            raise ValueError("sender and receiver roles must differ")
        if self.message_count < 1:
            raise ValueError("message_count must be positive")
        if self.recalled_message_index is not None and not (
            0 <= self.recalled_message_index < self.message_count
        ):
            raise ValueError("recalled_message_index is outside the message range")


@dataclass(frozen=True)
class MessageHandle:
    message: BusinessObjectRef
    status: MessageStatus


@dataclass(frozen=True)
class DirectConversationResult:
    conversation: BusinessObjectRef
    messages: tuple[MessageHandle, ...]
    delivery_source: BusinessObjectRef


@dataclass(frozen=True)
class GroupConversationParams:
    actors: OutputRef[AcceptanceActorSet]
    # 群聊创建要求 owner 与每个受邀成员互关（CHAT.USER.group_member_not_mutual）；
    # gate 引用 user_service relationship 的 directions 输出，仅用于建立 DAG 前置。
    mutual_follow_gates: tuple[OutputRef[int], ...]
    owner_role: ActorRole
    member_roles: tuple[ActorRole, ...]
    admin_role: ActorRole
    announcement: str

    def __post_init__(self) -> None:
        if len(self.member_roles) < 2 or len(set(self.member_roles)) != len(
            self.member_roles
        ):
            raise ValueError(
                "group conversation requires at least two distinct member roles"
            )
        if self.owner_role in self.member_roles:
            raise ValueError("group owner role must not repeat inside member roles")
        if self.admin_role not in self.member_roles:
            raise ValueError("group admin role must be one of the invited members")
        if len(self.mutual_follow_gates) != len(self.member_roles):
            raise ValueError("each invited member requires one mutual-follow gate")
        if not self.announcement.strip():
            raise ValueError("group conversation requires a non-empty announcement")


@dataclass(frozen=True)
class GroupConversationResult:
    conversation: BusinessObjectRef
    members: tuple[BusinessObjectRef, ...]
    admin: BusinessObjectRef
    owner_role: ActorRole
    admin_role: ActorRole
    announcement: str


DIRECT_CONVERSATION_WITH_MESSAGES = CapabilityRef(
    key=CapabilityKey("chat.message.direct_conversation_with_messages"),
    params_type=DirectConversationWithMessagesParams,
    result_type=DirectConversationResult,
    owner_service="chat_service",
)

GROUP_CONVERSATION = CapabilityRef(
    key=CapabilityKey("chat.conversation.group_conversation"),
    params_type=GroupConversationParams,
    result_type=GroupConversationResult,
    owner_service="chat_service",
)

__all__ = (
    "DIRECT_CONVERSATION_WITH_MESSAGES",
    "GROUP_CONVERSATION",
    "DirectConversationResult",
    "DirectConversationWithMessagesParams",
    "GroupConversationParams",
    "GroupConversationResult",
    "MessageHandle",
    "MessageStatus",
)
