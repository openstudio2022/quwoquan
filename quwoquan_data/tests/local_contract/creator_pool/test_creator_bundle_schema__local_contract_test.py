from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCHEMA = REPO / "quwoquan_data/schema/creator/creator_bundle.schema.json"
GOLDEN = REPO / "quwoquan_data/tests/fixtures/creator_pool/travel_scale10_verify/golden_creator_bundle.json"


def test_golden_creator_bundle_required_fields() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for field in (
        "creatorProfileId",
        "subAccountId",
        "authorId",
        "creatorArchetype",
        "profile",
        "provenance",
        "content",
        "operations",
    ):
        assert field in data
    assert data["provenance"]["derivationPolicy"] == "derivative_persona_v1"
    assert data["schemaVersion"] == "quwoquan_data.creator_bundle/1"


def test_creator_bundle_schema_file_exists() -> None:
    assert SCHEMA.is_file()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "quwoquan_data.creator_bundle"
