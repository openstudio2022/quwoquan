"""Canonical SourceAttribution validation shared by source and post stages."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.schema import load_schema, validate_strict


def canonical_source_attribution(value: object) -> dict[str, Any]:
    """Return one schema-valid attribution object without deriving defaults."""

    if not isinstance(value, Mapping):
        raise ValueError("sourceAttribution must be one object")
    attribution = dict(value)
    manifest_schema = load_schema("content", "post_manifest")
    definition = (manifest_schema.get("$defs") or {}).get("sourceAttribution")
    if not isinstance(definition, dict):
        raise ValueError("post manifest sourceAttribution schema is unavailable")
    issues = validate_strict(
        attribution,
        definition,
        path="$.sourceAttribution",
        _root_schema=manifest_schema,
    )
    if issues:
        raise ValueError(
            "sourceAttribution schema violation:\n  - "
            + "\n  - ".join(issues[:20])
        )
    return attribution


def source_attribution_fragment(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project an explicitly present source attribution without a fallback."""

    if "sourceAttribution" not in payload:
        return {}
    return {
        "sourceAttribution": canonical_source_attribution(payload["sourceAttribution"])
    }


__all__ = ["canonical_source_attribution", "source_attribution_fragment"]
