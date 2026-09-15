"""单入口：Content真实私有提交/HTTP/stream→Search+Rec三consumer持久对账。
Search三kind源与Rec候选/premium使用typed fixture进入真实准备/投影；非完整生产activation资格。
"""
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tempfile

ROOT = Path(__file__).resolve().parents[7]
SERVICE = ROOT / "quwoquan_service"
sys.path.insert(0, str(SERVICE / "services/recommendation-service"))
from redis import Redis
import httpx
from pymongo import MongoClient
from generated.recommendation.recommendation_candidate_index_view.events.content_post_ContentReleaseFenceChanged import ContentReleaseFenceChangedPayload as CandidateFence, ContentActiveReleaseFence
from generated.recommendation.recommendation_feature_profile_view.events.content_post_ContentReleaseFenceChanged import ContentReleaseFenceChangedPayload as FeatureFence
from internal.recommendation.recommendation_candidate_index_view.application.fence_reconciliation import FenceReconciler
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import canonical, digest
from internal.recommendation.recommendation_candidate_index_view.infrastructure.fence_reconciliation import CandidateFenceReceipts, ContentReceiptClient, content_service_authorization
from internal.recommendation.recommendation_feature_profile_view.infrastructure.fence_reconciliation import FeatureFenceReceipts
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import MongoCandidateIndexStore
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import MongoFeatureProfileStore
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import PostLifecycleConsumer as CandidateConsumer
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import PostLifecycleConsumer as FeatureConsumer
from tests.api_integration.recommendation.recommendation_candidate_index_view.test_release_candidate__api_integration_test import prepared, premium


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def harness(package, test, marker, env):
    process = subprocess.Popen(["go", "test", package, "-run", "^" + test + "$", "-count=1", "-v", "-timeout=300s"], cwd=SERVICE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = queue.Queue()
    def drain():
        for line in process.stdout:
            print(line.rstrip(), flush=True); lines.put(line)
    threading.Thread(target=drain, daemon=True).start()
    deadline = time.monotonic() + 140
    while time.monotonic() < deadline:
        try: line = lines.get(timeout=.2)
        except queue.Empty:
            if process.poll() is not None: raise RuntimeError(f"{test} failed: {process.returncode}")
            continue
        if line.startswith(marker): return process, httpx.Client(base_url=line[len(marker):].strip(), timeout=20)
    raise RuntimeError(test + " bounded startup expired")


def main():
    redis_bin, mongo_bin = shutil.which("redis-server"), shutil.which("mongod")
    assert redis_bin and mongo_bin, "isolated redis-server/mongod required"
    rp, mp = port(), port()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TESTCONTAINERS_RYUK_DISABLED="true", QWQ_FENCE_JOINT_REDIS=f"127.0.0.1:{rp}", AUTH_JWT_SECRET="d"*32, AUTH_JWT_ISSUER="joint-fence", AUTH_JWT_AUDIENCE="content-service", AUTH_JWT_TOKEN_VERSION="1")
    for key in ("TEST_MONGO_URI", "QWQ_TEST_MONGO_URI", "TEST_PG_DSN", "QWQ_TEST_POSTGRES_DSN"): env.pop(key, None)
    os.environ.update({k:env[k] for k in ("AUTH_JWT_SECRET", "AUTH_JWT_ISSUER", "AUTH_JWT_AUDIENCE", "AUTH_JWT_TOKEN_VERSION")})
    processes, clients = [], []
    with tempfile.TemporaryDirectory(prefix="fence-joint-") as directory:
        try:
            processes.append(subprocess.Popen([redis_bin,"--bind","127.0.0.1","--port",str(rp),"--save","","--appendonly","no"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            processes.append(subprocess.Popen([mongo_bin,"--dbpath",directory,"--port",str(mp),"--bind_ip","127.0.0.1","--replSet","joint","--quiet"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            redis = Redis(host="127.0.0.1",port=rp,decode_responses=False); direct = MongoClient(f"mongodb://127.0.0.1:{mp}/?directConnection=true",serverSelectionTimeoutMS=500,tz_aware=True)
            deadline=time.monotonic()+20
            while True:
                try: redis.ping(); direct.admin.command("ping"); break
                except Exception:
                    if time.monotonic()>deadline: raise
                    time.sleep(.1)
            direct.admin.command({"replSetInitiate":{"_id":"joint","members":[{"_id":0,"host":f"127.0.0.1:{mp}"}]}})
            while not direct.admin.command("hello").get("isWritablePrimary"):
                assert time.monotonic()<deadline;time.sleep(.1)
            direct.close()
            direct=MongoClient(f"mongodb://127.0.0.1:{mp}/?replicaSet=joint",serverSelectionTimeoutMS=3000,tz_aware=True)
            direct.admin.command("ping")
            db=direct["fence_joint_rec"]
            content_process, content = harness("./services/content-service/internal/content/post/infrastructure/releaseimport","TestFenceJointContentHarness","CONTENT_FENCE_JOINT_READY ",env);processes.append(content_process);clients.append((content,"/fixture/done"))
            env["QWQ_FENCE_JOINT_CONTENT"]=str(content.base_url).rstrip("/")
            search_process, search = harness("./services/search-service/tests/api_integration/search/search_release_preparation","TestFenceJointSearchHarness","SEARCH_FENCE_JOINT_READY ",env);processes.append(search_process);clients.append((search,"/done"))
            targets=content.get("/fixture/snapshots").json()
            # 非空typed前置，不直接写任何fence receipt；真实Mongo候选/premium方法形成ready。
            candidate=MongoCandidateIndexStore(db);candidate.ensure_indexes();feature=MongoFeatureProfileStore(db);feature.ensure_indexes()
            events={}
            for name in ("a","b"):
                event=prepared("joint-"+name);event.binding.release.environment="alpha";event.binding.release.manifestDigest=targets[name]["manifestDigest"]
                release=canonical(event.binding.release);event.snapshot.release=event.binding.release
                for post in event.snapshot.posts:
                    post.identity.release=event.binding.release;post.documentDigest=digest(post,"documentDigest")
                event.snapshot.snapshotDigest=digest(event.snapshot,"snapshotDigest");event.publicationId=digest({"binding":event.binding,"snapshotDigest":event.snapshot.snapshotDigest})
                candidate.apply_release_candidate(event)
                entry=premium(event,revision=1 if name=="a" else 2)
                if name=="b":entry.releaseAdmissions.insert(0,premium(events["a"]).releaseAdmissions[0])
                candidate.apply_release_premium("fixture-premium-"+name,entry);events[name]=event
            candidate._release_runtime_binding=lambda release: {**canonical(events["a"].binding),"release":canonical(release)}
            def proof(after):
                name=after["releaseId"][-1];e=events[name];return digest(candidate.read_release_readiness(e.binding,e.snapshot.snapshotDigest))
            content_reader=ContentReceiptClient(str(content.base_url),content_service_authorization(),ContentActiveReleaseFence)
            candidate_receipts,feature_receipts=CandidateFenceReceipts(db),FeatureFenceReceipts(db)
            class NoOrdinary:
                def exists(self, *_): raise AssertionError("fence touched ordinary safety")
                def project_post_lifecycle(self, **_): raise AssertionError("fence became ordinary Post")
            class AckProxy:
                fail=False
                def __getattr__(self,name): return getattr(redis,name)
                def xack(self,*args):
                    if self.fail:self.fail=False;raise ConnectionError("injected ACK failure")
                    return redis.xack(*args)
            candidate_redis,feature_redis=AckProxy(),AckProxy()
            c=CandidateConsumer(redis_client=candidate_redis,projection=candidate,subject_closures=NoOrdinary(),consumer="rec-c",fence_reconciler=FenceReconciler(model=CandidateFence,store=candidate_receipts,content=content_reader,proof_reader=proof,environment="alpha"))
            f=FeatureConsumer(redis_client=feature_redis,feature_store=feature,projector=NoOrdinary(),consumer="rec-f",fence_reconciler=FenceReconciler(model=FeatureFence,store=feature_receipts,content=content_reader,proof_reader=proof,environment="alpha"))
            stream="events.content.post_lifecycle";groups=["joint-search-fence","recommendation-candidate-index","recommendation-feature-post-lifecycle"]
            def age_pending():
                for group in groups:
                    try:
                        for p in redis.xpending_range(stream,group,"-","+",100): redis.xclaim(stream,group,p["consumer"],0,[p["message_id"]],idle=31000)
                    except Exception as e:
                        if "NOGROUP" not in str(e):raise
            def consume(ok=True):
                age_pending();response=search.post("/process").json()
                if ok: assert "error" not in response,response
                else: assert "error" in response,response
                for consumer in (c,f):
                    if ok:consumer.process_once()
                    else:
                        try:consumer.process_once()
                        except Exception:pass
                        else:raise AssertionError("invalid fence acknowledged")
                if ok:
                    assert c.healthy() and f.healthy() and response["healthy"]
                    assert all(redis.xpending(stream,g)["pending"]==0 for g in groups)
                return response
            def content_stats():
                return {name:json.loads(raw) for name,raw in content.get("/fixture/stats").json().items()}
            original_candidates=list(db.rm_release_discovery_candidates.find({}))
            # 首次真实事务事件：三consumer ACK均失败，证据已写但pending/health不能假绿。
            a=content.post("/fixture/activate?target=a");assert a.status_code==200,a.text
            stable=content_stats();search.post("/ack-fail");candidate_redis.fail=True;feature_redis.fail=True
            consume(False);assert not c.healthy() and not f.healthy()
            # pending未够idle的空扫描也不能清除未解决状态。
            empty=search.post("/process").json();assert not empty["healthy"];c.process_once();f.process_once();assert not c.healthy() and not f.healthy()
            consume();assert content_stats()==stable
            assert candidate_receipts.collection.count_documents({})==feature_receipts.collection.count_documents({})==1
            first=redis.xrange(stream)[0][1]
            # Content故障先阻断三个consumer，不写成功receipt；恢复后处理B。
            b=content.post("/fixture/activate?target=b");assert b.status_code==200,b.text
            content.post("/fixture/receipt-mode?fail=1");consume(False);content.post("/fixture/receipt-mode?fail=0");consume()
            a2=content.post("/fixture/activate?target=a");assert a2.status_code==200 and a2.json()["revision"]==3
            search.post("/provider-fail?fail=1")
            failed=search.post("/process").json();assert "error" in failed and not failed["healthy"],failed
            assert redis.xpending(stream,groups[0])["pending"]==1
            search.post("/provider-fail?fail=0");consume()
            assert list(db.rm_release_discovery_candidates.find({}))==original_candidates
            stable=content_stats()
            # 清除仅测试消费凭据模拟新consumer恢复，无inbox的迟到A必须走真实旧提交query。
            search.post("/reset");candidate_receipts.collection.delete_many({});feature_receipts.collection.delete_many({});redis.xadd(stream,first);consume()
            assert candidate_receipts.collection.find_one({})["outcome"]=="superseded"
            assert feature_receipts.collection.find_one({})["outcome"]=="superseded"
            assert content_stats()==stable
            # 相同事件身份不同摘要，不能覆盖持久receipt。
            tampered=dict(first);body=json.loads(tampered[b"payload"]);body["after"]["projectionVersion"]+=1;tampered[b"payload"]=json.dumps(body);bad_id=redis.xadd(stream,tampered);consume(False)
            assert all(redis.xpending(stream,g)["pending"]==1 for g in groups)
            # malformed消息在测试隔离流中移除，仅用于继续验证下一个负例，非生产ACK策略。
            for group in groups:redis.xack(stream,group,bad_id)
            # 负例基于真实outbox字节定向损坏，不伪造成功提交事实。
            for patch in ({"revision":99}, {"environment":"beta"}, {"releaseId":"wrong-tuple"}):
                bad=dict(first);body=json.loads(bad[b"payload"]);body["after"].update(patch);bad[b"payload"]=json.dumps(body)
                bad_id=redis.xadd(stream,bad);consume(False)
                assert all(redis.xpending(stream,g)["pending"]==1 for g in groups)
                for group in groups:redis.xack(stream,group,bad_id)
            # 旧receipt不完整：新实例/无inbox不能凭较大当前revision推导superseded。
            search.post("/reset");candidate_receipts.collection.delete_many({});feature_receipts.collection.delete_many({})
            content.post("/fixture/incomplete",params={"eventId":first[b"eventId"].decode()});redis.xadd(stream,first);consume(False)
            assert candidate_receipts.collection.count_documents({})==feature_receipts.collection.count_documents({})==0
            print("JOINT_THREE_CONSUMERS_CONTENT_OUTBOX_REDIS_REAL_PROOFS_ACK_ABA_LATE_TAMPER_OLD_RECEIPT_PASS",flush=True)
            for client,path in clients:client.post(path)
            for p in (search_process,content_process):assert p.wait(timeout=30)==0
            direct.close();redis.close()
        finally:
            for client,path in clients:
                try: client.post(path)
                except Exception: pass
                client.close()
            for p in processes[2:]:
                try: p.wait(timeout=25)
                except subprocess.TimeoutExpired: pass
            for p in reversed(processes):
                if p.poll() is None:
                    p.terminate()
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)


if __name__=="__main__":main()
