#!/usr/bin/env python3
"""Verify shared avatar user pool consistency across sources, fixtures, and environments."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")
from typing import Any


ROOT = _find_repo_root()
SERVICE_ROOT = ROOT / "quwoquan_service"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
USER_POOL_PATH = SHARED / "user_pool.json"
USER_POOL_MANIFEST_PATH = SHARED / "user_pool.manifest.travel_photo_1k_v1.json"
SOURCE_CATALOG_PATH = SHARED / "source_catalog.json"
COMPOSITION_RULES_PATH = SHARED / "composition_rules.json"
CREATOR_POOL_SEED = SHARED / "creator_pool" / "creator_travel_photo_1k_v1.seed.json"
CREATOR_POOL_CANONICAL_REFS = ["creator_travel_photo_1k_v1", "creator_travel_photo_1k_v1_core"]
PROFILE_PRESET_MANIFEST = ROOT / "quwoquan_data" / "publish" / "user_media" / "profile_presets" / "manifest.json"
USER_SCENARIOS = METADATA / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
CONTENT_SCENARIOS = METADATA / "content" / "test_fixtures" / "scenarios" / "content_scenarios.json"
CIRCLE_SCENARIOS = METADATA / "social" / "circle" / "test_fixtures" / "scenarios" / "circle_scenarios.json"
CHAT_SCENARIOS = METADATA / "messages" / "chat" / "test_fixtures" / "scenarios" / "chat_scenarios.json"
MANIFESTS = {
    "alpha": SHARED / "app_alpha_seed_manifest.json",
    "beta": SHARED / "app_beta_seed_manifest.json",
    "gamma": SHARED / "app_gamma_seed_manifest.json",
}
GAMMA_CURATED_MEDIA_BUNDLE = ROOT / "quwoquan_ops" / "environments" / "gamma_curated_media_bundle.json"
GROUP_RENDER_PACKAGE = "./tools/render_group_avatar"
GAMMA_CURATED_EXPECTATIONS = {
    "content": {
        "fixturePath": "content/test_fixtures/scenarios/content_scenarios.gamma-curated.json",
        "refs": ["content_discovery_core", "intersection_core", "home_showcase_core"],
    },
    "circle": {
        "fixturePath": "social/circle/test_fixtures/scenarios/circle_scenarios.gamma-curated.json",
        "refs": ["circle_core", "circle_group_chat_link_core"],
    },
    "chat": {
        "fixturePath": "messages/chat/test_fixtures/scenarios/chat_scenarios.gamma-curated.json",
        "refs": ["chat_core", "chat_contacts_core", "chat_group_flow_core"],
    },
    "user": {
        "fixturePath": "user/test_fixtures/scenarios/user_scenarios.gamma-curated.json",
        "refs": ["user_profile_core", "persona_core", "profile_feed_core", "relationship_core"],
    },
    "entity": {
        "fixturePath": "entity/test_fixtures/scenarios/entity_scenarios.gamma-curated.json",
        "refs": ["entity_homepage_core", "entity_claim_core", "entity_picker_core"],
    },
}
MEDIA_FIELD_NAMES = {
    "avatarUrl",
    "authorAvatarUrl",
    "senderAvatarUrlSnapshot",
    "senderAvatar",
    "backgroundUrl",
    "authorBackgroundUrl",
    "coverUrl",
    "thumbnailUrl",
    "videoUrl",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def is_media_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith(
        ("media/avatar/", "media/background/", "media/image/", "media/video/", "media/preset/")
    )


def assert_media_ref(errors: list[str], context: str, value: object) -> None:
    if not is_media_ref(value):
        fail(errors, f"{context} must be a media object key, got {value!r}")


def user_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for item in pool.get("users", []):
        if not isinstance(item, dict):
            continue
        user_id = str(item.get("userId") or "").strip()
        if user_id:
            users[user_id] = item
        sub_account_id = str(item.get("subAccountId") or "").strip()
        if sub_account_id:
            users[sub_account_id] = item
        for ref in item.get("subAccountRefs") or []:
            ref_id = str(ref or "").strip()
            if ref_id:
                users[ref_id] = item
    return users


def post_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["postId"]): item for item in pool.get("posts", []) if isinstance(item, dict)}


def circle_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["circleId"]): item for item in pool.get("circles", []) if isinstance(item, dict)}


def conversation_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["conversationId"]): item for item in pool.get("conversations", []) if isinstance(item, dict)}


def _merge_users_by_id(*user_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for items in user_lists:
        for item in items:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("userId") or "").strip()
            if not user_id:
                continue
            merged[user_id] = item
    return list(merged.values())


def _profile_avatar_overlay() -> dict[str, dict[str, Any]]:
    user_doc = load_json(USER_SCENARIOS)
    profiles = (((user_doc.get("seedSets") or {}).get("user_profile_core") or {}).get("profiles") or [])
    overlay: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        user_id = str(profile.get("userId") or "").strip()
        if not user_id:
            continue
        avatar_key = str(profile.get("avatarObjectKey") or profile.get("avatarUrl") or "").strip()
        background_key = str(profile.get("backgroundObjectKey") or profile.get("backgroundUrl") or "").strip()
        overlay[user_id] = {
            "displayName": profile.get("displayName"),
            "avatarObjectKey": avatar_key,
            "backgroundObjectKey": background_key,
            "primaryTheme": profile.get("primaryTheme"),
            "themeTags": profile.get("themeTags"),
            "postThemeRefs": profile.get("postThemeRefs"),
            "circleThemeRefs": profile.get("circleThemeRefs"),
            "groupPersonaMix": profile.get("groupPersonaMix"),
        }
    return overlay


def _circle_summary_overlay() -> dict[str, dict[str, Any]]:
    circle_doc = load_json(CIRCLE_SCENARIOS)
    circle_core = ((circle_doc.get("seedSets") or {}).get("circle_core") or {})
    circles = circle_core.get("circles") or []
    members_by_circle = circle_core.get("members") or {}
    overlay: dict[str, dict[str, Any]] = {}
    for circle in circles:
        if not isinstance(circle, dict):
            continue
        circle_id = str(circle.get("id") or "").strip()
        if not circle_id:
            continue
        owner_user_id = str(circle.get("ownerId") or "").strip()
        member_user_ids: list[str] = []
        for member in members_by_circle.get(circle_id) or []:
            if not isinstance(member, dict):
                continue
            user_id = str(member.get("userId") or "").strip()
            if user_id:
                member_user_ids.append(user_id)
        if owner_user_id and owner_user_id not in member_user_ids:
            member_user_ids.insert(0, owner_user_id)
        primary_theme = str(circle.get("primaryTheme") or "").strip()
        secondary_themes = [str(value) for value in (circle.get("secondaryThemes") or []) if str(value).strip()]
        theme_tags = [str(value) for value in (circle.get("themeTags") or []) if str(value).strip()]
        if primary_theme and primary_theme not in theme_tags:
            theme_tags = [primary_theme, *theme_tags]
        overlay[circle_id] = {
            "circleId": circle_id,
            "ownerUserId": owner_user_id,
            "groupConversationId": circle.get("conversationId"),
            "circleType": circle.get("circleType"),
            "primaryTheme": primary_theme,
            "secondaryThemes": secondary_themes,
            "themeTags": theme_tags,
            "memberUserIds": member_user_ids,
        }
    return overlay


def _asset_meta_from_object_key(object_key: str, *, width: int, height: int) -> dict[str, Any]:
    path = MEDIA_ROOT / object_key
    mime_type = "image/png" if object_key.endswith(".png") else "image/jpeg"
    raw = path.read_bytes() if path.is_file() else b""
    return {
        "objectKey": object_key,
        "version": 1,
        "mimeType": mime_type,
        "width": width,
        "height": height,
        "sizeBytes": len(raw),
        "sourceHash": sha256_bytes(raw) if raw else "",
    }


def _circle_media_overlay() -> dict[str, dict[str, Any]]:
    circle_doc = load_json(CIRCLE_SCENARIOS)
    circle_core = ((circle_doc.get("seedSets") or {}).get("circle_core") or {})
    overlay: dict[str, dict[str, Any]] = {}
    for circle in circle_core.get("circles") or []:
        if not isinstance(circle, dict):
            continue
        circle_id = str(circle.get("id") or "").strip()
        avatar_key = str(circle.get("avatarObjectKey") or circle.get("avatarUrl") or "").strip()
        cover_key = str(circle.get("coverObjectKey") or circle.get("coverUrl") or "").strip()
        if not circle_id or not avatar_key or not cover_key:
            continue
        overlay[circle_id] = {
            "avatar": _asset_meta_from_object_key(avatar_key, width=512, height=512),
            "cover": _asset_meta_from_object_key(cover_key, width=1440, height=900),
        }
    return overlay


def load_effective_user_pool() -> dict[str, Any]:
    pool = load_json(USER_POOL_PATH)
    if not USER_POOL_MANIFEST_PATH.is_file():
        return pool
    manifest = load_json(USER_POOL_MANIFEST_PATH)
    merge_rules = manifest.get("mergeRules") if isinstance(manifest.get("mergeRules"), dict) else {}
    creator_rel = str(merge_rules.get("creatorPoolPath") or "").strip()
    archive_rel = str(merge_rules.get("archivePath") or "").strip()
    archive_path = METADATA / archive_rel if archive_rel else USER_POOL_PATH
    creator_path = METADATA / creator_rel if creator_rel else None
    archive_pool = load_json(archive_path) if archive_path.is_file() else pool
    if creator_path is None or not creator_path.is_file():
        return archive_pool
    creator_pool = load_json(creator_path)
    merged_pool = dict(archive_pool)
    merged_users = _merge_users_by_id(
        list(archive_pool.get("users") or []),
        list(creator_pool.get("users") or []),
    )
    profile_overlay = _profile_avatar_overlay()
    for user in merged_users:
        overlay = profile_overlay.get(str(user.get("userId") or ""))
        if not overlay:
            overlay = {}
        for field, value in overlay.items():
            if value in (None, "", []):
                continue
            user[field] = value
        theme_tags = list(user.get("themeTags") or [])
        if not isinstance(user.get("postThemeRefs"), list):
            user["postThemeRefs"] = list(theme_tags)
        if not isinstance(user.get("circleThemeRefs"), list):
            user["circleThemeRefs"] = list(theme_tags)
        if not isinstance(user.get("groupPersonaMix"), list):
            user["groupPersonaMix"] = []
    merged_pool["users"] = merged_users
    circles_by_id = circle_map(archive_pool)
    for item in creator_pool.get("circles") or []:
        if not isinstance(item, dict):
            continue
        circle_id = str(item.get("circleId") or "").strip()
        if circle_id:
            circles_by_id[circle_id] = item
    for circle_id, summary in _circle_summary_overlay().items():
        circles_by_id.setdefault(circle_id, summary)
    merged_pool["circles"] = list(circles_by_id.values())
    circle_media = dict(archive_pool.get("circleMedia") or {})
    for circle_id, bundle in (creator_pool.get("circleMedia") or {}).items():
        circle_media[str(circle_id)] = bundle
    for circle_id, bundle in _circle_media_overlay().items():
        circle_media.setdefault(circle_id, bundle)
    merged_pool["circleMedia"] = circle_media
    stats = dict(archive_pool.get("statistics") or {})
    stats["archiveUserCount"] = len(list(archive_pool.get("users") or []))
    stats["creatorPoolUserCount"] = len(list(creator_pool.get("users") or []))
    stats["mergedUserCount"] = len(merged_pool["users"])
    merged_pool["statistics"] = stats
    return merged_pool


def assert_pool_user(errors: list[str], users: dict[str, dict[str, Any]], context: str, user_id: object) -> dict[str, Any] | None:
    key = str(user_id or "")
    if key not in users:
        fail(errors, f"{context} references user outside user_pool: {key!r}")
        return None
    return users[key]


def resolved_user_media_key(user: dict[str, Any], field: str) -> str:
    value = str(user.get(field) or "").strip()
    if value:
        return value
    media_field = {
        "avatarObjectKey": "avatarMedia",
        "backgroundObjectKey": "backgroundMedia",
    }.get(field)
    media = user.get(media_field) if media_field else None
    if isinstance(media, dict):
        return str(media.get("objectKey") or "").strip()
    return ""


def required_user_field(
    errors: list[str],
    *,
    context: str,
    user: dict[str, Any],
    field: str,
) -> str | None:
    value = resolved_user_media_key(user, field)
    if not value:
        fail(errors, f"{context} user {user.get('userId')!r} missing {field}")
        return None
    return value


def verify_asset(
    errors: list[str],
    context: str,
    asset: dict[str, Any],
    *,
    allowed_mime_types: set[str],
    require_png: bool = False,
) -> None:
    object_key = str(asset.get("objectKey") or "")
    assert_media_ref(errors, f"{context}.objectKey", object_key)
    path = MEDIA_ROOT / object_key
    if not path.is_file():
        fail(errors, f"{context} media file missing: {path.relative_to(ROOT)}")
        return
    raw = path.read_bytes()
    expected_hash = str(asset.get("sourceHash") or "")
    actual_hash = sha256_bytes(raw)
    if expected_hash != actual_hash:
        fail(errors, f"{context} sourceHash mismatch: expected {expected_hash}, got {actual_hash}")
    mime_type = str(asset.get("mimeType") or "")
    if mime_type not in allowed_mime_types:
        fail(errors, f"{context} mimeType must be one of {sorted(allowed_mime_types)}, got {mime_type!r}")
    if require_png and mime_type != "image/png":
        fail(errors, f"{context} must remain image/png, got {mime_type!r}")
    if not isinstance(asset.get("width"), int) or not isinstance(asset.get("height"), int):
        fail(errors, f"{context} must declare integer width/height")


def render_group_avatar_hash(source_paths: list[Path]) -> str:
    with tempfile.TemporaryDirectory(prefix="group-avatar-verify-") as temp_dir:
        output_path = Path(temp_dir) / "composite.png"
        cmd = ["go", "run", GROUP_RENDER_PACKAGE, str(output_path), *[str(path) for path in source_paths[:9]]]
        result = subprocess.run(
            cmd,
            cwd=str(SERVICE_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"render group avatar failed: {' '.join(cmd)}\n{result.stdout}")
        return sha256_bytes(output_path.read_bytes())


def verify_group_avatar_semantics(
    errors: list[str],
    context: str,
    users: dict[str, dict[str, Any]],
    source_user_ids: list[str],
    asset: dict[str, Any],
    render_cache: dict[tuple[str, ...], str],
) -> None:
    normalized_source_ids = [user_id for user_id in source_user_ids if user_id]
    if len(normalized_source_ids) < 2:
        fail(errors, f"{context} must contain at least 2 source users, got {normalized_source_ids!r}")
        return
    cache_key = tuple(normalized_source_ids[:9])
    expected_hash = render_cache.get(cache_key)
    if expected_hash is None:
        source_paths: list[Path] = []
        for user_id in normalized_source_ids[:9]:
            user = users.get(user_id)
            if not user:
                fail(errors, f"{context} references missing user_pool user {user_id!r}")
                return
            avatar_key = resolved_user_media_key(user, "avatarObjectKey")
            avatar_path = MEDIA_ROOT / avatar_key
            if not avatar_path.is_file():
                fail(errors, f"{context} source avatar missing for {user_id!r}: {avatar_path.relative_to(ROOT)}")
                return
            source_paths.append(avatar_path)
        try:
            expected_hash = render_group_avatar_hash(source_paths)
        except RuntimeError as exc:
            fail(errors, f"{context} could not render expected composite: {exc}")
            return
        render_cache[cache_key] = expected_hash
    actual_hash = str(asset.get("sourceHash") or "")
    if actual_hash != expected_hash:
        fail(
            errors,
            f"{context} composite hash must match renderer output for source users {normalized_source_ids[:9]!r}: expected {expected_hash}, got {actual_hash}",
        )


def verify_source_catalog(errors: list[str], catalog: dict[str, Any]) -> None:
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        fail(errors, "source_catalog.entries must be a non-empty list")
        return
    for entry in entries:
        for field in ("sourceId", "sourceClass", "sourceUrl", "licenseType", "attribution", "ownerHint", "subjectType"):
            if not str(entry.get(field) or "").strip():
                fail(errors, f"source {entry.get('sourceId')!r} missing {field}")
        if entry.get("allowedForFixture") is not True:
            fail(errors, f"source {entry.get('sourceId')!r} must set allowedForFixture=true")
        if not isinstance(entry.get("themeTags"), list) or not entry.get("themeTags"):
            fail(errors, f"source {entry.get('sourceId')!r} must declare themeTags")
        if not isinstance(entry.get("toneTags"), list) or not entry.get("toneTags"):
            fail(errors, f"source {entry.get('sourceId')!r} must declare toneTags")
        download = entry.get("download")
        if not isinstance(download, dict):
            fail(errors, f"source {entry.get('sourceId')!r} missing download metadata")
            continue
        stored_rel = str(download.get("storedRelativePath") or "")
        if not stored_rel:
            fail(errors, f"source {entry.get('sourceId')!r} missing download.storedRelativePath")
            continue
        original_path = SHARED / stored_rel
        if not original_path.is_file():
            fail(errors, f"source {entry.get('sourceId')!r} original file missing: {original_path.relative_to(ROOT)}")
            continue
        raw = original_path.read_bytes()
        if str(download.get("originalSha256") or "") != sha256_bytes(raw):
            fail(errors, f"source {entry.get('sourceId')!r} originalSha256 mismatch")
        if not isinstance(download.get("originalWidth"), int) or not isinstance(download.get("originalHeight"), int):
            fail(errors, f"source {entry.get('sourceId')!r} must declare originalWidth/originalHeight")


def verify_pool_assets(errors: list[str], pool: dict[str, Any], rules: dict[str, Any]) -> None:
    media_contract = pool.get("mediaContract") or {}
    allowed_mime_types = set(media_contract.get("allowedMimeTypes") or [])
    if not allowed_mime_types:
        fail(errors, "user_pool.mediaContract.allowedMimeTypes must not be empty")
        return
    if pool.get("schemaVersion") != "shared.avatar-user-pool":
        fail(errors, f"user_pool schemaVersion must be shared.avatar-user-pool, got {pool.get('schemaVersion')!r}")
    stats = pool.get("statistics") or {}
    if int(stats.get("mediaAssetCount") or 0) < int((rules.get("targets") or {}).get("mediaAssetCountFloor") or 0):
        fail(errors, "user_pool mediaAssetCount below composition rule floor")
    for user in pool.get("users", []):
        verify_asset(errors, f"user[{user.get('userId')}].avatarMedia", user.get("avatarMedia") or {}, allowed_mime_types=allowed_mime_types)
        verify_asset(errors, f"user[{user.get('userId')}].backgroundMedia", user.get("backgroundMedia") or {}, allowed_mime_types=allowed_mime_types)
    for post_id, bundle in (pool.get("postMedia") or {}).items():
        verify_asset(errors, f"postMedia[{post_id}].cover", bundle.get("cover") or {}, allowed_mime_types=allowed_mime_types)
        for idx, asset in enumerate(bundle.get("images") or []):
            verify_asset(errors, f"postMedia[{post_id}].images[{idx}]", asset, allowed_mime_types=allowed_mime_types)
    for circle_id, bundle in (pool.get("circleMedia") or {}).items():
        verify_asset(errors, f"circleMedia[{circle_id}].avatar", bundle.get("avatar") or {}, allowed_mime_types=allowed_mime_types)
        verify_asset(errors, f"circleMedia[{circle_id}].cover", bundle.get("cover") or {}, allowed_mime_types=allowed_mime_types)
    for conv_id, bundle in (pool.get("groupAvatarMedia") or {}).items():
        verify_asset(errors, f"groupAvatarMedia[{conv_id}].composite", bundle.get("composite") or {}, allowed_mime_types=allowed_mime_types, require_png=True)


def verify_taxonomy(errors: list[str], pool: dict[str, Any], rules: dict[str, Any]) -> None:
    taxonomy = pool.get("taxonomy")
    if not isinstance(taxonomy, dict):
        fail(errors, "user_pool.taxonomy must be present")
        return
    theme_count = int((rules.get("targets") or {}).get("themeCount") or 0)
    themes = taxonomy.get("themes")
    if not isinstance(themes, list) or len(themes) != theme_count:
        fail(errors, f"user_pool.taxonomy.themes must declare {theme_count} themes")
    expected_hierarchy = list(rules.get("roleHierarchy") or rules.get("roles") or [])
    if taxonomy.get("roleHierarchy") != expected_hierarchy:
        fail(errors, "user_pool.taxonomy.roleHierarchy must match composition rules")
    if taxonomy.get("crossThemePairs") != list(rules.get("crossThemePairs") or []):
        fail(errors, "user_pool.taxonomy.crossThemePairs must match composition rules")
    association_rules = taxonomy.get("associationRules")
    if not isinstance(association_rules, dict):
        fail(errors, "user_pool.taxonomy.associationRules must be an object")
    for user in pool.get("users", []):
        theme_tags = user.get("themeTags")
        if not isinstance(theme_tags, list) or str(user.get("primaryTheme") or "") not in theme_tags:
            fail(errors, f"user[{user.get('userId')}] themeTags must include primaryTheme")
        if not isinstance(user.get("postThemeRefs"), list):
            fail(errors, f"user[{user.get('userId')}] postThemeRefs must be a list")
        if not isinstance(user.get("circleThemeRefs"), list):
            fail(errors, f"user[{user.get('userId')}] circleThemeRefs must be a list")
        if not isinstance(user.get("groupPersonaMix"), list):
            fail(errors, f"user[{user.get('userId')}] groupPersonaMix must be a list")


def verify_user_fixture(errors: list[str], users: dict[str, dict[str, Any]], user_doc: dict[str, Any]) -> None:
    profiles = user_doc["seedSets"]["user_profile_core"]["profiles"]
    for profile in profiles:
        user = assert_pool_user(errors, users, "user profile", profile.get("userId"))
        if not user:
            continue
        if profile.get("displayName") != user.get("displayName"):
            fail(errors, f"user profile {profile.get('userId')} displayName does not match user_pool")
        if profile.get("avatarUrl") != resolved_user_media_key(user, "avatarObjectKey"):
            fail(errors, f"user profile {profile.get('userId')} avatarUrl must equal avatarObjectKey")
        if profile.get("backgroundUrl") != resolved_user_media_key(user, "backgroundObjectKey"):
            fail(errors, f"user profile {profile.get('userId')} backgroundUrl must equal backgroundObjectKey")
        if profile.get("primaryTheme") != user.get("primaryTheme"):
            fail(errors, f"user profile {profile.get('userId')} primaryTheme must match user_pool")
        if profile.get("themeTags") != user.get("themeTags"):
            fail(errors, f"user profile {profile.get('userId')} themeTags must match user_pool")
        if profile.get("postThemeRefs") != user.get("postThemeRefs"):
            fail(errors, f"user profile {profile.get('userId')} postThemeRefs must match user_pool")
        if profile.get("circleThemeRefs") != user.get("circleThemeRefs"):
            fail(errors, f"user profile {profile.get('userId')} circleThemeRefs must match user_pool")
        if profile.get("groupPersonaMix") != user.get("groupPersonaMix"):
            fail(errors, f"user profile {profile.get('userId')} groupPersonaMix must match user_pool")


def verify_content_fixture(
    errors: list[str],
    users: dict[str, dict[str, Any]],
    pool: dict[str, Any],
    posts_by_id: dict[str, dict[str, Any]],
    content: dict[str, Any],
) -> None:
    post_media = pool.get("postMedia") or {}
    for post in content["seedSets"]["content_discovery_core"]["posts"]:
        post_id = str(post.get("postId") or post.get("id"))
        user = assert_pool_user(errors, users, f"content post {post_id}", post.get("authorId"))
        if not user:
            continue
        summary = posts_by_id.get(post_id)
        if not summary:
            fail(errors, f"content post {post_id} missing user_pool.posts summary")
            continue
        avatar_key = required_user_field(
            errors,
            context=f"content post {post_id}",
            user=user,
            field="avatarObjectKey",
        )
        background_key = required_user_field(
            errors,
            context=f"content post {post_id}",
            user=user,
            field="backgroundObjectKey",
        )
        if not avatar_key or not background_key:
            continue
        for field in ("authorAvatarUrl", "avatarUrl"):
            if post.get(field) != avatar_key:
                fail(errors, f"content post {post_id}.{field} must equal user avatarObjectKey")
        if post.get("authorBackgroundUrl") != background_key:
            fail(errors, f"content post {post_id}.authorBackgroundUrl must equal user backgroundObjectKey")
        if post.get("postType") != summary.get("postType"):
            fail(errors, f"content post {post_id}.postType must match user_pool.posts")
        if post.get("primaryTheme") != summary.get("primaryTheme"):
            fail(errors, f"content post {post_id}.primaryTheme must match user_pool.posts")
        if post.get("themeTags") != summary.get("themeTags"):
            fail(errors, f"content post {post_id}.themeTags must match user_pool.posts")
        bundle = post_media.get(post_id)
        if not bundle:
            fail(errors, f"content post {post_id} missing postMedia")
            continue
        cover_key = bundle["cover"]["objectKey"]
        for field in ("coverUrl", "thumbnailUrl"):
            if field in post and post.get(field) != cover_key:
                fail(errors, f"content post {post_id}.{field} must equal generated cover objectKey")
        for list_field in ("mediaUrls", "imageUrls"):
            for value in post.get(list_field) or []:
                assert_media_ref(errors, f"content post {post_id}.{list_field}", value)
        if post.get("videoUrl"):
            assert_media_ref(errors, f"content post {post_id}.videoUrl", post.get("videoUrl"))


def verify_circle_fixture(
    errors: list[str],
    users: dict[str, dict[str, Any]],
    pool: dict[str, Any],
    circles_by_id: dict[str, dict[str, Any]],
    circle: dict[str, Any],
) -> None:
    circle_media = pool.get("circleMedia") or {}
    seed = circle["seedSets"]["circle_core"]
    for item in seed["circles"]:
        circle_id = str(item.get("id") or "")
        assert_pool_user(errors, users, f"circle {circle_id}.ownerId", item.get("ownerId"))
        summary = circles_by_id.get(circle_id)
        if not summary:
            fail(errors, f"circle {circle_id} missing user_pool.circles summary")
            continue
        bundle = circle_media.get(circle_id)
        if not bundle:
            fail(errors, f"circle {circle_id} missing circleMedia")
            continue
        if item.get("avatarUrl") != bundle["avatar"]["objectKey"]:
            fail(errors, f"circle {circle_id}.avatarUrl must equal generated circle avatar objectKey")
        if item.get("coverUrl") != bundle["cover"]["objectKey"]:
            fail(errors, f"circle {circle_id}.coverUrl must equal generated circle cover objectKey")
        if item.get("circleType") != summary.get("circleType"):
            fail(errors, f"circle {circle_id}.circleType must match user_pool.circles")
        if item.get("primaryTheme") != summary.get("primaryTheme"):
            fail(errors, f"circle {circle_id}.primaryTheme must match user_pool.circles")
        if item.get("themeTags") != summary.get("themeTags"):
            fail(errors, f"circle {circle_id}.themeTags must match user_pool.circles")
    for members in seed.get("members", {}).values():
        for member in members:
            user = assert_pool_user(errors, users, "circle member", member.get("userId"))
            if user and member.get("avatarUrl") != resolved_user_media_key(user, "avatarObjectKey"):
                fail(errors, f"circle member {member.get('userId')} avatarUrl must equal user_pool avatar")
    for files in seed.get("files", {}).values():
        for item in files:
            assert_media_ref(errors, f"circle file {item.get('_id')}.objectKey", item.get("objectKey"))


def direct_target_user(conversation_id: str, current_user_id: str, members: dict[str, list[dict[str, Any]]]) -> str:
    for member in members.get(conversation_id, []):
        user_id = str(member.get("userId") or "")
        if user_id and user_id != current_user_id:
            return user_id
    return current_user_id


def verify_chat_fixture(
    errors: list[str],
    users: dict[str, dict[str, Any]],
    pool: dict[str, Any],
    conversations_by_id: dict[str, dict[str, Any]],
    chat: dict[str, Any],
) -> None:
    group_media = pool.get("groupAvatarMedia") or {}
    render_cache: dict[tuple[str, ...], str] = {}
    seed = chat["seedSets"]["chat_core"]
    current_user_id = str(seed.get("currentUserId") or "fixture_user_current")
    members = seed.get("members") or {}
    for conv in seed["conversations"]:
        conv_id = str(conv.get("conversationId") or conv.get("id") or "")
        conv_type = str(conv.get("type") or conv.get("conversationType") or "").lower()
        summary = conversations_by_id.get(conv_id)
        if not summary:
            fail(errors, f"conversation {conv_id} missing user_pool.conversations summary")
            continue
        if conv.get("conversationType") != summary.get("conversationType"):
            fail(errors, f"conversation {conv_id}.conversationType must match user_pool.conversations")
        if conv.get("primaryTheme") != summary.get("primaryTheme"):
            fail(errors, f"conversation {conv_id}.primaryTheme must match user_pool.conversations")
        if conv.get("themeTags") != summary.get("themeTags"):
            fail(errors, f"conversation {conv_id}.themeTags must match user_pool.conversations")
        if conv.get("groupPersonaMix") != summary.get("groupPersonaMix"):
            fail(errors, f"conversation {conv_id}.groupPersonaMix must match user_pool.conversations")
        if conv_type == "group":
            bundle = group_media.get(conv_id)
            if not bundle:
                fail(errors, f"group conversation {conv_id} missing groupAvatarMedia")
                continue
            if conv.get("avatarUrl") != bundle["composite"]["objectKey"]:
                fail(errors, f"group conversation {conv_id}.avatarUrl must equal derived group avatar objectKey")
            source_user_ids = [str(member.get("userId") or "") for member in members.get(conv_id, [])]
            if conv.get("groupAvatarSourceUserIds") != source_user_ids:
                fail(errors, f"group conversation {conv_id} groupAvatarSourceUserIds must match member order")
            verify_group_avatar_semantics(
                errors,
                f"group conversation {conv_id}",
                users,
                source_user_ids,
                bundle.get("composite") or {},
                render_cache,
            )
        else:
            target = direct_target_user(conv_id, current_user_id, members)
            user = assert_pool_user(errors, users, f"direct conversation {conv_id}.targetUserId", target)
            if user and conv.get("avatarUrl") != resolved_user_media_key(user, "avatarObjectKey"):
                fail(errors, f"direct conversation {conv_id}.avatarUrl must equal target user avatar")
    for conv_id, conv_members in members.items():
        for member in conv_members:
            user = assert_pool_user(errors, users, f"chat member {conv_id}", member.get("userId"))
            if user and member.get("avatarUrl") != resolved_user_media_key(user, "avatarObjectKey"):
                fail(errors, f"chat member {conv_id}/{member.get('userId')} avatarUrl must equal user_pool avatar")
            expected_current = str(member.get("userId") or "") == current_user_id
            if member.get("isCurrentUser") is not expected_current:
                fail(errors, f"chat member {conv_id}/{member.get('userId')} isCurrentUser must equal {expected_current}")
    for conv_id, messages in seed.get("messages", {}).items():
        for message in messages:
            user = assert_pool_user(errors, users, f"chat message {conv_id}/{message.get('messageId')}", message.get("senderId"))
            if user and message.get("senderAvatarUrlSnapshot") != resolved_user_media_key(user, "avatarObjectKey"):
                fail(errors, f"chat message {message.get('messageId')} senderAvatarUrlSnapshot must equal user_pool avatar")
    for contact in chat["seedSets"]["chat_contacts_core"].get("contacts", []):
        user = assert_pool_user(errors, users, "chat contact", contact.get("userId"))
        if user and contact.get("avatarUrl") != resolved_user_media_key(user, "avatarObjectKey"):
            fail(errors, f"chat contact {contact.get('userId')} avatarUrl must equal user_pool avatar")


def verify_no_external_media(errors: list[str], value: Any, path: str = "$", field_name: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            verify_no_external_media(errors, nested, f"{path}.{key}", str(key))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            verify_no_external_media(errors, nested, f"{path}[{idx}]", field_name)
    elif isinstance(value, str):
        lower = field_name.lower()
        looks_like_media_field = (
            field_name in MEDIA_FIELD_NAMES
            or field_name.endswith("ObjectKey")
            or lower in {"mediaurls", "imageurls", "mediaobjectkeys", "imageobjectkeys"}
        )
        if looks_like_media_field and value.startswith(("http://", "https://")):
            fail(errors, f"{path} must not hotlink external media: {value}")
        if "images.unsplash.com" in value or "pravatar.cc" in value:
            fail(errors, f"{path} still references external third-party media: {value}")


def collect_media_refs(value: Any, field_name: str = "") -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            refs.update(collect_media_refs(nested, str(key)))
    elif isinstance(value, list):
        for nested in value:
            refs.update(collect_media_refs(nested, field_name))
    elif isinstance(value, str):
        lower = field_name.lower()
        looks_like_media_field = (
            field_name in MEDIA_FIELD_NAMES
            or field_name.endswith("ObjectKey")
            or lower in {"mediaurls", "imageurls", "mediaobjectkeys", "imageobjectkeys"}
        )
        if looks_like_media_field and value.startswith("media/"):
            refs.add(value)
    return refs


def verify_manifests(errors: list[str]) -> dict[str, dict[str, Any]]:
    manifests = {env: load_json(path) for env, path in MANIFESTS.items()}
    domains = ["content", "circle", "chat", "user", "entity"]
    for domain in domains:
        alpha_item = next((item for item in manifests["alpha"]["seedRefs"] if item.get("domain") == domain), None)
        beta_item = next((item for item in manifests["beta"]["seedRefs"] if item.get("domain") == domain), None)
        gamma_item = next((item for item in manifests["gamma"]["seedRefs"] if item.get("domain") == domain), None)
        if not alpha_item or not beta_item or not gamma_item:
            fail(errors, f"seed manifests missing domain {domain}")
            continue
        if alpha_item.get("fixturePath") != beta_item.get("fixturePath"):
            fail(errors, f"{domain} fixturePath must match across alpha/beta manifests")
        if alpha_item.get("refs") != beta_item.get("refs"):
            fail(errors, f"{domain} refs must match across alpha/beta manifests")
        delivery_channels = alpha_item.get("deliveryChannels") or []
        if not isinstance(delivery_channels, list) or len(delivery_channels) < 2:
            fail(errors, f"alpha manifest domain {domain} must declare dual deliveryChannels")
        expected_gamma = GAMMA_CURATED_EXPECTATIONS.get(domain) or {}
        if gamma_item.get("fixturePath") != expected_gamma.get("fixturePath"):
            fail(errors, f"gamma manifest domain {domain} must use curated fixturePath {expected_gamma.get('fixturePath')!r}")
        if gamma_item.get("refs") != expected_gamma.get("refs"):
            fail(errors, f"gamma manifest domain {domain} must use curated refs {expected_gamma.get('refs')!r}")
    return manifests


def verify_gamma_curated_coverage(errors: list[str], gamma_docs: dict[str, dict[str, Any]]) -> None:
    content_posts = {
        str(item.get("postId") or item.get("id") or "")
        for item in gamma_docs["content"]["seedSets"]["content_discovery_core"].get("posts", [])
    }
    required_posts = {"fixture_photo_001", "fixture_video_001", "fixture_article_001", "fixture_moment_001"}
    missing_posts = sorted(required_posts - content_posts)
    if missing_posts:
        fail(errors, f"gamma curated content posts missing core coverage: {missing_posts}")

    user_profiles = {
        str(item.get("userId") or item.get("id") or "")
        for item in gamma_docs["user"]["seedSets"]["user_profile_core"].get("profiles", [])
    }
    required_users = {"fixture_user_current", "fixture_user_photo", "fixture_user_travel", "fixture_user_article"}
    missing_users = sorted(required_users - user_profiles)
    if missing_users:
        fail(errors, f"gamma curated user profiles missing core coverage: {missing_users}")

    circle_ids = {
        str(item.get("id") or item.get("circleId") or "")
        for item in gamma_docs["circle"]["seedSets"]["circle_core"].get("circles", [])
    }
    required_circles = {"fixture_circle_photo", "fixture_circle_travel", "fixture_circle_city", "fixture_circle_tech"}
    missing_circles = sorted(required_circles - circle_ids)
    if missing_circles:
        fail(errors, f"gamma curated circles missing core coverage: {missing_circles}")

    conversation_ids = {
        str(item.get("conversationId") or item.get("id") or "")
        for item in gamma_docs["chat"]["seedSets"]["chat_core"].get("conversations", [])
    }
    required_conversations = {
        "fixture_conv_direct",
        "fixture_conv_group",
        "fixture_conv_photo_group",
        "fixture_conv_article_direct",
    }
    missing_conversations = sorted(required_conversations - conversation_ids)
    if missing_conversations:
        fail(errors, f"gamma curated chat conversations missing core coverage: {missing_conversations}")


def verify_gamma_curated_media_bundle(
    errors: list[str],
    bundle: dict[str, Any],
    gamma_docs: dict[str, dict[str, Any]],
) -> None:
    if bundle.get("schemaVersion") != "gamma-curated-media-bundle":
        fail(errors, "gamma curated media bundle schemaVersion must be gamma-curated-media-bundle")
    if bundle.get("environment") != "gamma":
        fail(errors, "gamma curated media bundle environment must be gamma")
    max_images = int(bundle.get("maxImageObjectCount") or 0)
    image_count = int(bundle.get("imageObjectCount") or 0)
    if max_images <= 0:
        fail(errors, "gamma curated media bundle maxImageObjectCount must be positive")
    if image_count > max_images:
        fail(errors, f"gamma curated imageObjectCount exceeds cap: {image_count}")

    media_objects = bundle.get("mediaObjects")
    if not isinstance(media_objects, list) or not media_objects:
        fail(errors, "gamma curated media bundle must declare mediaObjects")
        return

    object_keys: set[str] = set()
    for item in media_objects:
        object_key = str(item.get("objectKey") or "")
        relative_path = str(item.get("relativePath") or "")
        expected_hash = str(item.get("sourceHash") or "")
        if not object_key or object_key in object_keys:
            fail(errors, f"gamma curated media bundle has duplicate/empty objectKey: {object_key!r}")
            continue
        object_keys.add(object_key)
        path = ROOT / relative_path
        if not path.is_file():
            fail(errors, f"gamma curated media bundle file missing: {relative_path}")
            continue
        raw = path.read_bytes()
        actual_hash = sha256_bytes(raw)
        if expected_hash != actual_hash:
            fail(errors, f"gamma curated media bundle hash mismatch for {object_key}: expected {expected_hash}, got {actual_hash}")

    scenario_media_refs: set[str] = set()
    for doc in gamma_docs.values():
        scenario_media_refs.update(collect_media_refs(doc))
    missing = sorted(scenario_media_refs - object_keys)
    if missing:
        fail(errors, f"gamma curated scenarios reference media outside curated bundle: {missing[:10]}")


def verify_creator_pool_media(errors: list[str]) -> None:
    """Creator pool avatar/cover must resolve through committed preset manifests.

    Canonical creator pool profiles no longer publish raw avatarObjectKey/backgroundObjectKey.
    The truth source is preset IDs -> preset manifest -> committed media assets.
    """
    if not CREATOR_POOL_SEED.is_file():
        fail(errors, f"creator_pool seed missing: {CREATOR_POOL_SEED.relative_to(ROOT)}")
        return
    if not PROFILE_PRESET_MANIFEST.is_file():
        fail(errors, f"profile preset manifest missing: {PROFILE_PRESET_MANIFEST.relative_to(ROOT)}")
        return
    seed = load_json(CREATOR_POOL_SEED)
    preset_manifest = load_json(PROFILE_PRESET_MANIFEST)
    avatar_ids = {str(item.get("presetId") or "") for item in preset_manifest.get("avatars") or []}
    cover_ids = {str(item.get("presetId") or "") for item in preset_manifest.get("covers") or []}
    users = seed.get("users") or []
    if not isinstance(users, list) or not users:
        fail(errors, "creator_pool seed has no users")
        return
    for user in users:
        handle = str(user.get("userHandle") or user.get("subAccountId") or "?")
        avatar = str(user.get("avatarPresetId") or "")
        cover = str(user.get("coverPresetId") or "")
        if avatar not in avatar_ids:
            fail(errors, f"creator_pool[{handle}] avatarPresetId not found in preset manifest: {avatar!r}")
        if cover not in cover_ids:
            fail(errors, f"creator_pool[{handle}] coverPresetId not found in preset manifest: {cover!r}")


def verify_creator_pool_manifests(errors: list[str], manifests: dict[str, dict[str, Any]]) -> None:
    entries: dict[str, dict[str, Any]] = {}
    for env, manifest in manifests.items():
        item = next(
            (it for it in manifest.get("seedRefs", []) if it.get("domain") == "creator_pool"),
            None,
        )
        if not item:
            fail(errors, f"{env} manifest missing creator_pool domain")
            continue
        entries[env] = item
    if len(entries) != len(manifests):
        return
    fixture_paths = {it.get("fixturePath") for it in entries.values()}
    if len(fixture_paths) != 1:
        fail(errors, f"creator_pool fixturePath must match across environments: {sorted(map(str, fixture_paths))}")
    refs_set = {tuple(it.get("refs") or []) for it in entries.values()}
    if len(refs_set) != 1:
        fail(errors, f"creator_pool refs must match across environments: {sorted(map(str, refs_set))}")
    if tuple(entries["alpha"].get("refs") or []) != tuple(CREATOR_POOL_CANONICAL_REFS):
        fail(errors, f"creator_pool refs must be canonical v1 set {CREATOR_POOL_CANONICAL_REFS}")


def verify_entity_scale(
    errors: list[str],
    rules: dict[str, Any],
    user_doc: dict[str, Any],
    content: dict[str, Any],
    circle: dict[str, Any],
    chat: dict[str, Any],
) -> None:
    total = 0
    total += len(user_doc["seedSets"]["user_profile_core"]["profiles"])
    total += len(content["seedSets"]["content_discovery_core"]["posts"])
    total += len(content["seedSets"]["content_discovery_core"].get("comments") or [])
    total += len(content["seedSets"]["content_discovery_core"].get("reactions") or [])
    total += len(circle["seedSets"]["circle_core"]["circles"])
    total += sum(len(items) for items in (circle["seedSets"]["circle_core"].get("groups") or {}).values())
    total += sum(len(items) for items in (circle["seedSets"]["circle_core"].get("members") or {}).values())
    total += len(chat["seedSets"]["chat_core"]["conversations"])
    total += sum(len(items) for items in (chat["seedSets"]["chat_core"].get("messages") or {}).values())
    total += sum(len(items) for items in (chat["seedSets"]["chat_core"].get("members") or {}).values())
    total += len(chat["seedSets"]["chat_contacts_core"].get("contacts") or [])
    if total < int((rules.get("targets") or {}).get("entityCountFloor") or 0):
        fail(errors, f"combined fixture entity volume below floor: {total}")


def main() -> int:
    errors: list[str] = []
    source_catalog = load_json(SOURCE_CATALOG_PATH)
    pool = load_effective_user_pool()
    rules = load_json(COMPOSITION_RULES_PATH)
    users = user_map(pool)
    posts_by_id = post_map(pool)
    circles_by_id = circle_map(pool)
    conversations_by_id = conversation_map(pool)
    verify_source_catalog(errors, source_catalog)
    verify_pool_assets(errors, pool, rules)
    verify_taxonomy(errors, pool, rules)
    user_doc = load_json(USER_SCENARIOS)
    content = load_json(CONTENT_SCENARIOS)
    circle = load_json(CIRCLE_SCENARIOS)
    chat = load_json(CHAT_SCENARIOS)
    verify_user_fixture(errors, users, user_doc)
    verify_content_fixture(errors, users, pool, posts_by_id, content)
    verify_circle_fixture(errors, users, pool, circles_by_id, circle)
    verify_chat_fixture(errors, users, pool, conversations_by_id, chat)
    manifests = verify_manifests(errors)
    verify_creator_pool_media(errors)
    verify_creator_pool_manifests(errors, manifests)
    verify_entity_scale(errors, rules, user_doc, content, circle, chat)
    for label, document in (
        ("user_scenarios", user_doc),
        ("content_scenarios", content),
        ("circle_scenarios", circle),
        ("chat_scenarios", chat),
    ):
        verify_no_external_media(errors, document, label)
    gamma_docs = {
        domain: load_json(METADATA / str(next(
            item.get("fixturePath")
            for item in manifests["gamma"]["seedRefs"]
            if item.get("domain") == domain
        )))
        for domain in ("content", "circle", "chat", "user", "entity")
    }
    verify_user_fixture(errors, users, gamma_docs["user"])
    verify_content_fixture(errors, users, pool, posts_by_id, gamma_docs["content"])
    verify_circle_fixture(errors, users, pool, circles_by_id, gamma_docs["circle"])
    verify_chat_fixture(errors, users, pool, conversations_by_id, gamma_docs["chat"])
    verify_gamma_curated_coverage(errors, gamma_docs)
    gamma_bundle = load_json(GAMMA_CURATED_MEDIA_BUNDLE)
    verify_gamma_curated_media_bundle(errors, gamma_bundle, gamma_docs)
    for label, document in gamma_docs.items():
        verify_no_external_media(errors, document, f"gamma_{label}_scenarios")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("avatar user pool consistency verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
