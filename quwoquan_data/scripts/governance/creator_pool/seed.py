"""Creator pool seed handoff stage."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.io import (
    artifacts_readiness_path,
    iter_creator_refs,
    read_review_gate,
    repo_seed_fixture_dir,
)
from _common.creator_pool.media_assets import materialize_batch_media
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def run_seed(*, vertical: str, batch_id: str, env: str = "alpha", dry_run: bool = False) -> dict[str, Any]:
    users: list[dict[str, Any]] = []
    for creator_ref in iter_creator_refs(vertical, batch_id):
        gate = read_review_gate(vertical, batch_id, creator_ref)
        if not gate or gate.get("decision") != "passed":
            raise RuntimeError(f"review gate not passed for {creator_ref}")
        bundle_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "4.materialize") / "creator_bundle.json"
        bundle = read_json(bundle_path)
        profile = bundle.get("profile") or {}
        users.append(
            {
                "creatorProfileId": bundle.get("creatorProfileId"),
                "subAccountId": bundle.get("subAccountId"),
                "authorId": bundle.get("authorId"),
                "displayName": profile.get("displayName"),
                "userHandle": profile.get("userHandle"),
                "avatarObjectKey": profile.get("avatarObjectKey"),
                "backgroundObjectKey": profile.get("backgroundObjectKey"),
                "bio": profile.get("bio"),
                "headline": profile.get("headline"),
                "creatorArchetype": bundle.get("creatorArchetype"),
                "vertical": vertical,
                "cohortId": batch_id,
            }
        )
    handoff = {
        "schemaVersion": "quwoquan_data.creator_seed_handoff/1",
        "batchId": batch_id,
        "vertical": vertical,
        "environment": env,
        "userCount": len(users),
        "generatedAt": now_iso(),
    }
    shared = creator_pool_shared_dir(vertical, batch_id)
    write_json(shared / "seed_handoff.json", handoff)
    if dry_run:
        return {"seeded": len(users), "dryRun": True}
    seed_name = _seed_fixture_name(vertical, batch_id, len(users))
    seed_path = repo_seed_fixture_dir() / seed_name
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        seed_path,
        {
            "schemaVersion": "creator_pool.seed/1",
            "batchId": batch_id,
            "vertical": vertical,
            "environment": env,
            "users": users,
        },
    )
    _write_relations_seed(users, batch_id)
    if not dry_run:
        materialize_batch_media(batch_id=batch_id, users=users)
    return {"seeded": len(users), "seedPath": str(seed_path), "dryRun": False}


def _seed_fixture_name(vertical: str, batch_id: str, count: int) -> str:
    if count <= 10:
        return f"creator_{vertical}_scale10.seed.json"
    return f"creator_{vertical}_batch100.seed.json"


def _write_relations_seed(users: list[dict[str, Any]], batch_id: str) -> None:
    edges: list[dict[str, Any]] = []
    for idx, user in enumerate(users):
        sub = user.get("subAccountId")
        if not sub:
            continue
        if idx > 0:
            prev = users[idx - 1].get("subAccountId")
            edges.append({"kind": "FollowEdge", "fromSubAccountId": sub, "toSubAccountId": prev})
        edges.append({"kind": "CircleMember", "subAccountId": sub, "circleId": f"fixture_circle_travel_{batch_id}"})
    write_json(
        repo_seed_fixture_dir() / "creator_relations.seed.json",
        {"schemaVersion": "creator_pool.relations/1", "batchId": batch_id, "edges": edges},
    )


def check_scale10_prerequisite(target: int) -> bool:
    if target <= 10:
        return True
    report_path = artifacts_readiness_path("creator_scale10_readiness.json")
    if not report_path.is_file():
        return False
    report = read_json(report_path)
    return isinstance(report, dict) and report.get("decision") == "go"
