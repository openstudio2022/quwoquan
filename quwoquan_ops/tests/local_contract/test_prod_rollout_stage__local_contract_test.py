from __future__ import annotations

import unittest
import time
from unittest.mock import patch

from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENTS
from quwoquan_ops.cli.stackctl import (
    _prod_rollout_canary_contract,
    _read_prometheus_slo,
    _resolve_prod_rollout_stage,
)


class ProdRolloutStageContractTest(unittest.TestCase):
    def test_gray_is_only_a_prod_rollout_stage(self) -> None:
        self.assertNotIn("prod-gray", ENVIRONMENTS)
        self.assertEqual(
            _prod_rollout_canary_contract.__name__,
            "_prod_rollout_canary_contract",
        )

    def test_three_rollout_stages_are_reachable(self) -> None:
        self.assertEqual(_resolve_prod_rollout_stage("5"), "gray-initial")
        self.assertEqual(_resolve_prod_rollout_stage("25"), "carry-on")
        self.assertEqual(_resolve_prod_rollout_stage("100"), "full")

        self.assertEqual(
            _resolve_prod_rollout_stage("5", "gray-initial"),
            "gray-initial",
        )
        self.assertEqual(
            _resolve_prod_rollout_stage("50", "carry-on"),
            "carry-on",
        )
        self.assertEqual(_resolve_prod_rollout_stage("100", "full"), "full")

    def test_stage_and_step_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "full 必须与 step=100"):
            _resolve_prod_rollout_stage("50", "full")
        with self.assertRaisesRegex(ValueError, "step=100 只能使用 full"):
            _resolve_prod_rollout_stage("100", "carry-on")
        with self.assertRaisesRegex(ValueError, "1..100"):
            _resolve_prod_rollout_stage("0")

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

    def test_gray_initial_and_carry_on_canaries_match_stage_dimensions(self) -> None:
        canary = _prod_rollout_canary_contract("gray-initial")
        self.assertGreaterEqual(canary["requests"], 100)
        self.assertEqual(canary["path"], "/healthz")
        self.assertEqual(canary["rolloutStage"], "gray-initial")
        self.assertEqual(canary["expectedRoute"], "gray")
        self.assertEqual(
            canary["headers"]["X-Client-User-Id"],
            "ops-release-canary",
        )
        carry_on = _prod_rollout_canary_contract("carry-on")
        self.assertEqual(carry_on["rolloutStage"], "carry-on")
        self.assertEqual(carry_on["expectedRoute"], "gray")
        self.assertEqual(
            carry_on["headers"]["X-Client-User-Id"],
            "ops-release-canary",
        )

    def test_full_canary_does_not_replay_a_gray_routing_header(self) -> None:
        canary = _prod_rollout_canary_contract("full")
        self.assertEqual(canary["rolloutStage"], "full")
        self.assertEqual(canary["expectedRoute"], "stable")
        self.assertNotIn("X-Client-User-Id", canary["headers"])

    def test_pre_full_stage_requires_a_matching_dimension(self) -> None:
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
                    "stageDimensions": {
                        "gray-initial": {
                            "appVersions": [],
                            "userIds": [],
                            "provinces": [],
                            "carriers": [],
                        },
                    },
                },
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "do not match"):
                _prod_rollout_canary_contract("gray-initial")


if __name__ == "__main__":
    unittest.main()
