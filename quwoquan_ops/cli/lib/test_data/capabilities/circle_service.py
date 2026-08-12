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


CIRCLE_WITH_MEMBERS = CapabilityRef(
    key=CapabilityKey("circle.membership.circle_with_members"),
    params_type=CircleWithMembersParams,
    result_type=CircleWithMembersResult,
    owner_service="circle_service",
)

__all__ = (
    "CIRCLE_WITH_MEMBERS",
    "CircleWithMembersParams",
    "CircleWithMembersResult",
)
