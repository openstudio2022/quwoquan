"""Canonical SourceAttribution validation shared by source and post stages."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.media_source_provenance import DerivedModification
from core.schema import load_schema, validate_strict


def derived_modifications_value(
    modifications: Iterable[DerivedModification] = (),
) -> list[str]:
    """把本次实际发生的衍生修改一次物化为 `DerivedModification` 闭集取值。

    这是该字段的唯一写侧物化口：调用方传入自己真的做过的操作，什么都没做时传空
    并落空数组，表示发布字节相对原始素材逐字节原样。读侧与测试替身都不得替这里
    补值——字段在 schema 上必填，所以漏写当场判否，而不是静默变成「没改过」。
    """

    return sorted({modification.value for modification in modifications})


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


__all__ = [
    "canonical_source_attribution",
    "derived_modifications_value",
    "source_attribution_fragment",
]
