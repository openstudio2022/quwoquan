from __future__ import annotations

from pathlib import Path

import pytest

from content.execution import discard
from content.execution import workspace
from core.io import write_json


EXECUTION_ID = "20260725--travel-homepage-coverage--test-region-a--scale-002"


def test_frozen_target_archive_survives_execution_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "execution" / "0.plan" / "target_set.json"
    archive = tmp_path / "workspace" / f"{EXECUTION_ID}.json"
    payload = {
        "executionId": EXECUTION_ID,
        "selectionPolicy": "frozen",
        "sourceRef": "quwoquan_data/reference/travel/entities/china",
        "entityCatalogDigest": "sha256:" + "1" * 64,
        "targetCount": 1,
        "targetRefs": ["地点/景区/测试景区"],
        "targets": [{"name": "测试景区", "entityType": "地点/景区"}],
    }
    write_json(source, payload)
    monkeypatch.setattr(workspace, "execution_target_set_path", lambda _value: source)
    monkeypatch.setattr(workspace, "frozen_target_archive_path", lambda _value: archive)

    assert workspace.archive_frozen_target_set(EXECUTION_ID) == archive
    source.unlink()

    assert workspace.load_frozen_target_set(EXECUTION_ID) == payload


def test_discard_removes_only_inactive_execution_and_derived_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    transactions = tmp_path / "transactions"
    derived = transactions / f"{EXECUTION_ID}--entity-测试对象"
    derived.mkdir(parents=True)
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(discard, "transaction_workspace_root", lambda: transactions)
    monkeypatch.setattr(discard, "active_controller_issue", lambda _execution_id: None)
    monkeypatch.setattr(discard, "_active_execution_processes", lambda _execution_id: ())
    archived: list[str] = []
    monkeypatch.setattr(
        discard,
        "archive_frozen_target_set",
        lambda execution_id: archived.append(execution_id),
    )

    discard.discard_execution(EXECUTION_ID)

    assert not root.exists()
    assert not derived.exists()
    assert archived == [EXECUTION_ID]


def test_discard_rejects_live_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        discard,
        "active_controller_issue",
        lambda _execution_id: "GATE_BLOCK controller lease active for execution",
    )

    with pytest.raises(RuntimeError, match="controller lease active"):
        discard.discard_execution(EXECUTION_ID)


def test_discard_purges_service_owned_fleet_before_local_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / EXECUTION_ID
    (root / "evidence" / "reliabletask").mkdir(parents=True)
    calls: list[str] = []
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(discard, "transaction_workspace_root", lambda: tmp_path / "transactions")
    monkeypatch.setattr(discard, "active_controller_issue", lambda _execution_id: None)
    monkeypatch.setattr(discard, "_active_execution_processes", lambda _execution_id: ())
    monkeypatch.setattr(discard, "archive_frozen_target_set", lambda _execution_id: None)
    from content.execution import reliabletask_fleet

    monkeypatch.setattr(
        reliabletask_fleet,
        "discard_reliabletask_execution",
        lambda execution_id: calls.append(execution_id),
    )

    discard.discard_execution(EXECUTION_ID)

    assert calls == [EXECUTION_ID]
    assert not root.exists()


def test_task_execute_process_matcher_ignores_shell_text_and_matches_real_cli() -> None:
    shell_command = (
        'zsh -c "python3 quwoquan_data/scripts/cli.py task execute '
        f'--execution-id {EXECUTION_ID}"'
    )
    cli_command = (
        "/usr/bin/python3 quwoquan_data/scripts/cli.py task execute "
        f"--execution-id {EXECUTION_ID}"
    )

    assert not discard._is_task_execute_command(shell_command, EXECUTION_ID)
    assert discard._is_task_execute_command(cli_command, EXECUTION_ID)
