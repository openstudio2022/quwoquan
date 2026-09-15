# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
import importlib
import json
import pytest

OWNERS = ["recommendation_candidate_index_view", "recommendation_feature_profile_view"]


def payload():
    cls = importlib.import_module("generated.recommendation.recommendation_candidate_index_view.events.content_post_PostPublished").PostLifecycleProjectionPayload
    wire = {}
    for name, field in cls.model_fields.items():
        if field.is_required():
            wire[name] = 1 if field.annotation is int else "2026-09-13T00:00:00Z" if name in {"createdAt", "updatedAt"} else "value"
    wire.update(postId="post", status="published", visibility="public", moderationStatus="approved", publishedAt="2026-09-13T00:00:00Z", visitedAt=None, sourceVersion=1)
    wire.update(dict.fromkeys(["environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest"]))
    return wire


def envelope(wire):
    return dict(eventId="event", eventType="PostPublished", aggregateType="Post", aggregateId="post", aggregateVersion="1", occurredAt="2026-09-13T00:00:00Z", payload=json.dumps(wire))


@pytest.mark.parametrize("owner", OWNERS)
def test_generated_post_wire_requires_presence_version_and_timestamps(owner):
    decoder = importlib.import_module(f"internal.recommendation.{owner}.adapters.inbound.stream.post_lifecycle_consumer").decode_post_lifecycle
    wire = payload()
    assert decoder(envelope(wire)) is not None
    for field in ["sourceOwner", "environment", "releaseId", "manifestDigest", "releaseDigest", "sourceVersion", "safetyRevision", "publishedAt"]:
        bad = wire.copy(); bad.pop(field)
        with pytest.raises(ValueError): decoder(envelope(bad))
    for patch in [{"unexpected": 1}, {"sourceVersion": 2}, {"sourceOwner": ""}, {"publishedAt": None}, {"visitedAt": ""}, {"sourceVersion": True}]:
        with pytest.raises(ValueError): decoder(envelope({**wire, **patch}))
    bad = envelope(wire); bad["eventType"] = "UnknownPostEvent"
    with pytest.raises(ValueError): decoder(bad)
    bad["eventType"] = "ContentReleaseFenceChanged"
    with pytest.raises(ValueError): decoder(bad)
