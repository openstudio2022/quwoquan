# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
# readiness_case: stage-model-release-local
# readiness_case: activate-model-release-local
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from internal.recommendation.recommendation_model_release.domain.model import (
    ActivateRelease,
    InvalidCommandError,
    StageRelease,
)
from support.path_setup import model_runtime_root


SHA = "a" * 64


def _stage(**overrides) -> StageRelease:
    values = {
        "release_id": "content-feed-20260731-001",
        "scenario": "content_feed",
        "model_digest": SHA,
        "feature_contract_digest": "b" * 64,
        "artifact_uri": "s3://quwoquan-models/models/content_feed/release/model.txt",
        "verification_digest": "c" * 64,
        "evaluation_metrics": {"auc": 0.91, "ndcg20": 0.73},
        "idempotency_key": "stage-content-feed-20260731-001",
    }
    values.update(overrides)
    return StageRelease.create(**values)


def test_stage_identity_and_digest_are_canonical() -> None:
    command = _stage()
    expected = hashlib.sha256(
        json.dumps(
            {
                "operation": "StageRecommendationModelRelease",
                "releaseId": command.release_id,
                "scenario": command.scenario,
                "modelDigest": command.model_digest,
                "featureContractDigest": command.feature_contract_digest,
                "artifactUri": command.artifact_uri,
                "verificationDigest": command.verification_digest,
                "evaluationMetrics": command.evaluation_metrics,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert command.command_digest() == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_digest", "A" * 64),
        ("feature_contract_digest", "short"),
        ("verification_digest", ""),
        ("artifact_uri", "/tmp/model.txt"),
        ("evaluation_metrics", {}),
        ("idempotency_key", " "),
    ],
)
def test_stage_rejects_noncanonical_or_unverified_release(field: str, value) -> None:
    with pytest.raises(InvalidCommandError):
        _stage(**{field: value})


def test_activate_models_rollback_as_the_same_cas_command() -> None:
    command = ActivateRelease.create(
        release_id="content-feed-20260730-002",
        scenario="content_feed",
        expected_active_release_id="content-feed-20260731-001",
        idempotency_key="activate-rollback-001",
    )
    assert command.release_id == "content-feed-20260730-002"
    assert command.expected_active_release_id == "content-feed-20260731-001"


def test_runtime_scripts_have_no_registry_mutation_or_parallel_command_track() -> None:
    scripts = model_runtime_root() / "scripts"
    governed = (
        "model_registry_cli.py",
        "model_release_client.py",
        "train.py",
        "train_multiobjective.py",
        "train_embedding.py",
        "activation_gate.py",
    )
    source = "\n".join(
        (scripts / name).read_text(encoding="utf-8") for name in governed
    )
    for forbidden in (
        'db["rec_model_registry"].insert',
        'db["rec_model_registry"].update',
        'coll.update_one(',
        'coll.update_many(',
        "--force",
        'add_parser("rollback"',
        'add_parser("promote"',
    ):
        assert forbidden not in source

    cli = (scripts / "model_registry_cli.py").read_text(encoding="utf-8")
    assert 'add_parser("stage"' in cli
    assert 'add_parser(\n        "activate"' in cli
    assert "stage_release(" in cli
    assert "activate_release(" in cli
