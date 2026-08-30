"""Typed source qualification for deterministic execution target selection."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    data_issue,
)


@dataclass(frozen=True, slots=True)
class TargetSourceQualification:
    """Pre-freeze source eligibility for one candidate target."""

    accepted: bool
    qualified_source: "QualifiedTargetSource | None"
    rejection_code: DataIssueCode | None = None

    def __post_init__(self) -> None:
        if self.accepted != (self.qualified_source is not None):
            raise ValueError("qualification acceptance and qualified source disagree")
        if self.qualified_source is not None and not hasattr(
            self.qualified_source, "to_dict"
        ):
            raise TypeError("qualified source must provide to_dict")
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


class QualifiedTargetSource(Protocol):
    """A pre-freeze evidence summary; only homepage persists it on targets."""

    def to_dict(self) -> dict[str, str]: ...


def rejection_summary(rows: list[dict[str, object]]) -> str:
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


def restrict_to_qualification_candidates(
    candidate_rows: list[dict[str, Any]],
    qualification_candidate_names: tuple[str, ...],
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Intersect catalog rows with an explicit upstream supply identity set."""
    requested = tuple(
        str(name).strip() for name in qualification_candidate_names if str(name).strip()
    )
    if len(requested) != len(qualification_candidate_names):
        raise ValueError("qualification candidate names must be non-empty")
    if len(requested) != len(set(requested)):
        raise ValueError("qualification candidate names must not contain duplicates")
    requested_set = set(requested)
    matched_names: set[str] = set()
    scoped_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        row_names = {
            str(row.get("name") or "").strip(),
            str(row.get("sourceName") or "").strip(),
            *(str(alias).strip() for alias in row.get("aliases") or []),
        }
        intersection = requested_set & row_names
        if not intersection:
            continue
        scoped_rows.append(row)
        matched_names.update(intersection)
    return scoped_rows, tuple(name for name in requested if name not in matched_names)


