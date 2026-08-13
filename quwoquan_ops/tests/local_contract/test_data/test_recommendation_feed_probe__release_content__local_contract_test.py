"""The release-mode recommendation probe cannot accept an empty premium pool.

spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock


def _probe_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "acceptance"
        / "user_acceptance"
        / "service_ops"
        / "content-service"
        / "smoke"
        / "run_recommendation_feed_probe.py"
    )
    spec = importlib.util.spec_from_file_location("recommendation_feed_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_recommendation_probe__rejects_empty_items__local_contract() -> None:
    probe = _probe_module()

    assert probe.check_non_empty_items({"items": []}, required=True)
    assert probe.check_non_empty_items({"items": [{"postId": "video-1"}]}, required=True) == []
    assert probe.check_non_empty_items({"items": []}, required=False) == []


def test_feed_outcome_contract_rejects_ambiguous_empty_and_content() -> None:
    probe = _probe_module()
    digest = "sha256:" + "a" * 64
    base = {"feedRequestId": "feed-1", "policyDigest": digest}

    assert probe.check_envelope(
        {
            **base,
            "items": [{"postId": "post-1"}],
            "outcome": "content",
            "emptyReason": None,
        }
    ) == []
    assert probe.check_envelope(
        {
            **base,
            "items": [],
            "outcome": "empty",
            "emptyReason": "no_eligible_content",
        }
    ) == []
    assert "empty outcome requires a canonical emptyReason" in probe.check_envelope(
        {**base, "items": [], "outcome": "empty"}
    )
    assert "non-empty items require outcome=content" in probe.check_envelope(
        {
            **base,
            "items": [{"postId": "post-1"}],
            "outcome": "empty",
            "emptyReason": "no_eligible_content",
        }
    )


def test_probe_requires_actor_lease_bound_identity() -> None:
    probe = _probe_module()
    with (
        mock.patch.dict(
            "os.environ",
            {
                "QWQ_TEST_DATA_PRIMARY_ACTOR_ID": "",
                "QWQ_TEST_DATA_INSTANCE_ID": "",
                "QWQ_TEST_DATA_ACTOR_LEASE_DIGEST": "",
                "QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST": "",
            },
            clear=False,
        ),
        mock.patch.object(
            sys,
            "argv",
            ["probe", "--env", "gamma", "--base-url", "https://gamma.invalid"],
        ),
    ):
        try:
            probe.parse_args()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("probe accepted a missing ActorLease binding")

    digest = "sha256:" + "a" * 64
    with mock.patch.object(
        sys,
        "argv",
        [
            "probe",
            "--env",
            "gamma",
            "--base-url",
            "https://gamma.invalid",
            "--viewer-id",
            "managed-primary",
            "--test-data-instance-id",
            "instance-1",
            "--actor-lease-digest",
            digest,
            "--candidate-binding-digest",
            digest,
        ],
    ):
        args = probe.parse_args()
    assert args.viewer_id == "managed-primary"
    assert args.test_data_instance_id == "instance-1"
