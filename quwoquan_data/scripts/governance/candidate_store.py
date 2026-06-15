"""Filesystem-backed candidate repository isolated from publish trees."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from _common.semantic_mentions import (
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_MAX_DEPTH,
    bounded_candidate_walk,
)
from governance.state_machine import (
    STATUS_PENDING_REVIEW,
    STATUS_PUBLISHED,
    transition_target,
)

_CANDIDATE_ID_RE = re.compile(r"^candidate_[0-9a-f]{24}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def candidate_id_for(kind: str, natural_key: str) -> str:
    kind_value = str(kind).strip()
    key_value = str(natural_key).strip()
    if not kind_value or not key_value:
        raise ValueError("candidate kind and natural_key are required")
    digest = hashlib.sha256(f"{kind_value}\x1f{key_value}".encode("utf-8")).hexdigest()[:24]
    return f"candidate_{digest}"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _append_ndjson(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n")


class CandidateRepository:
    """Candidate truth source. Publication is impossible without ``review``."""

    def __init__(self, root: str | Path, *, now: Callable[[], str] | None = None):
        self.root = Path(root)
        self.now = now or _utc_now

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    @property
    def reviews_dir(self) -> Path:
        return self.root / "reviews"

    @property
    def audit_path(self) -> Path:
        return self.root / "audit" / "audit.ndjson"

    @property
    def backfill_path(self) -> Path:
        return self.root / "events" / "backfill.ndjson"

    def candidate_path(self, candidate_id: str) -> Path:
        if not _CANDIDATE_ID_RE.fullmatch(str(candidate_id)):
            raise ValueError(f"invalid candidate id: {candidate_id!r}")
        return self.candidates_dir / f"{candidate_id}.json"

    def review_path(self, candidate_id: str) -> Path:
        if not _CANDIDATE_ID_RE.fullmatch(str(candidate_id)):
            raise ValueError(f"invalid candidate id: {candidate_id!r}")
        return self.reviews_dir / f"{candidate_id}.ndjson"

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        path = self.candidate_path(candidate_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def find(self, kind: str, natural_key: str) -> dict[str, Any] | None:
        return self.get(candidate_id_for(kind, natural_key))

    def list_candidates(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for path in sorted(self.candidates_dir.glob("candidate_*.json")):
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if status is not None and candidate.get("status") != status:
                continue
            if kind is not None and candidate.get("kind") != kind:
                continue
            output.append(candidate)
        return output

    def intake(
        self,
        *,
        kind: str,
        natural_key: str,
        payload: Mapping[str, Any],
        source_refs: Iterable[str] = (),
        mention_ids: Iterable[str] = (),
        actor: str = "system",
    ) -> dict[str, Any]:
        candidate_id = candidate_id_for(kind, natural_key)
        existing = self.get(candidate_id)
        timestamp = self.now()
        normalized_sources = sorted({str(value).strip() for value in source_refs if str(value).strip()})
        normalized_mentions = sorted({str(value).strip() for value in mention_ids if str(value).strip()})
        if existing is not None:
            changed = False
            merged_sources = sorted(set(existing.get("sourceRefs") or []) | set(normalized_sources))
            merged_mentions = sorted(set(existing.get("mentionIds") or []) | set(normalized_mentions))
            if merged_sources != existing.get("sourceRefs"):
                existing["sourceRefs"] = merged_sources
                changed = True
            if merged_mentions != existing.get("mentionIds"):
                existing["mentionIds"] = merged_mentions
                changed = True
            if dict(payload) != existing.get("payload"):
                existing["payload"] = dict(payload)
                changed = True
            if changed:
                existing["updatedAt"] = timestamp
                existing["version"] = int(existing.get("version") or 1) + 1
                _atomic_write_json(self.candidate_path(candidate_id), existing)
                self._audit(
                    action="candidate.intake_updated",
                    candidate=existing,
                    actor=actor,
                    occurred_at=timestamp,
                )
            return existing

        candidate = {
            "schemaVersion": "quwoquan_data.governance_candidate/1",
            "candidateId": candidate_id,
            "kind": str(kind).strip(),
            "naturalKey": str(natural_key).strip(),
            "status": STATUS_PENDING_REVIEW,
            "payload": dict(payload),
            "sourceRefs": normalized_sources,
            "mentionIds": normalized_mentions,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "version": 1,
        }
        _atomic_write_json(self.candidate_path(candidate_id), candidate)
        self._audit(
            action="candidate.intake",
            candidate=candidate,
            actor=actor,
            occurred_at=timestamp,
        )
        return candidate

    def intake_graph(
        self,
        seeds: Iterable[Mapping[str, Any]],
        expand: Callable[[Mapping[str, Any]], Iterable[Mapping[str, Any]]],
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        actor: str = "system",
    ) -> list[dict[str, Any]]:
        """Bounded recursive intake; descriptors require kind/naturalKey/payload."""
        walked = bounded_candidate_walk(
            seeds,
            expand,
            identity=lambda row: candidate_id_for(
                str(row.get("kind") or ""),
                str(row.get("naturalKey") or ""),
            ),
            max_depth=max_depth,
            max_candidates=max_candidates,
        )
        output: list[dict[str, Any]] = []
        for descriptor, depth in walked:
            payload = dict(descriptor.get("payload") or {})
            payload.setdefault("discoveryDepth", depth)
            output.append(
                self.intake(
                    kind=str(descriptor.get("kind") or ""),
                    natural_key=str(descriptor.get("naturalKey") or ""),
                    payload=payload,
                    source_refs=descriptor.get("sourceRefs") or (),
                    mention_ids=descriptor.get("mentionIds") or (),
                    actor=actor,
                )
            )
        return output

    def review(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewer: str,
        decision_id: str,
        reason: str = "",
        reviewed_at: str | None = None,
    ) -> dict[str, Any]:
        """Apply a human decision and emit audit/backfill records."""
        reviewer_value = str(reviewer).strip()
        decision_id_value = str(decision_id).strip()
        if not reviewer_value:
            raise ValueError("reviewer is required for the human-review checkpoint")
        if not decision_id_value:
            raise ValueError("decision_id is required for an auditable human review")

        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(f"candidate not found: {candidate_id}")
        for prior in self._read_reviews(candidate_id):
            if prior.get("decisionId") == decision_id_value:
                return candidate

        previous_status = str(candidate.get("status") or "")
        target_status = transition_target(previous_status, str(decision).strip())
        timestamp = reviewed_at or self.now()
        review_record = {
            "schemaVersion": "quwoquan_data.governance_review/1",
            "decisionId": decision_id_value,
            "candidateId": candidate_id,
            "decision": str(decision).strip(),
            "reviewer": reviewer_value,
            "actorType": "human",
            "reason": str(reason).strip(),
            "fromStatus": previous_status,
            "toStatus": target_status,
            "reviewedAt": timestamp,
        }
        _append_ndjson(self.review_path(candidate_id), review_record)

        if target_status != previous_status:
            candidate["status"] = target_status
            candidate["updatedAt"] = timestamp
            candidate["version"] = int(candidate.get("version") or 1) + 1
            candidate["lastReview"] = {
                "decisionId": decision_id_value,
                "reviewer": reviewer_value,
                "reviewedAt": timestamp,
            }
            _atomic_write_json(self.candidate_path(candidate_id), candidate)

        self._audit(
            action="candidate.reviewed",
            candidate=candidate,
            actor=reviewer_value,
            occurred_at=timestamp,
            details=review_record,
        )
        if target_status == STATUS_PUBLISHED and previous_status != STATUS_PUBLISHED:
            self._emit_backfill(candidate, review_record)
        return candidate

    def _read_reviews(self, candidate_id: str) -> list[dict[str, Any]]:
        path = self.review_path(candidate_id)
        if not path.is_file():
            return []
        output: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                output.append(json.loads(line))
        return output

    def _audit(
        self,
        *,
        action: str,
        candidate: Mapping[str, Any],
        actor: str,
        occurred_at: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        event_identity = "\x1f".join(
            (
                str(candidate.get("candidateId") or ""),
                action,
                str(candidate.get("version") or ""),
                occurred_at,
            )
        )
        event_id = "audit_" + hashlib.sha256(event_identity.encode("utf-8")).hexdigest()[:24]
        row: dict[str, Any] = {
            "schemaVersion": "quwoquan_data.governance_audit/1",
            "auditId": event_id,
            "candidateId": candidate.get("candidateId"),
            "action": action,
            "actor": actor,
            "occurredAt": occurred_at,
            "status": candidate.get("status"),
            "version": candidate.get("version"),
        }
        if details:
            row["details"] = dict(details)
        _append_ndjson(self.audit_path, row)

    def _emit_backfill(
        self,
        candidate: Mapping[str, Any],
        review_record: Mapping[str, Any],
    ) -> None:
        identity = "\x1f".join(
            (
                str(candidate.get("candidateId") or ""),
                str(review_record.get("decisionId") or ""),
                str(candidate.get("version") or ""),
            )
        )
        event_id = "backfill_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        _append_ndjson(
            self.backfill_path,
            {
                "schemaVersion": "quwoquan_data.governance_backfill_event/1",
                "eventId": event_id,
                "eventType": "governance.candidate.backfill_requested",
                "candidateId": candidate.get("candidateId"),
                "candidateKind": candidate.get("kind"),
                "naturalKey": candidate.get("naturalKey"),
                "payload": candidate.get("payload") or {},
                "sourceRefs": candidate.get("sourceRefs") or [],
                "mentionIds": candidate.get("mentionIds") or [],
                "approvedBy": review_record.get("reviewer"),
                "approvedAt": review_record.get("reviewedAt"),
            },
        )


__all__ = ["CandidateRepository", "candidate_id_for"]
