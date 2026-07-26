"""The execution identity guard rejects retired task/batch parameter identities."""
from __future__ import annotations

from verify import verify_execution_identity_purity as identity_gate


def test_execution_identity_purity__legacy_parameters__contract__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    scripts_root = tmp_path / "scripts"
    scripts_root.mkdir()
    (scripts_root / "legacy.py").write_text(
        "def load(\n    task: str,\n    batch: str,\n) -> None:\n    return None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(identity_gate, "SCRIPTS_ROOT", scripts_root)
    monkeypatch.setattr(identity_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(identity_gate, "ACTIVE_TEXT_ROOTS", ())

    issues = identity_gate.execution_identity_purity_issues()

    assert any("task" in issue for issue in issues)
    assert any("batch" in issue for issue in issues)
