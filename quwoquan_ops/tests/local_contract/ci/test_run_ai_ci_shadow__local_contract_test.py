from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from quwoquan_ops.ci.run_ai_ci_shadow import (
    ShadowAnalysisError,
    prepare_request,
    run_shadow,
)


GIT_SHA = "a" * 40
SOURCE_REF = "github-actions://quwoquan/quwoquan/runs/42/jobs/upstream"


@dataclass
class _Response:
    payload: dict[str, object]

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _model_response() -> dict[str, object]:
    return {
        "modelIdentity": "shadow-ci-triage",
        "findings": [{"title": "cache miss", "evidence": "build-image"}],
        "confidence": 0.8,
        "suggestedActions": ["inspect the immutable cache key"],
    }


def test_request_redacts_secrets_and_binds_receipt() -> None:
    request, evidence, receipt = prepare_request(
        {"job": "build", "authorization": "Bearer should-not-leak"},
        source_ref_prefix=SOURCE_REF,
        source_kind="ci-job-summary",
        source_git_sha=GIT_SHA,
        workflow_run_id="42",
    )
    assert request["evidence"]["authorization"] == "[REDACTED]"
    assert evidence["sourceRef"].endswith("@" + evidence["sourceDigest"])
    assert receipt["redactedValueCount"] == 1
    assert receipt["residualSensitiveValueCount"] == 0
    assert receipt["sourceDigest"] != receipt["modelInputDigest"]


def test_shadow_output_is_canonical_and_has_no_control_authority() -> None:
    observed: dict[str, object] = {}

    def opener(request: object, timeout: float) -> _Response:
        observed["request"] = request
        observed["timeout"] = timeout
        return _Response(_model_response())

    result = run_shadow(
        source={"jobs": [{"name": "build", "result": "failure"}]},
        endpoint="https://ai-ci.example.test/analyze",
        bearer_token="opaque-test-value",
        source_ref_prefix=SOURCE_REF,
        source_kind="ci-job-summary",
        source_git_sha=GIT_SHA,
        workflow_run_id="42",
        opener=opener,
    )
    assert result["schema"] == "ai-ci-advisory"
    assert result["modelIdentity"] == "shadow-ci-triage"
    serialized = json.dumps(result, sort_keys=True)
    assert "gateStatus" not in serialized
    assert "promotionDecision" not in serialized
    request = observed["request"]
    assert getattr(request, "get_header")("Authorization") == "Bearer opaque-test-value"


def test_shadow_rejects_model_control_fields() -> None:
    response = _model_response()
    response["gateStatus"] = "passed"
    with pytest.raises(ShadowAnalysisError, match="must return only"):
        run_shadow(
            source={"job": "build"},
            endpoint="https://ai-ci.example.test/analyze",
            bearer_token="opaque-test-value",
            source_ref_prefix=SOURCE_REF,
            source_kind="ci-job-summary",
            source_git_sha=GIT_SHA,
            workflow_run_id="42",
            opener=lambda _request, _timeout: _Response(response),
        )


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://ai-ci.example.test/analyze",
        "https://user:password@ai-ci.example.test/analyze",
    ),
)
def test_shadow_requires_credential_free_https_endpoint(endpoint: str) -> None:
    with pytest.raises(ShadowAnalysisError, match="credential-free HTTPS"):
        run_shadow(
            source={"job": "build"},
            endpoint=endpoint,
            bearer_token="opaque-test-value",
            source_ref_prefix=SOURCE_REF,
            source_kind="ci-job-summary",
            source_git_sha=GIT_SHA,
            workflow_run_id="42",
            opener=lambda _request, _timeout: _Response(_model_response()),
        )


def test_shadow_requires_token_before_network() -> None:
    with pytest.raises(ShadowAnalysisError, match="token is unavailable"):
        run_shadow(
            source={"job": "build"},
            endpoint="https://ai-ci.example.test/analyze",
            bearer_token="",
            source_ref_prefix=SOURCE_REF,
            source_kind="ci-job-summary",
            source_git_sha=GIT_SHA,
            workflow_run_id="42",
            opener=lambda _request, _timeout: _Response(_model_response()),
        )
