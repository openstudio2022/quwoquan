from __future__ import annotations

from _common import cursor_credentials as cc


def test_resolve_prefers_key_file_and_writes_back_env(tmp_path, monkeypatch):
    key_file = tmp_path / "cursor_api_key"
    key_file.write_text("  crsr_rotated_key_value\n", encoding="utf-8")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_stale_env_value")

    resolved = cc.resolve_cursor_api_key()

    assert resolved == "crsr_rotated_key_value"
    # 单一真相源回写 env，使随后启动的 bridge 子进程继承轮换后的 key。
    import os

    assert os.environ[cc.CURSOR_API_KEY_ENV] == "crsr_rotated_key_value"


def test_resolve_falls_back_to_env_when_no_file(tmp_path, monkeypatch):
    monkeypatch.delenv(cc.CURSOR_API_KEY_FILE_ENV, raising=False)
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_env_only")
    assert cc.resolve_cursor_api_key() == "crsr_env_only"


def test_resolve_ignores_empty_or_missing_file(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist"
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(missing))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_env_fallback")
    assert cc.resolve_cursor_api_key() == "crsr_env_fallback"

    blank = tmp_path / "blank"
    blank.write_text("\n\n", encoding="utf-8")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(blank))
    assert cc.resolve_cursor_api_key() == "crsr_env_fallback"


def test_resolve_refresh_false_skips_file(tmp_path, monkeypatch):
    key_file = tmp_path / "cursor_api_key"
    key_file.write_text("crsr_file_value", encoding="utf-8")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_cached_env")
    assert cc.resolve_cursor_api_key(refresh=False) == "crsr_cached_env"


def test_auth_error_detected_by_status_code_and_message():
    assert cc.is_cursor_auth_error("rejected", status=401)
    assert cc.is_cursor_auth_error("rejected", status=403)
    assert cc.is_cursor_auth_error("Unauthorized: API key invalid")
    assert cc.is_cursor_auth_error("plan_required for this model")
    assert cc.is_cursor_auth_error("anything", code="plan_required")
    assert cc.is_cursor_auth_error("Invalid API key supplied")
    assert cc.is_cursor_auth_error("Your API key expired")


def test_bridge_noise_is_not_classified_as_auth_error():
    # 这些是 retryable bridge 噪声，绝不能被误判为凭据失效（否则会停止重试）。
    assert not cc.is_cursor_auth_error(
        "Bridge exited before discovery with status 1: "
        "cursor-sdk-bridge failed: Error: Missing value for --tool-callback-auth-token"
    )
    assert not cc.is_cursor_auth_error(
        "Bridge request failed: ConnectError: [Errno 61] Connection refused"
    )
    assert not cc.is_cursor_auth_error("internal error", status=500)
    assert not cc.is_cursor_auth_error("CURSOR_API_KEY missing")
