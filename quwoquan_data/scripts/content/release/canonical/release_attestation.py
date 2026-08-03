"""Typed immutable receipt for a generic aggregate data release."""
from __future__ import annotations

from dataclasses import dataclass

from core.codec import JsonObject, JsonObjectDecodeError
from core.source_digest import SourceDigest, SourceDigestError
from content.release.model import DataSourceOwner, ReleaseKind
from governance.coverage.distribution import ProductLifecycleState, ReleaseClass


_SCHEMA = "quwoquan_data.release_attestation"


class ReleaseAttestationError(ValueError):
    """A release receipt does not satisfy its closed contract."""


@dataclass(frozen=True, slots=True)
class ReleaseAttestation:
    """The sole typed representation of immutable release evidence.

    Release scope and object counts are derived from the execution closures and
    desired state. They are not a second rollout model.
    """

    release_id: str
    source_owner: DataSourceOwner
    release_kind: ReleaseKind
    release_class: ReleaseClass
    product_lifecycle_state: ProductLifecycleState
    contains_unverified_assets: bool
    rights_status_counts: dict[str, int]
    authorization_required_asset_ids: tuple[str, ...]
    research_accepted_count: int
    commercial_accepted_count: int
    execution_ids: tuple[str, ...]
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
        if self.source_owner is not DataSourceOwner.QWQ_DATA:
            raise ReleaseAttestationError("sourceOwner must be qwq_data")
        if self.release_class.value != self.product_lifecycle_state.value:
            raise ReleaseAttestationError(
                "releaseClass must equal productLifecycleState"
            )
        expected_statuses = {"verified", "unverified", "restricted", "unknown"}
        if set(self.rights_status_counts) != expected_statuses or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.rights_status_counts.values()
        ):
            raise ReleaseAttestationError("rightsStatusCounts is invalid")
        if len(self.authorization_required_asset_ids) != len(
            set(self.authorization_required_asset_ids)
        ):
            raise ReleaseAttestationError(
                "authorizationRequiredAssetIds must be unique"
            )
        if self.contains_unverified_assets != bool(
            self.authorization_required_asset_ids
        ):
            raise ReleaseAttestationError(
                "containsUnverifiedAssets must match authorizationRequiredAssetIds"
            )
        if self.release_class is ReleaseClass.COMMERCIAL and (
            self.contains_unverified_assets
            or self.authorization_required_asset_ids
        ):
            raise ReleaseAttestationError(
                "commercial release cannot contain authorization-required assets"
            )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (
                self.research_accepted_count,
                self.commercial_accepted_count,
            )
        ):
            raise ReleaseAttestationError(
                "research/commercial accepted counts must be non-negative"
            )
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
        elif self.release_kind is ReleaseKind.EMPTY_BASELINE:
            if (
                self.execution_ids
                or any(self.counts)
                or self.research_accepted_count
                or self.commercial_accepted_count
                or self.authorization_required_asset_ids
            ):
                raise ReleaseAttestationError(
                    "empty baseline must not contain executions or canonical objects"
                )
        else:
            raise ReleaseAttestationError("releaseKind is invalid")

    @property
    def counts(self) -> tuple[int, int, int, int]:
        return (self.entity_count, self.post_count, self.creator_count, self.tag_count)

    def to_document(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "releaseId": self.release_id,
            "sourceOwner": self.source_owner.value,
            "releaseKind": self.release_kind.value,
            "releaseClass": self.release_class.value,
            "productLifecycleState": self.product_lifecycle_state.value,
            "containsUnverifiedAssets": self.contains_unverified_assets,
            "rightsStatusCounts": dict(self.rights_status_counts),
            "authorizationRequiredAssetIds": list(
                self.authorization_required_asset_ids
            ),
            "researchAcceptedCount": self.research_accepted_count,
            "commercialAcceptedCount": self.commercial_accepted_count,
            "executionIds": list(self.execution_ids),
            "entityCount": self.entity_count,
            "postCount": self.post_count,
            "creatorCount": self.creator_count,
            "tagCount": self.tag_count,
            "canonicalMerkle": self.canonical_merkle,
            "sourceDigests": [item.to_document() for item in self.source_digests],
            "payloadSha256": self.payload_sha256,
            "recordedAt": self.recorded_at,
        }

    @classmethod
    def from_document(cls, value: object) -> "ReleaseAttestation":
        try:
            document = JsonObject.from_value(value, label="release attestation")
            if document.string("schema") != _SCHEMA:
                raise ReleaseAttestationError("release attestation schema is invalid")
            source_documents = document.object_sequence("sourceDigests")
            source_digests = tuple(
                SourceDigest.from_document(item.to_document())
                for item in source_documents
            )
            return cls(
                release_id=document.string("releaseId"),
                source_owner=DataSourceOwner(document.string("sourceOwner")),
                release_kind=ReleaseKind(document.string("releaseKind")),
                release_class=ReleaseClass(document.string("releaseClass")),
                product_lifecycle_state=ProductLifecycleState(
                    document.string("productLifecycleState")
                ),
                contains_unverified_assets=document.boolean(
                    "containsUnverifiedAssets"
                ),
                rights_status_counts={
                    key: int(value)
                    for key, value in document.object("rightsStatusCounts")
                    .to_document()
                    .items()
                },
                authorization_required_asset_ids=document.string_sequence(
                    "authorizationRequiredAssetIds"
                ),
                research_accepted_count=document.integer("researchAcceptedCount"),
                commercial_accepted_count=document.integer(
                    "commercialAcceptedCount"
                ),
                execution_ids=document.string_sequence("executionIds"),
                entity_count=document.integer("entityCount"),
                post_count=document.integer("postCount"),
                creator_count=document.integer("creatorCount"),
                tag_count=document.integer("tagCount"),
                canonical_merkle=document.string("canonicalMerkle"),
                source_digests=source_digests,
                payload_sha256=document.string("payloadSha256"),
                recorded_at=document.string("recordedAt"),
            )
        except (JsonObjectDecodeError, SourceDigestError, ValueError) as exc:
            raise ReleaseAttestationError(str(exc)) from exc


__all__ = ["ReleaseAttestation", "ReleaseAttestationError"]
