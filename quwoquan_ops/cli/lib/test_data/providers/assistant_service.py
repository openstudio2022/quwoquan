from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
    ASSISTANT_SKILL_SUBSCRIPTION,
    AssistantRunParams,
    AssistantRunResult,
    SkillSubscriptionParams,
    SkillSubscriptionResult,
)
from ..capabilities.common import AcceptanceActorSet, ActorHandle
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import items, plan_for, required_id


_RUN = CapabilityDefinition(
    capability=ASSISTANT_PROMPT_RUN,
    operations=(
        "assistant.assistant_session.CreateAssistantSession",
        "assistant.assistant_run.StartAssistantRun",
        "assistant.assistant_run.GetAssistantRun",
    ),
)
_SKILL_SUBSCRIPTION = CapabilityDefinition(
    capability=ASSISTANT_SKILL_SUBSCRIPTION,
    operations=(
        "assistant.skill_catalog.ListSkills",
        "assistant.skill_subscription.CreateSkillSubscription",
        "assistant.skill_subscription.GetSkillSubscription",
        "assistant.skill_subscription.UpdateSkillSubscriptionStatus",
    ),
)


class AssistantAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_RUN, _SKILL_SUBSCRIPTION)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        definition = (
            _SKILL_SUBSCRIPTION
            if request.capability == ASSISTANT_SKILL_SUBSCRIPTION
            else _RUN
        )
        return plan_for(definition, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if isinstance(plan.resolved_params, SkillSubscriptionParams):
            return self._provision_skill_subscription(context, plan.resolved_params)
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

    def _provision_skill_subscription(
        self,
        context: TestDataContext,
        params: SkillSubscriptionParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        subscriber = params.actors.require(params.subscriber_role)
        executor = _executor(context, ASSISTANT_SKILL_SUBSCRIPTION.key.value)
        catalog = executor.call(
            "assistant.skill_catalog.ListSkills",
            actor=subscriber,
            step_id="list-skills",
            query={"limit": 50},
        )
        skills = items(catalog)
        if not skills:
            # fail-closed：active skill package 没有可订阅目录项时不得伪造成功。
            raise RuntimeError(
                "assistant skill catalog has no subscribable skills"
            )
        skill_id = str(skills[0].get("skillId") or "").strip()
        domain_id = str(skills[0].get("domainId") or "").strip()
        if not skill_id or not domain_id:
            raise RuntimeError(
                "assistant skill catalog item misses skillId/domainId"
            )
        create_step = "create-skill-subscription"
        created = executor.call(
            "assistant.skill_subscription.CreateSkillSubscription",
            actor=subscriber,
            step_id=create_step,
            body={
                "skillId": skill_id,
                "domainId": domain_id,
                "tagRefs": [],
                "searchQueryPlan": {
                    "rawText": "验收订阅检索",
                    "queries": ["验收订阅检索"],
                },
                "trigger": {
                    "type": "cron",
                    "cron": "0 9 * * *",
                    "timezone": "Asia/Shanghai",
                },
                "destination": {
                    "destinationType": "user",
                    "destinationId": "",
                    "maxPerDay": 1,
                    "cooldownMinutes": 60,
                    "quietHoursPolicy": "inherit_user_setting",
                },
                "clientRequestId": _command_identity(
                    executor,
                    subscriber,
                    "assistant.skill_subscription.CreateSkillSubscription",
                    create_step,
                ),
            },
        )
        subscription = BusinessObjectRef(
            "SkillSubscription",
            required_id(created, "subscriptionId", "id"),
        )
        return ProvisionedCapability(
            value=SkillSubscriptionResult(
                subscription=subscription,
                skill=BusinessObjectRef("Skill", skill_id),
                subscriber_role=params.subscriber_role,
            ),
            cleanup_handle=(subscription,),
            cleanup_context=subscriber,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if isinstance(provisioned.value, SkillSubscriptionResult):
            executor = _executor(
                context,
                ASSISTANT_SKILL_SUBSCRIPTION.key.value + ".readback",
            )
            response = executor.call(
                "assistant.skill_subscription.GetSkillSubscription",
                actor=provisioned.cleanup_context,
                step_id="get-skill-subscription",
                bindings={
                    "subscriptionId": provisioned.value.subscription.object_id,
                },
            )
            observed = str(
                response.get("subscriptionId") or response.get("id") or ""
            ).strip()
            status = str(response.get("status") or "").strip()
            return ReadbackResult(
                passed=(
                    observed == provisioned.value.subscription.object_id
                    and status == "active"
                ),
                operation_count=executor.operation_count,
                details={"status": status},
            )
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
        if isinstance(provisioned.value, SkillSubscriptionResult):
            executor = _executor(
                context,
                ASSISTANT_SKILL_SUBSCRIPTION.key.value + ".cleanup",
            )
            archive_step = "archive-skill-subscription"
            executor.call(
                "assistant.skill_subscription.UpdateSkillSubscriptionStatus",
                actor=provisioned.cleanup_context,
                step_id=archive_step,
                bindings={
                    "subscriptionId": provisioned.value.subscription.object_id,
                },
                body={
                    "status": "archived",
                    "clientRequestId": _command_identity(
                        executor,
                        provisioned.cleanup_context,
                        "assistant.skill_subscription.UpdateSkillSubscriptionStatus",
                        archive_step,
                    ),
                },
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        # Assistant sessions/runs are append-only evidence and are erased by the
        # later UserAccount closure boundary.
        return CleanupResult(state="released")


def _command_identity(
    executor: PublicOperationExecutor,
    actor: ActorHandle,
    operation_id: str,
    step_id: str,
) -> str:
    """skill_subscription 命令要求 body clientRequestId 与 Idempotency-Key 一致。

    与 ``PublicOperationExecutor.call`` 的 Idempotency-Key 构造公式同源。
    """

    return "/".join(
        (
            executor.target,
            executor.test_data_instance_id,
            executor.capability_key,
            actor.role.value,
            operation_id,
            step_id,
        )
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


def build_provider() -> AssistantAcceptanceDataProvider:
    return AssistantAcceptanceDataProvider()
