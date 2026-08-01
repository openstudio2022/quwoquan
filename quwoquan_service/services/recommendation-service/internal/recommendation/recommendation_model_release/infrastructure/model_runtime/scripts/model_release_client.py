"""HTTP client for the canonical RecommendationModelRelease command facade."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


STAGE_PATH = "/internal/recommendation/model-releases:stage"
ACTIVATE_PATH = "/internal/recommendation/model-releases:activate"


class ModelReleaseCommandError(RuntimeError):
    pass


def canonical_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def file_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_feature_contract_digest() -> str:
    value = os.environ.get("RECOMMENDATION_FEATURE_CONTRACT_DIGEST", "").strip()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ModelReleaseCommandError(
            "RECOMMENDATION_FEATURE_CONTRACT_DIGEST must be a lowercase SHA-256 digest"
        )
    return value


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ModelReleaseCommandError(f"missing required model release config: {name}")
    return value


def _post(path: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    base_url = _required_env("RECOMMENDATION_SERVICE_INTERNAL_URL").rstrip("/") + "/"
    token = _required_env("RECOMMENDATION_MODEL_MANAGE_TOKEN")
    body = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        urljoin(base_url, path.lstrip("/")),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ModelReleaseCommandError(
            f"model release command failed with HTTP {error.code}: {detail}"
        ) from error
    except (OSError, ValueError) as error:
        raise ModelReleaseCommandError("model release command transport failed") from error
    if not isinstance(result, dict):
        raise ModelReleaseCommandError("model release command returned a non-object")
    return result


def stage_release(
    *,
    release_id: str,
    scenario: str,
    artifact_uri: str,
    model_digest: str,
    feature_contract_digest: str,
    verification_digest: str,
    evaluation_metrics: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    payload = {
        "releaseId": release_id,
        "scenario": scenario,
        "modelDigest": model_digest,
        "featureContractDigest": feature_contract_digest,
        "artifactUri": artifact_uri,
        "verificationDigest": verification_digest,
        "evaluationMetrics": evaluation_metrics,
    }
    key = idempotency_key or f"stage:{release_id}:{canonical_digest(payload)}"
    return _post(STAGE_PATH, payload, key)


def activate_release(
    *,
    release_id: str,
    scenario: str,
    expected_active_release_id: str | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    payload = {
        "releaseId": release_id,
        "scenario": scenario,
        "expectedActiveReleaseId": expected_active_release_id,
    }
    key = idempotency_key or f"activate:{release_id}:{canonical_digest(payload)}"
    return _post(ACTIVATE_PATH, payload, key)
