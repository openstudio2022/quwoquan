"""Pre-production source-ready grading, including rights closure.

Rights closure used to surface at pool admission, long after the semantic agent
had already authored the object: an entity whose asset rows never carried a
``distributionDecision`` still consumed provider quota before being rejected.
Grading it here moves that verdict ahead of production, so an unclosed
candidate costs one cheap local check instead of one agent run.

Absent and blocked are graded apart on purpose. Several upstream writers project
a missing decision as ``""``; that is an absent decision wearing an empty-string
costume, not a decision to block. Collapsing the two would report a contract gap
as a rights denial and hide the writer that needs fixing, so the empty-string
shape is graded as absent and carries the shape in its evidence.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from governance.coverage.distribution import DistributionDecision

_ALLOWED_DECISIONS = frozenset(
    {
        DistributionDecision.RESEARCH_ALLOWED.value,
        DistributionDecision.COMMERCIAL_ALLOWED.value,
    }
)


class SourceReadyGrade(StrEnum):
    """Why one candidate may or may not enter production."""

    READY = "ready"
    SOURCE_ABSENT = "source_absent"
    RIGHTS_DECISION_ABSENT = "rights_decision_absent"
    RIGHTS_NOT_CLOSED = "rights_not_closed"


class DecisionShape(StrEnum):
    """How an unusable ``distributionDecision`` was encoded upstream."""

    KEY_MISSING = "key_missing"
    NULL = "null"
    EMPTY_STRING = "empty_string"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True, slots=True)
class SourceReadyVerdict:
    """One candidate's pre-production grade with its attributable evidence."""

    name: str
    grade: SourceReadyGrade
    reason: str = ""
    decision_shape: DecisionShape | None = None
    offending_asset_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("source-ready verdict requires a candidate name")
        if self.grade is SourceReadyGrade.READY:
            if self.reason or self.decision_shape is not None:
                raise ValueError("ready verdict cannot carry a rejection reason")
        elif not self.reason.strip():
            raise ValueError("rejected verdict requires a reason")
        if (
            self.decision_shape is not None
            and self.grade is not SourceReadyGrade.RIGHTS_DECISION_ABSENT
        ):
            raise ValueError("decision shape only describes an absent decision")

    @property
    def ready(self) -> bool:
        return self.grade is SourceReadyGrade.READY

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "name": self.name,
            "grade": self.grade.value,
            "ready": self.ready,
        }
        if self.reason:
            document["reason"] = self.reason
        if self.decision_shape is not None:
            document["decisionShape"] = self.decision_shape.value
        if self.offending_asset_ids:
            document["offendingAssetIds"] = list(self.offending_asset_ids)
        return document


def _decision_shape(asset: Mapping[str, Any]) -> DecisionShape | None:
    """Classify an unusable decision, or absent when the decision is usable."""

    if "distributionDecision" not in asset:
        return DecisionShape.KEY_MISSING
    raw = asset["distributionDecision"]
    if raw is None:
        return DecisionShape.NULL
    if not isinstance(raw, str):
        return DecisionShape.UNRECOGNIZED
    if not raw.strip():
        return DecisionShape.EMPTY_STRING
    if raw.strip() == DistributionDecision.BLOCKED.value:
        return None
    if raw.strip() not in _ALLOWED_DECISIONS:
        return DecisionShape.UNRECOGNIZED
    return None


def grade_source_ready_candidate(
    row: Mapping[str, Any],
    *,
    asset_key: str = "assets",
    require_assets: bool = True,
) -> SourceReadyVerdict:
    """Grade one candidate row before it is allowed to spend provider quota."""

    name = str(row.get("name") or "").strip()
    if not name:
        raise ValueError("source-ready candidate row requires a name")
    raw_assets = row.get(asset_key)
    assets = list(_asset_rows(raw_assets)) if raw_assets is not None else []
    if not assets:
        if not require_assets:
            return SourceReadyVerdict(name=name, grade=SourceReadyGrade.READY)
        return SourceReadyVerdict(
            name=name,
            grade=SourceReadyGrade.SOURCE_ABSENT,
            reason=f"candidate carries no {asset_key} to grade",
        )
    absent: list[tuple[str, DecisionShape]] = []
    blocked: list[str] = []
    for asset in assets:
        asset_id = str(asset.get("assetId") or "").strip() or "<unidentified>"
        shape = _decision_shape(asset)
        if shape is not None:
            absent.append((asset_id, shape))
            continue
        if (
            str(asset["distributionDecision"]).strip()
            == DistributionDecision.BLOCKED.value
        ):
            blocked.append(asset_id)
    if absent:
        shapes = sorted({shape.value for _asset_id, shape in absent})
        return SourceReadyVerdict(
            name=name,
            grade=SourceReadyGrade.RIGHTS_DECISION_ABSENT,
            reason=(
                f"{len(absent)} asset rows carry no usable distributionDecision "
                f"({', '.join(shapes)}); upstream rights projection is incomplete"
            ),
            decision_shape=absent[0][1],
            offending_asset_ids=tuple(asset_id for asset_id, _shape in absent),
        )
    if blocked:
        return SourceReadyVerdict(
            name=name,
            grade=SourceReadyGrade.RIGHTS_NOT_CLOSED,
            reason=f"{len(blocked)} asset rows are distribution-blocked",
            offending_asset_ids=tuple(blocked),
        )
    return SourceReadyVerdict(name=name, grade=SourceReadyGrade.READY)


def _asset_rows(value: object) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("source-ready candidate assets must be an array")
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("source-ready candidate assets must contain objects")
        yield raw


@dataclass(frozen=True, slots=True)
class SourceReadyPrecheck:
    """The graded partition of one candidate pool, ahead of production."""

    verdicts: tuple[SourceReadyVerdict, ...]

    @property
    def ready_names(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.verdicts if row.ready)

    def report(self) -> dict[str, Any]:
        by_grade: dict[str, int] = {}
        for row in self.verdicts:
            by_grade[row.grade.value] = by_grade.get(row.grade.value, 0) + 1
        return {
            "evaluatedCount": len(self.verdicts),
            "readyCount": len(self.ready_names),
            "gradeCounts": dict(sorted(by_grade.items())),
            "verdicts": [row.to_document() for row in self.verdicts],
        }


def precheck_source_ready_pool(
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    asset_key: str = "assets",
    require_assets: bool = True,
) -> SourceReadyPrecheck:
    """Grade a whole candidate pool before any of it reaches the semantic agent."""

    return SourceReadyPrecheck(
        verdicts=tuple(
            grade_source_ready_candidate(
                row,
                asset_key=asset_key,
                require_assets=require_assets,
            )
            for row in candidate_rows
        )
    )


__all__ = [
    "DecisionShape",
    "SourceReadyGrade",
    "SourceReadyPrecheck",
    "SourceReadyVerdict",
    "grade_source_ready_candidate",
    "precheck_source_ready_pool",
]
