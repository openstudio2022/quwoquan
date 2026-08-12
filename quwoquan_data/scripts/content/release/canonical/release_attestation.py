"""Typed immutable receipt for a generic aggregate data release."""
from __future__ import annotations

from dataclasses import dataclass

from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.model import DataSourceOwner, ReleaseKind
from core.codec import JsonObject, JsonObjectDecodeError
from core.source_digest import (
    FrozenSourceDigest,
    SourceDigest,
    SourceDigestError,
    content_source_revision,
)
from governance.coverage.distribution import ProductLifecycleState, ReleaseClass

_SCHEMA = "quwoquan_data.release_attestation"


class ReleaseAttestationError(ValueError):
    """A release receipt does not satisfy its closed contract."""


def _expand_source_identities(
    rows: tuple[dict[str, object], ...],
) -> list[dict[str, str]]:
    expanded: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseAttestationError("source identity entry is invalid")
        execution_ids = row.get("executionIds")
        if not isinstance(execution_ids, list) or not execution_ids:
            raise ReleaseAttestationError(
                "source identity executionIds are invalid"
            )
        for execution_id in execution_ids:
            normalized_id = str(execution_id or "").strip()
            if row.get("identityKind") == "legacy_canonical_migration":
                expanded.append(
                    {
                        "identityKind": "legacy_canonical_migration",
                        "executionId": normalized_id,
                        "sourceDigest": str(row.get("sourceDigest") or ""),
                        "canonicalObjectDigest": str(
                            row.get("canonicalObjectDigest") or ""
                        ),
                        "migrationEvidenceDigest": str(
                            row.get("migrationEvidenceDigest") or ""
                        ),
                    }
                )
            else:
                expanded.append(
                    {
                        "executionId": normalized_id,
                        "sourceRevision": str(row.get("sourceRevision") or ""),
                        "sourceDigest": str(row.get("sourceDigest") or ""),
                        "entityCatalogDigest": str(
                            row.get("entityCatalogDigest") or ""
                        ),
                    }
                )
    return expanded


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
    source_revision: str | None
    source_digest: str | None
    entity_catalog_digest: str | None
    source_digests: tuple[SourceDigest | FrozenSourceDigest, ...]
    payload_sha256: str
    recorded_at: str
    source_identities: tuple[dict[str, object], ...] = ()
    source_identity_set_digest: str | None = None

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
        if len(self.execution_ids) != len(set(self.execution_ids)):
            raise ReleaseAttestationError("executionIds must be unique")
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
            if self.source_identities:
                if self.release_class is not ReleaseClass.RESEARCH:
                    raise ReleaseAttestationError(
                        "source identity set is reserved for Research pool releases"
                    )
                if any(
                    value is not None
                    for value in (
                        self.source_revision,
                        self.source_digest,
                        self.entity_catalog_digest,
                    )
                ):
                    raise ReleaseAttestationError(
                        "source identity set forbids scalar source identity"
                    )
                expanded = _expand_source_identities(self.source_identities)
                try:
                    expected_rows, expected_digest = source_identity_set(expanded)
                except (ObjectTransactionError, TypeError, ValueError) as exc:
                    raise ReleaseAttestationError(
                        "source identity set is invalid"
                    ) from exc
                if (
                    list(self.source_identities) != expected_rows
                    or self.source_identity_set_digest != expected_digest
                    or sorted(self.execution_ids)
                    != sorted({row["executionId"] for row in expanded})
                    or {item.digest for item in self.source_digests}
                    != {str(row["sourceDigest"]) for row in self.source_identities}
                ):
                    raise ReleaseAttestationError(
                        "source identity set closure drifted"
                    )
                return
            if self.source_identity_set_digest is not None:
                raise ReleaseAttestationError(
                    "scalar source identity forbids sourceIdentitySetDigest"
                )
            if len(self.source_digests) != 1:
                raise ReleaseAttestationError(
                    "content release requires exactly one sourceDigest"
                )
            if not all(
                isinstance(value, str) and value.startswith("sha256:")
                for value in (
                    self.source_revision,
                    self.source_digest,
                    self.entity_catalog_digest,
                )
            ):
                raise ReleaseAttestationError(
                    "content release source identity is required"
                )
            if self.source_digest != self.source_digests[0].digest:
                raise ReleaseAttestationError(
                    "sourceDigest must match the frozen sourceDigests closure"
                )
            try:
                expected_revision = content_source_revision(
                    source_digest=self.source_digest,
                    entity_catalog_digest=self.entity_catalog_digest,
                )
            except SourceDigestError as exc:
                raise ReleaseAttestationError(str(exc)) from exc
            if self.source_revision != expected_revision:
                raise ReleaseAttestationError(
                    "sourceRevision does not match sourceDigest/entityCatalogDigest"
                )
        elif self.release_kind is ReleaseKind.EMPTY_BASELINE:
            if (
                self.execution_ids
                or any(self.counts)
                or self.research_accepted_count
                or self.commercial_accepted_count
                or self.authorization_required_asset_ids
                or any(
                    value is not None
                    for value in (
                        self.source_revision,
                        self.source_digest,
                        self.entity_catalog_digest,
                    )
                )
                or self.source_identities
                or self.source_identity_set_digest is not None
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
        document: dict[str, object] = {
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
        if self.release_kind is ReleaseKind.CONTENT:
            if self.source_identities:
                document.update(
                    {
                        "sourceIdentities": list(self.source_identities),
                        "sourceIdentitySetDigest": self.source_identity_set_digest,
                    }
                )
            else:
                document.update(
                    {
                        "sourceRevision": self.source_revision,
                        "sourceDigest": self.source_digest,
                        "entityCatalogDigest": self.entity_catalog_digest,
                    }
                )
        return document

    @classmethod
    def from_document(cls, value: object) -> ReleaseAttestation:
        try:
            document = JsonObject.from_value(value, label="release attestation")
            if document.string("schema") != _SCHEMA:
                raise ReleaseAttestationError("release attestation schema is invalid")
            plain = document.to_document()
            raw_source_identities = plain.get("sourceIdentities") or []
            if not isinstance(raw_source_identities, list) or any(
                not isinstance(item, dict) for item in raw_source_identities
            ):
                raise ReleaseAttestationError("sourceIdentities must be an array")
            source_digest_parser = (
                FrozenSourceDigest.from_document
                if raw_source_identities
                else SourceDigest.from_document
            )
            source_digests = [
                source_digest_parser(item.to_document())
                for item in document.object_sequence("sourceDigests")
            ]
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
                source_revision=document.optional_string("sourceRevision"),
                source_digest=document.optional_string("sourceDigest"),
                entity_catalog_digest=document.optional_string(
                    "entityCatalogDigest"
                ),
                source_digests=tuple(source_digests),
                payload_sha256=document.string("payloadSha256"),
                recorded_at=document.string("recordedAt"),
                source_identities=tuple(dict(item) for item in raw_source_identities),
                source_identity_set_digest=document.optional_string(
                    "sourceIdentitySetDigest"
                ),
            )
        except (JsonObjectDecodeError, SourceDigestError, ValueError) as exc:
            raise ReleaseAttestationError(str(exc)) from exc


__all__ = ["ReleaseAttestation", "ReleaseAttestationError"]
