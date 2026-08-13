from __future__ import annotations

from dataclasses import dataclass

from ..api import (
    BusinessObjectRef,
    CapabilityKey,
    CapabilityRef,
    OutputRef,
    ProviderCapabilityKey,
)
from .common import AcceptanceActorSet, ActorRole, ImmutableReleaseHandle


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


@dataclass(frozen=True)
class FollowingSubjectsParams:
    release: OutputRef[ImmutableReleaseHandle]
    actors: OutputRef[AcceptanceActorSet]
    follower_role: ActorRole


@dataclass(frozen=True)
class FollowingSubjectsResult:
    subject: BusinessObjectRef
    subject_type: str
    follower_role: ActorRole


@dataclass(frozen=True)
class GreetingInboxParams:
    actors: OutputRef[AcceptanceActorSet]
    sender_role: ActorRole
    receiver_role: ActorRole
    request_message: str

    def __post_init__(self) -> None:
        if self.sender_role is self.receiver_role:
            raise ValueError("greeting sender and receiver roles must differ")
        if not self.request_message.strip():
            raise ValueError("greeting requires a non-empty request message")


@dataclass(frozen=True)
class GreetingInboxResult:
    greeting: BusinessObjectRef
    sender_persona: BusinessObjectRef
    sender_role: ActorRole
    receiver_role: ActorRole


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

USER_FOLLOWING_SUBJECTS = CapabilityRef(
    key=CapabilityKey("user.profile_projection.following_subjects"),
    params_type=FollowingSubjectsParams,
    result_type=FollowingSubjectsResult,
    owner_service="user_service",
)

GREETING_INBOX = CapabilityRef(
    key=CapabilityKey("user.greeting_request.greeting_inbox"),
    params_type=GreetingInboxParams,
    result_type=GreetingInboxResult,
    owner_service="user_service",
)

__all__ = (
    "AUTHENTICATED_ACTORS",
    "GREETING_INBOX",
    "PERSONA_RELATIONSHIP",
    "USER_FOLLOWING_SUBJECTS",
    "AuthenticatedActorsParams",
    "FollowingSubjectsParams",
    "FollowingSubjectsResult",
    "GreetingInboxParams",
    "GreetingInboxResult",
    "RelationshipParams",
    "RelationshipResult",
)
