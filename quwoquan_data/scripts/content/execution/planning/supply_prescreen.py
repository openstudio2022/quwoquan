"""Four-state supply prescreening for candidate targets, ahead of target-set freeze.

The existing homepage qualification contract grades a candidate `confirmed` or
`blocked`. That binary collapses three outcomes an operator has to act on
differently: a source that exists but falls short, a source that does not exist
at all, and a probe that never reached a verdict. Collapsing them makes the
third one the most expensive — an interrupted probe reported as `blocked` reads
as a proven absence, so nobody re-runs it and the entity is dropped on evidence
that was never gathered.

The four states here keep those apart, and the merge order keeps them apart
under mixed evidence too: an entity holding both a below-threshold candidate and
an unfinished probe grades `PROBE_FAILED`, because a verdict that is still
pending cannot be reported as a settled shortfall.

Thresholds deliberately have no defaults. Every numeric bound arrives through
`PrescreenThresholds`, which is only constructible from a governed calibration
receipt that carries a `frozenPrescreen` block. A receipt without that block is
refused rather than filled in: the point of grading supply before the freeze is
to spend the calibrated bound, and a made-up bound would decide which entities
get produced while claiming calibration it never had. Classification, merge
order and per-entity accounting below do not read any threshold value, so they
hold before the calibration lands.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.data_issue import DataIssueCode


class SupplyState(StrEnum):
    """The four outcomes a candidate entity's supply probe can settle on."""

    PRESENT_USABLE = "present_usable"
    PRESENT_INSUFFICIENT = "present_insufficient"
    ABSENT = "absent"
    PROBE_FAILED = "probe_failed"


class SupplySubReason(StrEnum):
    """Why a non-usable state was reached, at the granularity an operator acts on."""

    LENGTH_BELOW_THRESHOLD = "length_below_threshold"
    NOT_THIS_ENTITY = "not_this_entity"
    NOT_LEGALLY_RETRIEVABLE = "not_legally_retrievable"
    NO_CANDIDATE = "no_candidate"
    PROBE_INTERRUPTED = "probe_interrupted"
    UNCLASSIFIED_REJECTION = "unclassified_rejection"


class SupplyRecoveryDirection(StrEnum):
    """Where an operator has to go to change a non-usable outcome."""

    RESUME_PROBE = "resume_probe"
    WIDEN_SOURCE_CLOSURE = "widen_source_closure"
    ADJUST_LENGTH_THRESHOLD_OR_SWAP_ENTITY = "adjust_length_threshold_or_swap_entity"
    SWAP_ENTITY = "swap_entity"


# The four rejection codes the homepage qualifier already emits map onto the
# four states without inventing a fifth outcome. `NO_CANDIDATE` and
# `NOT_LEGALLY_RETRIEVABLE` are both absence, but they send an operator to
# different places, which is why absence keeps two sub-reasons rather than one.
_CODE_CLASSIFICATION: Mapping[DataIssueCode, tuple[SupplyState, SupplySubReason]] = {
    DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING: (
        SupplyState.ABSENT,
        SupplySubReason.NO_CANDIDATE,
    ),
    DataIssueCode.SOURCE_UNREADABLE: (
        SupplyState.ABSENT,
        SupplySubReason.NOT_LEGALLY_RETRIEVABLE,
    ),
    DataIssueCode.SOURCE_CONTENT_INCOMPLETE: (
        SupplyState.PRESENT_INSUFFICIENT,
        SupplySubReason.LENGTH_BELOW_THRESHOLD,
    ),
    DataIssueCode.SOURCE_PAGE_TYPE_INVALID: (
        SupplyState.PRESENT_INSUFFICIENT,
        SupplySubReason.NOT_THIS_ENTITY,
    ),
}

_SUB_REASON_RECOVERY: Mapping[SupplySubReason, SupplyRecoveryDirection] = {
    SupplySubReason.LENGTH_BELOW_THRESHOLD: (
        SupplyRecoveryDirection.ADJUST_LENGTH_THRESHOLD_OR_SWAP_ENTITY
    ),
    SupplySubReason.NOT_THIS_ENTITY: SupplyRecoveryDirection.WIDEN_SOURCE_CLOSURE,
    SupplySubReason.NOT_LEGALLY_RETRIEVABLE: (
        SupplyRecoveryDirection.WIDEN_SOURCE_CLOSURE
    ),
    SupplySubReason.NO_CANDIDATE: SupplyRecoveryDirection.SWAP_ENTITY,
    SupplySubReason.PROBE_INTERRUPTED: SupplyRecoveryDirection.RESUME_PROBE,
    SupplySubReason.UNCLASSIFIED_REJECTION: SupplyRecoveryDirection.RESUME_PROBE,
}

