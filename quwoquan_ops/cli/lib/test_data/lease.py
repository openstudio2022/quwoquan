"""Actor lease lifecycle with TTL, fencing generation and quarantine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import json
from threading import Lock

from .receipts import ReceiptJournal


class ActorLeaseState(StrEnum):
    REQUESTED = "requested"
    ACQUIRING = "acquiring"
    ACTIVE = "active"
    RELEASING = "releasing"
    RELEASED = "released"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class ActorLease:
    lease_id: str
    case_run_id: str
    generation: int
    state: ActorLeaseState
    acquired_at: datetime
    expires_at: datetime

    @property
    def renewal_interval(self) -> timedelta:
        return (self.expires_at - self.acquired_at) / 3


class ActorLeaseManager:
    DEFAULT_TTL = timedelta(minutes=30)
    MAX_TTL = timedelta(hours=2)

    def __init__(self, journal: ReceiptJournal) -> None:
        self._journal = journal
        self._lease: ActorLease | None = None
        self._lock = Lock()
        self._last_generation = self._load_last_generation()

    def acquire(
        self,
        *,
        lease_id: str,
        case_run_id: str,
        ttl: timedelta = DEFAULT_TTL,
    ) -> ActorLease:
        with self._lock:
            if self._lease is not None and self._lease.state not in {
                ActorLeaseState.RELEASED,
                ActorLeaseState.QUARANTINED,
            }:
                raise RuntimeError("actor lease is already active")
            if ttl <= timedelta(0) or ttl > self.MAX_TTL:
                raise ValueError("actor lease TTL must be positive and at most two hours")
            now = datetime.now(timezone.utc)
            generation = self._last_generation + 1
            lease = ActorLease(
                lease_id=lease_id,
                case_run_id=case_run_id,
                generation=generation,
                state=ActorLeaseState.REQUESTED,
                acquired_at=now,
                expires_at=now + ttl,
            )
            self._transition(lease)
            lease = self._replace_state(lease, ActorLeaseState.ACQUIRING)
            self._transition(lease)
            lease = self._replace_state(lease, ActorLeaseState.ACTIVE)
            self._transition(lease)
            self._lease = lease
            self._last_generation = generation
            return lease

    def renew(self, *, generation: int) -> ActorLease:
        with self._lock:
            lease = self._require_active(generation)
            now = datetime.now(timezone.utc)
            ttl = lease.expires_at - lease.acquired_at
            renewed = ActorLease(
                lease_id=lease.lease_id,
                case_run_id=lease.case_run_id,
                generation=lease.generation,
                state=lease.state,
                acquired_at=now,
                expires_at=now + ttl,
            )
            self._transition(renewed, event="renewed")
            self._lease = renewed
            return renewed

    def release(self, *, generation: int) -> ActorLease:
        with self._lock:
            lease = self._require_active(generation)
            releasing = self._replace_state(lease, ActorLeaseState.RELEASING)
            self._transition(releasing)
            released = self._replace_state(releasing, ActorLeaseState.RELEASED)
            self._transition(released)
            self._lease = released
            return released

    def quarantine(self, *, generation: int, reason: str) -> ActorLease:
        with self._lock:
            lease = self._require_active(generation, allow_releasing=True)
            quarantined = self._replace_state(lease, ActorLeaseState.QUARANTINED)
            self._transition(quarantined, reason=reason)
            self._lease = quarantined
            return quarantined

    def _require_active(
        self,
        generation: int,
        *,
        allow_releasing: bool = False,
    ) -> ActorLease:
        lease = self._lease
        allowed = {ActorLeaseState.ACTIVE}
        if allow_releasing:
            allowed.add(ActorLeaseState.RELEASING)
        if lease is None or lease.state not in allowed:
            raise RuntimeError("actor lease is not active")
        if lease.generation != generation:
            raise RuntimeError("actor lease fencing generation mismatch")
        if lease.expires_at <= datetime.now(timezone.utc):
            raise RuntimeError("actor lease expired")
        return lease

    @staticmethod
    def _replace_state(lease: ActorLease, state: ActorLeaseState) -> ActorLease:
        return ActorLease(
            lease_id=lease.lease_id,
            case_run_id=lease.case_run_id,
            generation=lease.generation,
            state=state,
            acquired_at=lease.acquired_at,
            expires_at=lease.expires_at,
        )

    def _transition(
        self,
        lease: ActorLease,
        *,
        event: str = "state_changed",
        reason: str = "",
    ) -> None:
        self._journal.append(
            "actor-lease",
            {
                "event": event,
                "leaseId": lease.lease_id,
                "caseRunId": lease.case_run_id,
                "generation": lease.generation,
                "state": lease.state.value,
                "acquiredAt": lease.acquired_at.isoformat(),
                "expiresAt": lease.expires_at.isoformat(),
                "reason": reason,
            },
        )

    def _load_last_generation(self) -> int:
        maximum = 0
        for path in self._journal.root.glob("*-actor-lease.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                generation = int(
                    ((document.get("payload") or {}).get("generation")) or 0
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            maximum = max(maximum, generation)
        return maximum
