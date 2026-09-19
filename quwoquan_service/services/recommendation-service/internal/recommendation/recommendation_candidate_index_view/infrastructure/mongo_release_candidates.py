"""同一候选owner的Mongo事务与只读证明；不保存ready flag。"""
from datetime import datetime, timezone
from generated.recommendation.recommendation_candidate_index_view.events.content_post_PostReleaseCandidatePrepared import PostReleaseCandidatePrepared
from generated.recommendation.recommendation_candidate_index_view.events.ops_premium_pool_entry_PremiumPoolEntryUpserted import PremiumPoolEntry
from ..application.release_candidate import canonical, digest, validate_prepared, validate_binding, ReleaseCandidateError, ReleaseNotReady


class MongoReleaseCandidateOps:
    def ensure_release_indexes(self):
        self._release_candidates.create_index([("releaseBinding.release.environment", 1), ("releaseBinding.release.sourceOwner", 1), ("releaseBinding.release.releaseId", 1), ("releaseBinding.release.manifestDigest", 1), ("releaseBinding.providerBindingGeneration", 1), ("releaseBinding.schemaGeneration", 1), ("scenario", 1), ("contentId", 1)], unique=True, name="uq_rec_release_candidate")
        self._release_checkpoints.create_index([("checkpointId", 1)], unique=True, name="uq_rec_release_checkpoint")
        self._release_premium.create_index([("admission.source.release.environment", 1), ("admission.source.release.sourceOwner", 1), ("admission.source.release.releaseId", 1), ("admission.source.release.manifestDigest", 1), ("admission.source.objectId", 1)], unique=True, name="uq_rec_release_premium")

    def apply_release_candidate(self, event: PostReleaseCandidatePrepared):
        validate_prepared(event)
        key, event_digest = digest(event.binding), digest(event)
        with self._database.client.start_session() as session:
            with session.start_transaction():
                prior = self._release_checkpoints.find_one({"checkpointId": key}, session=session)
                if prior:
                    if prior["sourceEventDigest"] != event_digest:
                        raise ReleaseCandidateError("immutable source conflict")
                    return False
                inbox = self._inbox.find_one({"_id": event.publicationId}, session=session)
                if inbox:
                    raise ReleaseCandidateError("publication inbox without checkpoint")
                for post in event.snapshot.posts:
                    self._release_candidates.insert_one({"_id": digest({"binding": event.binding, "id": post.identity.objectId}), "releaseBinding": canonical(event.binding), "sourcePartition": key, "scenario": "content_feed", "contentId": post.identity.objectId, "snapshot": canonical(post)}, session=session)
                self._release_checkpoints.insert_one({"checkpointId": key, "binding": canonical(event.binding), "event": canonical(event), "sourceEventDigest": event_digest, "sourceVersion": event.sourceVersion}, session=session)
                self._inbox.insert_one({"_id": event.publicationId, "eventDigest": event_digest, "sourcePartition": key}, session=session)
        return True

    def apply_release_premium(self, event_id: str, entry: PremiumPoolEntry):
        if not event_id or entry.revision <= 0:
            raise ReleaseCandidateError("premium event identity missing")
        payload_digest = digest(entry)
        for admission in entry.releaseAdmissions:
            if (admission.source.objectId != entry.contentId or admission.source.objectType != "content.post"
                    or admission.source.release.sourceOwner != "qwq_data" or admission.admissionRevision <= 0 or admission.admissionRevision > entry.revision
                    or digest(admission, "admissionDigest") != admission.admissionDigest):
                raise ReleaseCandidateError("premium source binding invalid")
        with self._database.client.start_session() as session:
            with session.start_transaction():
                key = "premium:" + event_id
                prior = self._inbox.find_one({"_id": key}, session=session)
                if prior:
                    if prior["eventDigest"] != payload_digest:
                        raise ReleaseCandidateError("premium event replay conflict")
                    return False
                watermark_key = "premium-owner:" + entry.contentId
                watermark = self._inbox.find_one({"_id": watermark_key}, session=session)
                if watermark and watermark["revision"] >= entry.revision:
                    if watermark["revision"] == entry.revision and watermark["eventDigest"] != payload_digest:
                        raise ReleaseCandidateError("premium revision conflict")
                    return False
                known = list(self._release_premium.find({"admission.source.objectId": entry.contentId}, session=session))
                member_keys = {digest({"release": a.source.release, "id": a.source.objectId}) for a in entry.releaseAdmissions}
                if any(row["_id"] not in member_keys for row in known):
                    raise ReleaseCandidateError("premium owner omitted retained release members")
                for admission in entry.releaseAdmissions:
                    identity = {"release": admission.source.release, "id": admission.source.objectId}
                    self._release_premium.replace_one({"_id": digest(identity)}, {"_id": digest(identity), "admission": canonical(admission), "ownerRevision": entry.revision, "ownerStatus": entry.status, "sourceEventId": event_id, "sourceEventDigest": payload_digest}, upsert=True, session=session)
                self._inbox.replace_one({"_id": watermark_key}, {"_id": watermark_key, "revision": entry.revision, "eventDigest": payload_digest}, upsert=True, session=session)
                self._inbox.insert_one({"_id": key, "eventDigest": payload_digest}, session=session)
        return True

    def read_release_source(self, binding):
        validate_binding(binding)
        row = self._release_checkpoints.find_one({"checkpointId": digest(binding)})
        if row is None:
            raise ReleaseNotReady("candidate checkpoint missing")
        event = PostReleaseCandidatePrepared.model_validate(row["event"])
        validate_prepared(event)
        if canonical(event.binding) != canonical(binding) or row["sourceEventDigest"] != digest(event):
            raise ReleaseCandidateError("checkpoint drift")
        rows = list(self._release_candidates.find({"sourcePartition": digest(binding)}).sort("contentId", 1).limit(1001))
        if [r["snapshot"] for r in rows] != [canonical(p) for p in event.snapshot.posts]:
            raise ReleaseNotReady("candidate object set or document drift")
        return event

    def list_release_for_ranking(self, fence, *, scenario, subject_id, limit, eligible_content_types=None):
        if self._release_runtime_binding is None:
            raise ReleaseNotReady("managed candidate binding not configured")
        binding = self._release_runtime_binding(fence.release)
        validate_binding(binding)
        if canonical(binding.release) != canonical(fence.release):
            raise ReleaseCandidateError("runtime binding returned another release")
        event = self.read_release_source(binding)
        now = datetime.now(timezone.utc)
        allowed = None
        if scenario == "premium_stream":
            self.read_release_readiness(binding, event.snapshot.snapshotDigest, now=now)
            allowed = set()
            for p in event.snapshot.posts:
                row = self._release_premium.find_one({"_id": digest({"release": binding.release, "id": p.identity.objectId})})
                if row and row["ownerStatus"] == "active":
                    a = row["admission"]
                    if a["source"] == canonical(p.identity) and a["status"] == "active" and a["qualityAdmission"] == "approved" and a["scope"] == "global" and a["qualityScore"] >= .75 and datetime.fromisoformat(a["expiresAt"].replace("Z", "+00:00")) > now and p.contentType == "video" and p.videoUrl and p.durationMs > 0:
                        allowed.add(p.identity.objectId)
        following = set(self.following_persona_ids(subject_id)) if scenario == "following" else None
        out = []
        for p in self._presentable_release_posts(event.snapshot.posts, eligible_content_types):
            if p.status != "published" or p.visibility != "public" or p.moderationStatus != "approved": continue
            if allowed is not None and p.identity.objectId not in allowed: continue
            if following is not None and p.authorId not in following: continue
            if scenario == "travel_photography" and p.contentVertical != scenario: continue
            if self._account_restrictions.find_one({"subjectIds": p.authorId, "restricted": True}): continue
            out.append({"contentId": p.identity.objectId, "contentType": p.contentType, "authorId": p.authorId, "tagRefs": p.tagRefs, "entityRefs": p.entityRefs, "publishedAt": p.publishedAt, "updatedAt": p.updatedAt, "qualityScore": 0, "likeCount": 0, "commentCount": 0, "shareCount": 0, "viewCount": 0, "supplySource": "qwq_data", "contentVertical": p.contentVertical, "intersectionFeatures": {}, "recallPath": "premium_pool" if allowed is not None else "explore_recall"})
        ordinary = self.list_for_ranking(scenario=scenario, subject_id=subject_id, limit=limit, eligible_content_types=eligible_content_types)
        ids = {d["contentId"] for d in out}
        if any(d["contentId"] in ids for d in ordinary): raise ReleaseCandidateError("cross-source public identity collision")
        return (out + ordinary)[:limit]

    @staticmethod
    def _presentable_release_posts(posts, eligible_content_types):
        if eligible_content_types is None:
            return posts
        return tuple(post for post in posts if post.contentType in eligible_content_types)

    def read_release_supply_projection(self, binding, snapshot_digest, *, now=None):
        """只读重算完整home供给S与当前premium子集P；结果不是readiness proof。"""
        now = now or datetime.now(timezone.utc)
        if self._release_runtime_binding is None or canonical(binding) != canonical(self._release_runtime_binding(binding.release)):
            raise ReleaseNotReady("managed provider/schema binding unavailable or changed")
        event = self.read_release_source(binding)
        if event.snapshot.snapshotDigest != snapshot_digest:
            raise ReleaseCandidateError("source digest differs")
        posts, premium = [], []
        for post in event.snapshot.posts:
            # 候选级home必须覆盖S；不能将失效/受限成员当用户排序过滤掉。
            if post.status != "published" or post.visibility != "public" or post.moderationStatus != "approved":
                raise ReleaseNotReady("home source contains an unsafe member")
            if self._account_restrictions.find_one({"subjectIds": post.authorId, "restricted": True}):
                raise ReleaseNotReady("home source contains a restricted member")
            posts.append(post)
            row = self._release_premium.find_one({"_id": digest({"release": binding.release, "id": post.identity.objectId})})
            if not row:
                continue
            admission = row["admission"]
            if admission["source"] != canonical(post.identity):
                continue
            until = datetime.fromisoformat(admission["expiresAt"].replace("Z", "+00:00"))
            if (row["ownerStatus"] == "active" and admission["status"] == "active" and admission["scope"] == "global" and admission["qualityAdmission"] == "approved" and admission["qualityScore"] >= .75 and until > now and post.contentType == "video" and post.videoUrl and post.durationMs > 0):
                if digest(admission, "admissionDigest") != admission["admissionDigest"]:
                    raise ReleaseCandidateError("premium storage digest drift")
                premium.append(post)
        if not posts or not premium:
            raise ReleaseNotReady("home or premium exact eligible supply missing")
        return event, tuple(posts), tuple(premium)

    def read_release_readiness(self, binding, snapshot_digest, *, now=None):
        self.read_release_supply_projection(binding, snapshot_digest, now=now)
        # 当前合同尚未提供owner安全完整性authority、现役proof-time policy或
        # ClockHealth事实。缺少这些权威时，restriction集合为空不能证明安全，
        # 调用方也不能从本地时钟获得一个隐式证明窗口；因此只允许fail-closed。
        raise ReleaseNotReady("owner safety authority or proof-time policy unavailable")
