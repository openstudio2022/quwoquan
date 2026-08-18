"""In-place resume admission for an interrupted execution.

Requiring a new ``retryOf`` sequence after every interruption protected the
audit trail by throwing away work: objects that had already been authored,
reviewed and finalized were re-produced from scratch. That is a real cost at
thousand scale, and it is not what immutability requires.

The boundary this module draws:

*Rewriting existing evidence is forbidden.* The frozen manifest, request,
target set and execution spec, every recorded semantic attempt, and every
terminal receipt of a finished object are immutable. Nothing here can edit or
delete them, and a finished object is never re-entered.

*Continuing the unfinished part is allowed.* An object with no terminal receipt
may be resumed inside the same execution: new attempts append after the
existing ones, and its attempt budget may be widened only by an append-only
recovery grant that names its cause and its owner.

A new ``retryOf`` sequence therefore stays required exactly where identity
itself changed — a different provider, model, runtime or runtime-profile digest
cannot be replayed as a continuation of the frozen binding.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ResumeDisposition(StrEnum):
    """What one object's evidence permits."""

    FINISHED_IMMUTABLE = "finished_immutable"
    RESUMABLE_IN_PLACE = "resumable_in_place"
    REQUIRES_NEW_RETRY_OF = "requires_new_retry_of"


class ResumeBlocker(StrEnum):
    """Why in-place resume is refused for the whole execution."""

    SEMANTIC_BINDING_DRIFT = "semantic_binding_drift"
    RUNTIME_PROFILE_DRIFT = "runtime_profile_drift"
    SUPERSEDED_EXECUTION = "superseded_execution"


@dataclass(frozen=True, slots=True)
class ObjectResumeDecision:
    object_ref: str
    disposition: ResumeDisposition
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.object_ref.strip():
            raise ValueError("resume decision requires an objectRef")
        if (
            self.disposition is not ResumeDisposition.FINISHED_IMMUTABLE
            and not self.reason.strip()
        ):
            raise ValueError("non-finished resume decision requires a reason")

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "objectRef": self.object_ref,
            "disposition": self.disposition.value,
        }
        if self.reason:
            document["reason"] = self.reason
        return document


@dataclass(frozen=True, slots=True)
class ResumeAdmission:
    """The exact in-place resume scope, or the blocker that forbids it."""

    execution_id: str
    decisions: tuple[ObjectResumeDecision, ...]
    blocker: ResumeBlocker | None = None
    blocker_reason: str = ""

    def __post_init__(self) -> None:
        if (self.blocker is None) == bool(self.blocker_reason.strip()):
            raise ValueError("resume blocker and its reason must be stated together")
        refs = [row.object_ref for row in self.decisions]
        if len(refs) != len(set(refs)):
            raise ValueError("resume admission must not repeat an objectRef")

    @property
    def admitted(self) -> bool:
        return self.blocker is None

    @property
    def finished_refs(self) -> tuple[str, ...]:
        return tuple(
            row.object_ref
            for row in self.decisions
            if row.disposition is ResumeDisposition.FINISHED_IMMUTABLE
        )

    @property
    def resumable_refs(self) -> tuple[str, ...]:
        if not self.admitted:
            return ()
        return tuple(
            row.object_ref
            for row in self.decisions
            if row.disposition is ResumeDisposition.RESUMABLE_IN_PLACE
        )

    def report(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "executionId": self.execution_id,
            "admitted": self.admitted,
            "finishedCount": len(self.finished_refs),
            "resumableCount": len(self.resumable_refs),
            "decisions": [row.to_document() for row in self.decisions],
        }
        if self.blocker is not None:
            document["blocker"] = self.blocker.value
            document["blockerReason"] = self.blocker_reason
        return document


def admit_in_place_resume(
    *,
    execution_id: str,
    object_refs: Sequence[str],
    finished_refs: Sequence[str],
    identity_drift: Mapping[str, bool] | None = None,
    superseded_by: str | None = None,
) -> ResumeAdmission:
    """Decide the in-place resume scope from terminal receipts and identity.

    ``finished_refs`` must come from terminal receipts, not from a status field
    that a resume could overwrite: a finished object is the one piece of
    evidence this admission is designed never to touch.
    """

    normalized_execution_id = str(execution_id or "").strip()
    if not normalized_execution_id:
        raise ValueError("resume admission requires an executionId")
    refs = tuple(str(value).strip() for value in object_refs)
    if any(not ref for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("resume admission objectRefs must be non-empty and unique")
    finished = {str(value).strip() for value in finished_refs}
    unknown = sorted(finished - set(refs))
    if unknown:
        raise ValueError(
            "finished refs must be inside the frozen object set: "
            + ", ".join(unknown[:5])
        )
    drift = dict(identity_drift or {})
    blocker: ResumeBlocker | None = None
    blocker_reason = ""
    superseded = str(superseded_by or "").strip()
    if superseded:
        blocker = ResumeBlocker.SUPERSEDED_EXECUTION
        blocker_reason = (
            f"execution was superseded by {superseded}; resume the successor instead"
        )
    elif drift.get("runtimeProfile"):
        blocker = ResumeBlocker.RUNTIME_PROFILE_DRIFT
        blocker_reason = (
            "frozen runtimeProfileDigest no longer matches the runtime profile; "
            "the frozen budgets and model binding cannot be replayed"
        )
    elif drift.get("semanticBinding"):
        blocker = ResumeBlocker.SEMANTIC_BINDING_DRIFT
        blocker_reason = (
            "frozen provider/model/runtime binding drifted; a different binding "
            "is a different execution identity, not a continuation"
        )
    decisions: list[ObjectResumeDecision] = []
    for ref in refs:
        if ref in finished:
            decisions.append(
                ObjectResumeDecision(
                    object_ref=ref,
                    disposition=ResumeDisposition.FINISHED_IMMUTABLE,
                )
            )
        elif blocker is None:
            decisions.append(
                ObjectResumeDecision(
                    object_ref=ref,
                    disposition=ResumeDisposition.RESUMABLE_IN_PLACE,
                    reason="no terminal receipt; unfinished work may append",
                )
            )
        else:
            decisions.append(
                ObjectResumeDecision(
                    object_ref=ref,
                    disposition=ResumeDisposition.REQUIRES_NEW_RETRY_OF,
                    reason=blocker_reason,
                )
            )
    return ResumeAdmission(
        execution_id=normalized_execution_id,
        decisions=tuple(decisions),
        blocker=blocker,
        blocker_reason=blocker_reason,
    )


__all__ = [
    "ObjectResumeDecision",
    "ResumeAdmission",
    "ResumeBlocker",
    "ResumeDisposition",
    "admit_in_place_resume",
]
