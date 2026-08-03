from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.tag_feedback_consumer import (
    CONSUMER_GROUP,
    TAG_FEEDBACK_DLQ,
    TAG_FEEDBACK_STREAM,
    TagFeedbackConsumer,
)


def _fields(*, action: str = "dislike") -> dict[bytes, bytes]:
    values = {
        "eventName": "TagFeedbackRecorded",
        "eventId": "feedback-001",
        "id": "feedback-001",
        "actorId": "persona-001",
        "actorKind": "persona",
        "tagRef": "Topic/旅行",
        "action": action,
        "recordedAt": "2026-08-02T12:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self) -> None:
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []
        self.trimmed = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields())], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(TAG_FEEDBACK_STREAM.encode(), [(b"1000-0", _fields())])]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, stream, **kwargs):
        self.trimmed.append((stream, kwargs))

    def expire(self, *_args):
        return True


class _Store:
    def __init__(self) -> None:
        self.attempts = 0
        self.cleared = []

    def record_source_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


class _Projector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def project_tag_feedback(self, **event):
        if self.fail:
            raise RuntimeError("tag feature projection failed")
        self.events.append(event)
        return True


class _Closures:
    def exists(self, _subject_id: str) -> bool:
        return False


def test_consumer_projects_typed_tag_feedback_before_ack() -> None:
    redis = _Redis()
    store = _Store()
    projector = _Projector()
    consumer = TagFeedbackConsumer(
        redis_client=redis,
        feature_store=store,
        feature_projector=projector,
        subject_closures=_Closures(),
        consumer="tag-feedback-test",
    )
    assert consumer.process_once() == 1
    assert projector.events[0]["action"] == "dislike"
    assert projector.events[0]["tag_ref"] == "Topic/旅行"
    assert redis.acked == [(TAG_FEEDBACK_STREAM, CONSUMER_GROUP, "1000-0")]
    assert store.cleared == ["1000-0"]


def test_consumer_dead_letters_only_after_fifth_projection_failure() -> None:
    redis = _Redis()
    store = _Store()
    consumer = TagFeedbackConsumer(
        redis_client=redis,
        feature_store=store,
        feature_projector=_Projector(fail=True),
        subject_closures=_Closures(),
        consumer="tag-feedback-test",
    )
    for attempt in range(1, 6):
        if attempt < 5:
            try:
                consumer.process_once()
            except RuntimeError as error:
                assert "projection failed" in str(error)
            else:
                raise AssertionError("projection failure was not propagated")
            assert redis.acked == []
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == TAG_FEEDBACK_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(TAG_FEEDBACK_STREAM, CONSUMER_GROUP, "1000-0")]
    assert redis.trimmed[0][0] == TAG_FEEDBACK_DLQ
