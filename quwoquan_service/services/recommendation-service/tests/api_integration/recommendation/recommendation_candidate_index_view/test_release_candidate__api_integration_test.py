"""隔离Mongo/Redis，producer为生成typed fixture，非Content联合CAS证据。"""
from datetime import datetime, timedelta, timezone
import json
import pytest
from generated.recommendation.recommendation_candidate_index_view.events.content_post_PostReleaseCandidatePrepared import PostReleaseCandidatePrepared
from generated.recommendation.recommendation_candidate_index_view.events.ops_premium_pool_entry_PremiumPoolEntryUpserted import PremiumPoolEntry
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import digest, canonical, ReleaseNotReady, ReleaseCandidateError
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import MongoCandidateIndexStore
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import PostLifecycleConsumer, PREPARED_STREAM, CONSUMER_GROUP
from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis

D = "sha256:" + "a" * 64


def prepared(release_id="A"):
    release = dict(environment="gamma", sourceOwner="qwq_data", releaseId=release_id, manifestDigest=D)
    binding = dict(release=release, slice="recommendation", providerBindingGeneration=D, schemaGeneration=D)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    post = dict(identity=dict(release=release, objectType="content.post", objectId="p", sourceVersion=1, sourceDigest=D), postRef="ref", authorId="author", authorDisplayName="Author", authorAvatarUrl=None, contentType="video", status="published", visibility="public", moderationStatus="approved", title="title", body="", summary="", tagRefs=[], entityRefs=[], primaryHomepage=None, mediaAssetIds=["asset"], mediaUrls=["https://media.invalid/video"], coverUrl=None, thumbnailUrl=None, videoUrl="https://media.invalid/video", durationMs=1000, width=10, height=10, contentVertical=None, publishedAt=now, updatedAt=now, deepLink="/content/p", documentDigest="")
    post["documentDigest"] = digest(post, "documentDigest")
    snapshot = dict(release=release, sourceClosureDigest=D, mediaClosureDigest=D, objectSetDigest=digest([dict(objectType="content.post", objectId="p")]), snapshotDigest="", posts=[post])
    snapshot["snapshotDigest"] = digest(snapshot, "snapshotDigest")
    return PostReleaseCandidatePrepared(publicationId=digest(dict(binding=binding, snapshotDigest=snapshot["snapshotDigest"])), binding=binding, snapshot=snapshot, sourceVersion=1, occurredAt=now)


