"""Merge creator pool seed into user_pool overlay and scenarios."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.io import repo_seed_fixture_dir
from _common.creator_pool.media_assets import materialize_batch_media
from _common.io import read_json, write_json
from _common.paths import SERVICE_CONTRACTS_METADATA_ROOT, now_iso


def run_merge_user_fixtures(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    seed_name = _seed_fixture_name(vertical, batch_id)
    seed_path = repo_seed_fixture_dir() / seed_name
    if not seed_path.is_file():
        raise FileNotFoundError(f"missing seed fixture: {seed_path}")
    seed = read_json(seed_path)
    users = seed.get("users") if isinstance(seed, dict) else None
    if not isinstance(users, list):
        raise ValueError("seed users missing")
    overlay_users: list[dict[str, Any]] = []
    for user in users:
        if not isinstance(user, dict):
            continue
        user_id = str(user.get("creatorProfileId") or user.get("subAccountId") or "")
        avatar_key = str(user.get("avatarObjectKey") or "")
        cover_key = str(user.get("backgroundObjectKey") or "")
        overlay_users.append(
            {
                "userId": user_id,
                "displayName": user.get("displayName"),
                "avatarObjectKey": avatar_key,
                "backgroundObjectKey": cover_key,
                "avatarMedia": _media_meta(avatar_key),
                "backgroundMedia": _media_meta(cover_key, width=1600, height=900),
                "bio": user.get("bio"),
                "subAccountRefs": [user.get("subAccountId")],
                "tags": ["author", "creator_pool", vertical],
                "primaryTheme": vertical,
                "secondaryThemes": [vertical],
                "themeTags": [vertical],
                "primaryRole": "secondaryAuthor",
                "creatorArchetype": user.get("creatorArchetype"),
                "cohortId": batch_id,
            }
        )
    overlay = {
        "schemaVersion": "shared.avatar-user-pool.overlay/1",
        "batchId": batch_id,
        "vertical": vertical,
        "userCount": len(overlay_users),
        "users": overlay_users,
        "generatedAt": now_iso(),
    }
    overlay_path = repo_seed_fixture_dir() / f"creator_{vertical}_{batch_id}_user_overlay.json"
    scenario_path = (
        SERVICE_CONTRACTS_METADATA_ROOT / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
    )
    if not dry_run:
        write_json(overlay_path, overlay)
        materialize_batch_media(batch_id=batch_id, users=users)
        _merge_scenario(scenario_path, batch_id=batch_id, vertical=vertical, user_ids=[u["userId"] for u in overlay_users])
    return {"mergedUsers": len(overlay_users), "overlayPath": str(overlay_path), "dryRun": dry_run}


def _seed_fixture_name(vertical: str, batch_id: str) -> str:
    return f"creator_{vertical}_batch100.seed.json"


def _media_meta(object_key: str, *, width: int = 512, height: int = 512) -> dict[str, Any]:
    return {
        "objectKey": object_key,
        "version": 1,
        "mimeType": "image/jpeg",
        "width": width,
        "height": height,
        "sizeBytes": 512,
        "sourceHash": f"sha256:creator_pool_{object_key}",
    }


def _merge_scenario(path, *, batch_id: str, vertical: str, user_ids: list[str]) -> None:
    if not path.is_file():
        return
    data = read_json(path)
    scenario_id = f"creator_{vertical}_{batch_id}_core"
    seed_sets = data.get("seedSets") if isinstance(data, dict) else None
    if not isinstance(seed_sets, dict):
        seed_sets = {}
        data["seedSets"] = seed_sets
    seed_sets[scenario_id] = {
        "description": f"Creator pool {batch_id} curated pilot subset",
        "profiles": [{"userId": uid} for uid in user_ids[:20]],
    }
    scenarios = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(scenarios, list):
        scenarios = []
    filtered = [
        s
        for s in scenarios
        if isinstance(s, dict) and s.get("id") != scenario_id and s.get("scenarioId") != scenario_id
    ]
    filtered.append(
        {
            "id": scenario_id,
            "title": f"Creator pool {batch_id}",
            "type": "user_profile",
            "domainId": "user",
            "seedRefs": [scenario_id],
            "uiExpectations": {"userIds": user_ids[:20]},
            "remoteExpectations": {
                "profileUserIds": user_ids[:20],
                "subAccountIds": [],
            },
            "environments": {
                "alpha": {"enabled": True, "repository": "mock"},
                "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True},
                "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True},
            },
            "tags": ["creator_pool", vertical, "beta"],
        }
    )
    data["scenarios"] = filtered
    write_json(path, data)
