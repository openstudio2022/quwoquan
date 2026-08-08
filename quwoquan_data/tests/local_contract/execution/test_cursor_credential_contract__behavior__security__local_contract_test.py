from __future__ import annotations

import subprocess
from pathlib import Path

from verify.verify_cursor_credential_contract import cursor_credential_contract_issues


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@quwoquan.local"], cwd=root, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Quwoquan Test"], cwd=root, check=True
    )


def test_credential_gate_rejects_retired_alias_without_matching_itself(
    tmp_path: Path,
) -> None:
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
    (scripts / "bad.py").write_text(
        f"Client.launch_bridge({fallback})\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "quwoquan_data/scripts/bad.py"], cwd=tmp_path, check=True
    )

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert issues
    assert any(
        "forbidden Cursor credential environment fallback" in issue for issue in issues
    )


def test_credential_gate_rejects_sdk_managed_bridge_with_callback_token_argv(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    scripts = tmp_path / "quwoquan_data" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bad.py").write_text(
        "Client.launch_" + "bridge(workspace='.')\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "quwoquan_data/scripts/bad.py"], cwd=tmp_path, check=True
    )

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert len(issues) == 1
    assert "forbidden Cursor SDK callback-token argv transport" in issues[0]


def test_credential_gate_rejects_runtime_child_environment_passthrough(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    scripts = tmp_path / "quwoquan_data" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bad.py").write_text(
        "child_env = os.environ." + "copy()\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "quwoquan_data/scripts/bad.py"], cwd=tmp_path, check=True
    )

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert len(issues) == 1
    assert "forbidden Cursor runtime child environment passthrough" in issues[0]


def test_credential_gate_requires_canonical_runtime_child_sanitizer(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    handler = (
        tmp_path
        / "quwoquan_data"
        / "scripts"
        / "content"
        / "execution"
        / "preflight"
        / "handler.py"
    )
    handler.parent.mkdir(parents=True)
    handler.write_text(
        "def _preflight_in_python():\n    child_env = dict(os.environ)\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", handler.relative_to(tmp_path).as_posix()],
        cwd=tmp_path,
        check=True,
    )

    issues = cursor_credential_contract_issues(repo_root=tmp_path)

    assert issues == [
        "forbidden Cursor runtime child sanitizer missing: "
        "quwoquan_data/scripts/content/execution/preflight/handler.py"
    ]
