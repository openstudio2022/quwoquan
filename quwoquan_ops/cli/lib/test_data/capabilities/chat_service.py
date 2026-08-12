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


DIRECT_CONVERSATION_WITH_MESSAGES = CapabilityRef(
    key=CapabilityKey("chat.message.direct_conversation_with_messages"),
    params_type=DirectConversationWithMessagesParams,
    result_type=DirectConversationResult,
    owner_service="chat_service",
)

__all__ = (
    "DIRECT_CONVERSATION_WITH_MESSAGES",
    "DirectConversationResult",
    "DirectConversationWithMessagesParams",
    "MessageHandle",
    "MessageStatus",
)
