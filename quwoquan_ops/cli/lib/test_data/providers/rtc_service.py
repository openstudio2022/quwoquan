from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.common import AcceptanceActorSet
from ..capabilities.rtc_service import (
    COMPLETED_CALL,
    CompletedCallParams,
    CompletedCallResult,
)
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


_CALL = CapabilityDefinition(
    capability=COMPLETED_CALL,
    operations=(
        "rtc.call_session.InitiateCall",
        "rtc.call_session.ReportMediaConnected",
        "rtc.call_session.HangupCall",
        "rtc.call_session.ListCalls",
    ),
)


class RtcAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_CALL,)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        return plan_for(_CALL, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if not isinstance(plan.resolved_params, CompletedCallParams):
            raise TypeError("RTC Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        if not isinstance(params.conversation, BusinessObjectRef):
            raise TypeError("conversation dependency was not resolved")
        caller = params.actors.require(params.caller_role)
        callee = params.actors.require(params.callee_role)
        executor = _executor(context, COMPLETED_CALL.key.value)
        initiated = executor.call(
            "rtc.call_session.InitiateCall",
            actor=caller,
            step_id="initiate-call",
            body={
                "callType": "audio",
                "inviteeIds": [callee.persona.object_id],
                "conversationId": params.conversation.object_id,
                "maxParticipants": 2,
            },
        )
        call = BusinessObjectRef("CallSession", required_id(initiated, "callId", "id"))
        try:
            for index, actor in enumerate((caller, callee)):
                executor.call(
                    "rtc.call_session.ReportMediaConnected",
                    actor=actor,
                    step_id=f"media-connected-{index}",
                    bindings={"callId": call.object_id},
                )
            executor.call(
                "rtc.call_session.HangupCall",
                actor=caller,
                step_id="hangup-call",
                bindings={"callId": call.object_id},
            )
        except BaseException as error:
            raise PartialProvisioningError(
                "RTC Provider stopped before the call reached a terminal state",
                provisioned=ProvisionedCapability(
                    value=CompletedCallResult(call=call, final_state="partial"),
                    cleanup_context=caller,
                    operation_count=executor.operation_count,
                ),
            ) from error
        return ProvisionedCapability(
            value=CompletedCallResult(call=call, final_state="ended"),
            cleanup_context=caller,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if not isinstance(provisioned.value, CompletedCallResult):
            return ReadbackResult(passed=False)
        executor = _executor(context, COMPLETED_CALL.key.value + ".readback")
        response = executor.call(
            "rtc.call_session.ListCalls",
            actor=provisioned.cleanup_context,
            step_id="list-calls",
            query={"limit": 20},
        )
        observed = {
            str(item.get("callId") or item.get("id") or "").strip()
            for item in items(response)
        }
        return ReadbackResult(
            passed=provisioned.value.call.object_id in observed,
            operation_count=executor.operation_count,
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if not isinstance(provisioned.value, CompletedCallResult):
            return CleanupResult(state="quarantined")
        if provisioned.value.final_state == "ended":
            # ended is already terminal; UserAccount cleanup follows.
            return CleanupResult(state="released")
        executor = _executor(context, COMPLETED_CALL.key.value + ".cleanup")
        executor.call(
            "rtc.call_session.HangupCall",
            actor=provisioned.cleanup_context,
            step_id="hangup-partial-call",
            bindings={"callId": provisioned.value.call.object_id},
        )
        return CleanupResult(
            state="released",
            operation_count=executor.operation_count,
        )


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


def build_provider() -> RtcAcceptanceDataProvider:
    return RtcAcceptanceDataProvider()
