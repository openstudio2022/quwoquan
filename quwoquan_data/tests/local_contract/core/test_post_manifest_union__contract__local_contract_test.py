# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from core.schema import load_schema, validate_strict

ROOT = Path(__file__).resolve().parents[4]
VECTORS = ROOT / "quwoquan_data/tests/fixtures/contracts/post_manifest_vectors.json"


def test_post_manifest_union_vectors_match_draft_2020_12() -> None:
    schema = load_schema("content", "post_manifest")
    standard = Draft202012Validator(schema, format_checker=FormatChecker())
    payload = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert payload["spec_ref"].endswith("#gwt-046")
    for vector in payload["vectors"]:
        lightweight_valid = validate_strict(vector["manifest"], schema) == []
        standard_valid = not list(standard.iter_errors(vector["manifest"]))
        assert lightweight_valid == standard_valid == vector["valid"], vector["name"]


def test_post_manifest_keeps_cross_schema_pointer_facade() -> None:
    schema = load_schema("content", "post_manifest")
    assert {"sourceAttribution", "semanticMention"} <= schema["$defs"].keys()
    assert [branch["properties"]["contentType"]["const"] for branch in schema["oneOf"]] == [
        "article", "image", "video",
    ]
