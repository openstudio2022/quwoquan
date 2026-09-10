"""已退役研究 CLI 的反向合同；不导入、不执行研究运行时。

spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-001
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.cli.probes import run_environment_integration_probe as probe

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "flag",
    [
        "--research-anonymous-convergence",
        "--research-consumer-readback",
        "--release-signed-media",
        "--test-auth-token",
    ],
)
def test_retired_cli__old_flags_rejected_before_any_request__local_contract(flag):
    command = [
        sys.executable, "-B",
        str(ROOT / "quwoquan_ops/cli/probes/run_environment_integration_probe.py"),
        "--env", "gamma", "--base-url", "https://api.invalid", flag,
    ]
    result = subprocess.run(command, text=True, capture_output=True, timeout=10)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_retired_cli__ambient_attestation_not_consumed__local_contract(monkeypatch):
    monkeypatch.setenv("RESEARCH_CONSUMER_ATTESTATION", "retired-secret")
    monkeypatch.setenv("GAMMA_TEST_AUTH_TOKEN", "ordinary-login-token")
    monkeypatch.setattr(sys, "argv", [
        "probe", "--env", "gamma", "--base-url", "https://api.invalid",
    ])
    probe.parse_args.cache_clear()
    try:
        args = probe.parse_args()
        assert args.test_auth_token == "ordinary-login-token"
        assert not any("research" in field for field in vars(args))
        assert not hasattr(probe, "SIGNED_MEDIA_CHECK_NAME")
        assert not hasattr(probe, "_research_anonymous_convergence_issue")
    finally:
        probe.parse_args.cache_clear()