# A pending verdict outranks every settled one: reporting it as a shortfall or
# an absence would present evidence that was never gathered as if it were
# conclusive. A usable source outranks everything because the entity is already
# producible and the remaining candidates cannot take that away.
_MERGE_ORDER: tuple[SupplyState, ...] = (
    SupplyState.PRESENT_USABLE,
    SupplyState.PROBE_FAILED,
    SupplyState.PRESENT_INSUFFICIENT,
    SupplyState.ABSENT,
)

_RESUMABLE_STATES = frozenset({SupplyState.PROBE_FAILED})


class PrescreenCalibrationError(ValueError):
    """A prescreen threshold was requested from a receipt that never calibrated one."""


@dataclass(frozen=True, slots=True)
class PrescreenThresholds:
    """Calibrated bounds for supply prescreening. No field carries a default."""

    article_body_min_characters: int
    entity_anchor_min_confidence: float
    per_entity_probe_budget: int
    image_supply_min_candidates: int

    def __post_init__(self) -> None:
        if self.article_body_min_characters < 1:
            raise PrescreenCalibrationError(
                "articleBodyMinCharacters must be a positive character count"
            )
        if not 0 < self.entity_anchor_min_confidence <= 1:
            raise PrescreenCalibrationError(
                "entityAnchorMinConfidence must fall in (0, 1]"
            )
        if self.per_entity_probe_budget < 1:
            raise PrescreenCalibrationError(
                "perEntityProbeBudget must allow at least one probe"
            )
        if self.image_supply_min_candidates < 1:
            raise PrescreenCalibrationError(
                "imageSupplyMinCandidates must require at least one candidate"
            )

    @classmethod
    def from_calibration_receipt(
        cls, receipt: Mapping[str, Any]
    ) -> "PrescreenThresholds":
        """Read the governed block, refusing a receipt that never calibrated it."""
        block = receipt.get("frozenPrescreen")
        if block is None:
            raise PrescreenCalibrationError(
                "GATE_BLOCK: calibration receipt carries no frozenPrescreen block; "
                "prescreen thresholds have no default and cannot be inferred from "
                "capacity, liveness or draft-quality values"
            )
        if not isinstance(block, Mapping):
            raise PrescreenCalibrationError(
                "GATE_BLOCK: frozenPrescreen must be an object"
            )
        missing = sorted(
            key
            for key in (
                "articleBodyMinCharacters",
                "entityAnchorMinConfidence",
                "perEntityProbeBudget",
                "imageSupplyMinCandidates",
            )
            if key not in block
        )
        if missing:
            raise PrescreenCalibrationError(
                "GATE_BLOCK: frozenPrescreen is present but incomplete; missing "
                + ", ".join(missing)
            )
        return cls(
            article_body_min_characters=int(block["articleBodyMinCharacters"]),
            entity_anchor_min_confidence=float(block["entityAnchorMinConfidence"]),
            per_entity_probe_budget=int(block["perEntityProbeBudget"]),
            image_supply_min_candidates=int(block["imageSupplyMinCandidates"]),
        )


@dataclass(frozen=True, slots=True)
class CandidateVerdict:
    """One probed candidate's contribution to an entity's supply state.

    A pending verdict carries the refs needed to pick the probe back up; a
    settled one carries what it was settled on. The two are mutually exclusive
    by construction rather than by convention — a resumable outcome with no refs
    is a dead end wearing a retry label, and settled evidence attached to a
    pending probe would claim a conclusion that was never reached.
    """

    state: SupplyState
    sub_reason: SupplySubReason | None
    resume_refs: tuple[str, ...] = ()
    settled_evidence: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.state is SupplyState.PRESENT_USABLE:
            if self.sub_reason is not None:
                raise ValueError("a usable candidate carries no sub-reason")
        elif self.sub_reason is None:
            raise ValueError(f"{self.state} requires a sub-reason")
        if self.state is SupplyState.PROBE_FAILED:
            if not self.resume_refs:
                raise ValueError(
                    "a probe failure must carry non-empty resume refs; without them "
                    "the entity is dropped on a verdict nobody can re-reach"
                )
            if self.settled_evidence:
                raise ValueError(
                    "a probe failure has no settled evidence: its verdict is pending"
                )
        else:
            if self.resume_refs:
                raise ValueError(f"{self.state} is settled and carries no resume refs")
            if self.state is not SupplyState.PRESENT_USABLE and not self.settled_evidence:
                raise ValueError(
                    f"{self.state} must carry the evidence it was settled on"
                )


