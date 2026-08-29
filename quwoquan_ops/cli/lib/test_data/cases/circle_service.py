from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.circle_service import (
    CIRCLE_GATHERING,
    CIRCLE_GATHERING_PLAN,
    CIRCLE_PENDING_APPROVAL,
    CIRCLE_WITH_MEMBERS,
    CircleGatheringParams,
    CircleGatheringPlanParams,
    CircleGatheringPlanResult,
    CircleGatheringResult,
    CirclePendingApprovalParams,
    CirclePendingApprovalResult,
    CircleWithMembersParams,
    CircleWithMembersResult,
)
from ..capabilities.common import ActorRole
from ..capabilities.user_service import AUTHENTICATED_ACTORS, AuthenticatedActorsParams
from .ids import AcceptanceCaseId


class CircleMembershipCase(BusinessCaseRunner[CircleWithMembersResult]):
    result_type = CircleWithMembersResult

    @classmethod
    def execute(
        cls,
        value: CircleWithMembersResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        owner = context.actor(ActorRole.SENDER)
        executor = context.public_operations(CIRCLE_WITH_MEMBERS.key.value)
        response = executor.call(
            "circle.circle.GetCircle",
            actor=owner,
            step_id="business-get-circle",
            bindings={"circleId": value.circle.object_id},
        )
        observed_circle_id = str(response.get("circleId") or response.get("id") or "")
        persona_circles = executor.call(
            "circle.circle_membership.ListPersonaCircles",
            actor=owner,
            step_id="business-list-persona-circles",
            bindings={"personaId": owner.persona.object_id},
            query={"limit": 50},
        )
        rows = persona_circles.get("items")
        cold_start_visible = any(
            isinstance(row, dict)
            and str(row.get("circleId") or "") == value.circle.object_id
            for row in (rows if isinstance(rows, list) else [])
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "circle-readback",
                    (
                        AssertionStatus.PASSED
                        if observed_circle_id == value.circle.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "circle-membership-count",
                    (
                        AssertionStatus.PASSED
                        if len(value.memberships) == 1
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "circle-cold-start-persona-circles",
                    (
                        AssertionStatus.PASSED
                        if cold_start_visible
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def circle_membership_case() -> CaseRef[CircleWithMembersResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    circle = CIRCLE_WITH_MEMBERS.bind(
        CircleWithMembersParams(
            actors=actors.output.whole(),
            owner_role=ActorRole.SENDER,
            member_roles=(ActorRole.RECEIVER,),
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CIRCLE_MEMBERSHIP,
        request=circle,
        runner_type=CircleMembershipCase,
    )


class CircleGatheringCase(BusinessCaseRunner[CircleGatheringResult]):
    result_type = CircleGatheringResult

    @classmethod
    def execute(
        cls,
        value: CircleGatheringResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        organizer = context.actor(value.organizer_role)
        participant = context.actor(value.participant_role)
        executor = context.public_operations(CIRCLE_GATHERING.key.value)
        detail = executor.call(
            "circle.gathering.GetGathering",
            actor=organizer,
            step_id="business-get-gathering",
            bindings={"gatheringId": value.gathering.object_id},
        )
        observed_gathering_id = str(
            detail.get("gatheringId") or detail.get("id") or ""
        )
        roster = executor.call(
            "circle.gathering.ListGatheringRoster",
            actor=organizer,
            step_id="business-list-gathering-roster",
            bindings={"gatheringId": value.gathering.object_id},
            query={"limit": 50},
        )
        rows = roster.get("items")
        participant_active = any(
            isinstance(row, dict)
            and str(row.get("personaId") or "") == participant.persona.object_id
            and str(row.get("state") or "") == "active"
            for row in (rows if isinstance(rows, list) else [])
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "gathering-readback",
                    (
                        AssertionStatus.PASSED
                        if observed_gathering_id == value.gathering.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "gathering-roster-participant-active",
                    (
                        AssertionStatus.PASSED
                        if participant_active
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def circle_gathering_case() -> CaseRef[CircleGatheringResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    circle = CIRCLE_WITH_MEMBERS.bind(
        CircleWithMembersParams(
            actors=actors.output.whole(),
            owner_role=ActorRole.SENDER,
            member_roles=(ActorRole.RECEIVER,),
        )
    )
    gathering = CIRCLE_GATHERING.bind(
        CircleGatheringParams(
            circle=circle.output.whole(),
            actors=actors.output.whole(),
            organizer_role=ActorRole.SENDER,
            participant_role=ActorRole.RECEIVER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CIRCLE_GATHERING,
        request=gathering,
        runner_type=CircleGatheringCase,
    )


class CircleGatheringPlanCase(BusinessCaseRunner[CircleGatheringPlanResult]):
    result_type = CircleGatheringPlanResult

    @classmethod
    def execute(
        cls,
        value: CircleGatheringPlanResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        organizer = context.actor(value.organizer_role)
        participant = context.actor(value.participant_role)
        executor = context.public_operations(CIRCLE_GATHERING_PLAN.key.value)
        proposed = executor.call(
            "circle.gathering_plan.ProposeGatheringPlan",
            actor=participant,
            step_id="business-propose-gathering-plan",
            bindings={"planId": value.plan.object_id},
            body={
                "expectedPlanVersion": value.plan_version,
                "baseRevisionId": value.current_revision.object_id,
                "baseRevisionNumber": value.current_revision_number,
                "baseRevisionDigest": value.current_revision_digest,
                "items": [
                    {
                        "itemId": "task-1",
                        "kind": "task",
                        "order": 0,
                        "task": {"content": "确认补给", "completed": False},
                        "sourceRefs": [],
                    }
                ],
                "acknowledgementPolicy": {
                    "mode": "affected_participations",
                },
                "affectedParticipationRefs": [
                    {
                        "gatheringId": value.gathering.object_id,
                        "personaId": participant.persona.object_id,
                    }
                ],
            },
        )
        raw_proposal_id = proposed.get("proposalId")
        if not isinstance(raw_proposal_id, str) or not raw_proposal_id.strip():
            raise ValueError("GatheringPlan proposalId is missing or invalid")
        proposal_id = raw_proposal_id.strip()
        raw_proposal_digest = proposed.get("proposalDigest")
        if not isinstance(raw_proposal_digest, str) or not raw_proposal_digest.strip():
            raise ValueError("GatheringPlan proposalDigest is missing or invalid")
        proposal_digest = raw_proposal_digest.strip()
        raw_proposed_version = proposed.get("planVersion")
        expected_proposed_version = value.plan_version + 1
        if (
            type(raw_proposed_version) is not int
            or raw_proposed_version != expected_proposed_version
        ):
            raise ValueError("GatheringPlan proposal planVersion is invalid")
        proposed_version = raw_proposed_version
        committed = executor.call(
            "circle.gathering_plan.CommitGatheringPlanProposal",
            actor=organizer,
            step_id="business-commit-gathering-plan",
            bindings={"planId": value.plan.object_id},
            body={
                "proposalId": proposal_id,
                "expectedPlanVersion": proposed_version,
                "expectedProposalDigest": proposal_digest,
                "expectedBaseRevisionDigest": value.current_revision_digest,
            },
        )
        revisions = executor.call(
            "circle.gathering_plan.ListGatheringPlanRevisions",
            actor=participant,
            step_id="business-list-gathering-plan-revisions",
            bindings={"planId": value.plan.object_id},
            query={"limit": 20},
        )
        rows = revisions.get("items")
        revision_rows = tuple(
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "gathering-plan-proposal-identity",
                    (
                        AssertionStatus.PASSED
                        if proposal_id and proposal_digest and proposed_version == 2
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "gathering-plan-commit-revision",
                    (
                        AssertionStatus.PASSED
                        if str(committed.get("planId") or "")
                        == value.plan.object_id
                        and str(committed.get("gatheringId") or "")
                        == value.gathering.object_id
                        and int(committed.get("planVersion") or 0) == 3
                        and int(committed.get("currentRevisionNumber") or 0) == 2
                        and str(committed.get("currentRevisionDigest") or "")
                        != value.current_revision_digest
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "gathering-plan-immutable-revision-history",
                    (
                        AssertionStatus.PASSED
                        if len(revision_rows) == 2
                        and int(revision_rows[0].get("revisionNumber") or 0) == 1
                        and int(revision_rows[1].get("revisionNumber") or 0) == 2
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def circle_gathering_plan_case() -> CaseRef[CircleGatheringPlanResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    circle = CIRCLE_WITH_MEMBERS.bind(
        CircleWithMembersParams(
            actors=actors.output.whole(),
            owner_role=ActorRole.SENDER,
            member_roles=(ActorRole.RECEIVER,),
        )
    )
    gathering = CIRCLE_GATHERING.bind(
        CircleGatheringParams(
            circle=circle.output.whole(),
            actors=actors.output.whole(),
            organizer_role=ActorRole.SENDER,
            participant_role=ActorRole.RECEIVER,
        )
    )
    plan = CIRCLE_GATHERING_PLAN.bind(
        CircleGatheringPlanParams(
            gathering=gathering.output.whole(),
            actors=actors.output.whole(),
            organizer_role=ActorRole.SENDER,
            participant_role=ActorRole.RECEIVER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CIRCLE_GATHERING_PLAN,
        request=plan,
        runner_type=CircleGatheringPlanCase,
    )


class CirclePendingApprovalCase(BusinessCaseRunner[CirclePendingApprovalResult]):
    result_type = CirclePendingApprovalResult

    @classmethod
    def execute(
        cls,
        value: CirclePendingApprovalResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        owner = context.actor(value.owner_role)
        executor = context.public_operations(CIRCLE_PENDING_APPROVAL.key.value)
        response = executor.call(
            "circle.circle_membership.ListPendingCircleMemberships",
            actor=owner,
            step_id="business-list-pending-memberships",
            bindings={"circleId": value.circle.object_id},
            query={"limit": 50},
        )
        rows = response.get("items")
        records = tuple(
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
        )
        # 不 Approve：保持 pending 状态供待审入圈页面验收。
        applicant_pending = any(
            str(row.get("personaId") or "").strip()
            == value.applicant_persona.object_id
            and str(row.get("state") or "").strip() == "pending"
            for row in records
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "circle-pending-queue-not-empty",
                    (
                        AssertionStatus.PASSED
                        if records
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "circle-pending-contains-applicant",
                    (
                        AssertionStatus.PASSED
                        if applicant_pending
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def circle_pending_approval_case() -> CaseRef[CirclePendingApprovalResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )
    pending = CIRCLE_PENDING_APPROVAL.bind(
        CirclePendingApprovalParams(
            actors=actors.output.whole(),
            owner_role=ActorRole.SENDER,
            applicant_role=ActorRole.RECEIVER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CIRCLE_PENDING_APPROVAL,
        request=pending,
        runner_type=CirclePendingApprovalCase,
    )


__all__ = (
    "CircleGatheringCase",
    "CircleGatheringPlanCase",
    "CircleMembershipCase",
    "CirclePendingApprovalCase",
    "circle_gathering_case",
    "circle_gathering_plan_case",
    "circle_membership_case",
    "circle_pending_approval_case",
)
