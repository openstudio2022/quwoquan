"""Comprehensive prefab user compatibility + new batch validation."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from _common.prefab_user_resolver import (
    clear_cache,
    current_user_variant_sub_account_id,
    list_users,
    resolve_sub_account_id,
    resolve_user_id,
)

REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "quwoquan_service/contracts/metadata/_shared/test_fixtures"
SEED = FIXTURES / "creator_pool/creator_travel_photo_1k_v1.seed.json"
CREATOR_SLICE = FIXTURES / "user_pool.creator_pool.travel_photo_1k_v1.json"
MANIFEST = FIXTURES / "user_pool.manifest.travel_photo_1k_v1.json"
MIGRATION = FIXTURES / "prefab_user_migration_map.yaml"
CUTOVER = REPO / "quwoquan_service/contracts/metadata/_shared/prefab_cutover.yaml"


def setup_function() -> None:
    clear_cache()


def test_creator_slice_has_1001_users_with_current_slot() -> None:
    payload = json.loads(CREATOR_SLICE.read_text(encoding="utf-8"))
    users = payload.get("users") or []
    assert len(users) == 1201
    slot = [u for u in users if u.get("slotRole") == "currentUserVariant"]
    assert len(slot) == 1
    assert slot[0]["userId"] == "fixture_user_current"
    assert not slot[0]["userId"].startswith("sys_")


def test_seed_matches_creator_slice_excluding_current_slot() -> None:
    seed_users = json.loads(SEED.read_text(encoding="utf-8")).get("users") or []
    slice_users = json.loads(CREATOR_SLICE.read_text(encoding="utf-8")).get("users") or []
    author_users = [u for u in slice_users if u.get("slotRole") != "currentUserVariant"]
    assert len(seed_users) == 1200
    assert len(author_users) == 1200
    seed_ids = {u["creatorProfileId"] for u in seed_users}
    slice_ids = {u["userId"] for u in author_users}
    assert seed_ids == slice_ids


def test_manifest_statistics_and_current_user_variant() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stats = manifest.get("statistics") or {}
    assert stats.get("creatorPoolUserCount") == 1201
    assert stats.get("archiveUserCount", 0) >= 100
    slot = manifest.get("currentUserVariant") or {}
    assert slot.get("userId") == "fixture_user_current"
    assert slot.get("subAccountId") == current_user_variant_sub_account_id()


def test_current_user_resolves_without_legacy_alias() -> None:
    assert resolve_user_id("fixture_user_current") == "fixture_user_current"
    assert resolve_user_id("qwq_creator_current_user_variant") == "qwq_creator_current_user_variant"
    assert resolve_sub_account_id("fixture_user_current") == current_user_variant_sub_account_id()


def test_creator_track_list_count() -> None:
    assert len(list_users(track="creator_pool")) == 1201


def test_content_pilot_20_mappings_reference_creator_slice() -> None:
    migration = yaml.safe_load(MIGRATION.read_text(encoding="utf-8")) or {}
    mappings = (migration.get("content_pilot_20") or {}).get("mappings") or []
    assert len(mappings) == 20
    creator_ids = {u.user_id for u in list_users(track="creator_pool")}
    for item in mappings:
        assert item["creatorProfileId"] in creator_ids
        assert item["creatorProfileId"].startswith("sys_photo_")
        assert "authorId" not in item
        assert str(item["subAccountId"]).endswith("_sub_01")


def test_cutover_domains_marked_done() -> None:
    cutover = yaml.safe_load(CUTOVER.read_text(encoding="utf-8")) or {}
    domains = cutover.get("domains") or {}
    for name in ("content", "user", "chat", "circle"):
        assert domains.get(name, {}).get("cutover") == "done", name
