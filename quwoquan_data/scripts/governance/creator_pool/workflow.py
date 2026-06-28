"""Creator pool workflow orchestration."""
from __future__ import annotations

from typing import Any

from governance.creator_pool.acquire import run_acquire
from governance.creator_pool.diversify import run_diversify
from governance.creator_pool.enrich import run_enrich
from governance.creator_pool.materialize import run_materialize
from governance.creator_pool.plan import run_plan
from governance.creator_pool.score import run_score
from governance.creator_pool.seed import run_seed
from governance.creator_pool.validate import run_validate
from _common.creator_pool.candidate_pool import is_live_batch
from _common.creator_pool.io import iter_creator_refs
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, now_iso

STAGE_ORDER = ("plan", "acquire", "score", "diversify", "enrich", "materialize", "validate", "seed")


def run_workflow(
    *,
    vertical: str,
    batch_id: str,
    target: int = 0,
    through: str = "validate",
    dry_run: bool = False,
    fixture: str | None = None,
    env: str = "alpha",
) -> dict[str, Any]:
    if through not in STAGE_ORDER:
        raise ValueError(f"unsupported through stage: {through}")
    results: dict[str, Any] = {}
    shared = creator_pool_shared_dir(vertical, batch_id)
    if through == "plan" or not (shared / "creator_pool_plan.json").is_file():
        from pathlib import Path

        run_plan(
            vertical=vertical,
            batch_id=batch_id,
            target=target or len(iter_creator_refs(vertical, batch_id)) or 10,
            fixture=Path(fixture) if fixture else None,
        )
        results["plan"] = {"ok": True}
        if through == "plan":
            return results
    plan = read_json(shared / "creator_pool_plan.json")
    live_mode = bool(plan.get("liveMode")) or is_live_batch(batch_id, plan)
    if through in STAGE_ORDER[STAGE_ORDER.index("acquire") :]:
        results["acquire"] = run_acquire(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if through in STAGE_ORDER[STAGE_ORDER.index("score") :]:
        results["score"] = run_score(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if live_mode and through in STAGE_ORDER[STAGE_ORDER.index("diversify") :]:
        results["diversify"] = run_diversify(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if through in STAGE_ORDER[STAGE_ORDER.index("enrich") :]:
        results["enrich"] = run_enrich(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if through in STAGE_ORDER[STAGE_ORDER.index("materialize") :]:
        results["materialize"] = run_materialize(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if through in STAGE_ORDER[STAGE_ORDER.index("validate") :]:
        results["validate"] = run_validate(vertical=vertical, batch_id=batch_id, dry_run=dry_run)
    if through == "seed":
        results["seed"] = run_seed(vertical=vertical, batch_id=batch_id, env=env, dry_run=dry_run)
    _update_workflow_state(vertical, batch_id, through, results)
    return results


def _update_workflow_state(vertical: str, batch_id: str, through: str, results: dict[str, Any]) -> None:
    path = creator_pool_shared_dir(vertical, batch_id) / "creator_workflow_state.json"
    state = read_json(path) if path.is_file() else {}
    if not isinstance(state, dict):
        state = {}
    completed = list(state.get("completed") or [])
    if through not in completed:
        completed.append(through)
    failed: list[str] = []
    validate = results.get("validate") or {}
    planned = len(iter_creator_refs(vertical, batch_id))
    if through in ("validate", "seed") and validate.get("validated", 0) < planned:
        failed = [ref for ref in iter_creator_refs(vertical, batch_id) if _failed_ref(vertical, batch_id, ref)]
    write_json(
        path,
        {
            **state,
            "schemaVersion": "quwoquan.task.workflow_state/1",
            "batchId": batch_id,
            "completed": completed,
            "failedObjects": failed,
            "updatedAt": now_iso(),
        },
    )


def _failed_ref(vertical: str, batch_id: str, creator_ref: str) -> bool:
    from _common.creator_pool.io import read_review_gate

    gate = read_review_gate(vertical, batch_id, creator_ref)
    return not gate or gate.get("decision") != "passed"
