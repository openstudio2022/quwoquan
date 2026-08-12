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

__all__ = (
    "ACTIVE_REFERENCE_RELEASE",
    "POST_COMMENTS",
    "ActiveReleaseParams",
    "PostCommentsParams",
    "PostCommentsResult",
)
