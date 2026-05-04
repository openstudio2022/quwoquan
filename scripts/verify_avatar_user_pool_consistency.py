#!/usr/bin/env python3
"""Verify shared avatar user pool consistency across user/content/circle/chat fixtures."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
USER_POOL_PATH = SHARED / "user_pool.json"
USER_SCENARIOS = METADATA / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
CONTENT_SCENARIOS = METADATA / "content" / "test_fixtures" / "scenarios" / "content_scenarios.json"
CIRCLE_SCENARIOS = METADATA / "social" / "circle" / "test_fixtures" / "scenarios" / "circle_scenarios.json"
CHAT_SCENARIOS = METADATA / "messages" / "chat" / "test_fixtures" / "scenarios" / "chat_scenarios.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def user_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["userId"]): item for item in pool.get("users", []) if isinstance(item, dict)}


def is_media_ref(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("media/avatar/") or value.startswith("media/background/") or value.startswith("media/image/")


def assert_media_ref(errors: list[str], context: str, value: object) -> None:
    if not is_media_ref(value):
        fail(errors, f"{context} must be a media object key, got {value!r}")


def assert_pool_user(errors: list[str], users: dict[str, dict[str, Any]], context: str, user_id: object) -> dict[str, Any] | None:
    key = str(user_id or "")
    if key not in users:
        fail(errors, f"{context} references user outside user_pool: {key!r}")
        return None
    return users[key]


def verify_asset(errors: list[str], context: str, asset: dict[str, Any]) -> None:
    object_key = str(asset.get("objectKey") or "")
    assert_media_ref(errors, f"{context}.objectKey", object_key)
    path = MEDIA_ROOT / object_key
    if not path.is_file():
        fail(errors, f"{context} media file missing: {path.relative_to(ROOT)}")
        return
    raw = path.read_bytes()
    expected_hash = str(asset.get("sourceHash") or "")
    actual_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    if expected_hash != actual_hash:
        fail(errors, f"{context} sourceHash mismatch: expected {expected_hash}, got {actual_hash}")
    if asset.get("mimeType") != "image/png":
        fail(errors, f"{context} fixture assets currently must declare image/png, got {asset.get('mimeType')!r}")
    if not isinstance(asset.get("width"), int) or not isinstance(asset.get("height"), int):
        fail(errors, f"{context} must declare integer width/height")


def verify_pool_assets(errors: list[str], pool: dict[str, Any]) -> None:
    for user in pool.get("users", []):
        verify_asset(errors, f"user[{user.get('userId')}].avatarMedia", user.get("avatarMedia") or {})
        verify_asset(errors, f"user[{user.get('userId')}].backgroundMedia", user.get("backgroundMedia") or {})
    for post_id, bundle in (pool.get("postMedia") or {}).items():
        verify_asset(errors, f"postMedia[{post_id}].cover", bundle.get("cover") or {})
        for idx, asset in enumerate(bundle.get("images") or []):
            verify_asset(errors, f"postMedia[{post_id}].images[{idx}]", asset)
    for circle_id, bundle in (pool.get("circleMedia") or {}).items():
        verify_asset(errors, f"circleMedia[{circle_id}].avatar", bundle.get("avatar") or {})
        verify_asset(errors, f"circleMedia[{circle_id}].cover", bundle.get("cover") or {})
    for conv_id, bundle in (pool.get("groupAvatarMedia") or {}).items():
        verify_asset(errors, f"groupAvatarMedia[{conv_id}].composite", bundle.get("composite") or {})


def verify_user_fixture(errors: list[str], users: dict[str, dict[str, Any]], user_doc: dict[str, Any]) -> None:
    profiles = user_doc["seedSets"]["user_profile_core"]["profiles"]
    for profile in profiles:
        user = assert_pool_user(errors, users, "user profile", profile.get("userId"))
        if not user:
            continue
        if profile.get("displayName") != user.get("displayName"):
            fail(errors, f"user profile {profile.get('userId')} displayName does not match user_pool")
        if profile.get("avatarUrl") != user.get("avatarObjectKey"):
            fail(errors, f"user profile {profile.get('userId')} avatarUrl must equal avatarObjectKey")
        if profile.get("backgroundUrl") != user.get("backgroundObjectKey"):
            fail(errors, f"user profile {profile.get('userId')} backgroundUrl must equal backgroundObjectKey")


def verify_content_fixture(errors: list[str], users: dict[str, dict[str, Any]], pool: dict[str, Any], content: dict[str, Any]) -> None:
    post_media = pool.get("postMedia") or {}
    for post in content["seedSets"]["content_discovery_core"]["posts"]:
        post_id = str(post.get("postId") or post.get("id"))
        user = assert_pool_user(errors, users, f"content post {post_id}", post.get("authorId"))
        if not user:
            continue
        avatar_key = user["avatarObjectKey"]
        background_key = user["backgroundObjectKey"]
        if post.get("displayName") != user.get("displayName"):
            fail(errors, f"content post {post_id} displayName does not match user_pool")
        for field in ("authorAvatarUrl", "avatarUrl"):
            if post.get(field) != avatar_key:
                fail(errors, f"content post {post_id}.{field} must equal user avatarObjectKey")
        if post.get("authorBackgroundUrl") != background_key:
            fail(errors, f"content post {post_id}.authorBackgroundUrl must equal user backgroundObjectKey")
        bundle = post_media.get(post_id)
        if not bundle:
            fail(errors, f"content post {post_id} missing postMedia")
            continue
        cover_key = bundle["cover"]["objectKey"]
        for field in ("coverUrl", "thumbnailUrl"):
            if field in post and post.get(field) != cover_key:
                fail(errors, f"content post {post_id}.{field} must equal generated cover objectKey")
        for list_field in ("mediaUrls", "imageUrls"):
            if list_field in post:
                for value in post.get(list_field) or []:
                    assert_media_ref(errors, f"content post {post_id}.{list_field}", value)


def verify_circle_fixture(errors: list[str], users: dict[str, dict[str, Any]], pool: dict[str, Any], circle: dict[str, Any]) -> None:
    circle_media = pool.get("circleMedia") or {}
    seed = circle["seedSets"]["circle_core"]
    for item in seed["circles"]:
        circle_id = str(item.get("id") or "")
        assert_pool_user(errors, users, f"circle {circle_id}.ownerId", item.get("ownerId"))
        bundle = circle_media.get(circle_id)
        if not bundle:
            fail(errors, f"circle {circle_id} missing circleMedia")
            continue
        if item.get("avatarUrl") != bundle["avatar"]["objectKey"]:
            fail(errors, f"circle {circle_id}.avatarUrl must equal generated circle avatar objectKey")
        if item.get("coverUrl") != bundle["cover"]["objectKey"]:
            fail(errors, f"circle {circle_id}.coverUrl must equal generated circle cover objectKey")
    for members in seed.get("members", {}).values():
        for member in members:
            user = assert_pool_user(errors, users, "circle member", member.get("userId"))
            if user and member.get("avatarUrl") != user.get("avatarObjectKey"):
                fail(errors, f"circle member {member.get('userId')} avatarUrl must equal user_pool avatar")


def direct_target_user(conversation_id: str, current_user_id: str, members: dict[str, list[dict[str, Any]]]) -> str:
    for member in members.get(conversation_id, []):
        user_id = str(member.get("userId") or "")
        if user_id and user_id != current_user_id:
            return user_id
    return current_user_id


def verify_chat_fixture(errors: list[str], users: dict[str, dict[str, Any]], pool: dict[str, Any], chat: dict[str, Any]) -> None:
    group_media = pool.get("groupAvatarMedia") or {}
    seed = chat["seedSets"]["chat_core"]
    current_user_id = str(seed.get("currentUserId") or "fixture_user_current")
    members = seed.get("members") or {}
    for conv in seed["conversations"]:
        conv_id = str(conv.get("conversationId") or conv.get("id") or "")
        conv_type = str(conv.get("type") or conv.get("conversationType") or "").lower()
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
        else:
            target = direct_target_user(conv_id, current_user_id, members)
            user = assert_pool_user(errors, users, f"direct conversation {conv_id}.targetUserId", target)
            if user and conv.get("avatarUrl") != user.get("avatarObjectKey"):
                fail(errors, f"direct conversation {conv_id}.avatarUrl must equal target user avatar")
    for conv_id, conv_members in members.items():
        for member in conv_members:
            user = assert_pool_user(errors, users, f"chat member {conv_id}", member.get("userId"))
            if user and member.get("avatarUrl") != user.get("avatarObjectKey"):
                fail(errors, f"chat member {conv_id}/{member.get('userId')} avatarUrl must equal user_pool avatar")
    for conv_id, messages in seed.get("messages", {}).items():
        for message in messages:
            user = assert_pool_user(errors, users, f"chat message {conv_id}/{message.get('messageId')}", message.get("senderId"))
            if user and message.get("senderAvatarUrlSnapshot") != user.get("avatarObjectKey"):
                fail(errors, f"chat message {message.get('messageId')} senderAvatarUrlSnapshot must equal user_pool avatar")
    for contact in chat["seedSets"]["chat_contacts_core"].get("contacts", []):
        user = assert_pool_user(errors, users, "chat contact", contact.get("userId"))
        if user and contact.get("avatarUrl") != user.get("avatarObjectKey"):
            fail(errors, f"chat contact {contact.get('userId')} avatarUrl must equal user_pool avatar")


def verify_no_unsplash(errors: list[str], value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            verify_no_unsplash(errors, nested, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            verify_no_unsplash(errors, nested, f"{path}[{idx}]")
    elif isinstance(value, str) and "images.unsplash.com" in value:
        fail(errors, f"{path} still references unsplash external media")


def main() -> int:
    errors: list[str] = []
    pool = load_json(USER_POOL_PATH)
    users = user_map(pool)
    verify_pool_assets(errors, pool)
    user_doc = load_json(USER_SCENARIOS)
    content = load_json(CONTENT_SCENARIOS)
    circle = load_json(CIRCLE_SCENARIOS)
    chat = load_json(CHAT_SCENARIOS)
    verify_user_fixture(errors, users, user_doc)
    verify_content_fixture(errors, users, pool, content)
    verify_circle_fixture(errors, users, pool, circle)
    verify_chat_fixture(errors, users, pool, chat)
    for label, document in (
        ("user_scenarios", user_doc),
        ("content_scenarios", content),
        ("circle_scenarios", circle),
        ("chat_scenarios", chat),
    ):
        verify_no_unsplash(errors, document, label)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("avatar user pool consistency verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
