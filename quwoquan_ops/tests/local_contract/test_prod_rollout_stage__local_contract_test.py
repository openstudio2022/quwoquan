from __future__ import annotations

import unittest
import time
from unittest.mock import patch

from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENTS
from quwoquan_ops.cli.stackctl import (
    _prod_rollout_contract,
    _read_prometheus_slo,
    _resolve_prod_rollout_stage,
    build_parser,
)


class ProdRolloutStageContractTest(unittest.TestCase):
    def test_rollout_is_only_a_prod_stage(self) -> None:
        self.assertNotIn("prod-gray", ENVIRONMENTS)
        self.assertEqual(
            _prod_rollout_contract.__name__,
            "_prod_rollout_contract",
        )

    def test_five_rollout_stages_are_reachable(self) -> None:
        for step, stage in (("0", "canary"), ("5", "5"), ("20", "20"), ("50", "50"), ("100", "100")):
            self.assertEqual(_resolve_prod_rollout_stage(step), stage)
            self.assertEqual(_resolve_prod_rollout_stage(step, stage), stage)

    def test_stage_and_step_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "不匹配"):
            _resolve_prod_rollout_stage("50", "100")
        with self.assertRaisesRegex(ValueError, "0/5/20/50/100"):
            _resolve_prod_rollout_stage("25")

    def test_slo_gate_reads_prometheus_and_policy_window(self) -> None:
        def query(_base_url: str, expression: str, **_kwargs: object) -> float:
            if "increase(http_server_requests_total" in expression:
                return 1000
            return 0.005

        with patch("quwoquan_ops.cli.stackctl._prometheus_query_value", side_effect=query):
            result = _read_prometheus_slo(
                "http://prometheus:9090",
                "content-service",
                deadline_epoch=int(time.time()) + 60,
            )

        self.assertEqual(result["source"], "prometheus")
        self.assertEqual(result["window"], "5m")
        self.assertGreaterEqual(result["values"]["sampleCount"], result["minimumSamples"])
        self.assertIn("[5m]", result["queries"]["p95Ms"])

    def test_slo_readback_rejects_insufficient_samples(self) -> None:
        def query(_base_url: str, expression: str, **_kwargs: object) -> float:
            if "increase(http_server_requests_total" in expression:
                return 1
            return 0

        with patch("quwoquan_ops.cli.stackctl._prometheus_query_value", side_effect=query):
            with self.assertRaisesRegex(RuntimeError, "insufficient samples"):
                _read_prometheus_slo(
                    "http://prometheus:9090",
                    "content-service",
                    deadline_epoch=int(time.time()) + 60,
                )

    def test_post_100_soak_can_override_the_prometheus_query_window(self) -> None:
        def query(_base_url: str, expression: str, **_kwargs: object) -> float:
            if "increase(http_server_requests_total" in expression:
                return 1000
            return 0.005

        with patch("quwoquan_ops.cli.stackctl._prometheus_query_value", side_effect=query):
            result = _read_prometheus_slo(
                "http://prometheus:9090",
                "content-service",
                deadline_epoch=int(time.time()) + 60,
                window_override="24h",
            )

        self.assertEqual(result["window"], "24h")
        self.assertIn("[24h]", result["queries"]["p95Ms"])

    def test_canary_and_percentage_stages_bind_immutable_campaign(self) -> None:
        canary = _prod_rollout_contract("canary")
        self.assertGreaterEqual(canary["requests"], 100)
        self.assertEqual(canary["path"], "/healthz")
        self.assertEqual(canary["rolloutStage"], "canary")
        self.assertEqual(canary["expectedRoute"], "candidate")
        self.assertRegex(canary["routingPolicyDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(canary["platforms"]["values"], ["android", "ios", "web"])
        for stage, basis_points in (("5", 500), ("20", 2000), ("50", 5000)):
            contract = _prod_rollout_contract(stage)
            self.assertEqual(contract["rolloutStage"], stage)
            self.assertEqual(contract["basisPoints"], basis_points)
            self.assertEqual(contract["campaignId"], canary["campaignId"])
            self.assertEqual(contract["candidateDigest"], canary["candidateDigest"])

    def test_deploy_parser_accepts_only_an_explicit_promotion_evidence_path(self) -> None:
        args = build_parser().parse_args(
            [
                "deploy",
                "--target",
                "prod-hosted",
                "--promotion-evidence",
                "/protected/rollout/5.json",
            ]
        )
        self.assertEqual(args.promotion_evidence, "/protected/rollout/5.json")

    def test_100_stage_targets_stable_after_promotion(self) -> None:
        canary = _prod_rollout_contract("100")
        self.assertEqual(canary["rolloutStage"], "100")
        self.assertEqual(canary["expectedRoute"], "stable")

    def test_missing_stage_policy_fails_closed(self) -> None:
        with patch(
            "quwoquan_ops.cli.stackctl.load_json_yaml",
            return_value={
                "policy": {
                    "enabled": True,
                    "syntheticCanary": {
                        "path": "/healthz",
                        "requests": 100,
                        "headers": {"X-Client-User-Id": "ops-release-canary"},
                    },
                    "subjectKind": "device_actor",
                    "campaignId": "campaign-1",
                    "candidateDigest": "sha256:" + "a" * 64,
                    "allocationKeyId": "key-1",
                    "stages": {},
                },
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "missing stage"):
                _prod_rollout_contract("canary")

    def test_deployment_candidate_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            _prod_rollout_contract(
                "canary",
                expected_candidate_digest="sha256:" + "f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
