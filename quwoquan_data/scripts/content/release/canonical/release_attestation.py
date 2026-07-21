"""Typed immutable receipt for an aggregate data release."""
from __future__ import annotations

from dataclasses import dataclass
from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import RolloutMilestone
from core.source_digest import SourceDigest, SourceDigestError
from content.release.model import ReleaseKind


_SCHEMA = "quwoquan_data.aggregate_release_attestation"
_CONTENT_MILESTONES = {
    RolloutMilestone.CANARY,
    RolloutMilestone.M1,
    RolloutMilestone.M2,
    RolloutMilestone.M3,
    RolloutMilestone.H10K,
    RolloutMilestone.LAUNCH,
}


class ReleaseAttestationError(ValueError):
    """An aggregate release receipt does not satisfy its closed contract."""


@dataclass(frozen=True, slots=True)
class ReleaseAttestation:
    """The sole typed representation of the aggregate release evidence."""

    release_id: str
    release_kind: ReleaseKind
    execution_ids: tuple[str, ...]
    rollout_milestone: RolloutMilestone
    entity_count: int
    post_count: int
    creator_count: int
    tag_count: int
    canonical_merkle: str
    source_digests: tuple[SourceDigest, ...]
    payload_sha256: str
    recorded_at: str

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ReleaseAttestationError("releaseId is required")
        if not self.canonical_merkle.startswith("sha256:"):
            raise ReleaseAttestationError("canonicalMerkle must be a sha256 digest")
        if not self.payload_sha256.startswith("sha256:"):
            raise ReleaseAttestationError("payloadSha256 must be a sha256 digest")
        if not self.recorded_at.strip():
            raise ReleaseAttestationError("recordedAt is required")
        if any(count < 0 for count in self.counts):
            raise ReleaseAttestationError("release counts must be non-negative")
        if not self.source_digests:
            raise ReleaseAttestationError("sourceDigests must not be empty")
        digest_values = tuple(item.digest for item in self.source_digests)
        if digest_values != tuple(sorted(set(digest_values))):
            raise ReleaseAttestationError(
                "sourceDigests must be sorted and contain no duplicates"
            )
        if self.release_kind is ReleaseKind.CONTENT:
            if not self.execution_ids or not (self.entity_count or self.post_count):
                raise ReleaseAttestationError(
                    "content release requires executions and canonical entities or posts"
                )
            if self.rollout_milestone not in _CONTENT_MILESTONES:
                raise ReleaseAttestationError("content release milestone is invalid")
        elif self.release_kind is ReleaseKind.EMPTY_BASELINE:
            if self.execution_ids or any(self.counts):
                raise ReleaseAttestationError(
                    "empty baseline must not contain executions or canonical objects"
                )
            if self.rollout_milestone is not RolloutMilestone.BASELINE:
                raise ReleaseAttestationError("empty baseline milestone must be baseline")
        else:
            raise ReleaseAttestationError("releaseKind is invalid")

    @property
    def counts(self) -> tuple[int, int, int, int]:
        return (self.entity_count, self.post_count, self.creator_count, self.tag_count)

    def to_document(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "releaseId": self.release_id,
            "releaseKind": self.release_kind.value,
            "executionIds": list(self.execution_ids),
            "rolloutMilestone": self.rollout_milestone.value,
            "entityCount": self.entity_count,
            "postCount": self.post_count,
            "creatorCount": self.creator_count,
            "tagCount": self.tag_count,
            "canonicalMerkle": self.canonical_merkle,
            "sourceDigests": [
                source_digest.to_document() for source_digest in self.source_digests
            ],
            "payloadSha256": self.payload_sha256,
            "recordedAt": self.recorded_at,
        }

    @classmethod
    def from_document(cls, value: object) -> "ReleaseAttestation":
        try:
            document = JsonObject.from_value(
                value, label="aggregate release attestation"
            )
            release_kind = ReleaseKind(document.string("releaseKind"))
            milestone = RolloutMilestone(document.string("rolloutMilestone"))
            raw_source_digests = document.value("sourceDigests")
            if not isinstance(raw_source_digests, list):
                raise ReleaseAttestationError("sourceDigests must be an array")
            source_digests = tuple(
                SourceDigest.from_document(item) for item in raw_source_digests
            )
            execution_ids = document.string_sequence("executionIds")
            entity_count = document.integer("entityCount")
            post_count = document.integer("postCount")
            creator_count = document.integer("creatorCount")
            tag_count = document.integer("tagCount")
        except (JsonObjectDecodeError, SourceDigestError, ValueError) as exc:
            raise ReleaseAttestationError(str(exc)) from exc
        return cls(
            release_id=document.string("releaseId"),
            release_kind=release_kind,
            execution_ids=execution_ids,
            rollout_milestone=milestone,
            entity_count=entity_count,
            post_count=post_count,
            creator_count=creator_count,
            tag_count=tag_count,
            canonical_merkle=document.string("canonicalMerkle"),
            source_digests=source_digests,
            payload_sha256=document.string("payloadSha256"),
            recorded_at=document.string("recordedAt"),
        )


__all__ = ["ReleaseAttestation", "ReleaseAttestationError"]
