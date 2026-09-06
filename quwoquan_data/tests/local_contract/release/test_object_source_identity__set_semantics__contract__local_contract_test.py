# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Source identity sets preserve execution and object identity boundaries."""

from __future__ import annotations

import pytest
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)


def test_identity_set_rejects_retired_migration_identity_shape() -> None:
    retired_shape = {
        "identityKind": "retired_migration_kind",
        "executionId": "20260905--travel-article-identity--test-region-a--pilot-001",
        "sourceDigest": "sha256:" + "1" * 64,
        "canonicalObjectDigest": "sha256:" + "2" * 64,
        "migrationEvidenceDigest": "sha256:" + "3" * 64,
    }

    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_INVALID"):
        source_identity_set([retired_shape])


def test_modern_identity_set_still_rejects_one_execution_with_drift() -> None:
    execution_id = "20260905--travel-article-identity--test-region-a--pilot-001"
    first = {
        "executionId": execution_id,
        "sourceRevision": "sha256:" + "6" * 64,
        "sourceDigest": "sha256:" + "7" * 64,
        "entityCatalogDigest": "sha256:" + "8" * 64,
    }
    second = {**first, "sourceDigest": "sha256:" + "9" * 64}

    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_DRIFT"):
        source_identity_set([first, second])
