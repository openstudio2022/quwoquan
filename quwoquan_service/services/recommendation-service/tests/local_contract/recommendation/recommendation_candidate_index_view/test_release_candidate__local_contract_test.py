# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
from datetime import datetime, timedelta, timezone
import pytest
import copy
from generated.recommendation.recommendation_candidate_index_view.events.content_post_PostReleaseCandidatePrepared import PostReleaseCandidatePrepared
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_release_candidates import MongoReleaseCandidateOps
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import ReleaseNotReady, digest, canonical, ReleaseCandidateError


_NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
_DIGEST = "sha256:" + "a" * 64


def _prepared_pair():
    release = dict(environment="gamma", sourceOwner="qwq_data", releaseId="proof-local", manifestDigest=_DIGEST)
    binding = dict(release=release, slice="recommendation", providerBindingGeneration=_DIGEST, schemaGeneration=_DIGEST)
    posts = []
    for identity in ("a", "b"):
        post = dict(identity=dict(release=release, objectType="content.post", objectId=identity, sourceVersion=1, sourceDigest=_DIGEST), postRef=identity, authorId="author-" + identity, authorDisplayName="Author", authorAvatarUrl=None, contentType="video", contentIdentity="work", status="published", visibility="public", moderationStatus="approved", title=identity, body="", summary="", tagRefs=[], entityRefs=[], primaryHomepage=None, mediaAssetIds=["asset-" + identity], mediaUrls=["https://example.invalid/video"], coverUrl=None, thumbnailUrl=None, videoUrl="https://example.invalid/video", durationMs=1000, width=10, height=10, contentVertical=None, publishedAt=_NOW, updatedAt=_NOW, deepLink="/post/" + identity, documentDigest="")
        post["documentDigest"] = digest(post, "documentDigest")
        posts.append(post)
    snapshot = dict(release=release, sourceClosureDigest=_DIGEST, mediaClosureDigest=_DIGEST, objectSetDigest=digest([dict(objectType="content.post", objectId=i) for i in ("a", "b")]), snapshotDigest="", posts=posts)
    snapshot["snapshotDigest"] = digest(snapshot, "snapshotDigest")
    return PostReleaseCandidatePrepared(publicationId=digest(dict(binding=binding, snapshotDigest=snapshot["snapshotDigest"])), binding=binding, snapshot=snapshot, sourceVersion=1, occurredAt=_NOW)


class _ReadOnlyCollection:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.reads = 0

    def find_one(self, query):
        self.reads += 1
        return next((copy.deepcopy(row) for row in self.rows if all((value in row.get(key, []) if isinstance(row.get(key), list) else row.get(key) == value) for key, value in query.items())), None)

    def find(self, query):
        self.reads += 1
        return _Cursor([copy.deepcopy(row) for row in self.rows if all(row.get(k) == v for k, v in query.items())])


class _Cursor(list):
    def sort(self, field, direction):
        return _Cursor(sorted(self, key=lambda r: r[field], reverse=direction < 0))

    def limit(self, count):
        return _Cursor(self[:count])


def _reader(approved=("a",), restricted=()):
    event = _prepared_pair()
    store = MongoReleaseCandidateOps()
    store._release_runtime_binding = lambda release: event.binding
    store._release_checkpoints = _ReadOnlyCollection([dict(checkpointId=digest(event.binding), event=canonical(event), sourceEventDigest=digest(event))])
    store._release_candidates = _ReadOnlyCollection([dict(sourcePartition=digest(event.binding), contentId=p.identity.objectId, snapshot=canonical(p)) for p in event.snapshot.posts])
    store._account_restrictions = _ReadOnlyCollection([dict(subjectIds=["author-" + i], restricted=True) for i in restricted])
    admissions = []
    for p in event.snapshot.posts:
        if p.identity.objectId not in approved:
            continue
        a = dict(source=canonical(p.identity), admissionRevision=1, auditId="audit", qualityScore=.9, status="active", qualityAdmission="approved", scope="global", expiresAt=canonical(_NOW + timedelta(hours=1)), admissionDigest="")
        a["admissionDigest"] = digest(a, "admissionDigest")
        admissions.append(dict(_id=digest(dict(release=event.binding.release, id=p.identity.objectId)), admission=a, ownerStatus="active"))
    store._release_premium = _ReadOnlyCollection(admissions)
    return store, event


