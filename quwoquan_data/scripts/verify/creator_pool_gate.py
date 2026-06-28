"""Batch-level creator pool gate helpers."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.io import iter_creator_refs, read_review_gate
from _common.io import read_json
from _common.paths import creator_pool_shared_dir


def gate_creator_batch(vertical: str, batch_id: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    shared = creator_pool_shared_dir(vertical, batch_id)
    for name in ("creator_pool_plan.json", "creator_object_index.json", "batch_manifest.json"):
        if not (shared / name).is_file():
            issues.append(f"missing _shared/{name}")
    refs = iter_creator_refs(vertical, batch_id)
    if not refs:
        issues.append("empty creatorRefs")
    for ref in refs:
        gate = read_review_gate(vertical, batch_id, ref)
        if not gate or gate.get("decision") != "passed":
            issues.append(f"review gate failed: {ref}")
    rollup_path = shared / "creator_rollup_report.json"
    if rollup_path.is_file():
        rollup = read_json(rollup_path)
        if isinstance(rollup, dict):
            funnel = rollup.get("funnel") or {}
            if float(funnel.get("reviewGatePassRate") or 0) < 1.0:
                issues.append("reviewGatePassRate < 1.0")
    return not issues, issues
