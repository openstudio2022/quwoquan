from __future__ import annotations

import subprocess
from pathlib import Path

from verify.verify_cursor_credential_contract import cursor_credential_contract_issues


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@quwoquan.local"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Quwoquan Test"], cwd=root, check=True)


def test_credential_gate_rejects_retired_alias_without_matching_itself(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    retired_alias = "QWQ_CURSOR_API_KEY" + "FILE"
    (tmp_path / "bad.py").write_text(f'{retired_alias} = "secret"\n', encoding="utf-8")
    subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, check=True)

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert len(issues) == 1
    assert "bad.py" in issues[0]


def test_credential_gate_accepts_repo_without_retired_alias(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "good.py").write_text('KEY_FILE = "external"\n', encoding="utf-8")
    subprocess.run(["git", "add", "good.py"], cwd=tmp_path, check=True)

    assert cursor_credential_contract_issues(repo_root=tmp_path) == []


def test_credential_gate_rejects_sdk_environment_fallback(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    scripts = tmp_path / "quwoquan_data" / "scripts"
    scripts.mkdir(parents=True)
    fallback = "allow_api_key_env_fallback" + "=True"
    (scripts / "bad.py").write_text(f"Client.launch_bridge({fallback})\n", encoding="utf-8")
    subprocess.run(["git", "add", "quwoquan_data/scripts/bad.py"], cwd=tmp_path, check=True)

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert len(issues) == 1
    assert "forbidden Cursor credential environment fallback" in issues[0]
