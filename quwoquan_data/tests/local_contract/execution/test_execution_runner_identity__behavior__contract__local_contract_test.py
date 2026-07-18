from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution import runner


EXECUTION_ID = "20260714--travel-homepage-coverage--cn-zhejiang--canary-001"
RECIPE = {
    "execution": {
        "runtime": "local",
        "model": "composer",
        "modelFamily": "composer",
        "reviewModel": "gpt-5.5",
        "reviewModelFamily": "gpt",
    }
}


def test_execution_runner_passes_only_execution_id_to_internal_controller(monkeypatch):
    observed: dict[str, object] = {}

    monkeypatch.setattr(runner, "preflight_execution_models", lambda _recipe: {})
    monkeypatch.setattr(runner, "_prepare_execution", lambda execution_id: observed.setdefault("prepared", execution_id))
    monkeypatch.setattr(runner, "prepare_execution_qualification", lambda execution_id: observed.setdefault("qualified", execution_id))
    monkeypatch.setattr(
        runner,
        "run_controlled_execution",
        lambda request: observed.setdefault("run", request),
    )

    runner.run_execution(EXECUTION_ID, RECIPE)

    assert observed["prepared"] == EXECUTION_ID
    assert observed["qualified"] == EXECUTION_ID
    args = observed["run"]
    assert getattr(args, "execution_id") == EXECUTION_ID
    assert not hasattr(args, "task")
    assert not hasattr(args, "batch")


def test_execution_runner_carries_an_audited_checkpoint_recovery(monkeypatch):
    observed: dict[str, object] = {}

    monkeypatch.setattr(runner, "preflight_execution_models", lambda _recipe: {})
    monkeypatch.setattr(runner, "_prepare_execution", lambda _execution_id: None)
    monkeypatch.setattr(runner, "prepare_execution_qualification", lambda _execution_id: None)
    monkeypatch.setattr(
        runner,
        "run_controlled_execution",
        lambda request: observed.setdefault("run", request),
    )

    runner.run_execution(
        EXECUTION_ID,
        RECIPE,
        recover_stage="build_homepage",
        recovery_reason="corrected managed agent subprocess import root",
    )

    args = observed["run"]
    assert getattr(args, "recover_stage").value == "build_homepage"
    assert getattr(args, "recovery_reason") == "corrected managed agent subprocess import root"
