from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Protocol

from .intersection_materializer import Materializer
from .intersection_reader import ALLOWED_SUPPLY_KEYS


@dataclass(frozen=True, slots=True)
class IntersectionProjectionInventory:
    subject_id: str
    intersection_class: str
    channel: str
    source_event_digest: str
    checkpoint: int


@dataclass(frozen=True, slots=True)
class IntersectionSupplyInventory:
    supply_key: str
    source_event_digest: str
    checkpoint: int


@dataclass(frozen=True, slots=True)
class IntersectionRebuildReport:
    source_subject_count: int
    closed_subject_count: int
    changed_snapshot_count: int
    snapshot_count: int
    changed_supply_count: int
    supply_count: int
    source_identity_digest: str
    projection_identity_digest: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IntersectionRebuildPlan:
    open_subjects: tuple[str, ...]
    closed_subjects: tuple[str, ...]
    source_rows: tuple[tuple[str, str], ...]
    supply_digest: str
    source_identity_digest: str

    def public_summary(self) -> dict[str, Any]:
        return {
            "sourceSubjectCount": len(self.open_subjects),
            "closedSubjectCount": len(self.closed_subjects),
            "sourceIdentityDigest": self.source_identity_digest,
        }


class IntersectionRebuildStore(Protocol):
    def list_intersection_rebuild_subject_ids(self) -> tuple[str, ...]: ...

    def subject_intersection_evidence_digest(self, subject_id: str) -> str: ...

    def intersection_supply_evidence_digest(self) -> str: ...

    def list_subject_projection_inventory(
        self, subject_ids: tuple[str, ...]
    ) -> tuple[IntersectionProjectionInventory, ...]: ...

    def list_supply_projection_inventory(
        self,
    ) -> tuple[IntersectionSupplyInventory, ...]: ...

    def erase_subject(self, subject_id: str) -> int: ...


class SubjectClosureReader(Protocol):
    def exists(self, subject_id: str) -> bool: ...


class IntersectionRebuilder:
    """Rebuilds canonical snapshots from object-local typed-event evidence.

    Retired Content snapshots are deliberately not read or translated: they are
    reconstructable projections, not authoritative facts. The coordinator
    reconciles the complete expected identity/digest set and is idempotent for
    one immutable evidence snapshot.
    """

    def __init__(
        self,
        *,
        store: IntersectionRebuildStore,
        materializer: Materializer,
        subject_closures: SubjectClosureReader,
    ) -> None:
        if store is None or materializer is None or subject_closures is None:
            raise ValueError("intersection rebuild dependencies are required")
        self._store = store
        self._materializer = materializer
        self._subject_closures = subject_closures

    def plan(self) -> IntersectionRebuildPlan:
        candidates = self._store.list_intersection_rebuild_subject_ids()
        open_subjects: list[str] = []
        closed_subjects: list[str] = []
        for subject_id in candidates:
            if self._subject_closures.exists(subject_id):
                closed_subjects.append(subject_id)
                continue
            open_subjects.append(subject_id)
        source_rows = tuple(
            (subject_id, self._store.subject_intersection_evidence_digest(subject_id))
            for subject_id in open_subjects
        )
        supply_digest = self._store.intersection_supply_evidence_digest()
        source_identity_digest = _digest(
            {
                "subjects": source_rows,
                "supplyDigest": supply_digest,
            }
        )
        return IntersectionRebuildPlan(
            open_subjects=tuple(open_subjects),
            closed_subjects=tuple(closed_subjects),
            source_rows=source_rows,
            supply_digest=supply_digest,
            source_identity_digest=source_identity_digest,
        )

    def rebuild(self, expected_source_identity_digest: str) -> IntersectionRebuildReport:
        requested_plan = self.plan()
        expected_digest = expected_source_identity_digest.strip().lower()
        if expected_digest != requested_plan.source_identity_digest:
            raise RuntimeError("intersection rebuild source identity digest drifted")
        for subject_id in requested_plan.closed_subjects:
            self._store.erase_subject(subject_id)
        plan = self.plan()

        changed_snapshot_count = 0
        for subject_id, digest in plan.source_rows:
            changed_snapshot_count += sum(
                self._materializer.rebuild_subject(
                    source_event_id=f"intersection-rebuild:{digest}",
                    source_event_digest=digest,
                    subject_id=subject_id,
                    channel=None,
                )
            )

        supply_digest = self._store.intersection_supply_evidence_digest()
        if supply_digest != plan.supply_digest:
            raise RuntimeError("intersection rebuild supply evidence drifted")
        changed_supply_count = self._materializer.rebuild_supplies(
            source_event_id=f"intersection-rebuild-supply:{supply_digest}",
            source_event_digest=supply_digest,
        )

        expected_subject_rows = tuple(
            sorted(
                (subject_id, intersection_class, "", digest)
                for subject_id, digest in plan.source_rows
                for intersection_class in ("affinity", "fact")
            )
        )
        actual_subject_inventory = self._store.list_subject_projection_inventory(
            plan.open_subjects
        )
        actual_subject_rows = tuple(
            sorted(
                (
                    row.subject_id,
                    row.intersection_class,
                    row.channel,
                    row.source_event_digest,
                )
                for row in actual_subject_inventory
            )
        )
        if any(row.checkpoint <= 0 for row in actual_subject_inventory):
            raise RuntimeError("intersection rebuild produced a non-positive checkpoint")
        if actual_subject_rows != expected_subject_rows:
            raise RuntimeError("intersection subject projection identity reconciliation failed")

        expected_supply_rows = tuple(
            sorted((key, supply_digest) for key in ALLOWED_SUPPLY_KEYS)
        )
        actual_supply_inventory = self._store.list_supply_projection_inventory()
        actual_supply_rows = tuple(
            sorted((row.supply_key, row.source_event_digest) for row in actual_supply_inventory)
        )
        if any(row.checkpoint <= 0 for row in actual_supply_inventory):
            raise RuntimeError("intersection supply rebuild produced a non-positive checkpoint")
        if actual_supply_rows != expected_supply_rows:
            raise RuntimeError("intersection supply projection identity reconciliation failed")

        if self.plan().source_identity_digest != plan.source_identity_digest:
            raise RuntimeError("intersection rebuild evidence changed during reconciliation")
        projection_identity_digest = _digest(
            {
                "subjects": actual_subject_rows,
                "supplies": actual_supply_rows,
            }
        )
        return IntersectionRebuildReport(
            source_subject_count=len(plan.open_subjects),
            closed_subject_count=len(requested_plan.closed_subjects),
            changed_snapshot_count=changed_snapshot_count,
            snapshot_count=len(actual_subject_rows),
            changed_supply_count=changed_supply_count,
            supply_count=len(actual_supply_rows),
            source_identity_digest=plan.source_identity_digest,
            projection_identity_digest=projection_identity_digest,
        )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
