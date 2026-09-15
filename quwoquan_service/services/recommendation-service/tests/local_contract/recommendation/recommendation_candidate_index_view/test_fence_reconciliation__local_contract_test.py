# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
import json
import pytest
from generated.recommendation.recommendation_candidate_index_view.events.content_post_ContentReleaseFenceChanged import ContentReleaseFenceChangedPayload as CandidateModel
from generated.recommendation.recommendation_feature_profile_view.events.content_post_ContentReleaseFenceChanged import ContentReleaseFenceChangedPayload as FeatureModel
from internal.recommendation.recommendation_candidate_index_view.application.fence_reconciliation import FenceReconciler, content_payload_digest
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import digest


@pytest.mark.parametrize("model", [CandidateModel, FeatureModel])
def test_fence_reconcile_is_exact_read_only_and_old_requires_receipt(model):
    before = dict(found=False, environment="alpha", sourceOwner="qwq_data", releaseId="", manifestDigest="", revision=0, projectionVersion=0, activatedAt=None)
    after = dict(before, found=True, releaseId="a", manifestDigest="sha256:" + "a" * 64, revision=1, projectionVersion=2, activatedAt="2026-09-13T00:00:00Z")
    event = model.model_validate(dict(before=before, after=after))
    identity = "content-release-fence:" + digest(["alpha", "qwq_data", 1])[7:]
    values = dict(eventId=identity, eventType="ContentReleaseFenceChanged", aggregateType="Post", aggregateId="alpha/qwq_data", aggregateVersion="1", occurredAt=after["activatedAt"], payload=json.dumps(dict(before=before, after=after)))
    class Store:
        value = None
        def find(self, key): return self.value
        def save(self, value): self.value = value
    class Content:
        missing = False
        current = event.after
        reads = 0
        def read_active(self, *_): return self.current
        def read_commit(self, *_):
            self.reads += 1
            if self.missing: raise ValueError("missing exact receipt")
            return dict(eventId=identity, payloadDigest=content_payload_digest(event), transition=dict(before=before, after=after))
    calls = []
    store, content = Store(), Content()
    runner = FenceReconciler(model=model, store=store, content=content, proof_reader=lambda f: calls.append(f) or "sha256:" + "b" * 64, environment="alpha")
    runner.apply(values); runner.apply(values)
    assert content.reads == 1 and len(calls) == 1 and store.value["outcome"] == "reconciled"
    store.value = None; content.current = event.after.model_copy(update={"revision": 3}); content.missing = True
    with pytest.raises(ValueError, match="missing exact"): runner.apply(values)
    assert store.value is None
    content.missing = False; runner.apply(values)
    assert store.value["outcome"] == "superseded" and len(calls) == 1
    store.value = None
    bad = dict(values, payload=json.dumps(dict(before=before, after=after, postId="wrong")))
    with pytest.raises(ValueError): runner.apply(bad)
    assert store.value is None
