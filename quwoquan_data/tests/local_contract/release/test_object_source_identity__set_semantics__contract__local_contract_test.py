# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Source identity sets preserve execution and object identity boundaries."""

from __future__ import annotations

import pytest
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)


def _legacy_identity(*, object_digit: str, evidence_digit: str) -> dict[str, str]:
    return {
        "identityKind": "legacy_canonical_migration",
        "executionId": "sequence-017-article",
        "sourceDigest": "sha256:" + "1" * 64,
        "canonicalObjectDigest": "sha256:" + object_digit * 64,
        "migrationEvidenceDigest": "sha256:" + evidence_digit * 64,
    }


def test_legacy_identity_set_allows_multiple_objects_for_one_execution() -> None:
    first = _legacy_identity(object_digit="2", evidence_digit="3")
    second = _legacy_identity(object_digit="4", evidence_digit="5")

    rows, digest = source_identity_set([second, first, first])
    replay_rows, replay_digest = source_identity_set([first, second])

    assert rows == replay_rows == [
        {
            "identityKind": "legacy_canonical_migration",
            "sourceDigest": first["sourceDigest"],
            "canonicalObjectDigest": first["canonicalObjectDigest"],
            "migrationEvidenceDigest": first["migrationEvidenceDigest"],
            "executionIds": [first["executionId"]],
        },
        {
            "identityKind": "legacy_canonical_migration",
            "sourceDigest": second["sourceDigest"],
            "canonicalObjectDigest": second["canonicalObjectDigest"],
            "migrationEvidenceDigest": second["migrationEvidenceDigest"],
            "executionIds": [second["executionId"]],
        },
    ]
    assert digest == replay_digest


def test_modern_identity_set_still_rejects_one_execution_with_drift() -> None:
    execution_id = "sequence-017-article"
    first = {
        "executionId": execution_id,
        "sourceRevision": "sha256:" + "6" * 64,
        "sourceDigest": "sha256:" + "7" * 64,
        "entityCatalogDigest": "sha256:" + "8" * 64,
    }
    second = {**first, "sourceDigest": "sha256:" + "9" * 64}

    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_DRIFT"):
        source_identity_set([first, second])
