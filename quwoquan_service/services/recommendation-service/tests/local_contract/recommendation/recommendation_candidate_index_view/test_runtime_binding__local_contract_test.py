# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
import pytest
from internal.recommendation.recommendation_candidate_index_view.infrastructure.runtime_binding import compose_release_binding
from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import ReleaseNotReady


def test_production_binding_requires_explicit_inputs_and_rejects_conflict():
    class DB:
        name = "actual"
    with pytest.raises(ReleaseNotReady): compose_release_binding(DB(), {}, environment="gamma", environ={})
    with pytest.raises(ReleaseNotReady):
        compose_release_binding(DB(), {"release_candidate": {"binding_digest": "sha256:" + "a" * 64}}, environment="gamma", environ={"RECOMMENDATION_RELEASE_CANDIDATE_BINDING_DIGEST": "sha256:" + "b" * 64})
