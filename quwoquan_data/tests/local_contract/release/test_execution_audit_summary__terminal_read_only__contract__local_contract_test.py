from pathlib import Path

import pytest

from verify import audit_summary


@pytest.mark.parametrize("terminal_decision", ("interrupted", "superseded", "succeeded"))
def test_terminal_execution_summary_is_written_outside_protected_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_decision: str,
) -> None:
    execution_id = "20260830--travel-article-audit--china--pilot-001"
    execution_root = tmp_path / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    report_root = tmp_path / "data/local/workspace/reports"
    monkeypatch.setattr(audit_summary, "execution_root", lambda _execution: execution_root)
    monkeypatch.setattr(audit_summary, "OUTPUT_ARTIFACTS_ROOT", report_root)
    monkeypatch.setattr(audit_summary, "_pick_focus_entity", lambda *_args: None)
    monkeypatch.setattr(audit_summary, "_iter_entity_dirs", lambda _root: [])
    monkeypatch.setattr(audit_summary, "_iter_post_dirs", lambda _execution: [])
    monkeypatch.setattr(audit_summary, "_post_sample", lambda *_args: {})
    monkeypatch.setattr(audit_summary, "_entity_sample", lambda *_args: {})
    monkeypatch.setattr(audit_summary, "_manual_checklist", lambda *_args, **_kwargs: {"items": []})
    monkeypatch.setattr(
        audit_summary,
        "load_terminal_execution_evidence",
        lambda _root: type("Terminal", (), {"decision": terminal_decision})(),
    )
    before = sorted(item.relative_to(execution_root).as_posix() for item in execution_root.rglob("*"))

    written = audit_summary.write_execution_audit_summary(
        execution_id, roots=[], issues=[]
    )

    expected_root = report_root / "execution-audit" / execution_id
    assert written == (
        expected_root / "audit_summary.json",
        expected_root / "audit_summary.md",
    )
    assert all(item.is_file() for item in written)
    assert before == sorted(
        item.relative_to(execution_root).as_posix()
        for item in execution_root.rglob("*")
    )


def test_active_execution_summary_is_diagnostic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260830--travel-article-audit--china--pilot-001"
    execution_root = tmp_path / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    report_root = tmp_path / "data/local/workspace/reports"
    monkeypatch.setattr(audit_summary, "execution_root", lambda _execution: execution_root)
    monkeypatch.setattr(audit_summary, "OUTPUT_ARTIFACTS_ROOT", report_root)
    monkeypatch.setattr(audit_summary, "_pick_focus_entity", lambda *_args: None)
    monkeypatch.setattr(audit_summary, "_iter_entity_dirs", lambda _root: [])
    monkeypatch.setattr(audit_summary, "_iter_post_dirs", lambda _execution: [])
    monkeypatch.setattr(audit_summary, "_post_sample", lambda *_args: {})
    monkeypatch.setattr(audit_summary, "_entity_sample", lambda *_args: {})
    monkeypatch.setattr(audit_summary, "_manual_checklist", lambda *_args, **_kwargs: {"items": []})
    monkeypatch.setattr(audit_summary, "load_terminal_execution_evidence", lambda _root: None)

    before = sorted(
        item.relative_to(execution_root).as_posix()
        for item in execution_root.rglob("*")
    )

    written = audit_summary.write_execution_audit_summary(
        execution_id, roots=[], issues=[]
    )

    expected_root = report_root / "execution-audit" / execution_id
    assert written == (
        expected_root / "audit_summary.json",
        expected_root / "audit_summary.md",
    )
    assert all(item.is_file() for item in written)
    assert before == sorted(
        item.relative_to(execution_root).as_posix()
        for item in execution_root.rglob("*")
    )
