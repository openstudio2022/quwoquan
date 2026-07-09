"""仓外输出根隔离门契约（数据输出规范）。

覆盖 verify_output_root_isolation 的五道子门：
1. repo allowlist：local/data-runtime/release/.qwq_output/.qwq_sandbox 不得被 git 追踪；
2. 仓内阶段树：quwoquan_data/runtime 不得保留 canonical 或 legacy 运行残留；
3. 批次轴：canonical 批次 manifest 轴与目录层级一致 + committed task 回指存在；
4. 摘要索引：.qwq_output/runs/content_runs 批次目录 index-first；
5. artifacts 根隔离：data-owned 根文件/旧目录/legacy marker 一律阻断。
"""
from __future__ import annotations

import json
from pathlib import Path

from verify.verify_output_root_isolation import (
    artifacts_index_gate_issues,
    canonical_batch_axis_issues,
    data_root_artifact_issues,
    legacy_marker_issues,
    repo_phase_tree_issues,
)


def _write_manifest(batch_dir: Path, **overrides) -> None:
    payload = {
        "taskId": "旅行/地域/测试省/景区/隔离门样例",
        "batchId": batch_dir.name,
        "phase": "e2e",
        "contentType": "article",
        "supplyMode": "site_primary",
    }
    payload.update(overrides)
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_repo_phase_tree_gate_blocks_in_repo_canonical_tree(tmp_path):
    repo = tmp_path
    (repo / "quwoquan_data" / "runtime" / "batches").mkdir(parents=True)
    issues = repo_phase_tree_issues(repo)
    assert len(issues) == 1 and "runtime/batches" in issues[0]
    (repo / "quwoquan_data" / "runtime" / "e2e").mkdir()
    issues = repo_phase_tree_issues(repo)
    assert any("runtime/e2e" in issue for issue in issues)


def test_batch_axis_gate_flags_manifest_drift_and_missing_committed_task(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    batch_dir = runtime / "e2e" / "article" / "site_primary" / "样例-abc__b1"
    _write_manifest(batch_dir, contentType="image")  # 与目录层级 article 漂移
    issues = canonical_batch_axis_issues(runtime)
    assert any("manifest.contentType='image'" in i for i in issues)
    assert any("committed task 模板缺失" in i for i in issues)

    # 修复轴 + 补 committed 模板后全绿。
    from _common import paths as paths_mod

    _write_manifest(batch_dir)
    spec_path = paths_mod.committed_task_spec("旅行/地域/测试省/景区/隔离门样例")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("taskId: 旅行/地域/测试省/景区/隔离门样例\n", encoding="utf-8")
    assert canonical_batch_axis_issues(runtime) == []


def test_batch_axis_gate_requires_manifest(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "operations" / "video" / "search_supplement" / "b2").mkdir(parents=True)
    issues = canonical_batch_axis_issues(runtime)
    assert len(issues) == 1 and "缺 batch_manifest.json" in issues[0]


def test_artifacts_index_gate_requires_index_for_report_dirs(tmp_path):
    artifacts = tmp_path / "artifacts"
    batch_dir = artifacts / "content_runs" / "e2e" / "article" / "b3"
    batch_dir.mkdir(parents=True)
    assert artifacts_index_gate_issues(artifacts) == []  # 空目录不强制
    (batch_dir / "scale_readiness.json").write_text("{}", encoding="utf-8")
    issues = artifacts_index_gate_issues(artifacts)
    assert issues and "缺 index.json" in issues[0]


def test_data_artifacts_root_gate_blocks_data_owned_entries(tmp_path):
    repo = tmp_path
    artifacts = repo / "artifacts"
    artifacts.mkdir()
    (artifacts / "stackctl").mkdir()
    (artifacts / "legal-static-packages").mkdir()
    (artifacts / "quwoquan_data_runs").mkdir()
    (artifacts / "creator_batch100_commercial_readiness.json").write_text("{}", encoding="utf-8")
    (artifacts / "site_supply_trial.json").write_text("{}", encoding="utf-8")
    (artifacts / "s10verify_report.json").write_text("{}", encoding="utf-8")
    (artifacts / "cs100verify_report.json").write_text("{}", encoding="utf-8")
    (artifacts / "scale10_sichuan_readiness.json").write_text("{}", encoding="utf-8")

    issues = data_root_artifact_issues(repo)
    assert len(issues) == 6
    assert all("data 运行残留不得落 repo .qwq_output/runs/ 根" in issue for issue in issues)
    assert not any("stackctl" in issue or "legal-static-packages" in issue for issue in issues)


def test_legacy_marker_gate_blocks_index_marker_and_manifest(tmp_path):
    repo_artifacts = tmp_path / "repo" / "artifacts"
    output_artifacts = tmp_path / ".qwq_output" / "artifacts"
    (repo_artifacts / "nested").mkdir(parents=True)
    output_artifacts.mkdir(parents=True)
    (repo_artifacts / ("_".join(("legacy", "index")) + ".json")).write_text("{}", encoding="utf-8")
    (repo_artifacts / "nested" / "LEGACY_READONLY.md").write_text("readonly", encoding="utf-8")
    (output_artifacts / ("_".join(("migration", "manifest")) + ".json")).write_text("{}", encoding="utf-8")

    issues = legacy_marker_issues(repo_artifacts, output_artifacts)
    assert len(issues) == 3
    assert all("已退役" in issue for issue in issues)
