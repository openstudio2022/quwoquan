from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationResult,
    DirectConversationWithMessagesParams,
    MessageHandle,
    MessageStatus,
)
from ..capabilities.common import AcceptanceActorSet
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    PartialProvisioningError,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import items, plan_for, required_id


_DIRECT_MESSAGES = CapabilityDefinition(
    capability=DIRECT_CONVERSATION_WITH_MESSAGES,
    operations=(
        "chat.conversation.CreateConversation",
        "chat.message.SendMessage",
        "chat.message.RecallMessage",
        "chat.message.ListMessages",
        "chat.conversation.DissolveConversation",
    ),
)


class ChatAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_DIRECT_MESSAGES,)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        return plan_for(_DIRECT_MESSAGES, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if not isinstance(plan.resolved_params, DirectConversationWithMessagesParams):
            raise TypeError("Chat Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        sender = params.actors.require(params.sender_role)
        receiver = params.actors.require(params.receiver_role)
        executor = _executor(context, DIRECT_CONVERSATION_WITH_MESSAGES.key.value)
        created = executor.call(
            "chat.conversation.CreateConversation",
            actor=sender,
            step_id="create-direct-conversation",
            body={
                "type": "direct",
                "title": "验收会话",
                "maxGroupSize": 2,
                "initialMemberIds": [receiver.account.object_id],
            },
        )
        conversation = BusinessObjectRef(
            "Conversation",
            required_id(created, "conversationId", "id"),
        )
        messages: list[MessageHandle] = []
        try:
            for index in range(params.message_count):
                sent = executor.call(
                    "chat.message.SendMessage",
                    actor=sender,
                    step_id=f"send-message-{index:03d}",
                    bindings={"conversationId": conversation.object_id},
                    body={
                        "type": "text",
                        "content": f"验收消息 {index + 1}",
                        "clientMsgId": (
                            f"{context.test_data_instance_id[:20]}-{index:03d}"
                        ),
                    },
                )
                messages.append(
                    MessageHandle(
                        message=BusinessObjectRef(
                            "Message", required_id(sent, "messageId", "id")
                        ),
                        status=MessageStatus.SENT,
                    )
                )
            recalled = params.recalled_message_index
            if recalled is not None:
                executor.call(
                    "chat.message.RecallMessage",
                    actor=sender,
                    step_id="recall-message",
                    bindings={
                        "conversationId": conversation.object_id,
                        "messageId": messages[recalled].message.object_id,
                    },
                )
                messages[recalled] = MessageHandle(
                    message=messages[recalled].message,
                    status=MessageStatus.RECALLED,
                )
        except BaseException as error:
            raise PartialProvisioningError(
                "Chat Provider stopped after creating a conversation",
                provisioned=ProvisionedCapability(
                    value=DirectConversationResult(
                        conversation=conversation,
                        messages=tuple(messages),
                        # The partial result is cleanup-only and never exposed
                        # as a successful capability result.  Keep a concrete
                        # reference so its strongly typed shape remains valid.
                        delivery_source=(
                            messages[-1].message if messages else conversation
                        ),
                    ),
                    cleanup_handle=(conversation,),
                    cleanup_context=sender,
                    operation_count=executor.operation_count,
                ),
            ) from error
        return ProvisionedCapability(
            value=DirectConversationResult(
                conversation=conversation,
                messages=tuple(messages),
                delivery_source=messages[-1].message,
            ),
            cleanup_handle=(conversation,),
            cleanup_context=sender,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if not isinstance(provisioned.value, DirectConversationResult):
            return ReadbackResult(passed=False)
        sender = provisioned.cleanup_context
        executor = _executor(context, DIRECT_CONVERSATION_WITH_MESSAGES.key.value + ".readback")
        listed = executor.call(
            "chat.message.ListMessages",
            actor=sender,
            step_id="list-messages",
            bindings={
                "conversationId": provisioned.value.conversation.object_id,
            },
            query={"limit": max(20, len(provisioned.value.messages))},
        )
        observed = {
            str(item.get("messageId") or item.get("id") or "").strip()
            for item in items(listed)
        }
        expected = {message.message.object_id for message in provisioned.value.messages}
        return ReadbackResult(
            passed=expected.issubset(observed),
            operation_count=executor.operation_count,
            details={"expectedMessages": len(expected), "observedMessages": len(observed)},
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if not isinstance(provisioned.value, DirectConversationResult):
            return CleanupResult(state="quarantined")
        executor = _executor(context, DIRECT_CONVERSATION_WITH_MESSAGES.key.value + ".cleanup")
        executor.call(
            "chat.conversation.DissolveConversation",
            actor=provisioned.cleanup_context,
            step_id="dissolve-conversation",
            bindings={"conversationId": provisioned.value.conversation.object_id},
        )
        return CleanupResult(state="released", operation_count=executor.operation_count)


def _executor(context: TestDataContext, capability_key: str) -> PublicOperationExecutor:
    if not isinstance(context.runtime, TestDataRuntime):
        raise TypeError("TestData runtime is unavailable")
    return PublicOperationExecutor(
        base_url=context.base_url,
        target=context.candidate.target,
        test_data_instance_id=context.test_data_instance_id,
        capability_key=capability_key,
        runtime=context.runtime,
    )


def build_provider() -> ChatAcceptanceDataProvider:
    return ChatAcceptanceDataProvider()
