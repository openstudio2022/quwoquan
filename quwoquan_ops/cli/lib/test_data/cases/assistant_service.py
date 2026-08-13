from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
    ASSISTANT_SKILL_SUBSCRIPTION,
    AssistantRunParams,
    AssistantRunResult,
    SkillSubscriptionParams,
    SkillSubscriptionResult,
)
from ..capabilities.common import ActorRole
from ..capabilities.user_service import AUTHENTICATED_ACTORS, AuthenticatedActorsParams
from .ids import AcceptanceCaseId


class AssistantPromptCase(BusinessCaseRunner[AssistantRunResult]):
    result_type = AssistantRunResult

    @classmethod
    def execute(
        cls,
        value: AssistantRunResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        sender = context.actor(ActorRole.SENDER)
        executor = context.public_operations(ASSISTANT_PROMPT_RUN.key.value)
        response = executor.call(
            "assistant.assistant_run.GetAssistantRun",
            actor=sender,
            step_id="business-get-run",
            bindings={"runId": value.run.object_id},
        )
        observed_run_id = str(
            response.get("runId") or response.get("turnId") or response.get("id") or ""
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "assistant-run-readback",
                    (
                        AssertionStatus.PASSED
                        if observed_run_id == value.run.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "assistant-session-reference",
                    (
                        AssertionStatus.PASSED
                        if value.session.object_type == "AssistantSession"
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def assistant_prompt_case() -> CaseRef[AssistantRunResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.SENDER,))
    )
    run = ASSISTANT_PROMPT_RUN.bind(
        AssistantRunParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            prompt="请返回用于验收的简短确认。",
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.ASSISTANT_PROMPT,
        request=run,
        runner_type=AssistantPromptCase,
    )


class AssistantSkillSubscriptionCase(BusinessCaseRunner[SkillSubscriptionResult]):
    result_type = SkillSubscriptionResult

    @classmethod
    def execute(
        cls,
        value: SkillSubscriptionResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        subscriber = context.actor(value.subscriber_role)
        executor = context.public_operations(ASSISTANT_SKILL_SUBSCRIPTION.key.value)
        response = executor.call(
            "assistant.skill_subscription.GetSkillSubscription",
            actor=subscriber,
            step_id="business-get-skill-subscription",
            bindings={"subscriptionId": value.subscription.object_id},
        )
        observed_subscription_id = str(
            response.get("subscriptionId") or response.get("id") or ""
        )
        observed_skill_id = str(response.get("skillId") or "")
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "skill-subscription-readback",
                    (
                        AssertionStatus.PASSED
                        if observed_subscription_id == value.subscription.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "skill-subscription-skill-binding",
                    (
                        AssertionStatus.PASSED
                        if observed_skill_id == value.skill.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def assistant_skill_subscription_case() -> CaseRef[SkillSubscriptionResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.SENDER,))
    )
    subscription = ASSISTANT_SKILL_SUBSCRIPTION.bind(
        SkillSubscriptionParams(
            actors=actors.output.whole(),
            subscriber_role=ActorRole.SENDER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.ASSISTANT_SKILL_SUBSCRIPTION,
        request=subscription,
        runner_type=AssistantSkillSubscriptionCase,
    )


__all__ = (
    "AssistantPromptCase",
    "AssistantSkillSubscriptionCase",
    "assistant_prompt_case",
    "assistant_skill_subscription_case",
)
