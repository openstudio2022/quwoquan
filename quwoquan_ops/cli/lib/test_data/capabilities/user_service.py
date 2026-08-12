from __future__ import annotations

from dataclasses import dataclass

from ..api import CapabilityKey, CapabilityRef, OutputRef, ProviderCapabilityKey
from .common import AcceptanceActorSet, ActorRole


@dataclass(frozen=True)
class AuthenticatedActorsParams:
    roles: tuple[ActorRole, ...]

    def __post_init__(self) -> None:
        if not self.roles or len(set(self.roles)) != len(self.roles):
            raise ValueError("actor roles must be non-empty and unique")


@dataclass(frozen=True)
class RelationshipParams:
    actors: OutputRef[AcceptanceActorSet]
    source_role: ActorRole
    target_role: ActorRole
    mutual: bool = False


@dataclass(frozen=True)
class RelationshipResult:
    source_role: ActorRole
    target_role: ActorRole
    directions: int


AUTHENTICATED_ACTORS = CapabilityRef(
    key=CapabilityKey("user.acceptance.authenticated_actors"),
    params_type=AuthenticatedActorsParams,
    result_type=AcceptanceActorSet,
    owner_service="user_service",
    required_provider_capabilities=(
        ProviderCapabilityKey("identity.sms.otp"),
    ),
)

PERSONA_RELATIONSHIP = CapabilityRef(
    key=CapabilityKey("user.persona.relationship"),
    params_type=RelationshipParams,
    result_type=RelationshipResult,
    owner_service="user_service",
)

__all__ = (
    "AUTHENTICATED_ACTORS",
    "PERSONA_RELATIONSHIP",
    "AuthenticatedActorsParams",
    "RelationshipParams",
    "RelationshipResult",
)
