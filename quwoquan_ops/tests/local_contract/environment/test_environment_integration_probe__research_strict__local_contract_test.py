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


@pytest.mark.parametrize(
    "check_name", ["research_anonymous_convergence", "release_signed_media"]
)
def test_retired_cli__research_only_check_is_explicitly_rejected__local_contract(
    monkeypatch, check_name,
):
    monkeypatch.delenv("DATA_RELEASE_READINESS_RECEIPT", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "probe", "--env", "gamma", "--base-url", "https://api.invalid",
        "--only-check", check_name,
    ])
    probe.parse_args.cache_clear()
    try:
        args = probe.parse_args()
        monkeypatch.setattr(
            probe, "request",
            lambda *_args, **_kwargs: pytest.fail("退役专轨不得发送请求"),
        )
        report = probe.run_checks(args)
        assert report["status"] == "failed"
        assert report["checks"] == []
        assert report["findings"] == [
            "GATE_BLOCK: unknown integration check(s): " + check_name
        ]
    finally:
        probe.parse_args.cache_clear()


def test_retired_cli__default_path_keeps_ordinary_auth_and_public_feeds__local_contract(
    monkeypatch,
):
    monkeypatch.delenv("DATA_RELEASE_READINESS_RECEIPT", raising=False)
    monkeypatch.setenv("GAMMA_TEST_AUTH_TOKEN", "ordinary-login-token")
    monkeypatch.setenv("RESEARCH_CONSUMER_ATTESTATION", "retired-secret")
    monkeypatch.setattr(sys, "argv", [
        "probe", "--env", "gamma", "--base-url", "https://api.invalid",
    ])
    probe.parse_args.cache_clear()
    try:
        args = probe.parse_args()
        checks = {check["name"]: check for check in probe.build_checks(args)}
        assert args.only_check == []
        assert {"gateway_healthz", "app_config", "content_feed",
                "homepage_recommend", "entity_homepage_search",
                "global_search", "user_sync"} <= set(checks)
        assert checks["user_sync"]["headers"]["Authorization"] == (
            "Bearer ordinary-login-token"
        )
        for name in ("content_feed", "homepage_recommend"):
            assert "Authorization" not in checks[name]["headers"]
        assert not any("research" in name or "signed_media" in name for name in checks)
    finally:
        probe.parse_args.cache_clear()
