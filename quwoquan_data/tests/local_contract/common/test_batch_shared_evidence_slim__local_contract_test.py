"""batch/_shared 证据面瘦身契约（数据输出规范）。

单一真相源：`_common.paths` 的
- `BATCH_SHARED_AUTHORITATIVE_ENTRIES`：不可重算真相源（readiness/审计只认它们）；
- `BATCH_SHARED_RECLAIMABLE_ENTRIES` + `tmp_*` 前缀：调试/过程层，可随时清理；
- 其余条目 unknown → 目录证据链门 BLOCK。

task/_shared 最小证据面同样由 `TASK_SHARED_ALLOWED_ENTRIES` 冻结。
"""
from __future__ import annotations

from _common import paths as paths_mod
from verify.verify_directory_evidence_chain import _batch_shared_issues


PLAN_FROZEN_EVIDENCE = {
    "content_plan_packet.json",
    "content_object_index.json",
    "env_ready_report.json",
    "task_workflow_state.json",
    "token_ledger.json",
    "managed_batch_audit.json",
    "sdk_monitoring_report.json",
    "scale_readiness.json",
    "ship_report.json",
    "failure_ledger.jsonl",
}


def test_plan_frozen_evidence_all_authoritative():
    """计划冻结的十项批次权威证据必须全部登记为 authoritative。"""
    missing = PLAN_FROZEN_EVIDENCE - paths_mod.BATCH_SHARED_AUTHORITATIVE_ENTRIES
    assert missing == set(), missing


def test_debug_layers_are_reclaimable_not_authoritative():
    """assistant_tasks / workflow_packets 等调试态必须是可清理层，不得升级为权威证据。"""
    for name in ("assistant_tasks", "workflow_packets", "object_queue", "image_safety_cache"):
        assert paths_mod.batch_shared_entry_role(name) == "reclaimable", name
        assert name not in paths_mod.BATCH_SHARED_AUTHORITATIVE_ENTRIES, name


def test_role_partition_is_disjoint_and_tmp_prefix_reclaimable():
    overlap = (
        paths_mod.BATCH_SHARED_AUTHORITATIVE_ENTRIES
        & paths_mod.BATCH_SHARED_RECLAIMABLE_ENTRIES
    )
    assert overlap == set(), overlap
    assert paths_mod.batch_shared_entry_role("tmp_source_unit_image_checks") == "reclaimable"
    assert paths_mod.batch_shared_entry_role("made_up_second_truth.json") == "unknown"


def test_gate_blocks_unknown_shared_entry(tmp_path):
    batch = tmp_path / "batch"
    shared = batch / "_shared"
    shared.mkdir(parents=True)
    (shared / "env_ready_report.json").write_text("{}", encoding="utf-8")
    (shared / "assistant_tasks").mkdir()
    (shared / "tmp_probe").mkdir()
    assert _batch_shared_issues(batch) == []
    (shared / "rogue_summary.json").write_text("{}", encoding="utf-8")
    issues = _batch_shared_issues(batch)
    assert len(issues) == 1
    assert "rogue_summary.json" in issues[0]
    assert "未登记" in issues[0]


def test_task_shared_allowlist_is_minimal_ledger_face():
    """task/_shared 只允许跨批次账本 + explore/baseline 不可重算决策包。"""
    assert paths_mod.TASK_SHARED_ALLOWED_ENTRIES == frozenset(
        {
            *paths_mod.TASK_SHARED_LEDGER_FILENAMES,
            "baseline_freeze_packet.json",
            "baseline_report.json",
            "explore_packet.json",
            "discovery_adopt",
        }
    )
