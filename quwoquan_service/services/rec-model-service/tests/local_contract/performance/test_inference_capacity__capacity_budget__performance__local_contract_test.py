from __future__ import annotations

import concurrent.futures
import sys
import threading
from pathlib import Path

_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from support.path_setup import ensure_rec_model_paths

ensure_rec_model_paths()

from api.capacity import (  # noqa: E402
    MicroBatcher,
    ScoreCache,
    score_cache_key,
)
from generated.models.request_response import (  # noqa: E402
    CandidateInput,
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)


def _service_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "deploy" / "Dockerfile").is_file():
            return parent
    raise AssertionError("rec-model-service root not found")


def _request() -> ModelScoreRequest:
    return ModelScoreRequest(
        scenario="content_feed",
        userId="u1",
        sessionId="s1",
        userFeatures={"tagAffinities": {"travel": 1.0}},
        sessionSignals={"tagWeights": {"travel": 3.0}},
        candidates=[
            CandidateInput(
                contentId="c1",
                tagRefs=["travel"],
                likeCount=1,
                viewCount=10,
                ageHours=1,
            )
        ],
        context={"modelVersion": "champion"},
    )


def test_score_cache_key_is_stable_for_same_candidate_features() -> None:
    req1 = _request()
    req2 = _request()

    assert score_cache_key(req1, "rule") == score_cache_key(req2, "rule")
    assert score_cache_key(req1, "rule") != score_cache_key(req2, "multi_obj")


def test_score_cache_respects_ttl_and_clear() -> None:
    cache = ScoreCache(ttl_s=10, max_entries=2)
    response = ModelScoreResponse(scores=[CandidateScore(contentId="c1", score=1.0)])

    cache.set("k1", response)
    assert cache.get("k1") == response

    cache.clear()
    assert cache.get("k1") is None


def test_microbatcher_coalesces_duplicate_concurrent_requests() -> None:
    batcher = MicroBatcher(window_ms=20)
    calls = 0
    lock = threading.Lock()

    def compute() -> ModelScoreResponse:
        nonlocal calls
        with lock:
            calls += 1
        return ModelScoreResponse(scores=[CandidateScore(contentId="c1", score=1.0)])

    def run_once() -> ModelScoreResponse:
        return batcher.run(
            key="same-request",
            scenario="content_feed",
            model_version="rule",
            compute=compute,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run_once(), range(4)))

    assert calls == 1
    assert all(r.scores[0].contentId == "c1" for r in results)


def test_dockerfile_uses_configurable_multi_worker_startup() -> None:
    dockerfile = _service_root() / "deploy" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    assert "REC_MODEL_UVICORN_WORKERS" in text
    assert "--workers ${REC_MODEL_UVICORN_WORKERS:-2}" in text
