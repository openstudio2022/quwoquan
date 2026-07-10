"""Creator pool plan stage."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from _common.creator_pool.candidate_pool import build_candidate_pool, is_live_batch
from _common.creator_pool.diversity import assign_creator_slots, build_diversity_matrix
from _common.creator_pool.io import ensure_batch_dirs, write_stage_result
from _common.io import write_json
from _common.paths import creator_pool_shared_dir, now_iso


def run_plan(
    *,
    vertical: str,
    batch_id: str,
    target: int,
    fixture: Path | None = None,
) -> dict[str, Any]:
    ensure_batch_dirs(vertical, batch_id)
    shared = creator_pool_shared_dir(vertical, batch_id)
    live_mode = fixture is None and is_live_batch(batch_id)
    fixture_mode = fixture is not None or (not live_mode and batch_id.endswith("_v1"))
    candidate_pool_size = max(target * 5, 350) if live_mode else max(target * 3, target + 20)
    matrix = build_diversity_matrix(vertical, target, batch_id=batch_id)
    if live_mode:
        candidates = build_candidate_pool(
            vertical=vertical,
            batch_id=batch_id,
            target=target,
            pool_size=candidate_pool_size,
        )
        write_json(
            shared / "candidate_pool.json",
            {
                "schemaVersion": "quwoquan_data.creator_candidate_pool/1",
                "batchId": batch_id,
                "poolSize": len(candidates),
                "candidates": candidates,
            },
        )
        slots: list[dict[str, str]] = []
        creator_refs: list[str] = []
    else:
        slots = assign_creator_slots(vertical, target, batch_id=batch_id)
        creator_refs = [s["creatorRef"] for s in slots]
    plan = {
        "schemaVersion": "quwoquan_data.creator_pool_plan/1",
        "vertical": vertical,
        "batchId": batch_id,
        "targetCount": target,
        "candidatePoolSize": candidate_pool_size,
        "creatorRefs": creator_refs,
        "diversityQuotas": {
            "verticalSegmentBuckets": matrix["dimensions"].get("verticalSegment"),
            "archetypeBuckets": matrix["dimensions"]["archetype"],
            "regionBuckets": matrix["dimensions"]["region"],
            "carrierBuckets": matrix["dimensions"]["carrier"],
            "platformBuckets": matrix["dimensions"].get("platform"),
            "popularityTierBuckets": matrix["dimensions"].get("popularityTier"),
            "outputTierBuckets": matrix["dimensions"].get("outputTier"),
            "sourceRegionClassBuckets": matrix["dimensions"].get("sourceRegionClass"),
        },
        "fixtureMode": fixture_mode,
        "liveMode": live_mode,
        "createdAt": now_iso(),
    }
    write_json(shared / "creator_pool_plan.json", plan)
    with (shared / "diversity_matrix.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(matrix, f, allow_unicode=True, sort_keys=False)
    index_objects = [
        {
            "creatorRef": slot["creatorRef"],
            "stage": "planned",
            "archetype": slot["archetype"],
            "regionBucket": slot["regionBucket"],
        }
        for slot in slots
    ] if slots else []
    write_json(
        shared / "creator_object_index.json",
        {
            "schemaVersion": "quwoquan_data.creator_object_index/1",
            "batchId": batch_id,
            "objects": index_objects,
        },
    )
    write_json(
        shared / "creator_workflow_state.json",
        {
            "schemaVersion": "quwoquan.task.workflow_state/1",
            "batchId": batch_id,
            "completed": [],
            "waitingCheckpoint": [],
            "failedObjects": [],
        },
    )
    if fixture is not None and fixture.is_file():
        write_json(shared / "fixture_source.json", {"path": str(fixture)})
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vertical", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--fixture")
    args = parser.parse_args(argv)
    run_plan(
        vertical=args.vertical,
        batch_id=args.batch,
        target=args.target,
        fixture=Path(args.fixture) if args.fixture else None,
    )
    print(f"[creator-pool plan] batch={args.batch} target={args.target}")
    return 0
