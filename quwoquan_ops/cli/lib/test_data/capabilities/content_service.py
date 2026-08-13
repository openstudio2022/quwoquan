from __future__ import annotations

from dataclasses import dataclass

from ..api import BusinessObjectRef, CapabilityKey, CapabilityRef, OutputRef
from .common import AcceptanceActorSet, ActorRole, ImmutableReleaseHandle


@dataclass(frozen=True)
class ActiveReleaseParams:
    minimum_posts: int = 1

    def __post_init__(self) -> None:
        if self.minimum_posts < 1:
            raise ValueError("minimum_posts must be positive")


@dataclass(frozen=True)
class PostCommentsParams:
    release: OutputRef[ImmutableReleaseHandle]
    actors: OutputRef[AcceptanceActorSet]
    author_role: ActorRole
    comment_count: int
    replies_per_comment: int = 0

    def __post_init__(self) -> None:
        if self.comment_count < 1 or self.replies_per_comment < 0:
            raise ValueError("comment counts are outside the supported boundary")


@dataclass(frozen=True)
class PostCommentsResult:
    post: BusinessObjectRef
    comments: tuple[BusinessObjectRef, ...]


@dataclass(frozen=True)
class PostReactionParams:
    release: OutputRef[ImmutableReleaseHandle]
    actors: OutputRef[AcceptanceActorSet]
    reactor_role: ActorRole


@dataclass(frozen=True)
class PostReactionResult:
    post: BusinessObjectRef
    reactor_role: ActorRole


@dataclass(frozen=True)
class PostFootprintParams:
    release: OutputRef[ImmutableReleaseHandle]
    actors: OutputRef[AcceptanceActorSet]
    viewer_role: ActorRole


@dataclass(frozen=True)
class PostFootprintResult:
    post: BusinessObjectRef
    viewer_role: ActorRole


ACTIVE_REFERENCE_RELEASE = CapabilityRef(
    key=CapabilityKey("content.release.active_reference"),
    params_type=ActiveReleaseParams,
    result_type=ImmutableReleaseHandle,
    owner_service="content_service",
    mutates_environment=False,
    candidate_cacheable=True,
)

POST_COMMENTS = CapabilityRef(
    key=CapabilityKey("content.comment.post_comments"),
    params_type=PostCommentsParams,
    result_type=PostCommentsResult,
    owner_service="content_service",
)

POST_REACTIONS = CapabilityRef(
    key=CapabilityKey("content.content_reaction.post_reactions"),
    params_type=PostReactionParams,
    result_type=PostReactionResult,
    owner_service="content_service",
)

POST_FOOTPRINT = CapabilityRef(
    key=CapabilityKey("content.content_behavior_fact.post_footprint"),
    params_type=PostFootprintParams,
    result_type=PostFootprintResult,
    owner_service="content_service",
)

__all__ = (
    "ACTIVE_REFERENCE_RELEASE",
    "POST_COMMENTS",
    "POST_FOOTPRINT",
    "POST_REACTIONS",
    "ActiveReleaseParams",
    "PostCommentsParams",
    "PostCommentsResult",
    "PostFootprintParams",
    "PostFootprintResult",
    "PostReactionParams",
    "PostReactionResult",
)
