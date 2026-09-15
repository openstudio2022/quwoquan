# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
import pytest
from tests.support.recommendation_mongo import mongo_client, mongo_database
from internal.recommendation.recommendation_candidate_index_view.infrastructure.fence_reconciliation import CandidateFenceReceipts
from internal.recommendation.recommendation_feature_profile_view.infrastructure.fence_reconciliation import FeatureFenceReceipts


def test_two_owners_fence_receipts_are_independent_and_revision_conflicts(mongo_database):
    stores = [CandidateFenceReceipts(mongo_database), FeatureFenceReceipts(mongo_database)]
    row = dict(eventDigest="sha256:" + "a" * 64, scopeDigest="sha256:" + "b" * 64, revision=1, payloadDigest="sha256:" + "c" * 64, proofEvidenceDigest="sha256:" + "d" * 64, outcome="reconciled")
    for store in stores:
        store.save(row.copy()); store.save(row.copy())
        assert store.collection.count_documents({}) == 1
        with pytest.raises(ValueError): store.save({**row, "eventDigest": "sha256:" + "e" * 64, "payloadDigest": "sha256:" + "f" * 64})
        assert store.find(row["eventDigest"])["payloadDigest"] == row["payloadDigest"]
    assert stores[0].collection.name != stores[1].collection.name


def test_fence_checks_real_prepared_candidate_without_mutation(mongo_database):
    from tests.api_integration.recommendation.recommendation_candidate_index_view.test_release_candidate__api_integration_test import prepared, premium
    from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import MongoCandidateIndexStore
    from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import canonical, digest
    from internal.recommendation.recommendation_candidate_index_view.application.fence_reconciliation import FenceReconciler, content_payload_digest
    from generated.recommendation.recommendation_candidate_index_view.events.content_post_ContentReleaseFenceChanged import ContentReleaseFenceChangedPayload
    import json
    event = prepared()
    candidates = MongoCandidateIndexStore(mongo_database, release_runtime_binding=lambda release: {**canonical(event.binding), "release": canonical(release)})
    candidates.ensure_indexes(); candidates.apply_release_candidate(event); candidates.apply_release_premium("premium-fence", premium(event))
    before = dict(found=False, environment="gamma", sourceOwner="qwq_data", releaseId="", manifestDigest="", revision=0, projectionVersion=0, activatedAt=None)
    after = dict(before, found=True, releaseId=event.binding.release.releaseId, manifestDigest=event.binding.release.manifestDigest, revision=1, projectionVersion=1, activatedAt="2026-09-13T00:00:00Z")
    fence = ContentReleaseFenceChangedPayload.model_validate(dict(before=before, after=after)); identity = "content-release-fence:" + digest(["gamma", "qwq_data", 1])[7:]
    class Content:
        def read_active(self, *_): return fence.after
        def read_commit(self, *_): return dict(eventId=identity, payloadDigest=content_payload_digest(fence), transition=canonical(fence))
    original = list(mongo_database.rm_release_discovery_candidates.find({}))
    receipts = CandidateFenceReceipts(mongo_database)
    runner = FenceReconciler(model=ContentReleaseFenceChangedPayload, store=receipts, content=Content(), proof_reader=lambda _: digest(candidates.read_release_readiness(event.binding, event.snapshot.snapshotDigest)), environment="gamma")
    values = dict(eventId=identity, eventType="ContentReleaseFenceChanged", aggregateType="Post", aggregateId="gamma/qwq_data", aggregateVersion="1", occurredAt=after["activatedAt"], payload=json.dumps(dict(before=before, after=after)))
    runner.apply(values); runner.apply(values)
    assert receipts.collection.count_documents({}) == 1
    assert list(mongo_database.rm_release_discovery_candidates.find({})) == original
