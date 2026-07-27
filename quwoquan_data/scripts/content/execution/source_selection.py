"""Typed source qualification for deterministic execution target selection."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    data_issue,
)
from core.runtime_policy import active_runtime_policy
from content.source.contracts import QualifiedHomepageSource


@dataclass(frozen=True, slots=True)
class TargetSourceQualification:
    """Pre-freeze source eligibility for one candidate target."""

    accepted: bool
    qualified_source: QualifiedHomepageSource | None
    rejection_code: DataIssueCode | None = None

    def __post_init__(self) -> None:
        if self.accepted != (self.qualified_source is not None):
            raise ValueError("qualification acceptance and qualified source disagree")
        if self.accepted and self.rejection_code is not None:
            raise ValueError("accepted qualification cannot carry rejection_code")
        if not self.accepted and not self.rejection_code:
            raise ValueError("rejected qualification requires rejection_code")
        if self.rejection_code is not None and not isinstance(self.rejection_code, DataIssueCode):
            raise TypeError("rejection_code must be DataIssueCode")


@dataclass(frozen=True, slots=True)
class TargetSourceCandidate:
    """Typed source-qualification input projected from a master-list target."""

    name: str
    aliases: tuple[str, ...]
    geo_tag_ref: str


TargetSourceQualifier = Callable[[TargetSourceCandidate], TargetSourceQualification]


def _rejection_summary(rows: list[dict[str, object]]) -> str:
    """Render typed qualification rejections for a bounded GATE_BLOCK receipt."""

    counts = Counter(
        str(row["rejectionCode"])
        for row in rows
        if not bool(row["accepted"]) and row["rejectionCode"]
    )
    return ",".join(f"{code}:{count}" for code, count in sorted(counts.items()))


def _candidate_from_row(row: Mapping[str, Any]) -> TargetSourceCandidate:
    geo_tag_ref = str(row.get("geoTagRef") or "").strip()
    if not geo_tag_ref:
        geo_refs = row.get("geoTagRefs")
        if isinstance(geo_refs, list) and geo_refs:
            geo_tag_ref = str(geo_refs[0]).strip()
    return TargetSourceCandidate(
        name=str(row["name"]),
        aliases=tuple(
            str(value).strip()
            for value in row.get("aliases") or []
            if str(value).strip()
        ),
        geo_tag_ref=geo_tag_ref,
    )


def _restrict_to_requested_targets(
    candidate_rows: list[dict[str, Any]],
    requested_target_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    requested_by_name = {name: index for index, name in enumerate(requested_target_names)}
    matched_rows: dict[str, dict[str, Any]] = {}
    for row in candidate_rows:
        row_names = {
            str(row.get("name") or "").strip(),
            str(row.get("sourceName") or "").strip(),
            *(str(alias).strip() for alias in row.get("aliases") or []),
        }
        for requested_name in requested_by_name:
            if requested_name not in row_names:
                continue
            existing = matched_rows.get(requested_name)
            if existing is not None and existing is not row:
                raise ValueError(
                    f"explicit target is ambiguous in region reference: {requested_name}"
                )
            matched_rows[requested_name] = row
    missing_names = [name for name in requested_target_names if name not in matched_rows]
    if missing_names:
        raise ValueError(
            "explicit targets are absent from the region reference: "
            + ", ".join(missing_names)
        )
    return [matched_rows[name] for name in requested_target_names]


def qualify_source_ready_targets(
    candidate_rows: list[dict[str, Any]],
    *,
    discovery_ref: str,
    limit: int,
    quota: int,
    source_qualifier: TargetSourceQualifier,
    target_names: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, object], tuple[str, ...]]:
    """Freeze the qualified candidate pool from the complete ordered reference set.

    The reference set is finite and version-controlled.  A qualification budget
    must never turn early source rejections into an incorrect claim that the
    region has no eligible targets.  ``limit`` caps the oversampled pool while
    ``quota`` is the only count that must be reached.
    """
    requested_target_names = tuple(name.strip() for name in target_names if name.strip())
    if len(set(requested_target_names)) != len(requested_target_names):
        raise ValueError("explicit target names must not contain duplicates")
    if requested_target_names and not quota <= len(requested_target_names) <= limit:
        raise ValueError(
            "explicit target count must fall inside the [--quota, --count] candidate pool range"
        )
    if requested_target_names:
        scoped_rows = _restrict_to_requested_targets(candidate_rows, requested_target_names)
    else:
        scoped_rows = candidate_rows
    qualification_rows: list[dict[str, object]] = []
    selected: list[dict[str, Any]] = []
    worker_count = max(1, active_runtime_policy().research_workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for start in range(0, len(scoped_rows), worker_count):
            batch = scoped_rows[start : start + worker_count]
            futures = [executor.submit(source_qualifier, _candidate_from_row(row)) for row in batch]
            for row, future in zip(batch, futures, strict=True):
                try:
                    verdict = future.result()
                except DataIssueError:
                    raise
                except Exception as exc:  # noqa: BLE001 - converted at the boundary.
                    raise DataIssueError(
                        (
                            data_issue(
                                DataIssueCode.INTERNAL_UNEXPECTED,
                                stage=DataIssueStage.SOURCE_GATE,
                                ref=str(row["name"]),
                                message="source qualification adapter raised unexpectedly",
                            ),
                        )
                    ) from exc
                qualification_rows.append(
                    {
                        "name": str(row["name"]),
                        "accepted": verdict.accepted,
                        "qualifiedHomepageSource": (
                            verdict.qualified_source.to_dict()
                            if verdict.qualified_source is not None
                            else None
                        ),
                        "rejectionCode": verdict.rejection_code.value if verdict.rejection_code else None,
                    }
                )
                if verdict.accepted:
                    selected.append(
                        {
                            **row,
                            "qualifiedHomepageSource": verdict.qualified_source.to_dict(),
                        }
                    )
                if len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break
    if len(selected) < quota:
        raise DataIssueError(
            (
                data_issue(
                    DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED,
                    stage=DataIssueStage.SOURCE_GATE,
                    ref=discovery_ref,
                    message="候选池耗尽，区域实体供给不足：source qualification 未达准出配额",
                    attributes={
                        "candidatePool": limit,
                        "approvedQuota": quota,
                        "acceptedCount": len(selected),
                        "evaluatedCount": len(qualification_rows),
                        "candidateCount": len(scoped_rows),
                        "rejectionCounts": _rejection_summary(qualification_rows),
                    },
                ),
            )
        )
    return (
        selected,
        {
            "evaluatedCount": len(qualification_rows),
            "acceptedCount": sum(1 for row in qualification_rows if row["accepted"]),
            "rejectedCount": sum(1 for row in qualification_rows if not row["accepted"]),
            "candidates": qualification_rows,
        },
        requested_target_names,
    )


__all__ = [
    "TargetSourceCandidate",
    "TargetSourceQualification",
    "TargetSourceQualifier",
    "qualify_source_ready_targets",
]
