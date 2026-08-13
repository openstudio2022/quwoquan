from __future__ import annotations

import datetime as dt
import time
from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.circle_service import (
    CIRCLE_GATHERING,
    CIRCLE_PENDING_APPROVAL,
    CIRCLE_WITH_MEMBERS,
    CircleGatheringParams,
    CircleGatheringResult,
    CirclePendingApprovalParams,
    CirclePendingApprovalResult,
    CircleWithMembersParams,
    CircleWithMembersResult,
)
from ..capabilities.common import AcceptanceActorSet, ActorHandle
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


_CIRCLE = CapabilityDefinition(
    capability=CIRCLE_WITH_MEMBERS,
    operations=(
        "circle.circle.CreateCircle",
        "circle.circle_membership.JoinCircle",
        "circle.circle.GetCircle",
        "circle.circle_membership.ListPersonaCircles",
        "circle.circle.ArchiveCircle",
    ),
)
_GATHERING = CapabilityDefinition(
    capability=CIRCLE_GATHERING,
    operations=(
        "circle.gathering.CreateGatheringDraft",
        "circle.gathering.GetGathering",
        "circle.gathering.PublishGathering",
        "circle.gathering.JoinOpenGathering",
        "circle.gathering.ListGatheringRoster",
        "circle.gathering.CancelGathering",
    ),
)
_PENDING_APPROVAL = CapabilityDefinition(
    capability=CIRCLE_PENDING_APPROVAL,
    operations=(
        "circle.circle.CreateCircle",
        "circle.circle_membership.JoinCircle",
        "circle.circle_membership.ListPendingCircleMemberships",
        "circle.circle.ArchiveCircle",
    ),
)
# Publish 的前置是 room binding 收敛（CIRCLE.DEPENDENCY.gathering_room_provision_pending）。
_ROOM_READY_ATTEMPTS = 20
_ROOM_READY_INTERVAL_SECONDS = 3.0


class CircleAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_CIRCLE, _GATHERING, _PENDING_APPROVAL)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        if request.capability == CIRCLE_WITH_MEMBERS:
            definition = _CIRCLE
        elif request.capability == CIRCLE_PENDING_APPROVAL:
            definition = _PENDING_APPROVAL
        else:
            definition = _GATHERING
        return plan_for(definition, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if isinstance(plan.resolved_params, CircleGatheringParams):
            return self._provision_gathering(context, plan.resolved_params)
        if isinstance(plan.resolved_params, CirclePendingApprovalParams):
            return self._provision_pending_approval(context, plan.resolved_params)
        if not isinstance(plan.resolved_params, CircleWithMembersParams):
            raise TypeError("Circle Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        owner = params.actors.require(params.owner_role)
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value)
        created = executor.call(
            "circle.circle.CreateCircle",
            actor=owner,
            step_id="create-circle",
            body={
                "name": "验收圈子",
                "description": "按用例隔离的验收圈子",
                "category": "travel",
                "tags": ["acceptance"],
                "visibility": "public",
                "joinPolicy": "open",
                "autoSyncChat": True,
            },
        )
        circle = BusinessObjectRef("Circle", required_id(created, "circleId", "id"))
        memberships: list[BusinessObjectRef] = []
        try:
            for index, role in enumerate(params.member_roles):
                member = params.actors.require(role)
                joined = executor.call(
                    "circle.circle_membership.JoinCircle",
                    actor=member,
                    step_id=f"join-circle-{index:02d}",
                    bindings={"circleId": circle.object_id},
                )
                membership_id = str(
                    joined.get("membershipId")
                    or joined.get("id")
                    or member.persona.object_id
                ).strip()
                memberships.append(
                    BusinessObjectRef("CircleMembership", membership_id)
                )
        except BaseException as error:
            raise PartialProvisioningError(
                "Circle Provider stopped after creating a circle",
                provisioned=ProvisionedCapability(
                    value=CircleWithMembersResult(
                        circle=circle,
                        memberships=tuple(memberships),
                    ),
                    cleanup_handle=(circle,),
                    cleanup_context=owner,
                    operation_count=executor.operation_count,
                ),
            ) from error
        return ProvisionedCapability(
            value=CircleWithMembersResult(
                circle=circle,
                memberships=tuple(memberships),
            ),
            cleanup_handle=(circle,),
            cleanup_context=owner,
            operation_count=executor.operation_count,
        )

    def _provision_gathering(
        self,
        context: TestDataContext,
        params: CircleGatheringParams,
    ) -> ProvisionedCapability:
        circle = params.circle
        if not isinstance(circle, CircleWithMembersResult):
            raise TypeError("circle dependency was not resolved")
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        organizer = params.actors.require(params.organizer_role)
        participant = params.actors.require(params.participant_role)
        executor = _executor(context, CIRCLE_GATHERING.key.value)
        start_at = (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
        ).replace(minute=0, second=0, microsecond=0)
        created = executor.call(
            "circle.gathering.CreateGatheringDraft",
            actor=organizer,
            step_id="create-gathering-draft",
            body={
                "hostBinding": {
                    "hostSubjectKind": "persona",
                    "hostSubjectId": organizer.persona.object_id,
                    "authorityEvidenceRef": (
                        f"persona:{organizer.persona.object_id}:self"
                    ),
                    "authorityVersion": 1,
                },
                "creatorParticipates": True,
                "purpose": {
                    "title": "圈子同好验收小聚",
                    "summary": "按用例隔离的验收 Gathering。",
                    "topicRefs": [],
                    "requirementRefs": [],
                    "sourceObjectRefs": [
                        {
                            "objectRef": {
                                "objectTypeRef": "circle",
                                "objectId": circle.circle.object_id,
                            },
                            "routeId": "circleDetail",
                            "sourceDigest": "acceptance:circle-gathering",
                        }
                    ],
                    "costNotice": "free",
                },
                "schedule": {
                    "timezone": "Asia/Shanghai",
                    "startAt": _instant(start_at),
                    "endAt": _instant(start_at + dt.timedelta(hours=2)),
                },
                "place": {
                    "mode": "physical",
                    "coarsePlaceLabel": "验收集合地",
                    "exactMeetingPoint": "正门集合",
                },
                "policySet": {
                    "audiencePolicy": "public",
                    "admissionPolicy": "open",
                    "capacityPolicy": {"maxParticipants": 4},
                    "disclosurePolicy": {
                        "timeDisclosure": "exact",
                        "placeDisclosure": "exact",
                        "rosterDisclosure": "joined_members",
                    },
                    "applicationQuestions": [],
                    "riskControlPolicyRef": "risk/standard-day-public-v1",
                },
            },
        )
        gathering = BusinessObjectRef(
            "Gathering",
            required_id(created, "gatheringId", "id"),
        )
        result = CircleGatheringResult(
            gathering=gathering,
            source_circle=circle.circle,
            organizer_role=params.organizer_role,
            participant_role=params.participant_role,
        )
        version = int(created.get("aggregateVersion") or 1)
        try:
            version = self._await_room_ready(executor, organizer, gathering, version)
            published = executor.call(
                "circle.gathering.PublishGathering",
                actor=organizer,
                step_id="publish-gathering",
                bindings={"gatheringId": gathering.object_id},
                body={
                    "gatheringId": gathering.object_id,
                    "expectedGatheringVersion": version,
                },
            )
            version = int(published.get("aggregateVersion") or version)
            executor.call(
                "circle.gathering.JoinOpenGathering",
                actor=participant,
                step_id="join-open-gathering",
                bindings={"gatheringId": gathering.object_id},
                body={
                    "gatheringId": gathering.object_id,
                    "expectedGatheringVersion": version,
                    "expectedParticipationVersion": 0,
                },
            )
        except BaseException as error:
            raise PartialProvisioningError(
                "Circle Provider stopped after creating a gathering draft",
                provisioned=ProvisionedCapability(
                    value=result,
                    cleanup_handle=(gathering,),
                    cleanup_context=organizer,
                    operation_count=executor.operation_count,
                ),
            ) from error
        return ProvisionedCapability(
            value=result,
            cleanup_handle=(gathering,),
            cleanup_context=organizer,
            operation_count=executor.operation_count,
        )

    def _provision_pending_approval(
        self,
        context: TestDataContext,
        params: CirclePendingApprovalParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        owner = params.actors.require(params.owner_role)
        applicant = params.actors.require(params.applicant_role)
        executor = _executor(context, CIRCLE_PENDING_APPROVAL.key.value)
        created = executor.call(
            "circle.circle.CreateCircle",
            actor=owner,
            step_id="create-approval-circle",
            body={
                "name": "验收审批圈子",
                "description": "按用例隔离的待审入圈验收圈子",
                "category": "travel",
                "tags": ["acceptance"],
                "visibility": "public",
                "joinPolicy": "approval",
                "autoSyncChat": True,
            },
        )
        circle = BusinessObjectRef("Circle", required_id(created, "circleId", "id"))

        def result_for(membership_id: str) -> CirclePendingApprovalResult:
            return CirclePendingApprovalResult(
                circle=circle,
                pending_membership=BusinessObjectRef(
                    "CircleMembership",
                    membership_id,
                ),
                applicant_persona=applicant.persona,
                owner_role=params.owner_role,
                applicant_role=params.applicant_role,
            )

        try:
            joined = executor.call(
                "circle.circle_membership.JoinCircle",
                actor=applicant,
                step_id="join-approval-circle",
                bindings={"circleId": circle.object_id},
            )
        except BaseException as error:
            raise PartialProvisioningError(
                "Circle Provider stopped after creating an approval circle",
                provisioned=ProvisionedCapability(
                    value=result_for(applicant.persona.object_id),
                    cleanup_handle=(circle,),
                    cleanup_context=owner,
                    operation_count=executor.operation_count,
                ),
            ) from error
        membership_id = str(
            joined.get("membershipId")
            or joined.get("id")
            or applicant.persona.object_id
        ).strip()
        if str(joined.get("state") or "").strip() != "pending":
            raise PartialProvisioningError(
                "Circle join intent did not enter the pending approval queue",
                provisioned=ProvisionedCapability(
                    value=result_for(membership_id),
                    cleanup_handle=(circle,),
                    cleanup_context=owner,
                    operation_count=executor.operation_count,
                ),
            )
        return ProvisionedCapability(
            value=result_for(membership_id),
            cleanup_handle=(circle,),
            cleanup_context=owner,
            operation_count=executor.operation_count,
        )

    def _await_room_ready(
        self,
        executor: PublicOperationExecutor,
        organizer: ActorHandle,
        gathering: BusinessObjectRef,
        version: int,
    ) -> int:
        for attempt in range(_ROOM_READY_ATTEMPTS):
            current = executor.call(
                "circle.gathering.GetGathering",
                actor=organizer,
                step_id=f"await-room-ready-{attempt:02d}",
                bindings={"gatheringId": gathering.object_id},
            )
            version = int(current.get("aggregateVersion") or version)
            if str(current.get("roomBindingStatus") or "") == "ready":
                return version
            time.sleep(_ROOM_READY_INTERVAL_SECONDS)
        raise RuntimeError(
            "gathering room binding did not become ready before publish"
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if isinstance(provisioned.value, CirclePendingApprovalResult):
            executor = _executor(
                context,
                CIRCLE_PENDING_APPROVAL.key.value + ".readback",
            )
            listed = executor.call(
                "circle.circle_membership.ListPendingCircleMemberships",
                actor=provisioned.cleanup_context,
                step_id="list-pending-memberships",
                bindings={"circleId": provisioned.value.circle.object_id},
                query={"limit": 50},
            )
            rows = items(listed)
            applicant_pending = any(
                str(row.get("personaId") or "").strip()
                == provisioned.value.applicant_persona.object_id
                and str(row.get("state") or "").strip() == "pending"
                for row in rows
            )
            return ReadbackResult(
                passed=applicant_pending,
                operation_count=executor.operation_count,
                details={"pendingCount": len(rows)},
            )
        if isinstance(provisioned.value, CircleGatheringResult):
            executor = _executor(context, CIRCLE_GATHERING.key.value + ".readback")
            response = executor.call(
                "circle.gathering.GetGathering",
                actor=provisioned.cleanup_context,
                step_id="get-gathering",
                bindings={"gatheringId": provisioned.value.gathering.object_id},
            )
            observed = str(
                response.get("gatheringId") or response.get("id") or ""
            ).strip()
            lifecycle = str(response.get("lifecycleStatus") or "").strip()
            return ReadbackResult(
                passed=(
                    observed == provisioned.value.gathering.object_id
                    and lifecycle == "published"
                ),
                operation_count=executor.operation_count,
                details={"lifecycleStatus": lifecycle},
            )
        if not isinstance(provisioned.value, CircleWithMembersResult):
            return ReadbackResult(passed=False)
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value + ".readback")
        response = executor.call(
            "circle.circle.GetCircle",
            actor=provisioned.cleanup_context,
            step_id="get-circle",
            bindings={"circleId": provisioned.value.circle.object_id},
        )
        observed = str(response.get("circleId") or response.get("id") or "").strip()
        return ReadbackResult(
            passed=observed == provisioned.value.circle.object_id,
            operation_count=executor.operation_count,
            details={"membershipCount": len(provisioned.value.memberships)},
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if isinstance(provisioned.value, CirclePendingApprovalResult):
            executor = _executor(
                context,
                CIRCLE_PENDING_APPROVAL.key.value + ".cleanup",
            )
            executor.call(
                "circle.circle.ArchiveCircle",
                actor=provisioned.cleanup_context,
                step_id="archive-approval-circle",
                bindings={"circleId": provisioned.value.circle.object_id},
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if isinstance(provisioned.value, CircleGatheringResult):
            executor = _executor(context, CIRCLE_GATHERING.key.value + ".cleanup")
            current = executor.call(
                "circle.gathering.GetGathering",
                actor=provisioned.cleanup_context,
                step_id="get-gathering-before-cancel",
                bindings={"gatheringId": provisioned.value.gathering.object_id},
            )
            executor.call(
                "circle.gathering.CancelGathering",
                actor=provisioned.cleanup_context,
                step_id="cancel-gathering",
                bindings={"gatheringId": provisioned.value.gathering.object_id},
                body={
                    "gatheringId": provisioned.value.gathering.object_id,
                    "reasonRef": "acceptance:test-data-cleanup",
                    "evidenceRefs": [],
                    "expectedGatheringVersion": int(
                        current.get("aggregateVersion") or 1
                    ),
                },
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if not isinstance(provisioned.value, CircleWithMembersResult):
            return CleanupResult(state="quarantined")
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value + ".cleanup")
        executor.call(
            "circle.circle.ArchiveCircle",
            actor=provisioned.cleanup_context,
            step_id="archive-circle",
            bindings={"circleId": provisioned.value.circle.object_id},
        )
        return CleanupResult(state="released", operation_count=executor.operation_count)


def _instant(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


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


def build_provider() -> CircleAcceptanceDataProvider:
    return CircleAcceptanceDataProvider()
