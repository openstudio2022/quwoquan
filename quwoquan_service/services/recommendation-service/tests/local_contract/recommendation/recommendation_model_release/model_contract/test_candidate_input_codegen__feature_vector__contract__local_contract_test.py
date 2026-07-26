"""N3-3：模型评分 wire 必须保留线上已补齐的候选特征。"""

from __future__ import annotations

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateInput,
)


def test_generated_candidate_input_preserves_online_features():
    payload = {
        "contentId": "post-1",
        "publishHour": 9,
        "qualityScore": 0.82,
        "intersectionFactStrength": 0.7,
        "intersectionFreshness": 0.9,
        "affinityIntersectionScore": 0.6,
        "intersectionSourceRefTop": "shared_circle",
        "intersectionConfidenceLabel": "high",
        "intersectionClass": "fact",
    }

    candidate = CandidateInput.model_validate(payload)
    serialized = candidate.model_dump()

    for field, want in payload.items():
        assert serialized[field] == want, (
            f"generated CandidateInput dropped {field}: "
            "metadata/codegen drift would force the serving feature to its default"
        )

    for retired in ("bodyLength", "aspectRatio", "hasCover"):
        assert retired not in CandidateInput.model_fields, (
            f"{retired} must stay retired until the online candidate projection supplies it"
        )
