#!/usr/bin/env python3
"""Verify generated models: run from services/rec-model-service with pydantic installed (e.g. in venv)."""
import sys

sys.path.insert(0, ".")
from generated.models.request_response import (
    CandidateInput,
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)
from generated.models.projections import LearningEvent, ModelRegistryEntry, TrainingSample

# Contract alignment with fields.yaml / Go ModelPredictRequest / OpenAPI
req = ModelScoreRequest(scenario="content_feed", userId="u1", sessionId="s1", candidates=[])
assert req.scenario == "content_feed" and req.userId == "u1"
resp = ModelScoreResponse(scores=[CandidateScore(contentId="c1", score=0.5)])
assert len(resp.scores) == 1 and resp.scores[0].contentId == "c1"
assert resp.scores[0].score == 0.5

print("OK: generated models import and contract check passed")
