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

    def __post_init__(self) -> None:
        if self.account.object_type != "UserAccount":
            raise ValueError("actor handle account must reference UserAccount")
        if self.persona.object_type != "Persona":
            raise ValueError("actor handle persona must reference Persona")
        if not self.session_handle.strip():
            raise ValueError("actor handle requires a runtime session handle")


@dataclass(frozen=True)
class AcceptanceActorSet:
    actors: tuple[ActorHandle, ...]

    def __post_init__(self) -> None:
        if not self.actors or any(not isinstance(actor, ActorHandle) for actor in self.actors):
            raise ValueError("ActorSet must contain typed actor handles")
        roles = tuple(actor.role for actor in self.actors)
        if len(roles) != len(set(roles)):
            raise ValueError("ActorSet must contain each actor role at most once")

    def require(self, role: ActorRole) -> ActorHandle:
        matches = tuple(actor for actor in self.actors if actor.role is role)
        if len(matches) != 1:
            raise ValueError(f"actor role {role.value} must resolve exactly once")
        return matches[0]

    @property
    def identity_digest(self) -> str:
        from ..model import canonical_digest

        return canonical_digest(
            {
                "actors": [
                    {
                        "role": actor.role.value,
                        "accountId": actor.account.object_id,
                        "personaId": actor.persona.object_id,
                    }
                    for actor in sorted(self.actors, key=lambda item: item.role.value)
                ]
            }
        )


@dataclass(frozen=True)
class ImmutableReleaseHandle:
    release_id: str
    release_digest: str
    import_run_id: str
    readiness_phase: str
    readiness_receipt_digest: str
    posts: tuple[BusinessObjectRef, ...]
    creators: tuple[BusinessObjectRef, ...]
    entities: tuple[BusinessObjectRef, ...]
    homepages: tuple[BusinessObjectRef, ...]
    tags: tuple[BusinessObjectRef, ...]
    media_assets: tuple[BusinessObjectRef, ...]

    def __post_init__(self) -> None:
        if not self.release_id or not self.import_run_id:
            raise ValueError("immutable release handle requires release and import identities")
        if not self.release_digest.startswith("sha256:") or len(self.release_digest) != 71:
            raise ValueError("immutable release handle requires a canonical release digest")
        if self.readiness_phase not in {"research", "commercial"}:
            raise ValueError("immutable release handle has an invalid readiness phase")
        if (
            not self.readiness_receipt_digest.startswith("sha256:")
            or len(self.readiness_receipt_digest) != 71
        ):
            raise ValueError("immutable release handle requires a readiness receipt digest")
        for name, object_type in (
            ("posts", "Post"),
            ("creators", "Creator"),
            ("entities", "Entity"),
            ("homepages", "EntityHomepage"),
            ("tags", "Tag"),
            ("media_assets", "MediaAsset"),
        ):
            values = getattr(self, name)
            if (
                not values
                or any(
                    not isinstance(value, BusinessObjectRef)
                    or value.object_type != object_type
                    for value in values
                )
                or len({value.object_id for value in values}) != len(values)
            ):
                raise ValueError(
                    f"immutable release handle {name} must contain {object_type} references"
                )
