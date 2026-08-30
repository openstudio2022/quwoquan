"""Bind frozen media work objects to their exact materialized source assets."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.article_package import sha256_file
from core.io import read_json


def _text(payload: Mapping[str, Any], field: str) -> str:
    return str(payload.get(field) or "").strip()


def _identity(payload: Mapping[str, Any]) -> tuple[str, str, str] | None:
    values = (
        _text(payload, "receiptRef"),
        _text(payload, "assetId"),
        _text(payload, "contentSha256"),
    )
    return values if all(values) else None


def media_work_units_for_carrier(
    spec: Mapping[str, Any],
    *,
    carrier: str,
) -> tuple[dict[str, Any], ...] | None:
    """Return ``None`` for quota-only mode and exact rows for work-unit mode."""

    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    if "workUnits" not in content:
        return None
    raw_rows = content.get("workUnits")
    if not isinstance(raw_rows, list):
        raise TypeError("execution content.workUnits must be an array")
    return tuple(
        dict(row)
        for row in raw_rows
        if isinstance(row, Mapping) and _text(row, "carrier") == carrier
    )


def work_units_by_target(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        target = raw.get("coverageTarget")
        if not isinstance(target, Mapping):
            raise TypeError("media workUnit coverageTarget must be an object")
        name = _text(target, "name")
        if not name:
            raise ValueError("media workUnit coverageTarget.name is required")
        grouped.setdefault(name, []).append(dict(raw))
    return {name: tuple(values) for name, values in grouped.items()}


@dataclass(frozen=True, slots=True)
class MediaCandidateBinding:
    candidates: tuple[dict[str, Any], ...]
    missing_work_unit_ids: tuple[str, ...]
    ignored_candidate_count: int


def bind_candidates_to_work_units(
    *,
    expected_work_units: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any]],
) -> MediaCandidateBinding:
    """Join local source assets to frozen work objects by immutable evidence.

    Candidates without the exact receipt/asset/content identity are unrelated to
    this workload and are ignored. Duplicate local projections of the same
    accepted asset never create a second content object.
    """

    expected = tuple(dict(row) for row in expected_work_units)
    expected_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    expected_ids: list[str] = []
    for row in expected:
        identity = _identity(row)
        work_unit_id = _text(row, "workUnitId")
        if identity is None or not work_unit_id:
            raise ValueError("frozen media workUnit lacks exact identity")
        if identity in expected_by_identity:
            raise ValueError("frozen media workUnits contain duplicate asset identity")
        expected_by_identity[identity] = row
        expected_ids.append(work_unit_id)

    bound_by_id: dict[str, dict[str, Any]] = {}
    ignored = 0
    for raw_candidate in candidates:
        candidate = dict(raw_candidate)
        identity = _identity(candidate)
        expected_row = expected_by_identity.get(identity) if identity else None
        if expected_row is None:
            ignored += 1
            continue
        work_unit_id = _text(expected_row, "workUnitId")
        if work_unit_id in bound_by_id:
            ignored += 1
            continue
        candidate["workUnitId"] = work_unit_id
        bound_by_id[work_unit_id] = candidate

    return MediaCandidateBinding(
        candidates=tuple(
            bound_by_id[work_unit_id]
            for work_unit_id in expected_ids
            if work_unit_id in bound_by_id
        ),
        missing_work_unit_ids=tuple(
            work_unit_id
            for work_unit_id in expected_ids
            if work_unit_id not in bound_by_id
        ),
        ignored_candidate_count=ignored,
    )


def media_item_work_unit_issues(
    *,
    root: Path,
    item: Mapping[str, Any],
    work_unit: Mapping[str, Any],
) -> list[str]:
    """Re-prove that one planned item materializes its frozen accepted asset."""

    issues: list[str] = []
    ref = _text(item, "ref") or "<unknown>"
    carrier = _text(item, "carrier")
    if carrier != _text(work_unit, "carrier"):
        issues.append(f"item[{ref}]: workUnit carrier mismatch")
    target = work_unit.get("coverageTarget")
    expected_target = _text(target, "name") if isinstance(target, Mapping) else ""
    entity_tags = item.get("entityTags")
    tags = {
        str(value).strip()
        for value in entity_tags
        if str(value).strip()
    } if isinstance(entity_tags, list) else set()
    if not expected_target or expected_target not in tags:
        issues.append(f"item[{ref}]: workUnit coverageTarget mismatch")

    asset_refs = item.get("assetRefs")
    if not isinstance(asset_refs, list) or len(asset_refs) != 1:
        issues.append(f"item[{ref}]: workUnit requires exactly one source asset")
        return issues
    asset_path = (root / str(asset_refs[0])).resolve()
    if not asset_path.is_file() or not asset_path.is_relative_to(root.resolve()):
        issues.append(f"item[{ref}]: workUnit source asset is unavailable")
        return issues
    index_path = asset_path.parent / "index.json"
    if not index_path.is_file():
        issues.append(f"item[{ref}]: workUnit source asset index is missing")
        return issues
    try:
        payload = read_json(index_path)
    except (OSError, TypeError, ValueError):
        issues.append(f"item[{ref}]: workUnit source asset index is unreadable")
        return issues
    rows = payload.get("assets") if isinstance(payload, Mapping) else None
    row = next(
        (
            value
            for value in (rows or [])
            if isinstance(value, Mapping)
            and _text(value, "fileName") == asset_path.name
        ),
        None,
    )
    if row is None:
        issues.append(f"item[{ref}]: workUnit source asset is absent from index")
        return issues
    receipt_field = (
        "acquisitionReceiptRef"
        if carrier == "image"
        else "professionalAcquisitionReceiptRef"
    )
    observed = (
        _text(row, receipt_field),
        _text(row, "professionalAssetId"),
        _text(row, "professionalContentSha256"),
    )
    expected = _identity(work_unit)
    if expected is None or observed != expected:
        issues.append(f"item[{ref}]: workUnit source evidence identity mismatch")
    if _text(row, "sha256") != _text(work_unit, "contentSha256"):
        issues.append(f"item[{ref}]: workUnit source bytes digest mismatch")
    elif sha256_file(asset_path) != _text(work_unit, "contentSha256"):
        issues.append(f"item[{ref}]: workUnit source bytes digest mismatch")
    return issues


__all__ = [
    "MediaCandidateBinding",
    "bind_candidates_to_work_units",
    "media_item_work_unit_issues",
    "media_work_units_for_carrier",
    "work_units_by_target",
]
