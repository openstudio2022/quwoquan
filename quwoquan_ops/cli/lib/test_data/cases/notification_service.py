from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationWithMessagesParams,
)
from ..capabilities.common import ActorRole
from ..capabilities.notification_service import (
    NOTIFICATION_DELIVERY,
    NotificationDeliveryParams,
    NotificationDeliveryResult,
    NotificationMessageType,
)
from ..capabilities.user_service import AUTHENTICATED_ACTORS, AuthenticatedActorsParams
from .ids import AcceptanceCaseId


class NotificationDeliveryCase(BusinessCaseRunner[NotificationDeliveryResult]):
    result_type = NotificationDeliveryResult

    @classmethod
    def execute(
        cls,
        value: NotificationDeliveryResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        recipient = context.actor(ActorRole.RECEIVER)
        executor = context.public_operations(NOTIFICATION_DELIVERY.key.value)
        response = executor.call(
            "notification.notification.ListAppMessages",
            actor=recipient,
            step_id="business-list-app-messages",
            query={"limit": 100},
        )
        rows = _items(response)
        notification = next(
            (
                row
                for row in rows
                if str(
                    row.get("messageId")
                    or row.get("notificationId")
                    or row.get("id")
                    or ""
                ).strip()
                == value.notification.object_id
            ),
            None,
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "notification-delivery-readback",
                    (
                        AssertionStatus.PASSED
                        if value.delivered and notification is not None
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "notification-source-event",
                    (
                        AssertionStatus.PASSED
                        if notification is not None
                        and str(notification.get("source") or "").strip() == "chat_message"
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def notification_delivery_case() -> CaseRef[NotificationDeliveryResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    conversation = DIRECT_CONVERSATION_WITH_MESSAGES.bind(
        DirectConversationWithMessagesParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            receiver_role=ActorRole.RECEIVER,
            message_count=1,
        )
    )
    delivery = NOTIFICATION_DELIVERY.bind(
        NotificationDeliveryParams(
            actors=actors.output.whole(),
            source=conversation.output.delivery_source,
            recipient_role=ActorRole.RECEIVER,
            message_type=NotificationMessageType.CHAT,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.NOTIFICATION_DELIVERY,
        request=delivery,
        runner_type=NotificationDeliveryCase,
    )


def _items(response: object) -> tuple[dict[str, object], ...]:
    if not isinstance(response, dict):
        return ()
    rows = response.get("items")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


__all__ = ("NotificationDeliveryCase", "notification_delivery_case")
