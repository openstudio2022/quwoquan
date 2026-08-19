from __future__ import annotations

from core.schema import load_schema, validate_strict


def test_external_pointer_keeps_referenced_schema_local_defs() -> None:
    schema = load_schema("content", "post_manifest")
    admission_schema = schema["properties"]["admission"]

    assert validate_strict(
        {
            "processResult": "completed",
            "qualityResult": "passed",
            "usageScope": "research",
            "evidenceRef": "metadata_adoption.json",
            "evidenceDigest": "sha256:" + "a" * 64,
        },
        admission_schema,
        _root_schema=schema,
    ) == []
