# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-004.t2
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/design.md#dec-005
#
# 事实交集带 computedAt/expiresAt，过期触发重算：
# - 读面 rebuild-on-read 的物化收据按 (source_event_id, evidence digest) create-once，
#   evidence 不变时快照不会重写；
# - 当前快照存在过期 reason 时，读面把最早过期的 expiresAt 拼进 source_event_id，
#   projector 因此产生新收据并真正重物化；
# - 同一份过期快照重物化前得到同一标记（幂等），无过期时保持纯 evidence digest 路径。
from __future__ import annotations

from datetime import datetime, timezone

from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    ObjectIntersectionSnapshot,
    Reader,
    SubjectIntersectionSnapshot,
)


class _OpenSubjects:
    def exists(self, subject_id: str) -> bool:
        return False


class _RecordingMaterializer:
    def __init__(self) -> None:
        self.subject_calls: list[dict[str, object]] = []
        self.object_calls: list[dict[str, object]] = []

    def rebuild_subject(self, **kwargs) -> tuple[bool, bool]:
        self.subject_calls.append(kwargs)
        return True, True

    def rebuild_object(self, **kwargs) -> bool:
        self.object_calls.append(kwargs)
        return True


class _Store:
    def __init__(self, reasons) -> None:
        self.reasons = tuple(reasons)
        self.generated_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def subject_intersection_evidence_digest(self, subject_id: str) -> str:
        return "digest-subject"

    def object_intersection_evidence_digest(self, subject_id: str, object_type: str, object_id: str) -> str:
        return "digest-object"

    def read_subject_intersections(self, subject_id, intersection_class, channel):
        return SubjectIntersectionSnapshot(
            subject_id=subject_id,
            intersection_class=intersection_class,
            channel=channel,
            reasons=self.reasons,
            generated_at=self.generated_at,
        )

    def read_object_intersections(self, subject_id, object_type, object_id):
        return ObjectIntersectionSnapshot(
            subject_id=subject_id,
            object_type=object_type,
            object_id=object_id,
            reasons=self.reasons,
            generated_at=self.generated_at,
        )


def _reason(expires_at: str) -> dict[str, object]:
    return {
        "intersectionId": f"ix:{expires_at}",
        "intersectionClass": "fact",
        "computedAt": "2026-08-01T00:00:00Z",
        "expiresAt": expires_at,
    }


_NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_snapshot_keeps_evidence_digest_receipt() -> None:
    materializer = _RecordingMaterializer()
    store = _Store([_reason("2026-09-30T00:00:00Z")])
    reader = Reader(store, materializer, _OpenSubjects(), now=lambda: _NOW)

    reader.list_subject_intersections(subject_id="viewer", intersection_class="fact", channel=None)
    reader.list_object_intersections(subject_id="viewer", object_type="user", object_id="peer")

    assert materializer.subject_calls[0]["source_event_id"] == "intersection-subject-evidence:digest-subject"
    assert materializer.object_calls[0]["source_event_id"] == "intersection-object-evidence:digest-object"


def test_expired_reason_forces_a_new_materialization_receipt_deterministically() -> None:
    materializer = _RecordingMaterializer()
    store = _Store(
        [
            _reason("2026-09-30T00:00:00Z"),
            _reason("2026-09-01T00:00:00Z"),
            _reason("2026-08-15T00:00:00Z"),
        ]
    )
    reader = Reader(store, materializer, _OpenSubjects(), now=lambda: _NOW)

    reader.list_subject_intersections(subject_id="viewer", intersection_class="fact", channel=None)
    reader.list_subject_intersections(subject_id="viewer", intersection_class="fact", channel=None)
    reader.list_object_intersections(subject_id="viewer", object_type="user", object_id="peer")

    expected_subject = "intersection-subject-evidence:digest-subject:refresh:2026-08-15T00:00:00Z"
    assert [call["source_event_id"] for call in materializer.subject_calls] == [expected_subject, expected_subject]
    assert materializer.subject_calls[0]["source_event_digest"] == "digest-subject"
    assert (
        materializer.object_calls[0]["source_event_id"]
        == "intersection-object-evidence:digest-object:refresh:2026-08-15T00:00:00Z"
    )


def test_expiry_marker_ignores_unparseable_or_missing_expires_at() -> None:
    materializer = _RecordingMaterializer()
    store = _Store([_reason(""), _reason("not-a-timestamp"), {"intersectionId": "ix:none"}])
    reader = Reader(store, materializer, _OpenSubjects(), now=lambda: _NOW)

    reader.list_subject_intersections(subject_id="viewer", intersection_class="fact", channel=None)

    assert materializer.subject_calls[0]["source_event_id"] == "intersection-subject-evidence:digest-subject"


class _FirstReadStore(_Store):
    """首读：投影尚未物化，窥视抛 RuntimeError；物化后才可读。"""

    def __init__(self) -> None:
        super().__init__([_reason("2026-09-30T00:00:00Z")])
        self.subject_materialized = False
        self.object_materialized = False

    def read_subject_intersections(self, subject_id, intersection_class, channel):
        if not self.subject_materialized:
            self.subject_materialized = True
            raise RuntimeError("subject intersection projection is unavailable")
        return super().read_subject_intersections(subject_id, intersection_class, channel)

    def read_object_intersections(self, subject_id, object_type, object_id):
        if not self.object_materialized:
            self.object_materialized = True
            raise RuntimeError("object intersection projection is unavailable")
        return super().read_object_intersections(subject_id, object_type, object_id)


def test_first_read_materializes_without_expiry_marker() -> None:
    materializer = _RecordingMaterializer()
    reader = Reader(_FirstReadStore(), materializer, _OpenSubjects(), now=lambda: _NOW)

    subject = reader.list_subject_intersections(subject_id="viewer", intersection_class="fact", channel=None)
    obj = reader.list_object_intersections(subject_id="viewer", object_type="user", object_id="peer")

    assert materializer.subject_calls[0]["source_event_id"] == "intersection-subject-evidence:digest-subject"
    assert materializer.object_calls[0]["source_event_id"] == "intersection-object-evidence:digest-object"
    assert len(subject.reasons) == 1 and len(obj.reasons) == 1
