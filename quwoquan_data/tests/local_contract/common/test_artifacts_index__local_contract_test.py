"""artifacts 摘要索引层契约（index-first + 回指，数据输出规范）。

- `QWQ_OUTPUT_ROOT/data/runs/**` 只做镜像索引，不承载权威证据；
- 任意 summary 目录必须有 `index.json`，且回指 runtimeBatchRoot/taskId/
  publishRoot/releaseId/phase/contentType/supplyMode/sourceKey/maturity；
- 回指字段从 batch_manifest / paths 真相源构造，禁止手写第二套。
"""
from __future__ import annotations

import importlib

from _common import paths as paths_mod
from _common import artifacts_index as ai
from _common.batch_manifest import write_batch_manifest
from _common.io import read_json, write_json


TASK = "旅行/地域/测试省/景区/索引契约"


def test_artifacts_layout_dims_are_first_level():
    d = ai.content_run_artifacts_dir("e2e", "article", "b1")
    assert d == paths_mod.OUTPUT_ARTIFACTS_ROOT / "content_runs" / "e2e" / "article" / "b1"
    assert ai.pool_artifacts_dir("creator", "b2") == (
        paths_mod.OUTPUT_ARTIFACTS_ROOT / "pools" / "creator" / "b2"
    )
    assert ai.app_artifacts_dir("local-gamma") == (
        paths_mod.OUTPUT_ARTIFACTS_ROOT / "app" / "local-gamma"
    )


def test_pool_and_app_kinds_are_closed_enums():
    import pytest

    with pytest.raises(ValueError):
        ai.pool_artifacts_dir("bot", "b")
    with pytest.raises(ValueError):
        ai.app_artifacts_dir("random-place")


def test_index_entry_backrefs_come_from_batch_manifest(monkeypatch):
    batch_id = "artifacts_index_entry"
    monkeypatch.setenv("QWQ_BATCH_PHASE", "e2e")
    monkeypatch.setenv("QWQ_BATCH_CONTENT_TYPE", "article")
    monkeypatch.setenv("QWQ_BATCH_SUPPLY_MODE", "site_primary")
    write_batch_manifest(TASK, batch_id, command="task_run", source_key="site_demo")
    entry = ai.build_artifacts_index_entry(TASK, batch_id, maturity="pilot")
    assert entry["runtimeBatchRoot"] == str(paths_mod.batch_root(TASK, batch_id))
    assert entry["taskId"] == TASK
    assert entry["publishRoot"] == str(paths_mod.PUBLISH_ROOT)
    assert entry["phase"] == "e2e"
    assert entry["contentType"] == "article"
    assert entry["supplyMode"] == "site_primary"
    assert entry["sourceKey"] == "site_demo"
    assert entry["maturity"] == "pilot"
    for field in ai.ARTIFACTS_INDEX_REQUIRED_FIELDS:
        assert field in entry, field


def test_register_report_writes_index_inside_artifacts_root(monkeypatch):
    batch_id = "artifacts_index_register"
    monkeypatch.setenv("QWQ_BATCH_PHASE", "e2e")
    monkeypatch.setenv("QWQ_BATCH_CONTENT_TYPE", "article")
    monkeypatch.setenv("QWQ_BATCH_SUPPLY_MODE", "site_primary")
    write_batch_manifest(TASK, batch_id, command="task_run", source_key="site_demo")
    report_dir = ai.content_run_artifacts_dir("e2e", "article", batch_id)
    report_path = report_dir / "scale_readiness.json"
    write_json(report_path, {"passed": True})
    index_path = ai.register_artifact_report(
        report_path, task_id=TASK, batch_id=batch_id, report_kind="scale_readiness"
    )
    assert index_path.is_file()
    data = read_json(index_path)
    assert data["schema"] == ai.ARTIFACTS_INDEX_SCHEMA
    assert data["runtimeBatchRoot"] == str(paths_mod.batch_root(TASK, batch_id))
    assert [r["file"] for r in data["reports"]] == ["scale_readiness.json"]
    # 幂等：重复登记同一报告不产生重复条目。
    ai.register_artifact_report(
        report_path, task_id=TASK, batch_id=batch_id, report_kind="scale_readiness"
    )
    assert [r["file"] for r in read_json(index_path)["reports"]] == ["scale_readiness.json"]
    assert ai.artifacts_index_issues(index_path) == []


def test_register_skips_paths_outside_artifacts_root(tmp_path):
    report_path = tmp_path / "some_report.json"
    write_json(report_path, {"passed": True})
    index_path = ai.register_artifact_report(
        report_path, task_id=TASK, batch_id="whatever", report_kind="scale_readiness"
    )
    # batch/_shared 等权威证据面不属于摘要索引层，不落 index.json。
    assert not index_path.exists()


def test_index_issues_flag_missing_backrefs(tmp_path):
    index_path = tmp_path / "index.json"
    issues = ai.artifacts_index_issues(index_path)
    assert issues and "缺 index.json" in issues[0]
    write_json(index_path, {"schema": ai.ARTIFACTS_INDEX_SCHEMA, "taskId": "t"})
    issues = ai.artifacts_index_issues(index_path)
    assert any("runtimeBatchRoot" in i for i in issues)
    assert any("phase" in i for i in issues)
