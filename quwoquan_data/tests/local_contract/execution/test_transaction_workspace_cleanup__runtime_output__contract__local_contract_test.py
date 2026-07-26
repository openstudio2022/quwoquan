"""Execution reset must remove every disposable transaction artifact with its task."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core import paths as core_paths  # noqa: E402
from content.execution import workspace  # noqa: E402


EXECUTION_ID = "20260722--travel-homepage-generate--test-region-a--pilot-001"
TRANSACTION_ID = f"{EXECUTION_ID}--entity-0123456789ab"


def test_orphaned_transaction_workspace_blocks_new_execution_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executions = tmp_path / "tasks"
    transactions = tmp_path / "local/workspace/object-transactions"
    (transactions / TRANSACTION_ID).mkdir(parents=True)
    monkeypatch.setattr(core_paths, "DATA_EXECUTIONS_ROOT", executions)
    monkeypatch.setattr(core_paths, "DATA_LOCAL_ROOT", tmp_path / "local")

    assert workspace.orphaned_transaction_workspaces() == (transactions / TRANSACTION_ID,)
    with pytest.raises(ValueError, match="output reset is incomplete"):
        workspace.require_clean_transaction_workspace(EXECUTION_ID)


def test_transaction_workspace_is_not_orphaned_while_execution_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executions = tmp_path / "tasks"
    transactions = tmp_path / "local/workspace/object-transactions"
    (executions / EXECUTION_ID).mkdir(parents=True)
    (transactions / TRANSACTION_ID).mkdir(parents=True)
    monkeypatch.setattr(core_paths, "DATA_EXECUTIONS_ROOT", executions)
    monkeypatch.setattr(core_paths, "DATA_LOCAL_ROOT", tmp_path / "local")

    assert workspace.orphaned_transaction_workspaces() == ()
    workspace.require_clean_transaction_workspace(EXECUTION_ID)
