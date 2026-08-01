from __future__ import annotations

import os
from pathlib import Path

from core import cursor_credentials as cc


def _key_file(tmp_path, value: str = "crsr_test_key"):
    path = tmp_path / "cursor_api_key"
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_resolve_reads_only_restricted_key_file(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path, "crsr_rotated_key_value")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_stale_transient_value")

    assert cc.resolve_cursor_api_key() == "crsr_rotated_key_value"
    assert cc.CURSOR_API_KEY_ENV not in os.environ


def test_environment_value_is_never_a_credential_source(monkeypatch):
    monkeypatch.delenv(cc.CURSOR_API_KEY_FILE_ENV, raising=False)
    monkeypatch.setattr(cc, "DEFAULT_CURSOR_API_KEY_FILE", Path("/missing/cursor_api_key"))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_env_only")
    assert cc.resolve_cursor_api_key() is None


def test_default_home_config_key_file_is_the_credential_source(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path, "crsr_default_key_value")
    monkeypatch.delenv(cc.CURSOR_API_KEY_FILE_ENV, raising=False)
    monkeypatch.setattr(cc, "DEFAULT_CURSOR_API_KEY_FILE", key_file)

    assert cc.cursor_api_key_file() == key_file
    assert cc.resolve_cursor_api_key() == "crsr_default_key_value"


def test_missing_empty_or_permissive_key_file_is_rejected(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(missing))
    assert cc.resolve_cursor_api_key() is None

    blank = _key_file(tmp_path, "")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(blank))
    assert cc.resolve_cursor_api_key() is None

    permissive = _key_file(tmp_path, "crsr_permissive")
    permissive.chmod(0o644)
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(permissive))
    assert cc.resolve_cursor_api_key() is None
    assert "0600" in cc.cursor_key_file_issues()[0]


def test_rotated_file_keeps_only_the_first_active_key_line(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path, "crsr_rotated_new\n#crsr_rotated_old\n")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))

    assert cc.cursor_key_file_issues() == []
    assert cc.resolve_cursor_api_key() == "crsr_rotated_new"
    assert cc.CURSOR_API_KEY_ENV not in os.environ


def test_surrounding_whitespace_and_leading_blank_lines_are_stripped(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path, "\n   \n   # leading indented comment\n\t crsr_padded_key \t\n")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))

    assert cc.resolve_cursor_api_key() == "crsr_padded_key"


def test_comment_only_file_reports_no_active_key(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path, "#crsr_retired_one\n# crsr_retired_two\n")
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))

    issues = cc.cursor_key_file_issues()
    assert issues and "no active key line" in issues[0]
    assert cc.resolve_cursor_api_key() is None


def test_key_file_issues_never_leak_key_material(tmp_path, monkeypatch):
    secret = "crsr_super_secret_value"
    permissive = _key_file(tmp_path, f"{secret}\n#{secret}_old\n")
    permissive.chmod(0o644)
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(permissive))

    issues = cc.cursor_key_file_issues()
    assert issues
    assert all(secret not in issue for issue in issues)


def test_parse_cursor_api_key_is_a_pure_function():
    assert cc.parse_cursor_api_key("crsr_a\n#crsr_b\n") == "crsr_a"
    assert cc.parse_cursor_api_key("#crsr_a\ncrsr_b") == "crsr_b"
    assert cc.parse_cursor_api_key("") is None
    assert cc.parse_cursor_api_key("\n\n  \n") is None
    assert cc.parse_cursor_api_key("   # only a comment") is None


def test_refresh_false_still_reads_the_key_file_without_environment_fallback(tmp_path, monkeypatch):
    key_file = _key_file(tmp_path)
    monkeypatch.setenv(cc.CURSOR_API_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(cc.CURSOR_API_KEY_ENV, "crsr_transient")
    assert cc.resolve_cursor_api_key(refresh=False) == "crsr_test_key"
    assert cc.CURSOR_API_KEY_ENV not in os.environ


def test_redactor_masks_the_actual_key_even_without_cursor_prefix():
    secret = "nonstandard-provider-secret-123"
    assert cc.redact_cursor_api_key(
        f"provider rejected {secret}",
        api_key=secret,
    ) == "provider rejected <redacted-cursor-key>"


def test_auth_error_classification_excludes_bridge_noise():
    assert cc.is_cursor_auth_error("rejected", status=401)
    assert cc.is_cursor_auth_error("plan_required for this model")
    assert cc.is_cursor_auth_error("anything", code="plan_required")
    assert not cc.is_cursor_auth_error(
        "cursor-sdk-bridge failed: Missing value for --tool-callback-auth-token"
    )
    assert not cc.is_cursor_auth_error("internal error", status=500)
