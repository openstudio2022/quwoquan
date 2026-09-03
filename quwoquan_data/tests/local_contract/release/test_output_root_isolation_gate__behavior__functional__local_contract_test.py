"""Single data output-root gate contracts."""
from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify import verify_output_root_isolation as gate  # noqa: E402


def test_data_output_allows_only_tasks_releases_local(tmp_path, monkeypatch):
    output = tmp_path / "data"
    tasks = output / "tasks"
    releases = output / "releases"
    local = output / "local"
    for path in (tasks, releases, local / "cache", local / "runs", local / "workspace"):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gate, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.setattr(gate, "RELEASE_ROOT", releases)
    monkeypatch.setattr(gate, "DATA_LOCAL_ROOT", local)
    assert gate._output_layout_issues() == []


def test_data_output_blocks_parallel_runtime_branches(tmp_path, monkeypatch):
    output = tmp_path / "data"
    tasks = output / "tasks"
    local = output / "local"
    tasks.mkdir(parents=True)
    (output / "runs").mkdir()
    (output / "content_runs").mkdir()
    (local / "runtime").mkdir(parents=True)
    monkeypatch.setattr(gate, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.setattr(gate, "DATA_LOCAL_ROOT", local)
    issues = gate._output_layout_issues()
    assert len(issues) == 3
    assert any("only allows tasks/, releases/, local/" in issue for issue in issues)
    assert any("data/local only allows cache/, runs/, and workspace/" in issue for issue in issues)


def test_retired_source_and_runtime_roots_fail_closed(tmp_path):
    for relative in (
        "quwoquan_data/control_plane/tasks",
        "quwoquan_data/sop",
        "quwoquan_data/docs",
        "runtime/tasks",
        "artifacts",
    ):
        (tmp_path / relative).mkdir(parents=True)
    issues = gate._retired_root_issues(tmp_path)
    assert len(issues) == 5
    assert all("retired; delete it" in issue for issue in issues)


def test_legacy_markers_are_rejected_under_source_and_output(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    (source / "legacy_index.json").write_text("{}", encoding="utf-8")
    (output / "migration_manifest.json").write_text("{}", encoding="utf-8")
    issues = gate._legacy_marker_issues(source, output)
    assert len(issues) == 2
    assert all("legacy marker is forbidden" in issue for issue in issues)


def test_data_output_rejects_reusable_source_truth_but_skips_disposable_cache(tmp_path):
    output = tmp_path / "data"
    (output / "tasks/execution-1/templates").mkdir(parents=True)
    (output / "local/workspace/policies").mkdir(parents=True)
    (output / "local/cache/tool/schema").mkdir(parents=True)

    issues = gate._output_source_truth_issues(output)

    assert len(issues) == 2
    assert all("reusable source truth is forbidden" in issue for issue in issues)


def test_quarantine_name_alone_does_not_exempt_reusable_source_truth(tmp_path):
    output = tmp_path / "data"
    policies = (
        output
        / "local/workspace/quarantine/unattested-history/package/resources/policies"
    )
    policies.mkdir(parents=True)
    (policies / "policy.yaml").write_text("mode: active\n", encoding="utf-8")

    issues = gate._output_source_truth_issues(output)

    assert len(issues) == 1
    assert "reusable source truth is forbidden" in issues[0]
