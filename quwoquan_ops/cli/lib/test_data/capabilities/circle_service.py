from __future__ import annotations

from dataclasses import dataclass

from ..api import BusinessObjectRef, CapabilityKey, CapabilityRef, OutputRef
from .common import AcceptanceActorSet, ActorRole


@dataclass(frozen=True)
class CircleWithMembersParams:
    actors: OutputRef[AcceptanceActorSet]
    owner_role: ActorRole
    member_roles: tuple[ActorRole, ...]

    def __post_init__(self) -> None:
        if not self.member_roles or self.owner_role in self.member_roles:
            raise ValueError("circle requires distinct owner and members")


@dataclass(frozen=True)
class CircleWithMembersResult:
    circle: BusinessObjectRef
    memberships: tuple[BusinessObjectRef, ...]


@dataclass(frozen=True)
class CircleGatheringParams:
    circle: OutputRef[CircleWithMembersResult]
    actors: OutputRef[AcceptanceActorSet]
    organizer_role: ActorRole
    participant_role: ActorRole

    def __post_init__(self) -> None:
        if self.organizer_role is self.participant_role:
            raise ValueError("gathering requires distinct organizer and participant")


@dataclass(frozen=True)
class CircleGatheringResult:
    gathering: BusinessObjectRef
    source_circle: BusinessObjectRef
    organizer_role: ActorRole
    participant_role: ActorRole


@dataclass(frozen=True)
class CircleGatheringPlanParams:
    gathering: OutputRef[CircleGatheringResult]
    actors: OutputRef[AcceptanceActorSet]
    organizer_role: ActorRole
    participant_role: ActorRole

    def __post_init__(self) -> None:
        if self.organizer_role is self.participant_role:
            raise ValueError(
                "gathering plan requires distinct organizer and participant"
            )


@dataclass(frozen=True)
class CircleGatheringPlanResult:
    plan: BusinessObjectRef
    gathering: BusinessObjectRef
    current_revision: BusinessObjectRef
    current_revision_number: int
    current_revision_digest: str
    plan_version: int
    organizer_role: ActorRole
    participant_role: ActorRole

    def __post_init__(self) -> None:
        if self.current_revision_number < 1 or self.plan_version < 1:
            raise ValueError("gathering plan requires positive version identities")
        if not self.current_revision_digest.strip():
            raise ValueError("gathering plan requires a current revision digest")


@dataclass(frozen=True)
class CirclePendingApprovalParams:
    actors: OutputRef[AcceptanceActorSet]
    owner_role: ActorRole
    applicant_role: ActorRole

    def __post_init__(self) -> None:
        if self.owner_role is self.applicant_role:
            raise ValueError("pending approval requires distinct owner and applicant")


@dataclass(frozen=True)
class CirclePendingApprovalResult:
    circle: BusinessObjectRef
    pending_membership: BusinessObjectRef
    applicant_persona: BusinessObjectRef
    owner_role: ActorRole
    applicant_role: ActorRole


CIRCLE_WITH_MEMBERS = CapabilityRef(
    key=CapabilityKey("circle.membership.circle_with_members"),
    params_type=CircleWithMembersParams,
    result_type=CircleWithMembersResult,
    owner_service="circle_service",
)

CIRCLE_GATHERING = CapabilityRef(
    key=CapabilityKey("circle.gathering.circle_gathering"),
    params_type=CircleGatheringParams,
    result_type=CircleGatheringResult,
    owner_service="circle_service",
)

CIRCLE_GATHERING_PLAN = CapabilityRef(
    key=CapabilityKey("circle.gathering_plan.canonical_plan"),
    params_type=CircleGatheringPlanParams,
    result_type=CircleGatheringPlanResult,
    owner_service="circle_service",
)

CIRCLE_PENDING_APPROVAL = CapabilityRef(
    key=CapabilityKey("circle.circle_membership.pending_approval"),
    params_type=CirclePendingApprovalParams,
    result_type=CirclePendingApprovalResult,
    owner_service="circle_service",
)

__all__ = (
    "CIRCLE_GATHERING",
    "CIRCLE_GATHERING_PLAN",
    "CIRCLE_PENDING_APPROVAL",
    "CIRCLE_WITH_MEMBERS",
    "CircleGatheringParams",
    "CircleGatheringPlanParams",
    "CircleGatheringPlanResult",
    "CircleGatheringResult",
    "CirclePendingApprovalParams",
    "CirclePendingApprovalResult",
    "CircleWithMembersParams",
    "CircleWithMembersResult",
)
