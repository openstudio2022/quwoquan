"""真实ProductOps HTTP/PG/outbox/Redis publisher→Rec consumer/Mongo/readiness。
Content source为Go typed HTTP fixture；Post准备输入由同fixture的完整snapshot派生，非环境CAS。
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import time
import httpx
import pytest
from redis import Redis
from generated.recommendation.recommendation_candidate_index_view.events.content_post_PostReleaseCandidatePrepared import PostReleaseCandidatePrepared
from generated.recommendation.ranked_recommendation_window.models.request_response import ReleasePinnedQueryFence
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import canonical, digest, ReleaseNotReady
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import MongoCandidateIndexStore
from internal.recommendation.recommendation_candidate_index_view.infrastructure.runtime_binding import compose_release_binding
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import PostLifecycleConsumer, PREPARED_STREAM
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.premium_pool_consumer import PremiumPoolConsumer, PREMIUM_POOL_STREAM
from tests.support.recommendation_mongo import mongo_client, mongo_database


@pytest.fixture
def joint_owner(tmp_path):
    binary = shutil.which("redis-server")
    assert binary, "real redis-server required"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    redis_process = subprocess.Popen([binary, "--bind", "127.0.0.1", "--port", str(port), "--save", "", "--appendonly", "no"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    redis = Redis(host="127.0.0.1", port=port, decode_responses=False)
    root = Path(__file__).resolve().parents[7]
    env = dict(os.environ)
    for key in ("QWQ_TEST_POSTGRES_DSN", "TEST_PG_DSN"): env.pop(key, None)
    env["QWQ_JOINT_REDIS_ADDR"] = f"127.0.0.1:{port}"
    process = None
    try:
        for _ in range(100):
            try:
                if redis.ping(): break
            except Exception: time.sleep(.02)
        process = subprocess.Popen(["go", "test", "./services/product-ops-service/tests/api_integration/product_ops/premium_pool_entry", "-run", "^TestJointPremiumRelayHarness$", "-count=1", "-v"], cwd=root / "quwoquan_service", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + 120
        logs = []
        while time.monotonic() < deadline:
            if selector.select(.2):
                line = process.stdout.readline()
                if line.startswith("JOINT_READY "):
                    owner = json.loads(line.removeprefix("JOINT_READY ")); break
                logs.append(line)
            if process.poll() is not None: pytest.fail("joint owner startup failed: " + "".join(logs))
        else: pytest.fail("joint owner readiness timeout")
        with httpx.Client(base_url=owner["url"], timeout=15) as client:
            yield client, owner, redis
            client.post("/fixture/done")
        output, _ = process.communicate(timeout=30)
        assert process.returncode == 0, output
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        redis.close(); redis_process.terminate(); redis_process.wait(timeout=5)


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
def test_real_approval_relay_candidate_query_and_revocation(joint_owner, mongo_database):
    client, owner, redis = joint_owner
    snapshots = client.get("/fixture/snapshots").json()
    store = MongoCandidateIndexStore(mongo_database); store.ensure_indexes()
    rows = []
    for name in ("recommendation_release_source_checkpoints", "rm_release_discovery_candidates", "rm_release_premium_candidates"):
        for index in mongo_database[name].list_indexes():
            if index["name"].startswith("uq_rec_release_"): rows.append({"collection": name, "name": index["name"], "keys": dict(index["key"]), "unique": bool(index.get("unique", False))})
    schema = digest(sorted(rows, key=lambda r: r["name"]))
    generation = "sha256:" + "a" * 64
    store._release_runtime_binding = compose_release_binding(mongo_database, {"release_candidate": {"binding_digest": generation, "mongodb_namespace": mongo_database.name, "schema_generation": schema}}, environment="gamma", environ={})
    class Closures:
        def exists(self, _): return False
    posts = PostLifecycleConsumer(redis_client=redis, projection=store, subject_closures=Closures(), consumer="joint-posts")
    premium = PremiumPoolConsumer(redis_client=redis, store=store, consumer="joint-premium")
    events = {}
    for name, snapshot in snapshots.items():
        binding = {"release": snapshot["release"], "slice": "recommendation", "providerBindingGeneration": generation, "schemaGeneration": schema}
        event = PostReleaseCandidatePrepared(publicationId=digest({"binding": binding, "snapshotDigest": snapshot["snapshotDigest"]}), binding=binding, snapshot=snapshot, sourceVersion=1, occurredAt=datetime.now(timezone.utc).replace(microsecond=0))
        events[name] = event
        redis.xadd(PREPARED_STREAM, {"eventType": "PostReleaseCandidatePrepared", "aggregateType": "Post", "eventId": event.publicationId, "aggregateId": event.publicationId, "aggregateVersion": 1, "payload": json.dumps(canonical(event))})
    assert posts.process_once() == 2
    def ready(name):
        e = events[name]; return store.read_release_readiness(e.binding, e.snapshot.snapshotDigest)
    def command(name, key, actor="operatorA", expires=None):
        return client.post("/control-plane/product/recommendation/premium-pool", headers={"Authorization": "Bearer " + owner[actor], "Idempotency-Key": key}, json={"contentId": "p", "scope": "global", "qualityScore": .9, "qualityAdmission": "approved", "supplySource": "qwq_data", "auditId": "joint-audit", "expiresAt": expires or (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "releaseSource": snapshots[name]["posts"][0]["identity"]})
    with pytest.raises(ReleaseNotReady): ready("A")
    assert command("A", "wrong", "wrongScope").status_code == 403
    assert client.post("/control-plane/product/recommendation/premium-pool", json={}, headers={"Authorization": "Bearer tampered", "Idempotency-Key": "bad-signer"}).status_code == 403
    created = command("A", "approve-A"); assert created.status_code == 200, created.text
    assert premium.process_once() == 1
    _, home_a, premium_a = store.read_release_supply_projection(events["A"].binding, events["A"].snapshot.snapshotDigest)
    assert [post.identity.objectId for post in home_a] == ["p"]
    assert [post.identity.objectId for post in premium_a] == ["p"]
    with pytest.raises(ReleaseNotReady): ready("A")
    with pytest.raises(ReleaseNotReady): ready("B")
    before = redis.xlen(PREMIUM_POOL_STREAM)
    # 同一意图重放必须使用完全相同body；这里重放实际第一次请求字节。
    replay = client.post(created.request.url, content=created.request.content, headers=dict(created.request.headers))
    assert replay.status_code == 200
    assert redis.xlen(PREMIUM_POOL_STREAM) == before
    auth_headers = {"Authorization": "Bearer " + owner["operatorA"]}
    stats_before = client.get("/fixture/stats", headers=auth_headers).json()
    assert client.post("/fixture/fail-audit", headers=auth_headers).status_code == 204
    failed = command("B", "failed-B")
    assert failed.status_code >= 400
    assert client.get("/fixture/stats", headers=auth_headers).json() == stats_before
    assert redis.xlen(PREMIUM_POOL_STREAM) == before
    assert client.post("/fixture/recover-audit", headers=auth_headers).status_code == 204
    approved_b = command("B", "approve-B"); assert approved_b.status_code == 200, approved_b.text
    assert premium.process_once() == 1
    for name in ("A", "B"):
        source, home, premium_posts = store.read_release_supply_projection(events[name].binding, events[name].snapshot.snapshotDigest)
        assert source.snapshot.snapshotDigest == events[name].snapshot.snapshotDigest
        assert [post.identity.objectId for post in home] == ["p"]
        assert [post.identity.objectId for post in premium_posts] == ["p"]
        with pytest.raises(ReleaseNotReady): ready(name)
    counts = {n: mongo_database[n].count_documents({}) for n in mongo_database.list_collection_names()}
    assert counts == {n: mongo_database[n].count_documents({}) for n in counts}
    # 证明来自真实数据，再通过现役HTTP wire而非散文比对。
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.support.service_token import configure_test_auth_environment, service_token
    configure_test_auth_environment()
    from security.service_authorization import ServiceTokenVerifier
    from internal.recommendation.ranked_recommendation_window.adapters.inbound.http.router import build_router
    from internal.recommendation.ranked_recommendation_window.application.facade import Facade
    class Unused:
        def __getattr__(self, name): raise AssertionError("readiness must not access " + name)
    facade = Facade(store=Unused(), ranker=Unused(), subject_closures=Unused(), exclusion_profiles=Unused(), release_readiness=store)
    api = FastAPI(); api.include_router(build_router(facade_provider=lambda _: facade, token_verifier=ServiceTokenVerifier.from_env()))
    with TestClient(api) as query_client:
        query_body = {"binding": canonical(events["B"].binding), "snapshotDigest": events["B"].snapshot.snapshotDigest}
        header = {"Authorization": "Bearer " + service_token(scopes=["recommendation.release.readiness"])}
        response = query_client.post("/internal/recommendation/release-readiness:query", json=query_body, headers=header)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "RECOMMENDATION.RELEASE.not_ready"
        assert query_client.post("/internal/recommendation/release-readiness:query", json=query_body, headers={"Authorization": "Bearer " + service_token(scopes=["recommendation.ranked_page"])}).status_code == 403
        assert counts == {n: mongo_database[n].count_documents({}) for n in counts}
    # 真实relay消息重投，非伪造审批：复用Redis里已签发的原envelope。
    envelope = redis.xrange(PREMIUM_POOL_STREAM)[-1][1]; redis.xadd(PREMIUM_POOL_STREAM, envelope)
    assert premium.process_once() == 1
    assert counts == {n: mongo_database[n].count_documents({}) for n in counts}
    rollback = client.post("/control-plane/product/recommendation/premium-pool/p:rollback", json={}, headers={**auth_headers, "Idempotency-Key": "rollback"})
    assert rollback.status_code == 200, rollback.text
    assert premium.process_once() == 1
    with pytest.raises(ReleaseNotReady): ready("A")
    with pytest.raises(ReleaseNotReady): ready("B")
    assert command("A", "restore-A").status_code == 200
    assert command("B", "restore-B").status_code == 200
    assert premium.process_once() == 2
    for name in ("A", "B"):
        _, _, premium_posts = store.read_release_supply_projection(events[name].binding, events[name].snapshot.snapshotDigest)
        assert [post.identity.objectId for post in premium_posts] == ["p"]
        with pytest.raises(ReleaseNotReady): ready(name)
    # 只读注入clock推进，不修改真实签发/持久化的审批字节。
    with pytest.raises(ReleaseNotReady):
        store.read_release_readiness(events["A"].binding, events["A"].snapshot.snapshotDigest, now=datetime.now(timezone.utc) + timedelta(hours=2))
    path = "/control-plane/product/recommendation/premium-pool/p:takedown"
    one = client.post(path, json={}, headers={"Authorization": "Bearer " + owner["operatorA"], "Idempotency-Key": "take-a"})
    assert one.status_code in (200, 202), one.text
    _, _, premium_a = store.read_release_supply_projection(events["A"].binding, events["A"].snapshot.snapshotDigest)
    assert [post.identity.objectId for post in premium_a] == ["p"]
    with pytest.raises(ReleaseNotReady): ready("A")
    two = client.post(path, json={}, headers={"Authorization": "Bearer " + owner["operatorB"], "Idempotency-Key": "take-b"})
    assert two.status_code == 200, two.text
    assert premium.process_once() == 1
    with pytest.raises(ReleaseNotReady): ready("A")
    with pytest.raises(ReleaseNotReady): ready("B")
    assert store.list_release_for_ranking(ReleasePinnedQueryFence(release=snapshots["B"]["release"], revision=2), scenario="content_feed", subject_id="viewer", limit=20)