@dataclass(frozen=True, slots=True)
class EntitySupplyOutcome:
    """An entity's merged supply state and the one primary reason behind it."""

    entity_name: str
    state: SupplyState
    sub_reason: SupplySubReason | None
    resumable: bool
    recovery: SupplyRecoveryDirection | None
    resume_refs: tuple[str, ...] = ()
    settled_evidence: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.resumable != bool(self.resume_refs):
            raise ValueError(
                "resumability and resume refs disagree: one of them is lying about "
                "whether this entity can be picked back up"
            )

    @property
    def enters_frozen_work_unit(self) -> bool:
        return self.state is SupplyState.PRESENT_USABLE


def classify_rejection(
    code: DataIssueCode | str, *, resume_refs: tuple[str, ...] = ()
) -> CandidateVerdict:
    """Map one qualifier rejection onto the four-state closed set.

    A code outside the classification table is a probe that reached an outcome
    this contract cannot read. It fails closed onto `PROBE_FAILED` and names the
    code, rather than being folded into absence or shortfall — the entity might
    be perfectly producible, and the gap is in the mapping, not in the supply.
    An unclassified code therefore needs resume refs like any other pending
    verdict; a caller that has none cannot classify, because the entity would
    otherwise be dropped on a reason this contract admits it cannot read.
    """
    if isinstance(code, DataIssueCode):
        classified = _CODE_CLASSIFICATION.get(code)
        if classified is not None:
            state, sub_reason = classified
            return CandidateVerdict(
                state=state,
                sub_reason=sub_reason,
                settled_evidence=f"qualifier rejected the candidate: {code.value}",
            )
        named = code.value
    else:
        named = str(code).strip() or "<empty>"
    return CandidateVerdict(
        state=SupplyState.PROBE_FAILED,
        sub_reason=SupplySubReason.UNCLASSIFIED_REJECTION,
        resume_refs=resume_refs,
        detail=f"unclassified rejection code: {named}",
    )


def probe_interrupted(detail: str, *, resume_refs: tuple[str, ...]) -> CandidateVerdict:
    """A probe that stopped before reaching a verdict."""
    return CandidateVerdict(
        state=SupplyState.PROBE_FAILED,
        sub_reason=SupplySubReason.PROBE_INTERRUPTED,
        resume_refs=resume_refs,
        detail=detail,
    )


def probe_budget_exhausted(
    *, budget: int, resume_refs: tuple[str, ...]
) -> CandidateVerdict:
    """Budget ran out before a verdict. Unfinished, not absent."""
    return CandidateVerdict(
        state=SupplyState.PROBE_FAILED,
        sub_reason=SupplySubReason.PROBE_INTERRUPTED,
        resume_refs=resume_refs,
        detail=f"probe budget of {budget} exhausted before a verdict",
    )


def merge_candidate_verdicts(
    entity_name: str, verdicts: Iterable[CandidateVerdict]
) -> EntitySupplyOutcome:
    """Reduce one entity's candidate verdicts to its single primary outcome.

    An entity with no probed candidate at all is absence with no candidate,
    which is a verdict rather than an empty result: the probe did run and found
    nothing to grade.
    """
    collected = tuple(verdicts)
    if not collected:
        return _outcome(
            entity_name,
            CandidateVerdict(
                state=SupplyState.ABSENT,
                sub_reason=SupplySubReason.NO_CANDIDATE,
                settled_evidence="the probe ran and returned no candidate to grade",
                detail="no candidate was probed for this entity",
            ),
        )
    winner = min(collected, key=lambda verdict: _MERGE_ORDER.index(verdict.state))
    return _outcome(entity_name, winner)


def _outcome(entity_name: str, verdict: CandidateVerdict) -> EntitySupplyOutcome:
    return EntitySupplyOutcome(
        entity_name=entity_name,
        state=verdict.state,
        sub_reason=verdict.sub_reason,
        resumable=verdict.state in _RESUMABLE_STATES,
        recovery=(
            None
            if verdict.sub_reason is None
            else _SUB_REASON_RECOVERY[verdict.sub_reason]
        ),
        resume_refs=verdict.resume_refs,
        settled_evidence=verdict.settled_evidence,
        detail=verdict.detail,
    )


@dataclass(frozen=True, slots=True)
class PrimaryReasonTally:
    """Per-entity accounting over the four reason classes, each counted once.

    `undetermined` is kept out of the other three on purpose. Folding pending
    probes into the settled classes would inflate whichever class absorbed them
    and make the supply hit rate read as measured when part of it was never
    resolved.
    """

    no_retrievable_source: int
    body_below_threshold: int
    not_this_entity: int
    undetermined: int
    usable: int

    @property
    def graded(self) -> int:
        return (
            self.no_retrievable_source
            + self.body_below_threshold
            + self.not_this_entity
            + self.undetermined
            + self.usable
        )

    def share(self, count: int) -> float:
        graded = self.graded
        if graded == 0:
            raise ValueError("no graded entity: a share has no denominator")
        return count / graded


