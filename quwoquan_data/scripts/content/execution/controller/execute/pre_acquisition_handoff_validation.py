"""Confirmed handoff 的 scope、topic 与来源选择校验。"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from core import paths
from core.content_source_registry import lane_source_id_closure
from core.io import read_json

SCOPE_TYPES = ("vertical", "region", "topic", "region_topic")
SOURCE_SELECTION_MODES = ("site_primary", "search_supplement")
_TOPIC_REF_RE = re.compile(r"^Topic/.+$")
_SCOPE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ErrorFactory = Callable[[str, str], Exception]


def _taxonomy_definition_path(topic_ref: str) -> Path:
    return (
        paths.REPO_ROOT
        / "quwoquan_data"
        / "control_plane"
        / "governance"
        / "taxonomy"
        / topic_ref
        / "_definition.json"
    )


def _require_canonical_topic_ref(
    topic_ref: object,
    *,
    error_factory: ErrorFactory,
) -> dict[str, Any]:
    ref = str(topic_ref or "").strip()
    if not _TOPIC_REF_RE.fullmatch(ref) or ".." in Path(ref).parts:
        raise error_factory(
            "TOPIC_INVALID",
            f"topic ref must be a canonical Topic/** ref: {topic_ref}",
        )
    definition_path = _taxonomy_definition_path(ref)
    if not definition_path.is_file():
        raise error_factory(
            "TOPIC_UNKNOWN",
            f"topic ref is not in canonical taxonomy: {ref}",
        )
    definition = read_json(definition_path)
    if not isinstance(definition, dict):
        raise error_factory(
            "TOPIC_UNKNOWN",
            f"topic definition is not an object: {ref}",
        )
    return definition


def _scope_slug(
    value: str,
    *,
    label: str,
    error_factory: ErrorFactory,
) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not token or not _SCOPE_TOKEN_RE.fullmatch(token):
        raise error_factory(
            "SCOPE_INVALID",
            f"{label} cannot derive a deterministic scope token: {value}",
        )
    return token


def _region_scope_token(
    region_ref: str,
    *,
    error_factory: ErrorFactory,
) -> str:
    parts = [
        part
        for part in str(region_ref or "").strip().strip("/").split("/")
        if part
    ]
    if not parts:
        raise error_factory(
            "SCOPE_INVALID",
            "regionRef must be non-empty for region scopes",
        )
    for part in parts:
        candidate = part.strip().lower()
        if _SCOPE_TOKEN_RE.fullmatch(candidate):
            return candidate
    return _scope_slug(
        parts[0],
        label="regionRef",
        error_factory=error_factory,
    )


def _topic_scope_token(
    primary_topic_ref: str,
    *,
    error_factory: ErrorFactory,
) -> str:
    definition = _require_canonical_topic_ref(
        primary_topic_ref,
        error_factory=error_factory,
    )
    label_en = str(definition.get("labelEn") or "").strip()
    if not label_en:
        raise error_factory(
            "TOPIC_SLUG_UNAVAILABLE",
            f"topic definition lacks labelEn for scope projection: {primary_topic_ref}",
        )
    return _scope_slug(
        label_en,
        label="primaryTopicRef",
        error_factory=error_factory,
    )


def validated_scope_fields(
    *,
    scope_type: str,
    vertical: str,
    region_ref: str | None,
    primary_topic_ref: str | None,
    related_topic_refs: Sequence[str],
    error_factory: ErrorFactory,
) -> dict[str, Any]:
    if scope_type not in SCOPE_TYPES:
        raise error_factory("SCOPE_INVALID", f"unsupported scopeType: {scope_type}")
    region = str(region_ref or "").strip() or None
    primary = str(primary_topic_ref or "").strip() or None
    needs_region = scope_type in ("region", "region_topic")
    needs_topic = scope_type in ("topic", "region_topic")
    if needs_region != (region is not None):
        raise error_factory(
            "SCOPE_INVALID",
            f"scopeType={scope_type} requires regionRef exactly when region-scoped",
        )
    if needs_topic != (primary is not None):
        raise error_factory(
            "SCOPE_INVALID",
            f"scopeType={scope_type} requires primaryTopicRef exactly when topic-scoped",
        )
    related = [str(item or "").strip() for item in related_topic_refs]
    if any(not item for item in related):
        raise error_factory(
            "TOPIC_INVALID",
            "relatedTopicRefs must not contain empty refs",
        )
    if len(set(related)) != len(related):
        raise error_factory("TOPIC_INVALID", "relatedTopicRefs must be unique")
    if primary is not None and primary in related:
        raise error_factory(
            "TOPIC_INVALID",
            "relatedTopicRefs must not contain primaryTopicRef",
        )
    for ref in related:
        _require_canonical_topic_ref(ref, error_factory=error_factory)
    if primary is not None:
        _require_canonical_topic_ref(primary, error_factory=error_factory)
    if scope_type == "vertical":
        scope = _scope_slug(
            vertical,
            label="vertical",
            error_factory=error_factory,
        )
    elif scope_type == "region":
        scope = _region_scope_token(region or "", error_factory=error_factory)
    elif scope_type == "topic":
        scope = _topic_scope_token(primary or "", error_factory=error_factory)
    else:
        scope = (
            f"{_region_scope_token(region or '', error_factory=error_factory)}-"
            f"{_topic_scope_token(primary or '', error_factory=error_factory)}"
        )
    return {
        "scopeType": scope_type,
        "scope": scope,
        "regionRef": region,
        "primaryTopicRef": primary,
        "relatedTopicRefs": sorted(related),
    }


def validated_source_selection(
    source_selection: Mapping[str, Any],
    *,
    vertical: str,
    active_carriers: Sequence[str],
    error_factory: ErrorFactory,
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_selection, Mapping) or not source_selection:
        raise error_factory(
            "SOURCE_SELECTION_INVALID",
            "sourceSelection must be a non-empty carrier mapping",
        )
    if set(source_selection) != set(active_carriers):
        raise error_factory(
            "SOURCE_SELECTION_INVALID",
            "sourceSelection carriers must match activeCarriers exactly",
        )
    validated: dict[str, dict[str, Any]] = {}
    for carrier in active_carriers:
        row = source_selection[carrier]
        if not isinstance(row, Mapping):
            raise error_factory(
                "SOURCE_SELECTION_INVALID",
                f"sourceSelection.{carrier} must be an object",
            )
        unknown_keys = set(row) - {"mode", "providers"}
        if unknown_keys:
            raise error_factory(
                "SOURCE_SELECTION_INVALID",
                f"sourceSelection.{carrier} has unknown keys: {sorted(unknown_keys)}",
            )
        mode = str(row.get("mode") or "").strip()
        if mode not in SOURCE_SELECTION_MODES:
            raise error_factory(
                "SOURCE_SELECTION_INVALID",
                f"sourceSelection.{carrier}.mode must be one of {SOURCE_SELECTION_MODES}",
            )
        providers = [
            str(item or "").strip()
            for item in (row.get("providers") or [])
        ]
        if not providers or any(not item for item in providers):
            raise error_factory(
                "SOURCE_SELECTION_INVALID",
                f"sourceSelection.{carrier}.providers must be non-empty source ids",
            )
        if len(set(providers)) != len(providers):
            raise error_factory(
                "SOURCE_SELECTION_INVALID",
                f"sourceSelection.{carrier}.providers must be unique",
            )
        closure = lane_source_id_closure(carrier, vertical=vertical)
        unknown = sorted(set(providers) - closure)
        if unknown:
            raise error_factory(
                "SOURCE_SELECTION_UNDECLARED",
                f"sourceSelection.{carrier} providers outside content source "
                f"registry closed set: {', '.join(unknown)}",
            )
        validated[carrier] = {"mode": mode, "providers": sorted(providers)}
    return validated


def validate_document_carrier_alignment(
    handoff: Mapping[str, Any],
    targets: Mapping[str, int],
    *,
    error_factory: ErrorFactory,
) -> None:
    if set(handoff.get("carrierRequirements", {})) != set(targets):
        raise error_factory(
            "WORKLOAD_INVALID",
            "carrierRequirements must match activeCarriers exactly",
        )
    if set(handoff.get("sourceSelection", {})) != set(targets):
        raise error_factory(
            "SOURCE_SELECTION_INVALID",
            "sourceSelection must match activeCarriers exactly",
        )


__all__ = [
    "validate_document_carrier_alignment",
    "validated_scope_fields",
    "validated_source_selection",
]
