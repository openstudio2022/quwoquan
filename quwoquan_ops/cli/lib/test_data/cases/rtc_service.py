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
from ..capabilities.rtc_service import (
    COMPLETED_CALL,
    CompletedCallParams,
    CompletedCallResult,
)
from ..capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
    MutualActorRelationship,
)
from .ids import AcceptanceCaseId


class RtcCompletedCallCase(BusinessCaseRunner[CompletedCallResult]):
    result_type = CompletedCallResult

    @classmethod
    def execute(
        cls,
        value: CompletedCallResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        caller = context.actor(ActorRole.SENDER)
        executor = context.public_operations(COMPLETED_CALL.key.value)
        response = executor.call(
            "rtc.call_session.ListCalls",
            actor=caller,
            step_id="business-list-calls",
            query={"limit": 20},
        )
        calls = _items(response)
        call = next(
            (
                row
                for row in calls
                if str(row.get("callId") or row.get("id") or "").strip()
                == value.call.object_id
            ),
            None,
        )
        observed_state = str(
            (call or {}).get("state") or (call or {}).get("status") or ""
        ).lower()
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "rtc-call-readback",
                    (
                        AssertionStatus.PASSED
                        if call is not None
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "rtc-terminal-state-readback",
                    (
                        AssertionStatus.PASSED
                        if value.final_state == "ended" and observed_state == "ended"
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def rtc_completed_call_case() -> CaseRef[CompletedCallResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
            mutual_relationships=(
                MutualActorRelationship(
                    source_role=ActorRole.SENDER,
                    target_role=ActorRole.RECEIVER,
                ),
            ),
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
    call = COMPLETED_CALL.bind(
        CompletedCallParams(
            actors=actors.output.whole(),
            conversation=conversation.output.conversation,
            caller_role=ActorRole.SENDER,
            callee_role=ActorRole.RECEIVER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.RTC_COMPLETED_CALL,
        request=call,
        runner_type=RtcCompletedCallCase,
    )


def _items(response: object) -> tuple[dict[str, object], ...]:
    if not isinstance(response, dict):
        return ()
    rows = response.get("items")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


__all__ = ("RtcCompletedCallCase", "rtc_completed_call_case")
