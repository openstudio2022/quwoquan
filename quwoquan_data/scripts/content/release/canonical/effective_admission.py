"""Resolve the explicit pool-record admission for one canonical object."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import latest_pool_record
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)


@dataclass(frozen=True, slots=True)
class EffectiveAdmission:
    record: Mapping[str, Any] | None
    source: str


def resolve_effective_admission(
    object_root: Path,
    *,
    object_type: str,
    document: Mapping[str, Any] | None = None,
) -> EffectiveAdmission:
    """Admission truth is the explicit pool record; nothing is inferred."""

    del document
    explicit = latest_pool_record(object_root, object_type)
    return EffectiveAdmission(
        record=explicit,
        source="explicit" if explicit is not None else "missing",
    )


def effective_source_attribution_ready(
    admission: EffectiveAdmission,
) -> bool:
    """Check shared-pool attribution without selecting a release class."""

    record = admission.record
    if not isinstance(record, Mapping):
        return False
    return source_attribution_complete(
        {"sourceAttribution": record.get("sourceAttribution")}
    )


def effective_admission_record(
    object_root: Path,
    document: Mapping[str, Any],
    *,
    object_type: str,
) -> Mapping[str, Any] | None:
    """Return the one record view shared by inspect, selection, and build."""

    return resolve_effective_admission(
        object_root,
        object_type=object_type,
        document=document,
    ).record


__all__ = [
    "EffectiveAdmission",
    "effective_admission_record",
    "effective_source_attribution_ready",
    "resolve_effective_admission",
]
