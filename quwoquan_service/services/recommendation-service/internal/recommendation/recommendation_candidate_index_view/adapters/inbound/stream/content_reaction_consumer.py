from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from .persona_relationship_consumer import PersonaRelationshipConsumer, _text, _values

STREAM = "events.content.reaction_lifecycle"
GROUP = "recommendation-candidate-content-reaction"


class ContentReactionConsumer(PersonaRelationshipConsumer):
    def __init__(self, *, redis_client, projection, consumer: str, intersection_materializer=None) -> None:
        super().__init__(redis_client=redis_client, projection=projection, consumer=consumer)
        self._intersection_materializer = intersection_materializer

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(STREAM, GROUP, id="0-0", mkstream=True)
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    def _claimed(self):
        result = self._redis.xautoclaim(
            STREAM,
            GROUP,
            self._consumer,
            min_idle_time=30_000,
            start_id="0-0",
            count=50,
        )
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        return [(_text(stream_id), _values(values)) for stream_id, values in entries]

    def _new(self):
        return self._messages(
            self._redis.xreadgroup(
                GROUP, self._consumer, {STREAM: ">"}, count=50
            )
        )

    @staticmethod
    def _decode(values: dict[str, str]) -> dict:
        envelope_fields = (
            "eventId",
            "eventType",
            "partitionId",
            "partitionSequence",
            "aggregateId",
            "aggregateVersion",
            "payload",
            "occurredAt",
        )
        if any(not values.get(field, "").strip() for field in envelope_fields):
            raise ValueError("content reaction event envelope is incomplete")
        payload = json.loads(values["payload"])
        if not isinstance(payload, dict):
            raise ValueError("content reaction payload must be an object")
        payload_fields = (
            "reactionId",
            "targetKind",
            "targetId",
            "actorDimension",
            "actorId",
            "reaction",
            "version",
            "occurredAt",
        )
        if any(str(payload.get(field) or "").strip() == "" for field in payload_fields):
            raise ValueError("content reaction payload is incomplete")
        if (
            str(payload["reactionId"]).strip() != values["aggregateId"].strip()
            or int(payload["version"]) != int(values["aggregateVersion"])
        ):
            raise ValueError("content reaction envelope does not match payload")
        return payload

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        payload = self._decode(values)
        event_digest = hashlib.sha256(
            json.dumps(
                {"envelope": values, "payload": payload},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        occurred_at = datetime.fromisoformat(
            str(payload["occurredAt"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        actor_id = str(payload["actorId"]).strip()
        target_id = str(payload["targetId"]).strip()
        peers_before = set(self._projection.current_like_actors_for_target(target_id)) if self._intersection_materializer is not None and str(payload["actorDimension"]).strip() == "persona" else set()
        changed = self._projection.apply_content_reaction_event(
            event_id=values["eventId"].strip(),
            event_digest=event_digest,
            reaction_id=str(payload["reactionId"]).strip(),
            target_kind=str(payload["targetKind"]).strip(),
            target_id=target_id,
            actor_dimension=str(payload["actorDimension"]).strip(),
            actor_id=actor_id,
            reaction=str(payload["reaction"]).strip(),
            version=int(payload["version"]),
            partition_id=int(values["partitionId"]),
            partition_sequence=int(values["partitionSequence"]),
            occurred_at=occurred_at,
        )
        if changed and self._intersection_materializer is not None and str(payload["actorDimension"]).strip() == "persona":
            peers = peers_before.union(self._projection.current_like_actors_for_target(target_id))
            peers.discard(actor_id)
            for peer_id in sorted(peers):
                for subject_id, object_id in ((actor_id, peer_id), (peer_id, actor_id)):
                    pair_id = f"{values['eventId']}:{subject_id}:{object_id}"
                    self._intersection_materializer.rebuild_object(
                        source_event_id=pair_id,
                        source_event_digest=hashlib.sha256(pair_id.encode("utf-8")).hexdigest(),
                        subject_id=subject_id,
                        object_type="user",
                        object_id=object_id,
                    )
        self._redis.xack(STREAM, GROUP, stream_id)
