from __future__ import annotations

import pytest

from core.schema import load_schema, validate_strict


@pytest.mark.parametrize("scope", ["research", "commercial"])
def test_retired_pool_scope_is_rejected(scope: str) -> None:
    schema = load_schema("content", "pool_admission")
    assert validate_strict(scope, schema["$defs"]["usageScope"])


@pytest.mark.parametrize("decision", ["research_allowed", "commercial_allowed"])
def test_manifest_asset_rejects_retired_distribution(decision: str) -> None:
    schema = load_schema("content", "post_manifest")
    asset = {"assetId": "a", "fileName": "a.png", "distributionDecision": decision}
    assert validate_strict(asset, schema["properties"]["assets"]["items"], _root_schema=schema)


def test_external_pointer_keeps_referenced_schema_local_defs() -> None:
    schema = load_schema("content", "post_manifest")
    admission_schema = schema["properties"]["admission"]

    assert validate_strict(
        {
            "processResult": "completed",
            "qualityResult": "passed",
            "usageScope": "production",
            "rightsResult": "passed",
            "rightsAuthorityRef": "posts/article/test/content_review.json",
            "rightsAuthorityDigest": "sha256:" + "b" * 64,
            "evidenceRef": "metadata_adoption.json",
            "evidenceDigest": "sha256:" + "a" * 64,
        },
        admission_schema,
        _root_schema=schema,
    ) == []
