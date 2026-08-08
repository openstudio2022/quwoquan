"""Canonical data output root ownership contract."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from core import paths as paths_mod


_ENV_KEYS = (
    "QWQ_DATA_ROOT",
    "QWQ_OUTPUT_ROOT",
    "QWQ_PUBLISH_ROOT",
    "QWQ_SCHEMA_ROOT",
    "QWQ_RUNTIME_ROOT",
    "QWQ_RELEASE_ROOT",
    "QWQ_COMMITTED_TASKS_ROOT",
)
_BASELINE = {key: os.environ.get(key) for key in _ENV_KEYS}
EXECUTION_ID = "20260711--travel-homepage-output--test-region-a--pilot-001"


def _reload(monkeypatch, **env: str):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(paths_mod)


@pytest.fixture()
def restore_paths(monkeypatch):
    yield
    monkeypatch.undo()
    for key, value in _BASELINE.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(paths_mod)


def test_default_output_root_is_repo_local_and_gitignored():
    root = paths_mod.default_output_root()
    assert root == paths_mod.REPO_ROOT / ".qwq_output"
    assert ".qwq_output/" in (paths_mod.REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


def test_output_root_has_tasks_releases_and_disposable_local_only(tmp_path, monkeypatch, restore_paths):
    output = tmp_path / ".qwq_output"
    loaded = _reload(monkeypatch, QWQ_OUTPUT_ROOT=str(output))
    assert loaded.DATA_OUTPUT_ROOT == output / "data"
    assert loaded.DATA_EXECUTIONS_ROOT == output / "data/tasks"
    assert loaded.RELEASE_ROOT == output / "data/releases"
    assert loaded.DATA_LOCAL_ROOT == output / "data/local"
    assert loaded.OUTPUT_ARTIFACTS_ROOT == output / "data/local/workspace/reports"
    assert loaded.CAMPAIGN_SCALE_EVIDENCE_ROOT == (
        output / "data/local/workspace/research-scale/campaign-evidence"
    )
    assert loaded.RESEARCH_SCALE_PROMOTIONS_ROOT == (
        output / "data/local/workspace/research-scale/promotions"
    )
    alternate_output = tmp_path / "alternate-output"
    assert loaded.campaign_scale_evidence_root(output_root=alternate_output) == (
        alternate_output / "data/local/workspace/research-scale/campaign-evidence"
    )
    assert loaded.research_scale_promotions_root(output_root=alternate_output) == (
        alternate_output / "data/local/workspace/research-scale/promotions"
    )
    assert loaded.PUBLISH_ROOT == loaded._REPO_DATA_ROOT / "publish"


def test_data_root_does_not_relocate_runtime_output(tmp_path, monkeypatch, restore_paths):
    isolated = tmp_path / "isolated"
    loaded = _reload(monkeypatch, QWQ_DATA_ROOT=str(isolated))
    assert loaded.DATA_EXECUTIONS_ROOT == loaded.REPO_ROOT / ".qwq_output/data/tasks"
    assert loaded.RELEASE_ROOT == loaded.REPO_ROOT / ".qwq_output/data/releases"
    assert loaded.PUBLISH_ROOT == isolated / "publish"
    assert loaded.SCHEMA_ROOT == loaded._REPO_DATA_ROOT / "schema"


def test_execution_id_is_the_only_runtime_address(tmp_path, monkeypatch, restore_paths):
    loaded = _reload(monkeypatch, QWQ_OUTPUT_ROOT=str(tmp_path))
    assert loaded.execution_root(EXECUTION_ID) == tmp_path / "data/tasks" / EXECUTION_ID
    with pytest.raises(TypeError):
        loaded.execution_root(EXECUTION_ID, "retired-batch")
    with pytest.raises(ValueError, match="valid executionId"):
        loaded.execution_root("旅行/地域/test-region-a/旧任务")


def test_retired_output_environment_variables_are_ignored(tmp_path, monkeypatch, restore_paths):
    output = tmp_path / "current"
    loaded = _reload(
        monkeypatch,
        QWQ_OUTPUT_ROOT=str(output),
        QWQ_RUNTIME_ROOT=str(tmp_path / "retired-runtime"),
        QWQ_RELEASE_ROOT=str(tmp_path / "retired-release"),
        QWQ_COMMITTED_TASKS_ROOT=str(tmp_path / "retired-tasks"),
    )
    assert loaded.DATA_EXECUTIONS_ROOT == output / "data/tasks"
    assert loaded.RELEASE_ROOT == output / "data/releases"
