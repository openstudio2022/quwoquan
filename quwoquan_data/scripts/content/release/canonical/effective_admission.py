"""Resolve explicit admission or a strictly verified historical Research view."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    build_legacy_migration_source_identity,
    latest_pool_record,
)
from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
    _safe_rel,
)
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
    """Prefer modern explicit truth; otherwise verify historical Research only."""

    explicit = latest_pool_record(object_root, object_type)
    if explicit is None or not explicit.get("_legacyRecord"):
        return EffectiveAdmission(
            record=explicit,
            source="explicit" if explicit is not None else "missing",
        )
    if object_type == "author" or not isinstance(document, Mapping):
        return EffectiveAdmission(record=None, source="missing")
    if (
        explicit.get("status") != "active"
        or explicit.get("processResult") != "completed"
        or explicit.get("qualityResult") != "passed"
        or explicit.get("eligibilityResult") != "passed"
    ):
        return EffectiveAdmission(record=None, source="missing")
    evidence_ref = str(explicit.get("evidenceRef") or "").strip()
    evidence_path = object_root / _safe_rel(
        evidence_ref,
        label="historicalAdmission.evidenceRef",
    )
    if (
        evidence_path.is_symlink()
        or not evidence_path.is_file()
        or _digest_file(evidence_path) != explicit.get("evidenceDigest")
    ):
        raise ObjectTransactionError("DATA.POOL.EVIDENCE_DIGEST_DRIFT")
    evidence = _read_json(evidence_path)
    if not (
        evidence.get("decision") == "approved"
        and all(
            isinstance(evidence.get(key), Mapping)
            and evidence[key].get("status") == "passed"
            for key in (
                "deterministicGate",
                "independentReviewer",
                "mediaRefReview",
            )
        )
    ):
        return EffectiveAdmission(record=None, source="missing")
    execution_id = str(document.get("executionId") or "").strip()
    evidence_execution_id = str(evidence.get("executionId") or "").strip()
    if execution_id and evidence_execution_id and execution_id != evidence_execution_id:
        raise ObjectTransactionError("DATA.POOL.EVIDENCE_IDENTITY_DRIFT")

    attribution = (
        dict(document.get("sourceAttribution") or {})
        if isinstance(document.get("sourceAttribution"), Mapping)
        else {}
    )
    inferred = {
        key: value
        for key, value in explicit.items()
        if key not in {"_legacyRecord", "version"}
    }
    inferred["usageScope"] = "research"
    inferred["sourceAttribution"] = attribution
    inferred["canonicalObjectDigest"] = str(explicit.get("payloadDigest") or "")
    try:
        source_identity = validate_object_source_identity(document)
    except ObjectTransactionError:
        source_identity = build_legacy_migration_source_identity(
            manifest=document,
            canonical_object_digest=inferred["canonicalObjectDigest"],
            source_attribution=attribution,
            admission_evidence_digest=str(explicit["evidenceDigest"]),
        )
    if source_identity is not None:
        inferred["sourceIdentity"] = source_identity
    return EffectiveAdmission(
        record=inferred,
        source="historical_approved_research",
    )


def effective_source_attribution_ready(
    admission: EffectiveAdmission,
    *,
    release_mode: str,
) -> bool:
    """Apply attribution once, at the boundary that resolved admission truth."""

    record = admission.record
    if not isinstance(record, Mapping):
        return False
    if admission.source == "historical_approved_research":
        return release_mode == "research" and record.get("usageScope") == "research"
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
