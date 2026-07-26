from __future__ import annotations

from pathlib import Path

from verify import verify_data_layout


def test_data_layout_rejects_nested_output_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    data_root = repo_root / "quwoquan_data"
    nested_output = data_root / ".qwq_output"
    nested_output.mkdir(parents=True)
    schema_root = data_root / "schema"
    for name in verify_data_layout.ALLOWED_SCHEMA_DIRECTORIES:
        (schema_root / name).mkdir(parents=True)
    scripts_root = data_root / "scripts"
    scripts_root.mkdir(parents=True)
    (scripts_root / "cli.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(verify_data_layout, "ROOT", repo_root)
    monkeypatch.setattr(verify_data_layout, "DATA_ROOT", data_root)
    monkeypatch.setattr(verify_data_layout, "_tracked_files", lambda: [])

    issues = verify_data_layout.data_layout_issues()

    assert any(
        "quwoquan_data/.qwq_output" in issue
        and "generated/cache directory" in issue
        for issue in issues
    )
