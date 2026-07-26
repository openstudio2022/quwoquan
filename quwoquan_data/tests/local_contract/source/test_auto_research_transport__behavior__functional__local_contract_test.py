from __future__ import annotations

from dataclasses import replace

import pytest



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403
from content.source.research import network_io as network_io_mod  # noqa: E402



def test_auto_research_transport_requires_provider_owned_timeout():
    with pytest.raises(TypeError):
        network_io_mod.curl_json("https://example.test/api")
    assert network_io_mod.active_runtime_policy().curl_retries >= 1

def test_auto_research_curl_json_preserves_call_timeout_and_retry_floor(monkeypatch):
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = (
            b'{"ok": true}\n__QWQ_HTTP_META__200\thttps://example.test/api'
        )

    def _fake_run(cmd, *, capture_output, check):
        _ = (capture_output, check)
        calls.append(list(cmd))
        return _Proc()

    policy = network_io_mod.active_runtime_policy()
    monkeypatch.setattr(
        network_io_mod,
        "active_runtime_policy",
        lambda: replace(policy, curl_retries=0),
    )
    monkeypatch.setattr(network_io_mod.subprocess, "run", _fake_run)
    assert network_io_mod.curl_json("https://example.test/api", timeout=25) == {"ok": True}

    cmd = calls[0]
    assert cmd[cmd.index("--max-time") + 1] == "25"
    assert cmd[cmd.index("--retry") + 1] == "1"

def test_auto_research_curl_json_tolerates_non_utf8_stdout():
    original_run = network_io_mod.subprocess.run

    class _Proc:
        returncode = 0
        stdout = (
            b'{"ok": "\\xff"}\xff\n__QWQ_HTTP_META__200\t'
            b'https://example.test/bad-encoding'
        )

    def _fake_run(cmd, *, capture_output, check):
        _ = (cmd, capture_output, check)
        return _Proc()

    try:
        network_io_mod.subprocess.run = _fake_run
        assert network_io_mod.curl_json("https://example.test/bad-encoding", timeout=25) == {}
    finally:
        network_io_mod.subprocess.run = original_run
