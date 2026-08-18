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

def test_auto_research_curl_json_survives_non_utf8_stdout_and_reports_undecodable_body():
    """非法字节不得炸成 UnicodeDecodeError，但也不得被读成「主机说没有内容」。

    HTTP 200 配一个解不出 JSON 的正文，说明我们要的东西没拿到。上抛才让调用方能
    重试或记缺口；返回空对象会把它伪装成一次成功的空答复。
    """
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
        with pytest.raises(network_io_mod.NetworkFetchError) as caught:
            network_io_mod.curl_json("https://example.test/bad-encoding", timeout=25)
    finally:
        network_io_mod.subprocess.run = original_run
    # 走到 JSON 解析才抛，证明解码本身已容错，没有死在非法字节上。
    assert caught.value.reason == "response body is not JSON"
    assert caught.value.status_code == 200
