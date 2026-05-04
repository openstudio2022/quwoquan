#!/usr/bin/env python3
"""Generate the shared avatar user pool and align contract fixtures to it."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
USER_POOL_PATH = SHARED / "user_pool.json"

USER_SCENARIOS = METADATA / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
CONTENT_SCENARIOS = METADATA / "content" / "test_fixtures" / "scenarios" / "content_scenarios.json"
CIRCLE_SCENARIOS = METADATA / "social" / "circle" / "test_fixtures" / "scenarios" / "circle_scenarios.json"
CHAT_SCENARIOS = METADATA / "messages" / "chat" / "test_fixtures" / "scenarios" / "chat_scenarios.json"


@dataclass(frozen=True)
class FixtureUser:
    user_id: str
    display_name: str
    bio: str
    tags: tuple[str, ...]
    persona_refs: tuple[str, ...] = ()

    @property
    def avatar_object_key(self) -> str:
        return f"media/avatar/user/{self.user_id}/v1/avatar.png"

    @property
    def background_object_key(self) -> str:
        return f"media/background/user/{self.user_id}/v1/background.png"


USERS: tuple[FixtureUser, ...] = (
    FixtureUser("fixture_user_current", "契约当前用户", "用于 alpha/beta/gamma 的当前用户主页。", ("current", "author", "contact"), ("fixture_persona_daily", "fixture_persona_work")),
    FixtureUser("fixture_user_photo", "契约摄影师", "作者主页契约数据。", ("author", "photo", "contact")),
    FixtureUser("fixture_user_travel", "契约旅行家", "旅行、天气和行程记录作者。", ("author", "travel", "contact")),
    FixtureUser("fixture_user_video", "契约剪辑师", "视频剪辑与城市影像作者。", ("author", "video")),
    FixtureUser("fixture_user_article", "契约撰稿人", "文章、攻略与长图文作者。", ("author", "article", "contact")),
    FixtureUser("fixture_user_friend", "契约好友", "与当前用户互关的同好。", ("contact", "direct-chat")),
    FixtureUser("fixture_user_weekend_1", "契约同伴一", "周末群成员，也是联系人同好。", ("contact", "group-member")),
    FixtureUser("fixture_user_weekend_2", "契约同伴二", "周末群成员，提供路线建议。", ("contact", "group-member")),
    FixtureUser("fixture_user_owner", "契约摄影社主理人", "摄影圈 owner，用于圈子权限和群聊同步验证。", ("circle-owner",)),
    FixtureUser("fixture_user_travel_owner", "契约旅行圈主", "旅行圈 owner，用于圈子成员引用完整性验证。", ("circle-owner", "travel")),
    FixtureUser("fixture_user_commenter", "契约评论者", "内容详情评论作者，用于作者头像补水验证。", ("commenter",)),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixel(x, y))
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return {
        "mimeType": "image/png",
        "width": width,
        "height": height,
        "sizeBytes": len(data),
        "sourceHash": "sha256:" + hashlib.sha256(data).hexdigest(),
    }


def palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    colors = []
    for offset in (0, 5, 11):
        colors.append(
            (
                48 + digest[offset] % 160,
                48 + digest[offset + 1] % 160,
                48 + digest[offset + 2] % 160,
            )
        )
    return colors[0], colors[1], colors[2]


def patterned_image(object_key: str, width: int, height: int, kind: str) -> dict[str, Any]:
    a, b, c = palette(f"{kind}:{object_key}")
    cx, cy = width / 2, height / 2

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        gx = x / max(1, width - 1)
        gy = y / max(1, height - 1)
        wave = (math.sin((x + y) / max(8, width // 12)) + 1) / 2
        stripe = 1 if ((x // max(8, width // 18)) + (y // max(8, height // 18))) % 2 == 0 else 0
        dist = min(1.0, math.hypot((x - cx) / width, (y - cy) / height) * 2.2)
        mix_a = 0.48 + 0.22 * wave
        mix_b = 0.32 + 0.18 * (1 - dist)
        mix_c = max(0.0, 1.0 - mix_a - mix_b)
        if stripe:
            mix_c += 0.12
            mix_a -= 0.06
            mix_b -= 0.06
        red = int(a[0] * mix_a + b[0] * mix_b + c[0] * mix_c + 28 * gx)
        green = int(a[1] * mix_a + b[1] * mix_b + c[1] * mix_c + 24 * gy)
        blue = int(a[2] * mix_a + b[2] * mix_b + c[2] * mix_c + 20 * (1 - gx))
        return max(0, min(255, red)), max(0, min(255, green)), max(0, min(255, blue))

    return write_png(MEDIA_ROOT / object_key, width, height, pixel)


def asset_record(object_key: str, width: int, height: int, kind: str) -> dict[str, Any]:
    meta = patterned_image(object_key, width, height, kind)
    return {
        "objectKey": object_key,
        "version": 1,
        **meta,
    }


def build_media_assets(content: dict[str, Any], circle: dict[str, Any], chat: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    user_assets: dict[str, dict[str, Any]] = {}
    for user in USERS:
        user_assets[user.user_id] = {
            "avatar": asset_record(user.avatar_object_key, 256, 256, "user-avatar"),
            "background": asset_record(user.background_object_key, 1200, 480, "user-background"),
        }

    posts = content["seedSets"]["content_discovery_core"]["posts"]
    post_assets: dict[str, dict[str, Any]] = {}
    for post in posts:
        post_id = str(post.get("postId") or post.get("id"))
        media_count = max(1, len(post.get("imageUrls") or post.get("mediaUrls") or []))
        images = []
        for idx in range(media_count):
            suffix = "cover" if idx == 0 else f"image-{idx + 1}"
            images.append(asset_record(f"media/image/post/{post_id}/v1/{suffix}.png", 900, 600, "post-image"))
        post_assets[post_id] = {"cover": images[0], "images": images}

    circles = circle["seedSets"]["circle_core"]["circles"]
    circle_assets: dict[str, dict[str, Any]] = {}
    for item in circles:
        circle_id = str(item["id"])
        circle_assets[circle_id] = {
            "avatar": asset_record(f"media/avatar/circle/{circle_id}/v1/avatar.png", 256, 256, "circle-avatar"),
            "cover": asset_record(f"media/image/circle/{circle_id}/v1/cover.png", 1200, 520, "circle-cover"),
        }

    conversations = chat["seedSets"]["chat_core"]["conversations"]
    group_assets: dict[str, dict[str, Any]] = {}
    for conv in conversations:
        if str(conv.get("type") or conv.get("conversationType")).lower() != "group":
            continue
        conv_id = str(conv["conversationId"])
        group_assets[conv_id] = {
            "composite": asset_record(f"media/avatar/group/{conv_id}/v1/composite.png", 256, 256, "group-avatar"),
        }
    return user_assets, post_assets, circle_assets, group_assets


def user_by_id() -> dict[str, FixtureUser]:
    return {user.user_id: user for user in USERS}


def url_from_object_key(object_key: str) -> str:
    return object_key


def sync_user_fixture(user_doc: dict[str, Any], user_assets: dict[str, dict[str, Any]]) -> None:
    users = user_by_id()
    seed = user_doc["seedSets"]["user_profile_core"]
    by_id = {str(profile["userId"]): profile for profile in seed["profiles"]}
    for user in USERS:
        profile = by_id.get(user.user_id)
        if profile is None:
            profile = {"userId": user.user_id, "stats": {"followingCount": 0, "followerCount": 0, "postCount": 0, "circleCount": 0, "likeCount": 0}}
            seed["profiles"].append(profile)
        profile["displayName"] = user.display_name
        profile["avatarObjectKey"] = user.avatar_object_key
        profile["backgroundObjectKey"] = user.background_object_key
        profile["avatarUrl"] = url_from_object_key(user.avatar_object_key)
        profile["backgroundUrl"] = url_from_object_key(user.background_object_key)
        profile["bio"] = user.bio
        profile["personaRefs"] = list(user.persona_refs)
        profile["tags"] = list(user.tags)
        profile["media"] = copy.deepcopy(user_assets[user.user_id])
        profile.setdefault("stats", {})
    assert users


def sync_content_fixture(content: dict[str, Any], post_assets: dict[str, dict[str, Any]]) -> None:
    users = user_by_id()
    posts = content["seedSets"]["content_discovery_core"]["posts"]
    for post in posts:
        post_id = str(post.get("postId") or post.get("id"))
        author_id = str(post.get("authorId") or "")
        user = users[author_id]
        post["displayName"] = user.display_name
        post["authorDisplayNameSnapshot"] = user.display_name
        post["authorAvatarObjectKey"] = user.avatar_object_key
        post["avatarObjectKey"] = user.avatar_object_key
        post["authorBackgroundObjectKey"] = user.background_object_key
        post["authorAvatarUrl"] = url_from_object_key(user.avatar_object_key)
        post["avatarUrl"] = url_from_object_key(user.avatar_object_key)
        post["authorBackgroundUrl"] = url_from_object_key(user.background_object_key)
        assets = post_assets[post_id]
        cover_key = assets["cover"]["objectKey"]
        image_keys = [asset["objectKey"] for asset in assets["images"]]
        if "coverUrl" in post:
            post["coverObjectKey"] = cover_key
            post["coverUrl"] = url_from_object_key(cover_key)
        if "thumbnailUrl" in post:
            post["thumbnailObjectKey"] = cover_key
            post["thumbnailUrl"] = url_from_object_key(cover_key)
        if "mediaUrls" in post:
            post["mediaObjectKeys"] = image_keys
            post["mediaUrls"] = [url_from_object_key(key) for key in image_keys]
        if "imageUrls" in post:
            post["imageObjectKeys"] = image_keys
            post["imageUrls"] = [url_from_object_key(key) for key in image_keys]
        article_document = post.get("articleDocument")
        if isinstance(article_document, dict):
            for block in article_document.get("blocks", []):
                if isinstance(block, dict) and "imageUrl" in block:
                    block["imageObjectKey"] = cover_key
                    block["imageUrl"] = url_from_object_key(cover_key)
            for asset in article_document.get("assets", []):
                if isinstance(asset, dict) and "imageUrl" in asset:
                    asset["imageObjectKey"] = cover_key
                    asset["imageUrl"] = url_from_object_key(cover_key)
    for comment in content["seedSets"]["content_discovery_core"].get("comments", []):
        author_id = str(comment.get("authorId") or "")
        if author_id in users:
            user = users[author_id]
            comment["authorDisplayNameSnapshot"] = user.display_name
            comment["authorAvatarObjectKeySnapshot"] = user.avatar_object_key
            comment["authorAvatarUrlSnapshot"] = url_from_object_key(user.avatar_object_key)


def sync_circle_fixture(circle: dict[str, Any], circle_assets: dict[str, dict[str, Any]]) -> None:
    users = user_by_id()
    seed = circle["seedSets"]["circle_core"]
    for item in seed["circles"]:
        owner_id = str(item.get("ownerId") or "")
        if owner_id not in users:
            raise ValueError(f"circle owner missing from user pool: {owner_id}")
        circle_id = str(item["id"])
        assets = circle_assets[circle_id]
        item["ownerDisplayNameSnapshot"] = users[owner_id].display_name
        item["avatarObjectKey"] = assets["avatar"]["objectKey"]
        item["coverObjectKey"] = assets["cover"]["objectKey"]
        item["avatarUrl"] = url_from_object_key(assets["avatar"]["objectKey"])
        item["coverUrl"] = url_from_object_key(assets["cover"]["objectKey"])
    for groups in seed.get("groups", {}).values():
        for group in groups:
            owner_id = str(group.get("ownerUserId") or "")
            if owner_id not in users:
                raise ValueError(f"circle group owner missing from user pool: {owner_id}")
            group["ownerDisplayNameSnapshot"] = users[owner_id].display_name
    for members in seed.get("members", {}).values():
        for member in members:
            user_id = str(member.get("userId") or "")
            if user_id not in users:
                raise ValueError(f"circle member missing from user pool: {user_id}")
            user = users[user_id]
            member["displayName"] = user.display_name
            member["avatarObjectKey"] = user.avatar_object_key
            member["avatarUrl"] = url_from_object_key(user.avatar_object_key)


def direct_target_user(conversation_id: str, current_user_id: str, members: dict[str, list[dict[str, Any]]]) -> str:
    candidates = [str(item.get("userId") or "") for item in members.get(conversation_id, [])]
    for candidate in candidates:
        if candidate and candidate != current_user_id:
            return candidate
    return current_user_id


def sync_chat_fixture(chat: dict[str, Any], group_assets: dict[str, dict[str, Any]]) -> None:
    users = user_by_id()
    seed = chat["seedSets"]["chat_core"]
    contacts_seed = chat["seedSets"]["chat_contacts_core"]
    current_user_id = str(seed.get("currentUserId") or "fixture_user_current")
    members = seed.get("members", {})
    for conv in seed["conversations"]:
        conv_id = str(conv["conversationId"])
        conv_type = str(conv.get("type") or conv.get("conversationType") or "").lower()
        if conv_type == "group":
            object_key = group_assets[conv_id]["composite"]["objectKey"]
            conv["avatarObjectKey"] = object_key
            conv["avatarUrl"] = url_from_object_key(object_key)
            conv["groupAvatarVersion"] = 1
            conv["groupAvatarSourceUserIds"] = [str(item.get("userId") or "") for item in members.get(conv_id, []) if item.get("userId")]
        else:
            target_user_id = direct_target_user(conv_id, current_user_id, members)
            user = users[target_user_id]
            conv["targetUserId"] = target_user_id
            conv["avatarObjectKey"] = user.avatar_object_key
            conv["avatarUrl"] = url_from_object_key(user.avatar_object_key)
    for conv_id, conv_members in members.items():
        for member in conv_members:
            user_id = str(member.get("userId") or "")
            if user_id not in users:
                raise ValueError(f"chat member missing from user pool: {user_id}")
            user = users[user_id]
            member["displayName"] = user.display_name
            member["avatarObjectKey"] = user.avatar_object_key
            member["avatarUrl"] = url_from_object_key(user.avatar_object_key)
    for messages in seed.get("messages", {}).values():
        for message in messages:
            sender_id = str(message.get("senderId") or "")
            if sender_id not in users:
                raise ValueError(f"chat message sender missing from user pool: {sender_id}")
            user = users[sender_id]
            message["senderDisplayNameSnapshot"] = user.display_name
            message["senderAvatarObjectKeySnapshot"] = user.avatar_object_key
            message["senderAvatarUrlSnapshot"] = url_from_object_key(user.avatar_object_key)
            message["senderAvatar"] = url_from_object_key(user.avatar_object_key)
    for contact in contacts_seed.get("contacts", []):
        user_id = str(contact.get("userId") or "")
        if user_id not in users:
            raise ValueError(f"chat contact missing from user pool: {user_id}")
        user = users[user_id]
        contact["displayName"] = user.display_name
        contact["avatarObjectKey"] = user.avatar_object_key
        contact["avatarUrl"] = url_from_object_key(user.avatar_object_key)
        contact["bio"] = user.bio


def build_user_pool(user_assets: dict[str, dict[str, Any]], post_assets: dict[str, dict[str, Any]], circle_assets: dict[str, dict[str, Any]], group_assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": "shared.avatar-user-pool.v1",
        "description": "alpha/beta/gamma 共享身份与头像媒体真相源。各域 fixture 只引用 userId/objectKey，运行时由 CDN base 或 gateway /media/* 派生可访问 URL。",
        "mediaContract": {
            "urlDerivation": "runtime joins MEDIA_*_CDN_BASE_URL or gateway base with objectKey",
            "allowedMimeTypes": ["image/jpeg", "image/png", "image/webp"],
            "groupAvatarRenderer": "RenderGroupAvatarPNG",
            "groupAvatarMimeType": "image/png",
        },
        "users": [
            {
                "userId": user.user_id,
                "displayName": user.display_name,
                "avatarObjectKey": user.avatar_object_key,
                "backgroundObjectKey": user.background_object_key,
                "avatarMedia": user_assets[user.user_id]["avatar"],
                "backgroundMedia": user_assets[user.user_id]["background"],
                "bio": user.bio,
                "personaRefs": list(user.persona_refs),
                "tags": list(user.tags),
            }
            for user in USERS
        ],
        "postMedia": post_assets,
        "circleMedia": circle_assets,
        "groupAvatarMedia": group_assets,
        "derivationRules": {
            "contentAuthor": "authorId -> users[].avatarObjectKey/backgroundObjectKey/displayName",
            "chatDirectAvatar": "direct conversation avatar -> other member avatarObjectKey",
            "chatGroupAvatar": "group conversation avatar -> groupAvatarMedia[conversationId].composite",
            "chatMember": "member.userId/contact.userId/senderId -> users[]",
            "circleMember": "ownerId/member.userId -> users[]",
        },
        "syncEvents": {
            "userAvatarUpdated": "UserAvatarUpdated updates user projection and rehydrates contact/member/sender snapshots",
            "conversationAvatarUpdated": "ConversationAvatarUpdated updates group conversation avatar after member/avatar changes",
        },
    }


def main() -> int:
    user_doc = load_json(USER_SCENARIOS)
    content = load_json(CONTENT_SCENARIOS)
    circle = load_json(CIRCLE_SCENARIOS)
    chat = load_json(CHAT_SCENARIOS)

    user_assets, post_assets, circle_assets, group_assets = build_media_assets(content, circle, chat)
    sync_user_fixture(user_doc, user_assets)
    sync_content_fixture(content, post_assets)
    sync_circle_fixture(circle, circle_assets)
    sync_chat_fixture(chat, group_assets)

    write_json(USER_POOL_PATH, build_user_pool(user_assets, post_assets, circle_assets, group_assets))
    write_json(USER_SCENARIOS, user_doc)
    write_json(CONTENT_SCENARIOS, content)
    write_json(CIRCLE_SCENARIOS, circle)
    write_json(CHAT_SCENARIOS, chat)
    print(f"avatar user pool synced: {USER_POOL_PATH.relative_to(ROOT)}")
    print(f"media assets written under: {MEDIA_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
