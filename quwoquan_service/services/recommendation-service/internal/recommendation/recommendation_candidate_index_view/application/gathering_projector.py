from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol


@dataclass(frozen=True)
class GatheringCandidateSnapshot:
    """Circle-signed public card trimmed to recommendation index needs."""

    gathering_id: str
    source_version: int
    card_digest: str
    host_subject_kind: str
    host_subject_id: str
    title: str
    summary: str | None
    cover_object_type_ref: str | None
    cover_object_id: str | None
    tag_refs: tuple[str, ...]
    start_at: datetime | None
    end_at: datetime | None
    date_label: str | None
    place_mode: str
    coarse_place_object_type_ref: str | None
    coarse_place_object_id: str | None
    coarse_place_label: str | None
    max_participants: int
    occupied_seats: int
    remaining_seats: int
    full: bool
    admission_state: str
    lifecycle_status: str
    updated_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.gathering_id,
            self.host_subject_kind,
            self.host_subject_id,
            self.title,
            self.place_mode,
            self.admission_state,
            self.lifecycle_status,
        )
        if (
            any(not value.strip() for value in required)
            or self.source_version <= 0
            or len(self.card_digest) != 64
            or any(value not in "0123456789abcdef" for value in self.card_digest)
            or self.updated_at.tzinfo is None
            or self.lifecycle_status != "published"
            or self.max_participants <= 0
            or min(self.occupied_seats, self.remaining_seats) < 0
            or self.occupied_seats + self.remaining_seats != self.max_participants
            or self.full != (self.remaining_seats == 0)
        ):
            raise ValueError("gathering candidate snapshot is incomplete")
        if (
            self.start_at is not None
            and self.start_at.tzinfo is None
            or self.end_at is not None
            and self.end_at.tzinfo is None
            or self.start_at is not None
            and self.end_at is not None
            and self.end_at <= self.start_at
        ):
            raise ValueError("gathering candidate schedule is invalid")
        if bool(self.cover_object_type_ref) != bool(self.cover_object_id):
            raise ValueError("gathering cover reference must be complete")
        if bool(self.coarse_place_object_type_ref) != bool(self.coarse_place_object_id):
            raise ValueError("gathering coarse place reference must be complete")
        if any(not value.strip() for value in self.tag_refs):
            raise ValueError("gathering candidate tags must be non-empty")


class GatheringCandidateProjection(Protocol):
    def apply_gathering_source_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        snapshot: GatheringCandidateSnapshot | None = None,
        removal: tuple[str, int] | None = None,
    ) -> bool: ...

    def record_source_failure(
        self,
        stream_id: str,
        event_id: str,
        cause: Exception,
    ) -> int: ...

    def clear_source_failure(self, stream_id: str) -> None: ...


GatheringProjectionDecision = Literal["upsert", "remove", "ignore"]


def decide_gathering_projection(
    *,
    current_version: int,
    current_card_digest: str | None,
    tombstone_version: int,
    incoming_version: int,
    incoming_card_digest: str | None,
    removal: bool,
) -> GatheringProjectionDecision:
    """One monotonic rule shared by runtime persistence and local contracts."""

    if min(current_version, tombstone_version) < 0 or incoming_version <= 0:
        raise ValueError("Gathering projection versions are invalid")
    if max(current_version, tombstone_version) > incoming_version:
        return "ignore"
    if removal:
        return "ignore" if tombstone_version >= incoming_version else "remove"
    if not incoming_card_digest:
        raise ValueError("Gathering upsert requires cardDigest")
    if current_version == incoming_version:
        if current_card_digest != incoming_card_digest:
            raise RuntimeError("Gathering candidate sourceVersion conflict")
        return "ignore"
    if tombstone_version == incoming_version:
        return "ignore"
    return "upsert"


def gathering_event_receipt_is_duplicate(
    *,
    recorded_event_digest: str | None,
    incoming_event_digest: str,
) -> bool:
    if recorded_event_digest is None:
        return False
    if recorded_event_digest != incoming_event_digest:
        raise RuntimeError("Gathering candidate source event identity conflict")
    return True