def tally_primary_reasons(
    outcomes: Iterable[EntitySupplyOutcome],
) -> PrimaryReasonTally:
    """Count entities by primary reason. Every entity lands in exactly one class."""
    counts = {
        "no_retrievable_source": 0,
        "body_below_threshold": 0,
        "not_this_entity": 0,
        "undetermined": 0,
        "usable": 0,
    }
    for outcome in outcomes:
        if outcome.state is SupplyState.PRESENT_USABLE:
            counts["usable"] += 1
        elif outcome.state is SupplyState.PROBE_FAILED:
            counts["undetermined"] += 1
        elif outcome.state is SupplyState.ABSENT:
            counts["no_retrievable_source"] += 1
        elif outcome.sub_reason is SupplySubReason.NOT_THIS_ENTITY:
            counts["not_this_entity"] += 1
        else:
            counts["body_below_threshold"] += 1
    return PrimaryReasonTally(**counts)


RECEIPT_SCHEMA_REF = (
    "quwoquan_data/schema/execution/source_prescreen_verdict_receipt.schema.json"
)


def verdict_receipt_document(
    *,
    execution_id: str,
    carrier: str,
    calibration_receipt_digest: str,
    prescreened_at: str,
    outcomes: Iterable[EntitySupplyOutcome],
) -> dict[str, Any]:
    """Project the graded entities into the create-once receipt document.

    The receipt is written before the execution spec is frozen, because a
    prescreen that fails is precisely the case where no spec is ever written —
    anything landing after the freeze would be absent exactly when it is needed.
    Counts are derived here from the same outcomes as the rows, so the four
    classes cannot drift from the verdicts they summarize.
    """
    graded = tuple(outcomes)
    if not graded:
        raise ValueError(
            "a prescreen receipt with no verdict row would report the candidate set "
            "as empty rather than as unscreened"
        )
    tally = tally_primary_reasons(graded)
    return {
        "schemaRef": RECEIPT_SCHEMA_REF,
        "executionId": execution_id,
        "carrier": carrier,
        "calibrationReceiptDigest": calibration_receipt_digest,
        "prescreenedAt": prescreened_at,
        "verdicts": [_verdict_row(outcome) for outcome in graded],
        "primaryReasonCounts": {
            "usable": tally.usable,
            "noRetrievableSource": tally.no_retrievable_source,
            "bodyBelowThreshold": tally.body_below_threshold,
            "notThisEntity": tally.not_this_entity,
            "undetermined": tally.undetermined,
        },
    }


def _verdict_row(outcome: EntitySupplyOutcome) -> dict[str, Any]:
    row: dict[str, Any] = {
        "entityName": outcome.entity_name,
        "state": outcome.state.value,
        "recovery": "none" if outcome.recovery is None else outcome.recovery.value,
    }
    if outcome.sub_reason is not None:
        row["subReason"] = outcome.sub_reason.value
    if outcome.resume_refs:
        row["resumeRefs"] = list(outcome.resume_refs)
    if outcome.settled_evidence:
        row["settledEvidence"] = outcome.settled_evidence
    if outcome.detail:
        row["detail"] = outcome.detail
    return row


def project_for_selector(outcome: EntitySupplyOutcome) -> bool:
    """Project one verdict onto the selector's binary admission. One direction only.

    `source-ready-priority` requires a non-empty qualifier, and its contract is
    two-valued. Feeding it the four states directly would collapse them, so the
    projection is deliberately lossy: usable admits, the other three do not.

    Nothing may travel back. A consumer that reads the selector's rejection and
    infers which of the three states produced it would be reconstructing a
    distinction this boolean does not carry — and would get it wrong the moment
    two states project the same way, which is always. The verdict itself stays
    the only place the four states are readable, and this projection is never
    persisted as source evidence.
    """
    return outcome.enters_frozen_work_unit


__all__ = [
    "RECEIPT_SCHEMA_REF",
    "CandidateVerdict",
    "EntitySupplyOutcome",
    "PrescreenCalibrationError",
    "PrescreenThresholds",
    "PrimaryReasonTally",
    "SupplyRecoveryDirection",
    "SupplyState",
    "SupplySubReason",
    "classify_rejection",
    "merge_candidate_verdicts",
    "probe_budget_exhausted",
    "probe_interrupted",
    "project_for_selector",
    "tally_primary_reasons",
    "verdict_receipt_document",
]
