"""Gathering 候选源事件投影写入（``MongoCandidateIndexStore`` mixin）。

拆分自原 ``mongo_store.py``（行数治理）：gathering 候选 upsert/remove、
tombstone 与事件收件箱幂等（digest 去重 + 版本裁决）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..application.gathering_projector import (
    GatheringCandidateSnapshot,
    decide_gathering_projection,
    gathering_event_receipt_is_duplicate,
)


class MongoGatheringCandidateWriteOps:
    """Gathering 候选写操作；集合属性由组合根 ``__init__`` 装配。"""

    @staticmethod
    def _gathering_identity(gathering_id: str) -> str:
        return f"gathering\x1f{gathering_id.strip()}"

    def apply_gathering_source_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        snapshot: GatheringCandidateSnapshot | None = None,
        removal: tuple[str, int] | None = None,
    ) -> bool:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip().lower()
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or (snapshot is None) == (removal is None)
        ):
            raise ValueError("Gathering candidate source event is incomplete")
        gathering_id = (
            snapshot.gathering_id.strip() if snapshot is not None else removal[0].strip()
        )
        source_version = (
            snapshot.source_version if snapshot is not None else int(removal[1])
        )
        if not gathering_id or source_version <= 0:
            raise ValueError("Gathering candidate source identity is incomplete")
        identity = self._gathering_identity(gathering_id)

        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if gathering_event_receipt_is_duplicate(
                    recorded_event_digest=(
                        str(receipt.get("eventDigest")) if receipt is not None else None
                    ),
                    incoming_event_digest=normalized_digest,
                ):
                    return False

                current = self._gathering_candidates.find_one(
                    {"_id": identity},
                    session=session,
                )
                tombstone = self._tombstones.find_one(
                    {"_id": identity},
                    session=session,
                )
                current_version = int((current or {}).get("sourceVersion") or 0)
                tombstone_version = int((tombstone or {}).get("sourceVersion") or 0)
                changed = False
                decision = decide_gathering_projection(
                    current_version=current_version,
                    current_card_digest=(current or {}).get("cardDigest"),
                    tombstone_version=tombstone_version,
                    incoming_version=source_version,
                    incoming_card_digest=(
                        snapshot.card_digest if snapshot is not None else None
                    ),
                    removal=removal is not None,
                )
                stale = decision == "ignore"

                if snapshot is not None and decision == "upsert":
                    document = {
                            "_id": identity,
                            "objectKind": "gathering",
                            "sourceKey": gathering_id,
                            "sourceVersion": source_version,
                            "cardDigest": snapshot.card_digest,
                            "hostSubjectKind": snapshot.host_subject_kind.strip(),
                            "hostSubjectId": snapshot.host_subject_id.strip(),
                            "title": snapshot.title.strip(),
                            "summary": (
                                snapshot.summary.strip() if snapshot.summary else None
                            ),
                            "coverRef": (
                                {
                                    "objectTypeRef": snapshot.cover_object_type_ref,
                                    "objectId": snapshot.cover_object_id,
                                }
                                if snapshot.cover_object_id
                                else None
                            ),
                            "tagRefs": list(snapshot.tag_refs),
                            "startAt": (
                                snapshot.start_at.astimezone(timezone.utc)
                                if snapshot.start_at
                                else None
                            ),
                            "endAt": (
                                snapshot.end_at.astimezone(timezone.utc)
                                if snapshot.end_at
                                else None
                            ),
                            "dateLabel": snapshot.date_label,
                            "placeMode": snapshot.place_mode.strip(),
                            "coarsePlaceRef": (
                                {
                                    "objectTypeRef": (
                                        snapshot.coarse_place_object_type_ref
                                    ),
                                    "objectId": snapshot.coarse_place_object_id,
                                }
                                if snapshot.coarse_place_object_id
                                else None
                            ),
                            "coarsePlaceLabel": snapshot.coarse_place_label,
                            "maxParticipants": snapshot.max_participants,
                            "occupiedSeats": snapshot.occupied_seats,
                            "remainingSeats": snapshot.remaining_seats,
                            "full": snapshot.full,
                            "admissionState": snapshot.admission_state.strip(),
                            "lifecycleStatus": snapshot.lifecycle_status,
                            "updatedAt": snapshot.updated_at.astimezone(timezone.utc),
                    }
                    self._gathering_candidates.replace_one(
                        {"_id": identity},
                        document,
                        upsert=True,
                        session=session,
                    )
                    self._tombstones.delete_one(
                        {"_id": identity},
                        session=session,
                    )
                    changed = True
                elif removal is not None and decision == "remove":
                    card_digest = (current or {}).get("cardDigest")
                    self._tombstones.replace_one(
                        {"_id": identity},
                        {
                            "_id": identity,
                            "objectKind": "gathering",
                            "sourceKey": gathering_id,
                            "sourceVersion": source_version,
                            "cardDigest": card_digest,
                            "removedAt": datetime.now(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )
                    self._gathering_candidates.delete_one(
                        {"_id": identity},
                        session=session,
                    )
                    changed = True

                self._inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "source": "circle_gathering",
                        "sourceKey": gathering_id,
                        "sourceVersion": source_version,
                        "eventDigest": normalized_digest,
                        "changed": changed,
                        "stale": stale,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed
