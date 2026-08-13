# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
"""config-slo 决策入口只接受 Prometheus 真实读回（OPEN-004 收口）。

- 调用方直接传 SLO 数字必须被拒绝；
- 缺 --prometheus-url 必须失败；
- 读回样本不足时决策为 pause（exit 10），不得放行；
- 读回成功时把监控数值透传给 gate 脚本，禁止任何人工覆写。
"""
from __future__ import annotations

import argparse
import subprocess
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl


def _config_slo_args(**overrides: str) -> argparse.Namespace:
    values = {
        "command": "verify",
        "target": "prod-hosted",
        "env": "",
        "kind": "config-slo",
        "profile": "baseline",
        "error_rate": "",
        "p95_ms": "",
        "redis_error_rate": "",
        "prometheus_url": "",
        "report_dir": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ConfigSloPrometheusReadbackLocalContractTest(unittest.TestCase):
    def test_caller_supplied_slo_numbers_are_rejected(self) -> None:
        result = stackctl._command_verify_config_slo(
            _config_slo_args(error_rate="0.001", p95_ms="120", redis_error_rate="0")
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("caller-supplied" in detail for detail in result["details"]),
            result["details"],
        )

    def test_missing_prometheus_url_fails_closed(self) -> None:
        result = stackctl._command_verify_config_slo(_config_slo_args())
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("--prometheus-url" in detail for detail in result["details"]),
            result["details"],
        )

    def test_insufficient_samples_pause_the_rollout_decision(self) -> None:
        with mock.patch.object(
            stackctl,
            "_read_prometheus_slo",
            side_effect=stackctl._SloSamplesInsufficient("42 < 300"),
        ):
            result = stackctl._command_verify_config_slo(
                _config_slo_args(prometheus_url="http://prometheus:9090")
            )
        self.assertEqual(result["exitCode"], 10)
        self.assertTrue(
            any("insufficient_samples" in detail for detail in result["details"]),
            result["details"],
        )

    def test_readback_values_flow_into_the_gate_script_unmodified(self) -> None:
        readback = {
            "source": "prometheus",
            "values": {
                "errorRate": 0.0004,
                "p95Ms": 145.5,
                "redisErrorRate": 0.0,
                "sampleCount": 12000,
            },
        }
        recorded_commands: list[list[str]] = []

        def _fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            recorded_commands.append(list(command))
            return subprocess.CompletedProcess(
                args=list(command), returncode=0, stdout="decision=proceed", stderr=""
            )

        with (
            mock.patch.object(stackctl, "_read_prometheus_slo", return_value=readback),
            mock.patch.object(stackctl, "run", side_effect=_fake_run),
        ):
            result = stackctl._command_verify_config_slo(
                _config_slo_args(prometheus_url="http://prometheus:9090")
            )
        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(len(recorded_commands), 1)
        gate_command = recorded_commands[0]
        self.assertIn("quwoquan_ops/cli/prod/config_release_slo_gate.sh", gate_command)
        self.assertEqual(
            gate_command[gate_command.index("--error-rate") + 1], "0.0004"
        )
        self.assertEqual(gate_command[gate_command.index("--p95-ms") + 1], "145.5")
        self.assertEqual(
            gate_command[gate_command.index("--redis-error-rate") + 1], "0.0"
        )


if __name__ == "__main__":
    unittest.main()
