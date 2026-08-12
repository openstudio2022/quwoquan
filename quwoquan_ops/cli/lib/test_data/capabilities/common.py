from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..api import BusinessObjectRef


class ActorRole(StrEnum):
    PRIMARY = "primary"
    SENDER = "sender"
    RECEIVER = "receiver"
    MEMBER = "member"
    MODERATOR = "moderator"


@dataclass(frozen=True)
class ActorHandle:
    role: ActorRole
    account: BusinessObjectRef
    persona: BusinessObjectRef
    session_handle: str


@dataclass(frozen=True)
class AcceptanceActorSet:
    actors: tuple[ActorHandle, ...]

    def require(self, role: ActorRole) -> ActorHandle:
        matches = tuple(actor for actor in self.actors if actor.role is role)
        if len(matches) != 1:
            raise ValueError(f"actor role {role.value} must resolve exactly once")
        return matches[0]


@dataclass(frozen=True)
class ImmutableReleaseHandle:
    release_id: str
    release_digest: str
    import_run_id: str
    posts: tuple[BusinessObjectRef, ...]
