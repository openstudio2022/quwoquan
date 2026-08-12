from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
    AssistantRunParams,
    AssistantRunResult,
)
from ..capabilities.common import AcceptanceActorSet
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import plan_for, required_id


_RUN = CapabilityDefinition(
    capability=ASSISTANT_PROMPT_RUN,
    operations=(
        "assistant.assistant_session.CreateAssistantSession",
        "assistant.assistant_run.StartAssistantRun",
        "assistant.assistant_run.GetAssistantRun",
    ),
)


class AssistantAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_RUN,)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        return plan_for(_RUN, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if not isinstance(plan.resolved_params, AssistantRunParams):
            raise TypeError("Assistant Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        actor = params.actors.require(params.sender_role)
        executor = _executor(context, ASSISTANT_PROMPT_RUN.key.value)
        session_response = executor.call(
            "assistant.assistant_session.CreateAssistantSession",
            actor=actor,
            step_id="create-session",
            body={
                "summary": "按用例隔离的助手验收会话",
                "clientRequestId": context.test_data_instance_id[:32],
            },
        )
        session = BusinessObjectRef(
            "AssistantSession",
            required_id(session_response, "sessionId", "id"),
        )
        run_response = executor.call(
            "assistant.assistant_run.StartAssistantRun",
            actor=actor,
            step_id="start-run",
            bindings={"sessionId": session.object_id},
            body={
                "turnType": "user",
                "skillId": "travel_companion",
                "domainId": "travel",
                "input": {"text": params.prompt},
                "trigger": {"type": "user"},
                "clientRequestId": context.test_data_instance_id[:32] + "-run",
            },
        )
        run = BusinessObjectRef("AssistantRun", required_id(run_response, "runId", "turnId", "id"))
        return ProvisionedCapability(
            value=AssistantRunResult(session=session, run=run),
            cleanup_context=actor,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if not isinstance(provisioned.value, AssistantRunResult):
            return ReadbackResult(passed=False)
        executor = _executor(context, ASSISTANT_PROMPT_RUN.key.value + ".readback")
        response = executor.call(
            "assistant.assistant_run.GetAssistantRun",
            actor=provisioned.cleanup_context,
            step_id="get-run",
            bindings={
                "runId": provisioned.value.run.object_id,
            },
        )
        observed = str(response.get("runId") or response.get("turnId") or response.get("id") or "").strip()
        return ReadbackResult(
            passed=observed == provisioned.value.run.object_id,
            operation_count=executor.operation_count,
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        # Assistant sessions/runs are append-only evidence and are erased by the
        # later UserAccount closure boundary.
        return CleanupResult(state="released")


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


def build_provider() -> AssistantAcceptanceDataProvider:
    return AssistantAcceptanceDataProvider()
