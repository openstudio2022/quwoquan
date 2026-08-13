from __future__ import annotations

import uuid
from typing import Any

from ...local_environment_auth import open_test_data_acceptance_session
from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.common import (
    AcceptanceActorSet,
    ActorHandle,
    ImmutableReleaseHandle,
)
from ..capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    GREETING_INBOX,
    PERSONA_RELATIONSHIP,
    USER_FOLLOWING_SUBJECTS,
    AuthenticatedActorsParams,
    FollowingSubjectsParams,
    FollowingSubjectsResult,
    GreetingInboxParams,
    GreetingInboxResult,
    RelationshipParams,
    RelationshipResult,
)
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    PartialProvisioningError,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
    canonical_digest,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import items, plan_for


_ACTORS = CapabilityDefinition(
    capability=AUTHENTICATED_ACTORS,
    operations=(
        "user.authentication_challenge.SendOtp",
        "user.account_session.LoginWithPhone",
        "user.user_account.GetActivePersonaContext",
        "user.user_account.CloseAccount",
    ),
)
_RELATIONSHIP = CapabilityDefinition(
    capability=PERSONA_RELATIONSHIP,
    operations=(
        "user.persona_relationship.FollowUser",
        "user.persona_relationship.GetRelationship",
        "user.persona_relationship.UnfollowUser",
    ),
)
_FOLLOWING_SUBJECTS = CapabilityDefinition(
    capability=USER_FOLLOWING_SUBJECTS,
    operations=(
        "user.subject_follow.FollowSubject",
        "user.following_subject.ListFollowingSubjects",
        "user.subject_follow.UnfollowSubject",
    ),
)
_GREETING_INBOX = CapabilityDefinition(
    capability=GREETING_INBOX,
    operations=(
        "user.greeting_request.SendGreetingRequest",
        "user.greeting_request.ListGreetingInbox",
        "user.greeting_request.IgnoreGreetingRequest",
    ),
)
# SubjectFollowTargetKind 闭集中 release homepage 对应的 canonical 值。
_HOMEPAGE_SUBJECT_TYPE = "homepage"


class UserAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_ACTORS, _RELATIONSHIP, _FOLLOWING_SUBJECTS, _GREETING_INBOX)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        if request.capability == AUTHENTICATED_ACTORS:
            definition = _ACTORS
        elif request.capability == USER_FOLLOWING_SUBJECTS:
            definition = _FOLLOWING_SUBJECTS
        elif request.capability == GREETING_INBOX:
            definition = _GREETING_INBOX
        else:
            definition = _RELATIONSHIP
        return plan_for(definition, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if isinstance(plan.resolved_params, AuthenticatedActorsParams):
            runtime = _runtime(context)
            handles: list[ActorHandle] = []
            try:
                for index, role in enumerate(plan.resolved_params.roles):
                    actor = open_test_data_acceptance_session(
                        context.base_url,
                        environment=context.candidate.environment,
                        target_name=context.candidate.target,
                        test_data_instance_id=context.test_data_instance_id,
                        actor_role=role.value,
                        actor_index=index,
                    )
                    handle = ActorHandle(
                        role=role,
                        account=BusinessObjectRef(
                            "UserAccount",
                            actor.session.owner_id,
                        ),
                        persona=BusinessObjectRef(
                            "Persona",
                            actor.session.persona_id,
                        ),
                        session_handle=str(uuid.uuid4()),
                    )
                    runtime.register_actor(
                        handle,
                        actor,
                        test_data_instance_id=context.test_data_instance_id,
                    )
                    handles.append(handle)
                    for operation_id, step_id in (
                        (
                            "user.authentication_challenge.SendOtp",
                            f"send-otp-{index:02d}",
                        ),
                        (
                            "user.account_session.LoginWithPhone",
                            f"login-phone-{index:02d}",
                        ),
                    ):
                        runtime.append_operation(
                            {
                                "operationId": operation_id,
                                "actorRole": role.value,
                                "stepId": step_id,
                                "requestDigest": canonical_digest(
                                    {
                                        "target": context.candidate.target,
                                        "testDataInstanceId": (
                                            context.test_data_instance_id
                                        ),
                                        "actorIndex": index,
                                    }
                                ),
                                "responseDigest": canonical_digest(
                                    {
                                        "ownerId": actor.session.owner_id,
                                        "personaId": actor.session.persona_id,
                                    }
                                ),
                            },
                            test_data_instance_id=context.test_data_instance_id,
                        )
            except BaseException as error:
                if handles:
                    partial_actors = AcceptanceActorSet(tuple(handles))
                    raise PartialProvisioningError(
                        "User Provider actor provisioning stopped after a partial mutation",
                        provisioned=ProvisionedCapability(
                            value=partial_actors,
                            cleanup_handle=tuple(
                                handle.account for handle in handles
                            ),
                            operation_count=2 * len(handles),
                        ),
                    ) from error
                raise
            return ProvisionedCapability(
                value=AcceptanceActorSet(tuple(handles)),
                cleanup_handle=tuple(handle.account for handle in handles),
                operation_count=2 * len(handles),
            )
        if isinstance(plan.resolved_params, FollowingSubjectsParams):
            return self._provision_following_subject(context, plan.resolved_params)
        if isinstance(plan.resolved_params, GreetingInboxParams):
            return self._provision_greeting_inbox(context, plan.resolved_params)
        if not isinstance(plan.resolved_params, RelationshipParams):
            raise TypeError("User Provider received invalid resolved params")
        params = plan.resolved_params
        actors = params.actors
        if not isinstance(actors, AcceptanceActorSet):
            raise TypeError("relationship actors dependency was not resolved")
        source = actors.require(params.source_role)
        target = actors.require(params.target_role)
        executor = _executor(context, PERSONA_RELATIONSHIP.key.value)
        executor.call(
            "user.persona_relationship.FollowUser",
            actor=source,
            step_id="follow-forward",
            bindings={"targetPersonaId": target.persona.object_id},
            body={"source": "acceptance"},
        )
        directions = 1
        if params.mutual:
            executor.call(
                "user.persona_relationship.FollowUser",
                actor=target,
                step_id="follow-reverse",
                bindings={"targetPersonaId": source.persona.object_id},
                body={"source": "acceptance"},
            )
            directions = 2
        return ProvisionedCapability(
            value=RelationshipResult(
                source_role=params.source_role,
                target_role=params.target_role,
                directions=directions,
            ),
            cleanup_context=params,
            operation_count=executor.operation_count,
        )

    def _provision_following_subject(
        self,
        context: TestDataContext,
        params: FollowingSubjectsParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.release, ImmutableReleaseHandle):
            raise TypeError("release dependency was not resolved")
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        follower = params.actors.require(params.follower_role)
        subject = params.release.homepages[0]
        executor = _executor(context, USER_FOLLOWING_SUBJECTS.key.value)
        executor.call(
            "user.subject_follow.FollowSubject",
            actor=follower,
            step_id="follow-subject",
            bindings={
                "subjectType": _HOMEPAGE_SUBJECT_TYPE,
                "subjectId": subject.object_id,
            },
            body={"source": "homepage_detail"},
        )
        return ProvisionedCapability(
            value=FollowingSubjectsResult(
                subject=subject,
                subject_type=_HOMEPAGE_SUBJECT_TYPE,
                follower_role=params.follower_role,
            ),
            cleanup_handle=(subject,),
            cleanup_context=follower,
            operation_count=executor.operation_count,
        )

    def _provision_greeting_inbox(
        self,
        context: TestDataContext,
        params: GreetingInboxParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        sender = params.actors.require(params.sender_role)
        receiver = params.actors.require(params.receiver_role)
        executor = _executor(context, GREETING_INBOX.key.value)
        created = executor.call(
            "user.greeting_request.SendGreetingRequest",
            actor=sender,
            step_id="send-greeting-request",
            body={
                "targetPersonaId": receiver.persona.object_id,
                "requestMessage": params.request_message,
                "source": "profile",
            },
        )
        greeting_id = str(
            created.get("id") or created.get("requestId") or ""
        ).strip()
        if not greeting_id:
            raise RuntimeError("greeting request response misses required identity")
        return ProvisionedCapability(
            value=GreetingInboxResult(
                greeting=BusinessObjectRef("GreetingRequest", greeting_id),
                sender_persona=sender.persona,
                sender_role=params.sender_role,
                receiver_role=params.receiver_role,
            ),
            cleanup_handle=(BusinessObjectRef("GreetingRequest", greeting_id),),
            cleanup_context=params,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if isinstance(provisioned.value, GreetingInboxResult):
            params = provisioned.cleanup_context
            if not isinstance(params, GreetingInboxParams) or not isinstance(
                params.actors,
                AcceptanceActorSet,
            ):
                return ReadbackResult(passed=False)
            receiver = params.actors.require(params.receiver_role)
            executor = _executor(context, GREETING_INBOX.key.value + ".readback")
            listed = executor.call(
                "user.greeting_request.ListGreetingInbox",
                actor=receiver,
                step_id="list-greeting-inbox",
                query={"limit": 50, "status": "pending"},
            )
            observed = {
                (
                    str(item.get("id") or "").strip(),
                    str(item.get("requesterPersonaId") or "").strip(),
                )
                for item in items(listed)
            }
            expected = (
                provisioned.value.greeting.object_id,
                provisioned.value.sender_persona.object_id,
            )
            return ReadbackResult(
                passed=expected in observed,
                operation_count=executor.operation_count,
                details={"inboxCount": len(observed)},
            )
        if isinstance(provisioned.value, FollowingSubjectsResult):
            executor = _executor(
                context,
                USER_FOLLOWING_SUBJECTS.key.value + ".readback",
            )
            listed = executor.call(
                "user.following_subject.ListFollowingSubjects",
                actor=provisioned.cleanup_context,
                step_id="list-following-subjects",
                query={
                    "limit": 50,
                    "subjectType": provisioned.value.subject_type,
                },
            )
            observed = {
                str(item.get("subjectId") or "").strip()
                for item in items(listed)
            }
            return ReadbackResult(
                passed=provisioned.value.subject.object_id in observed,
                operation_count=executor.operation_count,
                details={"followingSubjectCount": len(observed)},
            )
        if isinstance(provisioned.value, AcceptanceActorSet):
            executor = _executor(context, AUTHENTICATED_ACTORS.key.value + ".readback")
            observed = 0
            for index, actor in enumerate(provisioned.value.actors):
                active_context = executor.call(
                    "user.user_account.GetActivePersonaContext",
                    actor=actor,
                    step_id=f"get-active-persona-{index:02d}",
                )
                if (
                    str(active_context.get("ownerUserId") or "").strip()
                    != actor.account.object_id
                    or str(active_context.get("personaId") or "").strip()
                    != actor.persona.object_id
                ):
                    return ReadbackResult(
                        passed=False,
                        operation_count=executor.operation_count,
                    )
                observed += 1
            return ReadbackResult(
                passed=observed == len(provisioned.value.actors) and observed > 0,
                operation_count=executor.operation_count,
                details={"actorCount": observed},
            )
        result = provisioned.value
        if not isinstance(result, RelationshipResult):
            return ReadbackResult(passed=False)
        params = provisioned.cleanup_context
        if not isinstance(params, RelationshipParams) or not isinstance(
            params.actors,
            AcceptanceActorSet,
        ):
            return ReadbackResult(passed=False)
        source = params.actors.require(params.source_role)
        target = params.actors.require(params.target_role)
        executor = _executor(context, PERSONA_RELATIONSHIP.key.value + ".readback")
        relationship = executor.call(
            "user.persona_relationship.GetRelationship",
            actor=source,
            step_id="get-relationship",
            bindings={"personaId": target.persona.object_id},
        )
        expected_state = "mutual" if params.mutual else "following"
        return ReadbackResult(
            passed=(
                result.directions == (2 if params.mutual else 1)
                and relationship.get("relationState") == expected_state
            ),
            operation_count=executor.operation_count,
            details={
                "directions": result.directions,
                "relationState": relationship.get("relationState"),
            },
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if isinstance(provisioned.value, GreetingInboxResult):
            params = provisioned.cleanup_context
            if not isinstance(params, GreetingInboxParams) or not isinstance(
                params.actors,
                AcceptanceActorSet,
            ):
                return CleanupResult(state="quarantined")
            receiver = params.actors.require(params.receiver_role)
            executor = _executor(context, GREETING_INBOX.key.value + ".cleanup")
            # 契约上 decline 对应 IgnoreGreetingRequest（终态 ignored）；
            # ReplyGreetingRequest 是接受语义，会创建正式会话副作用。
            executor.call(
                "user.greeting_request.IgnoreGreetingRequest",
                actor=receiver,
                step_id="ignore-greeting-request",
                bindings={"requestId": provisioned.value.greeting.object_id},
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if isinstance(provisioned.value, FollowingSubjectsResult):
            executor = _executor(
                context,
                USER_FOLLOWING_SUBJECTS.key.value + ".cleanup",
            )
            executor.call(
                "user.subject_follow.UnfollowSubject",
                actor=provisioned.cleanup_context,
                step_id="unfollow-subject",
                bindings={
                    "subjectType": provisioned.value.subject_type,
                    "subjectId": provisioned.value.subject.object_id,
                },
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if isinstance(provisioned.cleanup_context, RelationshipParams):
            params = provisioned.cleanup_context
            actors = params.actors
            if not isinstance(actors, AcceptanceActorSet):
                return CleanupResult(state="quarantined")
            source = actors.require(params.source_role)
            target = actors.require(params.target_role)
            executor = _executor(context, PERSONA_RELATIONSHIP.key.value + ".cleanup")
            executor.call(
                "user.persona_relationship.UnfollowUser",
                actor=source,
                step_id="unfollow-forward",
                bindings={"targetPersonaId": target.persona.object_id},
                body={},
            )
            if params.mutual:
                executor.call(
                    "user.persona_relationship.UnfollowUser",
                    actor=target,
                    step_id="unfollow-reverse",
                    bindings={"targetPersonaId": source.persona.object_id},
                    body={},
                )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if not isinstance(provisioned.value, AcceptanceActorSet):
            return CleanupResult(state="quarantined")
        executor = _executor(context, AUTHENTICATED_ACTORS.key.value + ".cleanup")
        for index, actor in enumerate(reversed(provisioned.value.actors)):
            executor.call(
                "user.user_account.CloseAccount",
                actor=actor,
                step_id=f"close-account-{index:02d}",
                body={
                    "clientRequestId": (
                        f"{context.test_data_instance_id[:24]}-close-{index:02d}"
                    )
                },
            )
        return CleanupResult(state="released", operation_count=executor.operation_count)


def _runtime(context: TestDataContext) -> TestDataRuntime:
    if not isinstance(context.runtime, TestDataRuntime):
        raise TypeError("TestData runtime is unavailable")
    return context.runtime


def _executor(context: TestDataContext, capability_key: str) -> PublicOperationExecutor:
    return PublicOperationExecutor(
        base_url=context.base_url,
        target=context.candidate.target,
        test_data_instance_id=context.test_data_instance_id,
        capability_key=capability_key,
        runtime=_runtime(context),
    )


def build_provider() -> UserAcceptanceDataProvider:
    return UserAcceptanceDataProvider()
