"""Tests for dual-track prefab user resolver."""
from __future__ import annotations

from _common.prefab_user_resolver import (
    clear_cache,
    current_user_variant_sub_account_id,
    list_users,
    resolve_sub_account_id,
    resolve_user_id,
)


def setup_function() -> None:
    clear_cache()


def test_resolve_user_id_keeps_current_id_without_legacy_alias() -> None:
    resolved = resolve_user_id("fixture_user_current")
    assert resolved == "fixture_user_current"
    assert resolve_user_id("qwq_creator_current_user_variant") == "qwq_creator_current_user_variant"


def test_list_users_creator_track_has_1001_entries() -> None:
    users = list_users(track="creator_pool")
    assert len(users) == 1201
    slot_roles = [u.slot_role for u in users]
    assert "currentUserVariant" in slot_roles


def test_current_user_variant_sub_account_id() -> None:
    sub = current_user_variant_sub_account_id()
    assert sub == "fixture_sub_current"
    assert resolve_sub_account_id("fixture_user_current") == sub
