from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403



def test_auto_research_curl_defaults_support_public_api_scale_probe():
    assert research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS >= 25
    assert research_plan_mod._AUTO_RESEARCH_CURL_RETRIES >= 1

def test_auto_research_curl_json_preserves_call_timeout_and_retry_floor():
    original_timeout = research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS
    original_retries = research_plan_mod._AUTO_RESEARCH_CURL_RETRIES
    original_run = research_plan_mod.subprocess.run
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = b'{"ok": true}'

    def _fake_run(cmd, *, capture_output, check):
        _ = (capture_output, check)
        calls.append(list(cmd))
        return _Proc()

    try:
        research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = 7
        research_plan_mod._AUTO_RESEARCH_CURL_RETRIES = 0
        research_plan_mod.subprocess.run = _fake_run
        assert research_plan_mod._curl_json("https://example.test/api", timeout=25) == {"ok": True}
    finally:
        research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = original_timeout
        research_plan_mod._AUTO_RESEARCH_CURL_RETRIES = original_retries
        research_plan_mod.subprocess.run = original_run

    cmd = calls[0]
    assert cmd[cmd.index("--max-time") + 1] == "25"
    assert cmd[cmd.index("--retry") + 1] == "1"

def test_auto_research_curl_json_tolerates_non_utf8_stdout():
    original_run = research_plan_mod.subprocess.run

    class _Proc:
        returncode = 0
        stdout = b'{"ok": "\\xff"}\xff'

    def _fake_run(cmd, *, capture_output, check):
        _ = (cmd, capture_output, check)
        return _Proc()

    try:
        research_plan_mod.subprocess.run = _fake_run
        assert research_plan_mod._curl_json("https://example.test/bad-encoding") == {}
    finally:
        research_plan_mod.subprocess.run = original_run

