from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain.experiment_policy import (
    ExperimentPolicy,
    PolicyVariant,
    canonical_policy,
)


COLLECTION = "rm_recommendation_experiment_policy"


class MongoExperimentPolicyStore:
    def __init__(self, database: Any) -> None:
        if database is None:
            raise ValueError("recommendation Experiment policy store requires Mongo")
        self._collection = database[COLLECTION]

    def ensure_indexes(self) -> None:
        self._collection.create_index(
            [("revision", -1), ("updatedAt", -1)],
            name="idx_recommendation_experiment_policy_revision",
        )

    def load(self, experiment_id: str) -> ExperimentPolicy | None:
        document = self._collection.find_one({"_id": experiment_id.strip()})
        return None if document is None else _from_document(document)

    def apply(self, policy: ExperimentPolicy) -> ExperimentPolicy:
        canonical = canonical_policy(policy)
        document = _document(canonical)
        try:
            self._collection.update_one(
                {
                    "_id": canonical.experiment_id,
                    "$or": [
                        {"revision": {"$lt": canonical.revision}},
                        {"revision": canonical.revision, "digest": canonical.digest},
                    ],
                },
                {"$set": document},
                upsert=True,
            )
        except Exception as error:
            current = self.load(canonical.experiment_id)
            if current is None:
                raise
            if current.revision > canonical.revision or (
                current.revision == canonical.revision
                and current.digest == canonical.digest
            ):
                return current
            raise ValueError(
                "recommendation Experiment policy revision has conflicting content"
            ) from error
        current = self.load(canonical.experiment_id)
        if current is None:
            raise RuntimeError("recommendation Experiment policy write was not observable")
        return current


def _document(policy: ExperimentPolicy) -> dict[str, Any]:
    return {
        "revision": policy.revision,
        "status": policy.status,
        "variants": [
            {
                "key": item.key,
                "allocationBasisPoints": item.allocation_basis_points,
            }
            for item in policy.variants
        ],
        "startsAt": policy.starts_at,
        "endsAt": policy.ends_at,
        "updatedAt": policy.updated_at,
        "digest": policy.digest,
    }


def _from_document(document: dict[str, Any]) -> ExperimentPolicy:
    updated_at = document.get("updatedAt")
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)
    starts_at = document.get("startsAt")
    if isinstance(starts_at, str):
        starts_at = datetime.fromisoformat(starts_at)
    ends_at = document.get("endsAt")
    if isinstance(ends_at, str):
        ends_at = datetime.fromisoformat(ends_at)
    return canonical_policy(
        ExperimentPolicy(
            experiment_id=str(document.get("_id") or ""),
            revision=int(document.get("revision") or 0),
            status=str(document.get("status") or ""),
            variants=tuple(
                PolicyVariant(
                    key=str(item.get("key") or ""),
                    allocation_basis_points=int(
                        item.get("allocationBasisPoints") or 0
                    ),
                )
                for item in document.get("variants") or []
            ),
            starts_at=starts_at,
            ends_at=ends_at,
            updated_at=(updated_at or datetime.min.replace(tzinfo=timezone.utc)),
            digest=str(document.get("digest") or ""),
        )
    )
