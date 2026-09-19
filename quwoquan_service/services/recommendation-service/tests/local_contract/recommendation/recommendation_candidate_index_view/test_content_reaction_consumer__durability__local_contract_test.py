import json

import pytest

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.content_reaction_consumer import ContentReactionConsumer, GROUP, STREAM


def _fields(sequence="1"):
    payload={"reactionId":"reaction-1","version":1,"targetKind":"post","targetId":"post-1","actorDimension":"persona","actorId":"persona-1","reaction":"like","occurredAt":"2026-08-05T08:00:00Z","idempotencyKey":"key-1"}
    return {key.encode():str(value).encode() for key,value in {"eventId":"reaction:reaction-1:1","eventType":"ContentReactionSet","partitionKey":"reaction-1","partitionId":"2","partitionSequence":sequence,"aggregateType":"ContentReaction","aggregateId":"reaction-1","aggregateVersion":"1","payload":json.dumps(payload,separators=(",",":")),"occurredAt":"2026-08-05T08:00:00Z"}.items()}

class _Redis:
    def __init__(self):self.deliver=True;self.acked=[]
    def xgroup_create(self,*args,**kwargs):return True
    def xautoclaim(self,*args,**kwargs):return ("0-0",[],[])
    def xreadgroup(self,*args,**kwargs):
        if not self.deliver:return []
        self.deliver=False;return [(STREAM.encode(),[(b"1-0",_fields())])]
    def xack(self,*args):self.acked.append(args)

class _Projection:
    def __init__(self,fail=False):self.events=[];self.fail=fail
    def apply_content_reaction_event(self,**event):
        if self.fail:raise RuntimeError("poison")
        self.events.append(event);return True

def test_reaction_event_projects_nested_payload_before_ack():
    redis=_Redis();projection=_Projection();consumer=ContentReactionConsumer(redis_client=redis,projection=projection,consumer="test")
    assert consumer.process_once()==1
    assert projection.events[0]["target_id"]=="post-1"
    assert projection.events[0]["partition_sequence"]==1
    assert redis.acked==[(STREAM,GROUP,"1-0")]

def test_reaction_poison_stays_pending_without_ack():
    redis=_Redis();consumer=ContentReactionConsumer(redis_client=redis,projection=_Projection(fail=True),consumer="test")
    with pytest.raises(RuntimeError,match="poison"):consumer.process_once()
    assert redis.acked==[]

class _Materializer:
    def __init__(self): self.calls=[]
    def rebuild_object(self,**call): self.calls.append(call);return True

class _FanoutProjection(_Projection):
    def __init__(self): super().__init__();self.actors={"persona-2"}
    def current_like_actors_for_target(self,target_id): return tuple(sorted(self.actors))
    def apply_content_reaction_event(self,**event):
        self.events.append(event);self.actors.add(event["actor_id"]);return True

def test_reaction_change_rebuilds_coliked_for_both_persona_directions_before_ack():
    redis=_Redis();projection=_FanoutProjection();materializer=_Materializer()
    consumer=ContentReactionConsumer(redis_client=redis,projection=projection,consumer="test",intersection_materializer=materializer)
    assert consumer.process_once()==1
    assert {(call["subject_id"],call["object_id"]) for call in materializer.calls}=={("persona-1","persona-2"),("persona-2","persona-1")}
    assert redis.acked==[(STREAM,GROUP,"1-0")]