def premium(event, revision=1, status="active"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    a = dict(source=canonical(event.snapshot.posts[0].identity), admissionRevision=revision, auditId="audit", qualityScore=.9, status=status, qualityAdmission="approved", scope="global", expiresAt=now + timedelta(hours=1), admissionDigest="")
    a["admissionDigest"] = digest(a, "admissionDigest")
    return PremiumPoolEntry(contentId="p", releaseAdmissions=[a], scope="global", status=status, qualityScore=.9, qualityAdmission="approved", supplySource="qwq_data", sourceTaskId=None, auditId="audit", rollbackToken="rollback", featuredAt=now, expiresAt=now + timedelta(hours=1), takedownEjected=status == "takedown_ejected", revision=revision, updatedAt=now)


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
def test_candidate_transaction_replay_readiness_and_retained_release(mongo_database, real_redis):
    a, b = prepared(), prepared("B")
    store = MongoCandidateIndexStore(mongo_database, release_runtime_binding=lambda release: {**canonical(a.binding), "release": canonical(release)})
    # composition返回正式typed binding，不是caller授权事实。
    store.ensure_indexes()
    from internal.recommendation.recommendation_candidate_index_view.infrastructure.runtime_binding import compose_release_binding
    rows = []
    for name in ("recommendation_release_source_checkpoints", "rm_release_discovery_candidates", "rm_release_premium_candidates"):
        for index in mongo_database[name].list_indexes():
            if index["name"].startswith("uq_rec_release_"):
                rows.append({"collection": name, "name": index["name"], "keys": dict(index["key"]), "unique": bool(index.get("unique", False))})
    generation = digest(sorted(rows, key=lambda r: r["name"]))
    for event in (a, b):
        event.binding.schemaGeneration = generation
        event.publicationId = digest({"binding": event.binding, "snapshotDigest": event.snapshot.snapshotDigest})
    store._release_runtime_binding = compose_release_binding(mongo_database, {"release_candidate": {"binding_digest": D, "mongodb_namespace": mongo_database.name, "schema_generation": generation}}, environment="gamma", environ={})
    class Closures:
        def exists(self, _): return False
    consumer = PostLifecycleConsumer(redis_client=real_redis, projection=store, subject_closures=Closures(), consumer="test")
    real_redis.xadd(PREPARED_STREAM, {"eventType": "PostReleaseCandidatePrepared", "aggregateType": "Post", "eventId": a.publicationId, "aggregateId": a.publicationId, "aggregateVersion": 1, "payload": json.dumps(canonical(a))})
    assert consumer.process_once() == 1
    assert real_redis.xpending(PREPARED_STREAM, CONSUMER_GROUP)["pending"] == 0
    assert not store.apply_release_candidate(a)
    with pytest.raises(ReleaseNotReady): store.read_release_readiness(a.binding, a.snapshot.snapshotDigest)
    assert store.apply_release_premium("approval-a", premium(a))
    before = {n: mongo_database[n].count_documents({}) for n in mongo_database.list_collection_names()}
    source, home, premium_posts = store.read_release_supply_projection(a.binding, a.snapshot.snapshotDigest)
    assert source.snapshot.snapshotDigest == a.snapshot.snapshotDigest
    assert [post.identity.objectId for post in home] == ["p"]
    assert [post.identity.objectId for post in premium_posts] == ["p"]
    with pytest.raises(ReleaseNotReady, match="safety authority or proof-time policy unavailable"):
        store.read_release_readiness(a.binding, a.snapshot.snapshotDigest)
    # 同生产service verifier；HTTP仍为测试组合，不宣称Content发布联合已通过。
    from tests.support.service_token import configure_test_auth_environment, service_token
    configure_test_auth_environment()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from security.service_authorization import ServiceTokenVerifier
    from internal.recommendation.ranked_recommendation_window.adapters.inbound.http.router import build_router
    class QueryFacade:
        def read_release_readiness(self, query):
            return store.read_release_readiness(query.binding, query.snapshotDigest)
    app = FastAPI()
    app.include_router(build_router(facade_provider=lambda _: QueryFacade(), token_verifier=ServiceTokenVerifier.from_env()))
    with TestClient(app) as client:
        body = {"binding": canonical(a.binding), "snapshotDigest": a.snapshot.snapshotDigest}
        token = service_token(scopes=["recommendation.release.readiness"])
        response = client.post("/internal/recommendation/release-readiness:query", json=body, headers={"Authorization": "Bearer " + token})
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "RECOMMENDATION.RELEASE.not_ready"
        assert client.post("/internal/recommendation/release-readiness:query", json=body).status_code == 401
    assert before == {n: mongo_database[n].count_documents({}) for n in before}
    assert store.apply_release_candidate(b)
    assert store.read_release_source(a.binding).snapshot.snapshotDigest == a.snapshot.snapshotDigest
    with pytest.raises(ReleaseNotReady):
        store.read_release_readiness(a.binding, a.snapshot.snapshotDigest)
    with pytest.raises(ReleaseNotReady): store.read_release_readiness(b.binding, b.snapshot.snapshotDigest)
    both = premium(b, 2)
    both.releaseAdmissions.insert(0, premium(a).releaseAdmissions[0])
    assert store.apply_release_premium("approval-b", both)
    _, home_b, premium_b = store.read_release_supply_projection(b.binding, b.snapshot.snapshotDigest)
    assert [post.identity.objectId for post in home_b] == ["p"]
    assert [post.identity.objectId for post in premium_b] == ["p"]
    with pytest.raises(ReleaseNotReady):
        store.read_release_readiness(b.binding, b.snapshot.snapshotDigest)
    from generated.recommendation.ranked_recommendation_window.models.request_response import ReleasePinnedQueryFence
    fence = ReleasePinnedQueryFence(release=canonical(b.binding.release), revision=2)
    with pytest.raises(ReleaseNotReady, match="safety authority or proof-time policy unavailable"):
        store.list_release_for_ranking(fence, scenario="premium_stream", subject_id="viewer", limit=20)
    revoked = premium(b, 3, "rolled_back")
    revoked.releaseAdmissions.insert(0, premium(a, 3, "rolled_back").releaseAdmissions[0])
    assert store.apply_release_premium("withdraw-b", revoked)
    with pytest.raises(ReleaseNotReady): store.read_release_readiness(b.binding, b.snapshot.snapshotDigest)
    # 专项损坏注入只用于证明query不能掩盖缺对象。
    mongo_database.rm_release_discovery_candidates.delete_one({"sourcePartition": digest(a.binding)})
    with pytest.raises(ReleaseNotReady): store.read_release_readiness(a.binding, a.snapshot.snapshotDigest)
    mongo_database.rm_release_premium_candidates.drop_index("uq_rec_release_premium")
    with pytest.raises(ReleaseNotReady): store._release_runtime_binding(a.binding.release)


def test_preparation_rejects_changed_source_without_partial_write(mongo_database):
    event = prepared()
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    assert store.apply_release_candidate(event)
    changed = event.model_copy(deep=True)
    changed.sourceVersion = 2
    with pytest.raises(ReleaseCandidateError): store.apply_release_candidate(changed)
    assert mongo_database.rm_release_discovery_candidates.count_documents({}) == 1
