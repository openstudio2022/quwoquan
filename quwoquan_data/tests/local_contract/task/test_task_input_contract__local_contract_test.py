"""task 输入契约固化（数据输出规范）。

三者边界的单一真相源：
- committed task spec（仓内可复用输入契约）：`quwoquan_data/control_plane/tasks/**/task.yaml`
  受版本控制；默认值唯一来源是 `presetRef → control_plane/families/<ref>.preset.yaml`
  （旧 `_defaults.yaml` 路径继承链已退役）；progress.json / runs/ / notes.md
  等运行进度只留本地，不入库。
- runtime snapshot（仓外一次性）：`local/data-runtime/tasks/{taskId}/` 只允许
  `task_manifest.json` + `_shared/` + `entities/`，不复制 committed 模板本体。
- publish 输出：task.yaml / 模板 / schema 不进入 `publish/**`。
"""
from __future__ import annotations

from pathlib import Path

from _common import paths as paths_mod
from _common.batch_manifest import write_task_manifest


def _gitignore_text() -> str:
    return (paths_mod.REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


def test_committed_task_contract_files_are_version_controlled():
    """control_plane/tasks 下 task.yaml 是仓内输入契约；运行进度不入库。"""
    text = _gitignore_text()
    assert "quwoquan_data/control_plane/tasks/**" in text
    assert "!quwoquan_data/control_plane/tasks/**/task.yaml" in text
    # 旧 tasks 根与 _defaults.yaml 机制已退役，禁止回归。
    assert "!quwoquan_data/tasks/**/task.yaml" not in text
    assert "_defaults.yaml" not in text
    # 不允许把 progress/runs/notes 重新加回白名单。
    assert "progress.json" not in text.replace("# ", "")
    assert "!quwoquan_data/control_plane/tasks/**/runs" not in text
    assert "!quwoquan_data/control_plane/tasks/**/notes.md" not in text


def test_committed_spec_path_is_repo_side_contract():
    spec_path = paths_mod.committed_task_spec("旅行/地域/示例省/景区/契约样例")
    assert spec_path.name == "task.yaml"
    assert str(spec_path).startswith(str(paths_mod.COMMITTED_TASKS_ROOT))
    # committed 根与 runtime 快照根物理隔离（模板复用引用、不复制进 runtime）。
    assert paths_mod.COMMITTED_TASKS_ROOT != paths_mod.TASKS_ROOT


def test_runtime_task_snapshot_is_minimal_allowlist():
    """local/data-runtime/tasks/{taskId} 是最小 snapshot 层，不承载 committed 模板本体。"""
    assert paths_mod.TASK_ROOT_ALLOWED_ENTRIES == frozenset(
        {"entities", "_shared", "task_manifest.json"}
    )


def test_write_task_manifest_snapshots_without_copying_template(tmp_path, monkeypatch):
    task_id = "旅行/地域/示例省/景区/快照样例"
    spec = {
        "schemaVersion": "quwoquan.task.spec",
        "taskId": task_id,
        "intentLabel": "快照样例",
        "vertical": "travel",
        "scope": {
            "organizeBy": "地域",
            "region": "示例省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"name": "示例景区", "entityType": "地点/景区"}],
        },
        "content": {"angles": ["体验"]},
    }
    manifest_path = write_task_manifest(task_id, spec)
    task_root = manifest_path.parent
    assert manifest_path.name == "task_manifest.json"
    assert str(task_root).startswith(str(paths_mod.TASKS_ROOT))
    # snapshot 只有 manifest（+ 允许的 _shared/entities），绝不复制 task.yaml。
    assert not (task_root / "task.yaml").exists()
    illegal = [
        entry.name
        for entry in task_root.iterdir()
        if not entry.name.startswith(".")
        and entry.name not in paths_mod.TASK_ROOT_ALLOWED_ENTRIES
    ]
    assert illegal == [], illegal


def test_templates_and_schema_stay_out_of_publish():
    publish_root = Path(paths_mod.PUBLISH_ROOT)
    for forbidden in ("task.yaml", "_defaults.yaml"):
        if publish_root.is_dir():
            assert not list(publish_root.rglob(forbidden)), forbidden