def _proof(store, event):
    return store.read_release_readiness(event.binding, event.snapshot.snapshotDigest, now=_NOW)


# 集合层独立刻画当前行为；不表示缺Safety/时间authority的整体准入合法。
# 后续authority接口冻结后，此builder需注入合法typed前置，不得删下面的缺配置红测。
def test_home_is_full_source_with_nonempty_premium_subset_and_query_is_read_only():
    store, event = _reader()
    collections = [store._release_checkpoints, store._release_candidates, store._account_restrictions, store._release_premium]
    before = [copy.deepcopy(c.rows) for c in collections]
    proof = _proof(store, event)
    classes = {r.queryClass: r for r in proof.queryClasses}
    assert proof.objectSetDigest == event.snapshot.objectSetDigest
    assert classes["home"].objectSetDigest == classes["required_detail"].objectSetDigest == event.snapshot.objectSetDigest
    assert classes["premium"].objectSetDigest == digest([dict(objectType="content.post", objectId="a")])
    assert before == [c.rows for c in collections]


def test_one_premium_revoked_recomputes_subset_without_invalidating_source():
    store, event = _reader(approved=("a", "b"))
    before = _proof(store, event)
    row = store._release_premium.rows[0]
    row["ownerStatus"] = "rolled_back"
    row["admission"]["status"] = "rolled_back"
    row["admission"]["admissionRevision"] = 2
    row["admission"]["admissionDigest"] = digest(row["admission"], "admissionDigest")
    after = _proof(store, event)
    assert after.objectSetDigest == before.objectSetDigest
    assert after.proofDigest != before.proofDigest
    assert after.premiumObjectSetDigest == digest([dict(objectType="content.post", objectId="b")])


@pytest.mark.parametrize("drift", ["same_count_id", "missing", "source_version", "source_digest"])
def test_source_projection_drift_is_not_ready(drift):
    store, event = _reader()
    if drift == "same_count_id":
        store._release_candidates.rows[0]["snapshot"]["identity"]["objectId"] = "replacement"
    elif drift == "missing":
        store._release_candidates.rows.pop()
    elif drift == "source_version":
        store._release_candidates.rows[0]["snapshot"]["identity"]["sourceVersion"] += 1
    else:
        store._release_candidates.rows[0]["snapshot"]["identity"]["sourceDigest"] = "sha256:" + "b" * 64
    with pytest.raises(ReleaseNotReady, match="candidate object set or document drift"):
        _proof(store, event)


def test_restricted_source_member_cannot_be_silently_excluded_from_home():
    store, event = _reader(approved=("a", "b"), restricted=("a",))
    with pytest.raises(ReleaseNotReady, match="home source contains a restricted member"):
        _proof(store, event)


def test_missing_safety_authority_is_not_proven_by_absent_restriction_rows():
    store, event = _reader()
    # 仅有源、投影、精品和索引binding；没有注入任何owner安全完整性authority。
    with pytest.raises(ReleaseNotReady):
        _proof(store, event)


def test_missing_proof_time_policy_does_not_grant_implicit_ten_second_window():
    store, event = _reader()
    # 不虚构clock-skew/requiredUntil数值；现有依赖未提供时间authority。
    with pytest.raises(ReleaseNotReady):
        _proof(store, event)


def test_expired_premium_and_generation_unavailable_are_not_ready():
    store, event = _reader()
    store._release_premium.rows[0]["admission"]["expiresAt"] = canonical(_NOW)
    with pytest.raises(ReleaseNotReady, match="eligible supply missing"):
        _proof(store, event)
    store._release_runtime_binding = None
    with pytest.raises(ReleaseNotReady, match="binding unavailable"):
        _proof(store, event)


def test_owner_canonical_digest_time_utf8_and_nonfinite():
    assert canonical(datetime(2026, 1, 1, 0, 0, 0, 120000, tzinfo=timezone.utc)) == "2026-01-01T00:00:00.12Z"
    assert digest({"z": "中文<旅行>", "a": 1}) == digest({"a": 1, "z": "中文<旅行>"})
    assert digest({"n": 1.0}) == digest({"n": 1})
    with pytest.raises(ReleaseCandidateError): digest({"n": float("nan")})
    with pytest.raises(ReleaseCandidateError): digest(datetime(2026, 1, 1))
