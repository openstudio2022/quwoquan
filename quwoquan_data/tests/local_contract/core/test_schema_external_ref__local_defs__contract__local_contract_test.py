from __future__ import annotations

from core.schema import load_schema, validate_strict


def test_pool_admission_has_no_object_usage_scope() -> None:
    schema = load_schema("content", "pool_admission")
    assert "usageScope" not in schema.get("$defs", {})
    admission = {
        "processResult": "completed", "qualityResult": "passed",
        "rightsResult": "passed",
        "rightsAuthorityRef": "posts/article/test/content_review.json",
        "rightsAuthorityDigest": "sha256:" + "b" * 64,
        "evidenceRef": "metadata_adoption.json",
        "evidenceDigest": "sha256:" + "a" * 64,
    }
    content_admission = schema["$defs"]["contentAdmission"]
    assert validate_strict(admission, content_admission, _root_schema=schema) == []
    assert validate_strict({**admission, "usageScope": "research"}, content_admission, _root_schema=schema)


def test_manifest_asset_keeps_three_value_usage_scope_and_rejects_distribution() -> None:
    schema = load_schema("content", "post_manifest")
    asset_schema = schema["properties"]["assets"]["items"]
    for scope in ("internal_reference", "app_publish", "editorial"):
        assert validate_strict({"assetId": "a", "fileName": "a.png", "usageScope": scope}, asset_schema, _root_schema=schema) == []
    assert "distributionDecision" not in asset_schema["properties"]
