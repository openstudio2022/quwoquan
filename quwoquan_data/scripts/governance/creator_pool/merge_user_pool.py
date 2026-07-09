"""Merge creator pool seed into canonical user_pool creator slice + manifest."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.batch_policy import CANONICAL_BATCH_ID
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
CURRENT_USER_VARIANT = {
    "creatorProfileId": "fixture_user_current",
    "subAccountId": "fixture_sub_current",
    "displayName": "小趣体验号",
    "userHandle": "qwq-demo",
    "avatarPresetId": "avatar_travel_wayfinder",
    "coverPresetId": "cover_travel_snowpeak_route",
    "bio": "用于本地验收的当前用户，关注旅行、摄影和日常记录。",
    "headline": "当前体验用户",
    "slogan": "先把体验走顺",
    "creatorArchetype": "experience_user",
    "vertical": "travel",
    "verticalRefs": ["travel", "photography"],
    "interestTagRefs": ["Topic/旅行/玩法/摄影旅拍"],
    "publicProfileTagRefs": ["Topic/旅行"],
    "creatorClassTagRefs": ["Audience/创作者/粉丝量级/素人"],
    "cohortId": CANONICAL_BATCH_ID,
    "slotRole": "currentUserVariant",
}


def _user_pool_entry(user: dict[str, Any], *, vertical: str, batch_id: str, slot_role: str | None = None) -> dict[str, Any]:
    user_id = str(user.get("creatorProfileId") or user.get("subAccountId") or "")
    avatar_key = str(user.get("avatarObjectKey") or "")
    cover_key = str(user.get("backgroundObjectKey") or "")
    vertical_refs = [str(ref) for ref in (user.get("verticalRefs") or [vertical]) if str(ref).strip()]
    primary_theme = str(user.get("primaryTheme") or (vertical_refs[0] if vertical_refs else vertical))
    theme_tags = list(dict.fromkeys([primary_theme, *vertical_refs]))
    public_tags = [str(ref) for ref in (user.get("publicProfileTagRefs") or []) if str(ref).strip()]
    interest_tags = [str(ref) for ref in (user.get("interestTagRefs") or []) if str(ref).strip()]
    entry: dict[str, Any] = {
        "userId": user_id,
        "displayName": user.get("displayName"),
        "avatarObjectKey": avatar_key,
        "backgroundObjectKey": cover_key,
        "avatarMedia": _media_meta(avatar_key),
        "backgroundMedia": _media_meta(cover_key, width=1600, height=900),
        "bio": user.get("bio"),
        "headline": user.get("headline"),
        "slogan": user.get("slogan"),
        "subAccountRefs": [user.get("subAccountId")],
        "subAccountId": user.get("subAccountId"),
        "userHandle": user.get("userHandle"),
        "avatarPresetId": user.get("avatarPresetId"),
        "coverPresetId": user.get("coverPresetId"),
        "tags": _profile_tags(vertical=vertical, vertical_refs=vertical_refs, public_tags=public_tags),
        "primaryTheme": primary_theme,
        "secondaryThemes": vertical_refs,
        "themeTags": theme_tags,
        "postThemeRefs": list(theme_tags),
        "circleThemeRefs": list(theme_tags),
        "groupPersonaMix": user.get("groupPersonaMix") or [],
        "primaryRole": "secondaryAuthor",
        "creatorArchetype": user.get("creatorArchetype"),
        "verticalSegment": user.get("verticalSegment"),
        "verticalRefs": vertical_refs,
        "interestTagRefs": interest_tags,
        "publicProfileTagRefs": public_tags,
        "creatorClassTagRefs": user.get("creatorClassTagRefs") or [],
        "coverageScope": user.get("coverageScope") or {},
        "carrierAffinity": user.get("carrierAffinity") or {},
        "preferredBlueprintIds": user.get("preferredBlueprintIds") or [],
        "relations": user.get("relations") or {},
        "shardId": user.get("shardId"),
        "riskTier": user.get("riskTier"),
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
    creator_pool_path = fixtures_dir / f"user_pool.creator_pool.{batch_id}.json"
    manifest_path = fixtures_dir / f"user_pool.manifest.{batch_id}.json"
    archive_path = fixtures_dir / "user_pool.json"

    archive = read_json(archive_path) if archive_path.is_file() else {}
    archive_count = len(archive.get("users") or []) if isinstance(archive, dict) else 0

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
        "archiveTrackPolicy": "read_only_until_t4",
        "mergeRules": {
            "archivePath": "_shared/test_fixtures/user_pool.json",
            "creatorPoolPath": f"_shared/test_fixtures/{creator_pool_path.name}",
            "resolutionOrder": ["creator_pool", "archive"],
            "conflictPolicy": "creator_pool_wins_with_warn",
        },
        "currentUserVariant": {
            "userId": CURRENT_USER_VARIANT["creatorProfileId"],
            "subAccountId": CURRENT_USER_VARIANT["subAccountId"],
        },
        "statistics": {
            "archiveUserCount": archive_count,
            "creatorPoolUserCount": len(creator_users),
            "mergedUserCount": archive_count + len(creator_users),
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
        "archiveUserCount": archive_count,
        "creatorPoolPath": str(creator_pool_path),
        "manifestPath": str(manifest_path),
        "overlay": overlay_result,
        "dryRun": dry_run,
    }


def _profile_tags(*, vertical: str, vertical_refs: list[str], public_tags: list[str]) -> list[str]:
    tags = ["author", "creator_pool", vertical, *vertical_refs, *public_tags]
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out
