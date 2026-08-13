from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.common import ActorRole
from ..capabilities.content_service import ACTIVE_REFERENCE_RELEASE, ActiveReleaseParams
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
from .ids import AcceptanceCaseId


class UserRelationshipCase(BusinessCaseRunner[RelationshipResult]):
    result_type = RelationshipResult

    @classmethod
    def execute(
        cls,
        value: RelationshipResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        source = context.actor(value.source_role)
        target = context.actor(value.target_role)
        executor = context.public_operations(PERSONA_RELATIONSHIP.key.value)
        response = executor.call(
            "user.persona_relationship.GetRelationship",
            actor=source,
            step_id="business-get-relationship",
            bindings={"personaId": target.persona.object_id},
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "relationship-directions",
                    (
                        AssertionStatus.PASSED
                        if value.directions == 2
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "relationship-readback-mutual",
                    (
                        AssertionStatus.PASSED
                        if response.get("relationState") == "mutual"
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def user_relationship_case() -> CaseRef[RelationshipResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    relationship = PERSONA_RELATIONSHIP.bind(
        RelationshipParams(
            actors=actors.output.whole(),
            source_role=ActorRole.SENDER,
            target_role=ActorRole.RECEIVER,
            mutual=True,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.USER_RELATIONSHIP,
        request=relationship,
        runner_type=UserRelationshipCase,
    )


class UserFollowingSubjectCase(BusinessCaseRunner[FollowingSubjectsResult]):
    result_type = FollowingSubjectsResult

    @classmethod
    def execute(
        cls,
        value: FollowingSubjectsResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        follower = context.actor(value.follower_role)
        executor = context.public_operations(USER_FOLLOWING_SUBJECTS.key.value)
        response = executor.call(
            "user.following_subject.ListFollowingSubjects",
            actor=follower,
            step_id="business-list-following-subjects",
            query={"limit": 50, "subjectType": value.subject_type},
        )
        rows = response.get("items")
        observed = {
            str(row.get("subjectId") or "").strip()
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
        }
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "following-subjects-not-empty",
                    (
                        AssertionStatus.PASSED
                        if observed
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "following-subjects-contains-followed-subject",
                    (
                        AssertionStatus.PASSED
                        if value.subject.object_id in observed
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def user_following_subject_case() -> CaseRef[FollowingSubjectsResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.PRIMARY,))
    )
    release = ACTIVE_REFERENCE_RELEASE.bind(ActiveReleaseParams(minimum_posts=1))
    following = USER_FOLLOWING_SUBJECTS.bind(
        FollowingSubjectsParams(
            release=release.output.whole(),
            actors=actors.output.whole(),
            follower_role=ActorRole.PRIMARY,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.USER_FOLLOWING_SUBJECT,
        request=following,
        runner_type=UserFollowingSubjectCase,
    )


class UserGreetingInboxCase(BusinessCaseRunner[GreetingInboxResult]):
    result_type = GreetingInboxResult

    @classmethod
    def execute(
        cls,
        value: GreetingInboxResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        receiver = context.actor(value.receiver_role)
        executor = context.public_operations(GREETING_INBOX.key.value)
        response = executor.call(
            "user.greeting_request.ListGreetingInbox",
            actor=receiver,
            step_id="business-list-greeting-inbox",
            query={"limit": 50, "status": "pending"},
        )
        rows = response.get("items")
        records = tuple(
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
        )
        sender_pending_visible = any(
            str(row.get("id") or "").strip() == value.greeting.object_id
            and str(row.get("requesterPersonaId") or "").strip()
            == value.sender_persona.object_id
            and str(row.get("status") or "").strip() == "pending"
            for row in records
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "greeting-inbox-not-empty",
                    (
                        AssertionStatus.PASSED
                        if records
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "greeting-inbox-contains-pending-sender",
                    (
                        AssertionStatus.PASSED
                        if sender_pending_visible
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def user_greeting_inbox_case() -> CaseRef[GreetingInboxResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    greeting = GREETING_INBOX.bind(
        GreetingInboxParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            receiver_role=ActorRole.RECEIVER,
            request_message="验收问候：按用例隔离的问候箱事实。",
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.USER_GREETING_INBOX,
        request=greeting,
        runner_type=UserGreetingInboxCase,
    )


__all__ = (
    "UserFollowingSubjectCase",
    "UserGreetingInboxCase",
    "UserRelationshipCase",
    "user_following_subject_case",
    "user_greeting_inbox_case",
    "user_relationship_case",
)