def qualify_source_ready_targets(
    candidate_rows: list[dict[str, Any]],
    *,
    discovery_ref: str,
    limit: int,
    quota: int,
    source_qualifier: TargetSourceQualifier,
    target_names: tuple[str, ...],
    qualification_source_key: str = "qualifiedHomepageSource",
    persist_qualified_source: bool = True,
    qualification_candidate_names: tuple[str, ...] | None = None,
    qualification_supply_count: int | None = None,
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
    # 四载体 campaign 共享同一份 current-wave targetNames：小配额载体（如 M100
    # video quota=10、count=18）从大名单中挑 quota 个交付，名单大于该载体候选池
    # 是共享名单的预期形态。唯一的硬下限是名单不得小于交付承诺（与
    # request.py / request_envelope_build.py 的同名校验保持同一语义）。
    if (
        requested_target_names
        and qualification_supply_count is None
        and len(requested_target_names) < quota
    ):
        raise ValueError(
            "explicit target count must reach the approved --quota"
        )
    if requested_target_names:
        scoped_rows = _restrict_to_requested_targets(candidate_rows, requested_target_names)
    else:
        scoped_rows = candidate_rows
    unmatched_qualification_names: tuple[str, ...] = ()
    if qualification_candidate_names is not None:
        scoped_rows, unmatched_qualification_names = restrict_to_qualification_candidates(
            scoped_rows,
            qualification_candidate_names,
        )
        # ``limit`` is the request's semantic candidate-pool size. The external
        # input set may be larger, but work outside this request does not belong
        # to this execution and must not create threads or file activity here.
        scoped_rows = scoped_rows[:limit]
    qualification_rows: list[dict[str, object]] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    # Homepage must keep only authority-qualified rows. Video (and other
    # non-persisted qualification lanes) still require ``quota`` accepted rows,
    # then fill the oversampled ``limit`` pool with rejected/unevaluated leaves
    # so download admission and M100→M1000 promotion see a full candidate set.
    if scoped_rows:
        with ThreadPoolExecutor(max_workers=len(scoped_rows)) as executor:
            futures = [
                executor.submit(source_qualifier, _candidate_from_row(row))
                for row in scoped_rows
            ]
            for row, future in zip(scoped_rows, futures, strict=True):
                try:
                    verdict = future.result()
                except DataIssueError as exc:
                    issue_code = (
                        exc.issues[0].code
                        if exc.issues
                        else DataIssueCode.INTERNAL_UNEXPECTED
                    )
                    qualification_rows.append(
                        {
                            "name": str(row["name"]),
                            "accepted": False,
                            qualification_source_key: None,
                            "rejectionCode": issue_code.value,
                        }
                    )
                    rejected.append(dict(row))
                    continue
                except Exception:  # noqa: BLE001 - isolated as one typed rejection.
                    qualification_rows.append(
                        {
                            "name": str(row["name"]),
                            "accepted": False,
                            qualification_source_key: None,
                            "rejectionCode": DataIssueCode.INTERNAL_UNEXPECTED.value,
                        }
                    )
                    rejected.append(dict(row))
                    continue
                qualification_rows.append(
                    {
                        "name": str(row["name"]),
                        "accepted": verdict.accepted,
                        qualification_source_key: (
                            verdict.qualified_source.to_dict()
                            if verdict.qualified_source is not None
                            else None
                        ),
                        "rejectionCode": verdict.rejection_code.value if verdict.rejection_code else None,
                    }
                )
                if verdict.accepted:
                    selected_row = dict(row)
                    if persist_qualified_source:
                        selected_row[qualification_source_key] = (
                            verdict.qualified_source.to_dict()
                        )
                    accepted.append(selected_row)
                else:
                    rejected.append(dict(row))
    if qualification_supply_count is None:
        available_supply_count = len(accepted)
    else:
        if (
            isinstance(qualification_supply_count, bool)
            or not isinstance(qualification_supply_count, int)
            or qualification_supply_count < 0
        ):
            raise ValueError("qualification supply count must be a non-negative integer")
        if qualification_supply_count < len(accepted):
            raise ValueError(
                "qualification supply count cannot be smaller than accepted targets"
            )
        available_supply_count = qualification_supply_count
    supply_shortfall = max(0, quota - available_supply_count)
    # persist_qualified_source（homepage）把 qualification 当作交付承诺的准入门，
    # 不足配额必须 fail-closed。非 persist lane（video 等）的真实供给由冻结的外部
    # 输入 receipt 决定，qualification 只是 precheck；与 download 阶段
    # absorb_download_shortfall_if_any_ready 同一语义——approvedQuota 是 scale
    # milestone 而非 lane 级 veto，只有零供给才是阻断性 shortfall。
    if supply_shortfall and (persist_qualified_source or not accepted):
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
                        "acceptedCount": len(accepted),
                        "evaluatedCount": len(qualification_rows),
                        "candidateCount": len(scoped_rows),
                        "rejectionCounts": rejection_summary(qualification_rows),
                    },
                ),
            )
        )
    selected = list(accepted[:limit])
    # persist lane（homepage）的 frozen coverage targets 必须逐行携带
    # qualifiedHomepageSource（spec_contract fail-closed）；用 rejected 行凑满
    # oversample 池会把不合格实体写进交付承诺。oversample 填充只属于非
    # persist lane（download admission 会对填充行重新验证）。
    allow_oversample_fill = (
        not persist_qualified_source and qualification_candidate_names is None
    )
    if len(selected) < limit and allow_oversample_fill:
        seen = {str(row.get("name") or "") for row in selected}
        for row in rejected:
            name = str(row.get("name") or "")
            if not name or name in seen:
                continue
            selected.append(row)
            seen.add(name)
            if len(selected) >= limit:
                break
        if len(selected) < limit and allow_oversample_fill:
            evaluated_names = {
                str(row.get("name") or "")
                for row in qualification_rows
                if str(row.get("name") or "")
            }
            for row in scoped_rows:
                name = str(row.get("name") or "")
                if not name or name in seen or name in evaluated_names:
                    continue
                selected.append(dict(row))
                seen.add(name)
                qualification_rows.append(
                    {
                        "name": name,
                        "accepted": False,
                        qualification_source_key: None,
                        "rejectionCode": DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL.value,
                        "oversampleFill": True,
                    }
                )
                if len(selected) >= limit:
                    break
    return (
        selected,
        {
            "evaluatedCount": len(qualification_rows),
            "acceptedCount": sum(1 for row in qualification_rows if row["accepted"]),
            "rejectedCount": sum(1 for row in qualification_rows if not row["accepted"]),
            "candidates": qualification_rows,
            "oversampleFilled": len(selected) - len(accepted[:limit]),
            "approvedQuota": quota,
            "availableSupplyCount": available_supply_count,
            "supplyShortfallCount": supply_shortfall,
            "qualificationCandidateCount": (
                None
                if qualification_candidate_names is None
                else len(qualification_candidate_names)
            ),
            "unmatchedQualificationNames": list(unmatched_qualification_names),
        },
        requested_target_names,
    )


__all__ = [
    "TargetSourceCandidate",
    "TargetSourceQualification",
    "TargetSourceQualifier",
    "qualify_source_ready_targets",
    "rejection_summary",
    "restrict_to_qualification_candidates",
]
