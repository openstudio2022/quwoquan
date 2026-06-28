"""Merge creator pool seed into canonical user_pool creator slice + manifest."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.io import repo_seed_fixture_dir
from _common.creator_pool.media_assets import materialize_batch_media
from _common.io import read_json, write_json
from _common.paths import SERVICE_CONTRACTS_METADATA_ROOT, now_iso
from governance.creator_pool.merge_user_fixtures import (
    _media_meta,
    _merge_scenario,
    _seed_fixture_name,
    run_merge_user_fixtures,
)

CANONICAL_BATCH_ID = "travel_batch_100_v1"

CURRENT_USER_VARIANT = {
    "creatorProfileId": "qwq_creator_current_user_variant",
    "subAccountId": "agent_sub_account_travel_current_user_variant",
    "authorId": "agent_author_travel_current_user_variant",
    "displayName": "趣我圈体验用户",
    "userHandle": "current_user_variant",
    "avatarObjectKey": "cold_start/creators/travel_batch_100_v1/current_user_variant/avatar.jpg",
    "backgroundObjectKey": "cold_start/creators/travel_batch_100_v1/current_user_variant/cover.jpg",
    "bio": "creator pool 当前登录体验槽位，与 100 作者同源工程。",
    "headline": "当前体验用户",
    "creatorArchetype": "experience_user",
    "vertical": "travel",
    "cohortId": "travel_batch_100_v1",
    "slotRole": "currentUserVariant",
}


def _user_pool_entry(user: dict[str, Any], *, vertical: str, batch_id: str, slot_role: str | None = None) -> dict[str, Any]:
    user_id = str(user.get("creatorProfileId") or user.get("subAccountId") or "")
    avatar_key = str(user.get("avatarObjectKey") or "")
    cover_key = str(user.get("backgroundObjectKey") or "")
    entry: dict[str, Any] = {
        "userId": user_id,
        "displayName": user.get("displayName"),
        "avatarObjectKey": avatar_key,
        "backgroundObjectKey": cover_key,
        "avatarMedia": _media_meta(avatar_key),
        "backgroundMedia": _media_meta(cover_key, width=1600, height=900),
        "bio": user.get("bio"),
        "subAccountRefs": [user.get("subAccountId")],
        "authorId": user.get("authorId"),
        "subAccountId": user.get("subAccountId"),
        "userHandle": user.get("userHandle"),
        "tags": ["author", "creator_pool", vertical],
        "primaryTheme": vertical,
        "secondaryThemes": [vertical],
        "themeTags": [vertical],
        "primaryRole": "secondaryAuthor",
        "creatorArchetype": user.get("creatorArchetype"),
        "cohortId": batch_id,
        "prefabTrack": "creator_pool",
    }
    if slot_role:
        entry["slotRole"] = slot_role
    return entry


def run_merge_user_pool(
    *,
    vertical: str,
    batch_id: str,
    include_current_user_slot: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    seed_name = _seed_fixture_name(vertical, batch_id)
    seed_path = repo_seed_fixture_dir() / seed_name
    if not seed_path.is_file():
        raise FileNotFoundError(f"missing seed fixture: {seed_path}")
    seed = read_json(seed_path)
    users = seed.get("users") if isinstance(seed, dict) else None
    if not isinstance(users, list):
        raise ValueError("seed users missing")

    creator_users: list[dict[str, Any]] = []
    for user in users:
        if isinstance(user, dict):
            creator_users.append(_user_pool_entry(user, vertical=vertical, batch_id=batch_id))

    if include_current_user_slot:
        creator_users.insert(0, _user_pool_entry(CURRENT_USER_VARIANT, vertical=vertical, batch_id=batch_id, slot_role="currentUserVariant"))

    fixtures_dir = SERVICE_CONTRACTS_METADATA_ROOT / "_shared" / "test_fixtures"
    creator_pool_path = fixtures_dir / "user_pool.creator_pool.json"
    manifest_path = fixtures_dir / "user_pool.manifest.json"
    legacy_path = fixtures_dir / "user_pool.json"

    legacy = read_json(legacy_path) if legacy_path.is_file() else {}
    legacy_count = len(legacy.get("users") or []) if isinstance(legacy, dict) else 0

    creator_payload = {
        "schemaVersion": "shared.avatar-user-pool.creator_slice/1",
        "batchId": batch_id,
        "vertical": vertical,
        "prefabTrack": "creator_pool",
        "userCount": len(creator_users),
        "users": creator_users,
        "generatedAt": now_iso(),
    }
    manifest = {
        "schemaVersion": "shared.avatar-user-pool.manifest/1",
        "defaultTrack": "creator_pool",
        "legacyTrackPolicy": "read_only_until_t4",
        "mergeRules": {
            "legacyPath": "_shared/test_fixtures/user_pool.json",
            "creatorPoolPath": "_shared/test_fixtures/user_pool.creator_pool.json",
            "resolutionOrder": ["creator_pool", "legacy"],
            "conflictPolicy": "creator_pool_wins_with_warn",
        },
        "currentUserVariant": {
            "userId": CURRENT_USER_VARIANT["creatorProfileId"],
            "subAccountId": CURRENT_USER_VARIANT["subAccountId"],
            "legacyAliases": ["fixture_user_current", "user_001"],
        },
        "statistics": {
            "legacyUserCount": legacy_count,
            "creatorPoolUserCount": len(creator_users),
            "mergedUserCount": legacy_count + len(creator_users),
        },
        "batchId": batch_id,
        "generatedAt": now_iso(),
    }

    overlay_result = run_merge_user_fixtures(vertical=vertical, batch_id=batch_id, dry_run=dry_run)

    if not dry_run:
        write_json(creator_pool_path, creator_payload)
        write_json(manifest_path, manifest)
        materialize_batch_media(
            batch_id=batch_id,
            users=[CURRENT_USER_VARIANT, *users] if include_current_user_slot else users,
        )
        scenario_path = SERVICE_CONTRACTS_METADATA_ROOT / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
        user_ids = [u["userId"] for u in creator_users if u.get("slotRole") != "currentUserVariant"]
        _merge_scenario(scenario_path, batch_id=batch_id, vertical=vertical, user_ids=user_ids)

    return {
        "creatorPoolUsers": len(creator_users),
        "legacyUserCount": legacy_count,
        "creatorPoolPath": str(creator_pool_path),
        "manifestPath": str(manifest_path),
        "overlay": overlay_result,
        "dryRun": dry_run,
    }
