#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "quwoquan_service"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
ORIGINAL_ROOT = SHARED / "original_media"
USER_POOL_PATH = SHARED / "user_pool.json"
SOURCE_CATALOG_PATH = SHARED / "source_catalog.json"
THEME_CATALOG_PATH = SHARED / "theme_catalog.json"
COMPOSITION_RULES_PATH = SHARED / "composition_rules.json"
USER_SCENARIOS = METADATA / "user" / "test_fixtures" / "scenarios" / "user_scenarios.json"
CONTENT_SCENARIOS = METADATA / "content" / "test_fixtures" / "scenarios" / "content_scenarios.json"
CIRCLE_SCENARIOS = METADATA / "social" / "circle" / "test_fixtures" / "scenarios" / "circle_scenarios.json"
CHAT_SCENARIOS = METADATA / "messages" / "chat" / "test_fixtures" / "scenarios" / "chat_scenarios.json"
GROUP_RENDER_PACKAGE = "./cmd/render-group-avatar"
BETA_VIDEO_OBJECT_KEY = "media/video/beta-sample.mp4"

ROLE_ORDER = [
    "leadAuthor",
    "secondaryAuthor",
    "circleOwner",
    "groupOrganizer",
    "friendContact",
    "commenter",
    "casualMember",
    "currentUserVariant",
]
ROLE_TAGS = {
    "leadAuthor": ["author"],
    "secondaryAuthor": ["author"],
    "circleOwner": ["circle-owner"],
    "groupOrganizer": ["group-organizer", "group-member"],
    "friendContact": ["contact"],
    "commenter": ["commenter"],
    "casualMember": ["group-member"],
    "currentUserVariant": ["current", "contact", "author"],
}
ROLE_BIOS = {
    "leadAuthor": "主题主作者，承担作者主页和高频 post。",
    "secondaryAuthor": "主题副作者，补充 feed 视觉层次。",
    "circleOwner": "主题圈主，用于圈子与公开群联动。",
    "groupOrganizer": "主题群组织者，用于群聊与活动编排。",
    "friendContact": "主题联系人，用于联系人和私聊入口。",
    "commenter": "主题评论者，用于详情评论与互动补水。",
    "casualMember": "主题普通成员，用于圈子与群成员扩容。",
    "currentUserVariant": "当前用户在该主题下的镜像身份。",
}
CIRCLE_CATEGORY = {
    "photography": ("humanity", "影像", "culture_arts"),
    "travel": ("travel", "攻略", "culture_arts"),
    "cityWalk": ("meet", "城市", "social_meet"),
    "food": ("food", "探店", "food"),
    "coffee": ("food", "咖啡", "food"),
    "lifestyle": ("life", "生活", "lifestyle"),
    "fitness": ("sport", "训练", "lifestyle"),
    "pet": ("pet", "陪伴", "lifestyle"),
    "parenting": ("family", "成长", "lifestyle"),
    "outdoor": ("outdoor", "营地", "culture_arts"),
    "tech": ("tech", "AI", "tech"),
    "designWriting": ("humanity", "表达", "culture_arts"),
}
CROSS_THEME_PAIRS = [
    ("photography", "travel"),
    ("cityWalk", "coffee"),
    ("food", "lifestyle"),
    ("tech", "designWriting"),
    ("outdoor", "pet"),
    ("fitness", "lifestyle"),
]
CORE_USER_PRESETS = {
    "fixture_user_current": {
        "themeId": "lifestyle",
        "role": "currentUserVariant",
        "displayName": "契约当前用户",
        "bio": "用于 alpha/beta/gamma 的当前用户主页。",
        "avatarSourceId": "portrait_legacy_lifestyle_01",
        "backgroundSourceId": "scene_lifestyle_home_01",
        "subAccountRefs": ["fixture_persona_daily", "fixture_persona_work"],
        "tags": ["current", "author", "contact"],
        "format": "png",
    },
    "fixture_user_photo": {
        "themeId": "photography",
        "role": "leadAuthor",
        "displayName": "契约摄影师",
        "bio": "作者主页契约数据。",
        "avatarSourceId": "portrait_legacy_photography_01",
        "backgroundSourceId": "scene_photo_architecture_01",
        "tags": ["author", "photo", "contact"],
        "format": "png",
    },
    "fixture_user_travel": {
        "themeId": "travel",
        "role": "leadAuthor",
        "displayName": "契约旅行家",
        "bio": "旅行、天气和行程记录作者。",
        "avatarSourceId": "portrait_legacy_travel_01",
        "backgroundSourceId": "landscape_travel_01",
        "tags": ["author", "travel", "contact"],
        "format": "png",
    },
    "fixture_user_video": {
        "themeId": "cityWalk",
        "role": "groupOrganizer",
        "displayName": "契约剪辑师",
        "bio": "视频剪辑与城市影像作者。",
        "avatarSourceId": "portrait_legacy_city_01",
        "backgroundSourceId": "scene_city_01",
        "tags": ["author", "video"],
        "format": "png",
    },
    "fixture_user_article": {
        "themeId": "designWriting",
        "role": "leadAuthor",
        "displayName": "契约撰稿人",
        "bio": "文章、攻略与长图文作者。",
        "avatarSourceId": "portrait_curated_writing_01",
        "backgroundSourceId": "scene_design_office_01",
        "tags": ["author", "article", "contact"],
        "format": "png",
    },
    "fixture_user_friend": {
        "themeId": "coffee",
        "role": "friendContact",
        "displayName": "契约好友",
        "bio": "与当前用户互关的同好。",
        "avatarSourceId": "portrait_legacy_food_01",
        "backgroundSourceId": "scene_coffee_night_01",
        "tags": ["contact", "direct-chat"],
        "format": "png",
    },
    "fixture_user_weekend_1": {
        "themeId": "lifestyle",
        "role": "groupOrganizer",
        "displayName": "契约同伴一",
        "bio": "周末群成员，也是联系人同好。",
        "avatarSourceId": "portrait_legacy_design_01",
        "backgroundSourceId": "scene_lifestyle_home_01",
        "tags": ["contact", "group-member"],
        "format": "png",
    },
    "fixture_user_weekend_2": {
        "themeId": "food",
        "role": "circleOwner",
        "displayName": "契约同伴二",
        "bio": "周末群成员，提供路线建议。",
        "avatarSourceId": "portrait_curated_family_01",
        "backgroundSourceId": "scene_food_01",
        "tags": ["contact", "group-member"],
        "format": "png",
    },
    "fixture_user_owner": {
        "themeId": "photography",
        "role": "circleOwner",
        "displayName": "契约摄影社主理人",
        "bio": "摄影圈 owner，用于圈子权限和群聊同步验证。",
        "avatarSourceId": "portrait_curated_design_02",
        "backgroundSourceId": "scene_article_beach_01",
        "tags": ["circle-owner"],
        "format": "png",
    },
    "fixture_user_travel_owner": {
        "themeId": "travel",
        "role": "circleOwner",
        "displayName": "契约旅行圈主",
        "bio": "旅行圈 owner，用于圈子成员引用完整性验证。",
        "avatarSourceId": "portrait_curated_outdoor_01",
        "backgroundSourceId": "landscape_travel_02",
        "tags": ["circle-owner", "travel"],
        "format": "png",
    },
    "fixture_user_commenter": {
        "themeId": "designWriting",
        "role": "commenter",
        "displayName": "契约评论者",
        "bio": "内容详情评论作者，用于作者头像补水验证。",
        "avatarSourceId": "portrait_curated_tech_01",
        "backgroundSourceId": "object_book_photography_01",
        "tags": ["commenter"],
        "format": "png",
    },
}
CORE_CIRCLE_PRESETS = {
    "photography": {"circleId": "fixture_circle_photo", "conversationId": "fixture_conv_circle_photo", "groupId": "fixture_group_photo_public", "name": "契约摄影社", "ownerId": "fixture_user_owner", "format": "png"},
    "travel": {"circleId": "fixture_circle_travel", "conversationId": "fixture_conv_circle_travel", "groupId": "fixture_group_travel_public", "name": "契约旅行手账", "ownerId": "fixture_user_travel_owner", "format": "png"},
    "cityWalk": {"circleId": "fixture_circle_city", "conversationId": "fixture_conv_circle_city", "groupId": "fixture_group_city_public", "name": "契约城市漫步", "ownerId": "fixture_user_video", "format": "png"},
    "lifestyle": {"circleId": "fixture_circle_life", "conversationId": "fixture_conv_circle_life", "groupId": "fixture_group_life_public", "name": "契约生活方式", "ownerId": "fixture_user_weekend_1", "format": "png"},
    "tech": {"circleId": "fixture_circle_tech", "conversationId": "fixture_conv_circle_tech", "groupId": "fixture_group_tech_public", "name": "契约科技前沿", "ownerId": "fixture_user_article", "format": "png"},
    "food": {"circleId": "fixture_circle_food", "conversationId": "fixture_conv_circle_food", "groupId": "fixture_group_food_public", "name": "契约美食探店", "ownerId": "fixture_user_weekend_2", "format": "png"},
}

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    return value.replace(" ", "-").replace("/", "-").replace("_", "-").lower()


def user_suffix(user_id: str) -> str:
    return user_id.replace("fixture_user_", "").replace("fixture_", "")


def circle_suffix(circle_id: str) -> str:
    return circle_id.replace("fixture_circle_", "").replace("fixture_", "")


def stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def ordered_theme_tags(primary_theme: str, secondary_themes: list[str]) -> list[str]:
    return stable_unique([primary_theme, *secondary_themes])


def role_mix(users_by_id: dict[str, dict[str, Any]], member_ids: list[str]) -> list[dict[str, Any]]:
    ordered_roles: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for member_id in member_ids:
        user = users_by_id.get(member_id)
        if not user:
            continue
        role = str(user.get("primaryRole") or "")
        if not role:
            continue
        bucket = buckets.setdefault(role, {"role": role, "count": 0, "userIds": []})
        bucket["count"] += 1
        bucket["userIds"].append(member_id)
        if role not in ordered_roles:
            ordered_roles.append(role)
    return [buckets[role] for role in ordered_roles]


def mime_for_ext(ext: str) -> str:
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    raise ValueError(f"unsupported ext: {ext}")


def sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def article_cover_asset_id(object_key: str) -> str:
    return "fixture_asset_" + object_key.replace("/", "_").replace(".", "_")


def build_article_payload(*, title: str, summary: str, body: str, cover: dict[str, Any]) -> dict[str, Any]:
    cover_object_key = str(cover.get("objectKey") or "")
    asset_id = article_cover_asset_id(cover_object_key)
    markdown = (
        f"---\n"
        f"title: {title}\n"
        f"summary: {summary}\n"
        f"template: journal\n"
        f"fontPreset: clean\n"
        f"coverImage: asset://{asset_id}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body}\n\n"
        f":::figure id=\"{asset_id}\" layout=\"fullWidth\" caption=\"\"\n"
        f"asset://{asset_id}\n"
        f":::\n"
    )
    markdown_digest = sha256_bytes(markdown.encode("utf-8"))
    return {
        "articleMarkdown": markdown,
        "articleMarkdownVersion": "qwq-rich-md/1",
        "articleMarkdownDigest": markdown_digest,
        "articleAssetManifest": {
            "schemaVersion": 1,
            "articleMarkdownVersion": "qwq-rich-md/1",
            "articleMarkdownDigest": markdown_digest,
            "assets": [
                {
                    "assetId": asset_id,
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": cover_object_key,
                    "caption": "封面",
                    "sha256": str(cover.get("sourceHash") or ""),
                }
            ],
        },
        "articleRenderProfile": {
            "template": "journal",
            "fontPreset": "clean",
            "layoutPolicy": {
                "wrapDowngrade": "compactWidthToFullWidth",
                "galleryDowngrade": "singleColumn",
            },
        },
    }


def palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    colors = []
    for offset in (0, 5, 11):
        colors.append((48 + digest[offset] % 160, 48 + digest[offset + 1] % 160, 48 + digest[offset + 2] % 160))
    return colors[0], colors[1], colors[2]


def png_chunk(kind: bytes, data: bytes) -> bytes:
    import struct
    import zlib
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def fallback_image(path: Path, width: int, height: int, seed: str) -> tuple[str, int]:
    import struct
    import zlib
    a, b, c = palette(seed)
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            gx = x / max(1, width - 1)
            gy = y / max(1, height - 1)
            stripe = 1 if ((x // max(8, width // 16)) + (y // max(8, height // 16))) % 2 == 0 else 0
            wave = (math.sin((x + y) / max(8, width // 10)) + 1) / 2
            mix_a = 0.52 + 0.18 * wave
            mix_b = 0.32 + 0.1 * (1 - gy)
            mix_c = max(0.0, 1.0 - mix_a - mix_b) + (0.08 if stripe else 0.0)
            red = int(a[0] * mix_a + b[0] * mix_b + c[0] * mix_c + 18 * gx)
            green = int(a[1] * mix_a + b[1] * mix_b + c[1] * mix_c + 20 * gy)
            blue = int(a[2] * mix_a + b[2] * mix_b + c[2] * mix_c + 14 * (1 - gx))
            rows.extend([max(0, min(255, red)), max(0, min(255, green)), max(0, min(255, blue))])
    data = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9)) + png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return "image/png", len(data)


def run_checked(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stdout}")
    return result.stdout


def sips_dimensions(path: Path) -> tuple[int, int]:
    output = run_checked(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    width = 0
    height = 0
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":", 1)[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":", 1)[1].strip())
    if width <= 0 or height <= 0:
        raise RuntimeError(f"cannot parse image size for {path}\n{output}")
    return width, height


def guess_ext(content_type: str, url: str) -> str:
    lower = content_type.lower()
    if "png" in lower or url.lower().endswith(".png"):
        return "png"
    if "webp" in lower or "webp" in url.lower():
        return "webp"
    return "jpg"


def fetch_source(entry: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    ORIGINAL_ROOT.mkdir(parents=True, exist_ok=True)
    download = dict(entry.get("download") or {})
    stored_rel = str(download.get("storedRelativePath") or "")
    expected_hash = str(download.get("originalSha256") or "")
    if stored_rel:
        existing = SHARED / stored_rel
        if existing.is_file():
            raw = existing.read_bytes()
            actual = sha256_bytes(raw)
            if expected_hash and actual == expected_hash:
                download.setdefault("bytes", len(raw))
                download.setdefault("contentType", mime_for_ext(existing.suffix.lstrip(".")))
                return existing, download
    try:
        req = urllib.request.Request(str(entry["sourceUrl"]), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context()) as response:
            raw = response.read()
            content_type = response.headers.get_content_type()
    except Exception:
        fallback_path = ORIGINAL_ROOT / f"{entry['sourceId']}.png"
        content_type, size_bytes = fallback_image(fallback_path, 1440, 1440, str(entry["sourceId"]))
        raw = fallback_path.read_bytes()
        return fallback_path, {"storedRelativePath": str(fallback_path.relative_to(SHARED)), "contentType": content_type, "bytes": size_bytes, "originalSha256": sha256_bytes(raw), "fallbackUsed": True}
    ext = guess_ext(content_type, str(entry["sourceUrl"]))
    stored = ORIGINAL_ROOT / f"{entry['sourceId']}.{ext}"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(raw)
    return stored, {"storedRelativePath": str(stored.relative_to(SHARED)), "contentType": content_type, "bytes": len(raw), "originalSha256": sha256_bytes(raw)}


def derive_image(source_path: Path, object_key: str, width: int, height: int, out_format: str) -> dict[str, Any]:
    dst = MEDIA_ROOT / object_key
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_w, src_h = sips_dimensions(source_path)
    target_ratio = width / float(height)
    src_ratio = src_w / float(src_h)
    crop_w = src_w
    crop_h = src_h
    if abs(src_ratio - target_ratio) > 0.01:
        if src_ratio > target_ratio:
            crop_w = max(1, int(round(src_h * target_ratio)))
            crop_h = src_h
        else:
            crop_w = src_w
            crop_h = max(1, int(round(src_w / target_ratio)))
    work = source_path
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        if crop_w != src_w or crop_h != src_h:
            cropped = temp_dir_path / f"crop{source_path.suffix or '.jpg'}"
            run_checked(["sips", "-c", str(crop_h), str(crop_w), str(source_path), "--out", str(cropped)])
            work = cropped
        sips_format = "jpeg" if out_format == "jpg" else out_format
        cmd = ["sips", "-s", "format", sips_format]
        if out_format == "jpg":
            cmd += ["-s", "formatOptions", "88"]
        cmd += ["-z", str(height), str(width), str(work), "--out", str(dst)]
        run_checked(cmd)
    raw = dst.read_bytes()
    return {"objectKey": object_key, "version": 1, "mimeType": mime_for_ext(out_format), "width": width, "height": height, "sizeBytes": len(raw), "sourceHash": sha256_bytes(raw)}


def render_group_composite(output_key: str, input_paths: list[Path]) -> dict[str, Any]:
    dst = MEDIA_ROOT / output_key
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        ["go", "run", GROUP_RENDER_PACKAGE, str(dst), *[str(path) for path in input_paths[:9]]],
        cwd=SERVICE_ROOT,
    )
    raw = dst.read_bytes()
    return {"objectKey": output_key, "version": 1, "mimeType": "image/png", "width": 256, "height": 256, "sizeBytes": len(raw), "sourceHash": sha256_bytes(raw)}


def ensure_beta_sample_video() -> None:
    path = MEDIA_ROOT / BETA_VIDEO_OBJECT_KEY
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")


def load_catalogs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return load_json(SOURCE_CATALOG_PATH), load_json(THEME_CATALOG_PATH), load_json(COMPOSITION_RULES_PATH)


def choose_source(theme: dict[str, Any], key: str, index: int) -> str:
    values = list(theme.get(key) or [])
    return values[index % len(values)]


def user_stats_template(theme_idx: int, role_idx: int) -> dict[str, int]:
    base = 8 + theme_idx * 3 + role_idx
    return {"followingCount": 12 + base, "followerCount": 30 + base * 4, "postCount": 0, "circleCount": 0, "likeCount": 60 + base * 9}


def role_display(theme_name: str, role: str) -> str:
    labels = {"leadAuthor": "作者", "secondaryAuthor": "副作者", "circleOwner": "圈主", "groupOrganizer": "组织者", "friendContact": "联系人", "commenter": "评论者", "casualMember": "成员", "currentUserVariant": "当前用户镜像"}
    return f"契约{theme_name}{labels[role]}"


def iso_at(offset_hours: int) -> str:
    base = datetime(2026, 4, 29, 8, 0, 0)
    return (base + timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def media_spec(post_id: str, variant: str, source_id: str, width: int, height: int, format_ext: str) -> dict[str, Any]:
    return {"sourceId": source_id, "objectKey": f"media/image/post/{post_id}/v1/{variant}.{format_ext}", "width": width, "height": height, "format": format_ext}


def build_users(source_catalog: dict[str, Any], theme_catalog: dict[str, Any], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    source_index = {entry["sourceId"]: entry for entry in source_catalog["entries"]}
    targets = dict(rules["targets"])
    users_per_theme = int(targets["userCount"] / len(theme_catalog["themes"]))
    user_assets: dict[str, dict[str, Any]] = {}
    background_assets: dict[str, dict[str, Any]] = {}
    users: list[dict[str, Any]] = []
    source_updates: list[dict[str, Any]] = []

    for entry in source_catalog["entries"]:
        path, download_meta = fetch_source(entry)
        download = dict(entry.get("download") or {})
        download.update(download_meta)
        width, height = sips_dimensions(path)
        download["originalWidth"] = width
        download["originalHeight"] = height
        source_updates.append({**entry, "download": download})

    source_index = {entry["sourceId"]: entry for entry in source_updates}

    for preset_id, preset in CORE_USER_PRESETS.items():
        avatar_format = preset.get("format", "png")
        avatar = derive_image(
            SHARED / source_index[preset["avatarSourceId"]]["download"]["storedRelativePath"],
            f"media/avatar/user/{preset_id}/v1/avatar.{avatar_format}",
            512,
            512,
            avatar_format,
        )
        background = derive_image(
            SHARED / source_index[preset["backgroundSourceId"]]["download"]["storedRelativePath"],
            f"media/background/user/{preset_id}/v1/background.{avatar_format}",
            1600,
            900,
            avatar_format,
        )
        user_assets[preset_id] = avatar
        background_assets[preset_id] = background
        theme = next(item for item in theme_catalog["themes"] if item["themeId"] == preset["themeId"])
        users.append(
            {
                "userId": preset_id,
                "displayName": preset["displayName"],
                "headline": f"{theme['displayName']} · {preset['bio']}",
                "bio": preset["bio"],
                "primaryTheme": preset["themeId"],
                "secondaryThemes": list(theme.get("adjacentThemes") or [])[:2],
                "primaryRole": preset["role"],
                "roleTags": sorted(set(ROLE_TAGS[preset["role"]] + list(preset.get("tags") or []))),
                "subAccountRefs": list(preset.get("subAccountRefs") or []),
                "themeTags": ordered_theme_tags(preset["themeId"], list(theme.get("adjacentThemes") or [])[:2]),
                "postThemeRefs": [],
                "circleThemeRefs": [],
                "groupPersonaMix": [],
                "profile": {"avatar": avatar, "background": background},
                "crossDomainRefs": {"posts": [], "circles": [], "conversations": []},
                "stats": {"followingCount": 96, "followerCount": 240, "postCount": 0, "circleCount": 0, "likeCount": 360},
                "sourceRefs": {"avatarSourceId": preset["avatarSourceId"], "backgroundSourceId": preset["backgroundSourceId"]},
                "createdAt": iso_at(len(users) * 3),
                "isCoreFixture": True,
            }
        )

    theme_offsets = {theme["themeId"]: idx for idx, theme in enumerate(theme_catalog["themes"])}
    for theme_idx, theme in enumerate(theme_catalog["themes"]):
        for role_idx in range(users_per_theme):
            role = ROLE_ORDER[role_idx % len(ROLE_ORDER)]
            user_id = f"fixture_user_{slug(theme['themeId'])}_{role_idx + 1:02d}"
            if any(user["userId"] == user_id for user in users):
                continue
            avatar_source_id = choose_source(theme, "portraitSourceIds", role_idx)
            background_source_id = choose_source(theme, "backgroundSourceIds", role_idx)
            avatar_format = "jpg" if role_idx % 3 else "png"
            background_format = "jpg" if role_idx % 4 else "png"
            avatar = derive_image(
                SHARED / source_index[avatar_source_id]["download"]["storedRelativePath"],
                f"media/avatar/user/{user_id}/v1/avatar.{avatar_format}",
                512,
                512,
                avatar_format,
            )
            background = derive_image(
                SHARED / source_index[background_source_id]["download"]["storedRelativePath"],
                f"media/background/user/{user_id}/v1/background.{background_format}",
                1600,
                900,
                background_format,
            )
            user_assets[user_id] = avatar
            background_assets[user_id] = background
            users.append(
                {
                    "userId": user_id,
                    "displayName": role_display(theme["displayName"], role),
                    "headline": f"{theme['displayName']} · {ROLE_BIOS[role]}",
                    "bio": f"{theme['displayName']} 主题用户样本，覆盖作者、联系人、圈主与群成员。",
                    "primaryTheme": theme["themeId"],
                    "secondaryThemes": list(theme.get("adjacentThemes") or [])[:2],
                    "primaryRole": role,
                    "roleTags": sorted(set(ROLE_TAGS[role] + [theme['themeId']])),
                    "subAccountRefs": [f"sub_account_{slug(theme['themeId'])}_{role_idx + 1:02d}"],
                    "themeTags": ordered_theme_tags(theme["themeId"], list(theme.get("adjacentThemes") or [])[:2]),
                    "postThemeRefs": [],
                    "circleThemeRefs": [],
                    "groupPersonaMix": [],
                    "profile": {"avatar": avatar, "background": background},
                    "crossDomainRefs": {"posts": [], "circles": [], "conversations": []},
                    "stats": user_stats_template(theme_offsets[theme["themeId"]], role_idx),
                    "sourceRefs": {"avatarSourceId": avatar_source_id, "backgroundSourceId": background_source_id},
                    "createdAt": iso_at(50 + theme_idx * 20 + role_idx),
                    "isCoreFixture": False,
                }
            )

    return users, user_assets, background_assets, source_updates


def users_by_theme(users: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for user in users:
        grouped.setdefault(user["primaryTheme"], []).append(user)
    return grouped


def build_circles(users: list[dict[str, Any]], user_assets: dict[str, dict[str, Any]], source_catalog: dict[str, Any], theme_catalog: dict[str, Any], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    source_index = {entry["sourceId"]: entry for entry in source_catalog["entries"]}
    grouped = users_by_theme(users)
    circles: list[dict[str, Any]] = []
    circle_assets: dict[str, dict[str, Any]] = {}
    circle_covers: dict[str, dict[str, Any]] = {}
    memberships: dict[str, list[str]] = {}

    targets = dict(rules["targets"])
    circles_per_theme = int(targets["circleCount"] / len(theme_catalog["themes"]))
    kinds = list(rules.get("circleTypes") or ["flagshipCircle", "nicheCircle", "hybridCircle", "eventCircle"])

    for theme in theme_catalog["themes"]:
        theme_users = grouped[theme["themeId"]]
        for index in range(circles_per_theme):
            circle_id = f"fixture_circle_{slug(theme['themeId'])}_{index + 1:02d}"
            conversation_id = f"fixture_conv_{slug(theme['themeId'])}_{index + 1:02d}"
            owner = theme_users[index % len(theme_users)]
            source_id = choose_source(theme, "circleSourceIds", index)
            cover_format = "jpg" if index % 2 == 0 else "png"
            avatar_format = "jpg" if index % 3 else "png"
            cover = derive_image(
                SHARED / source_index[source_id]["download"]["storedRelativePath"],
                f"media/image/circle/{circle_id}/v1/cover.{cover_format}",
                1440,
                900,
                cover_format,
            )
            avatar = derive_image(
                SHARED / source_index[source_id]["download"]["storedRelativePath"],
                f"media/avatar/circle/{circle_id}/v1/avatar.{avatar_format}",
                512,
                512,
                avatar_format,
            )
            circle_assets[circle_id] = avatar
            circle_covers[circle_id] = cover
            member_count = 6 + (index % 5)
            member_ids = [theme_users[(index + offset) % len(theme_users)]["userId"] for offset in range(member_count)]
            memberships[circle_id] = member_ids
            primary, secondary, domain = CIRCLE_CATEGORY[theme["themeId"]]
            circles.append(
                {
                    "circleId": circle_id,
                    "displayName": f"{theme['displayName']}{(theme.get('circleNames') or ['主题圈'])[index % len(theme.get('circleNames') or ['主题圈'])]}",
                    "summary": f"围绕 {theme['displayName']} 生成的共享池主题圈，用于验证圈子头像、封面和成员关系。",
                    "avatar": avatar,
                    "cover": cover,
                    "ownerUserId": owner["userId"],
                    "primaryTheme": theme["themeId"],
                    "secondaryThemes": list(theme.get("adjacentThemes") or [])[:1],
                    "themeTags": ordered_theme_tags(theme["themeId"], list(theme.get("adjacentThemes") or [])[:1]),
                    "circleType": kinds[index % len(kinds)],
                    "groupConversationId": conversation_id,
                    "memberUserIds": member_ids,
                    "contentDomain": domain,
                    "primaryCategory": primary,
                    "secondaryCategory": secondary,
                    "stats": {"memberCount": len(member_ids), "postCount": 8 + index * 2, "dailyActiveMemberCount": 3 + index % 4},
                    "createdAt": iso_at(200 + len(circles) * 2),
                    "isCoreFixture": False,
                }
            )

    for theme_id, preset in CORE_CIRCLE_PRESETS.items():
        theme = next(item for item in theme_catalog["themes"] if item["themeId"] == theme_id)
        source_id = choose_source(theme, "circleSourceIds", 0)
        cover = derive_image(
            SHARED / source_index[source_id]["download"]["storedRelativePath"],
            f"media/image/circle/{preset['circleId']}/v1/cover.{preset['format']}",
            1440,
            900,
            preset['format'],
        )
        avatar = derive_image(
            SHARED / source_index[source_id]["download"]["storedRelativePath"],
            f"media/avatar/circle/{preset['circleId']}/v1/avatar.{preset['format']}",
            512,
            512,
            preset['format'],
        )
        circle_assets[preset["circleId"]] = avatar
        circle_covers[preset["circleId"]] = cover
        member_ids = [user["userId"] for user in grouped[theme_id][:6]]
        memberships[preset["circleId"]] = member_ids
        primary, secondary, domain = CIRCLE_CATEGORY[theme_id]
        circles.insert(
            0,
            {
                "circleId": preset["circleId"],
                "displayName": preset["name"],
                "summary": f"{theme['displayName']} 核心夹具圈子。",
                "avatar": avatar,
                "cover": cover,
                "ownerUserId": preset["ownerId"],
                "primaryTheme": theme_id,
                "secondaryThemes": list(theme.get("adjacentThemes") or [])[:1],
                "themeTags": ordered_theme_tags(theme_id, list(theme.get("adjacentThemes") or [])[:1]),
                "circleType": "flagshipCircle",
                "groupConversationId": preset["conversationId"],
                "memberUserIds": member_ids,
                "contentDomain": domain,
                "primaryCategory": primary,
                "secondaryCategory": secondary,
                "stats": {"memberCount": len(member_ids), "postCount": 18, "dailyActiveMemberCount": 8},
                "createdAt": iso_at(160),
                "isCoreFixture": True,
            },
        )

    return circles, circle_assets, circle_covers, memberships


def build_posts(users: list[dict[str, Any]], circles: list[dict[str, Any]], source_catalog: dict[str, Any], theme_catalog: dict[str, Any], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    source_index = {entry["sourceId"]: entry for entry in source_catalog["entries"]}
    grouped_users = users_by_theme(users)
    circles_by_theme: dict[str, list[dict[str, Any]]] = {}
    for circle in circles:
        circles_by_theme.setdefault(circle["primaryTheme"], []).append(circle)
    posts: list[dict[str, Any]] = []
    post_assets: dict[str, list[dict[str, Any]]] = {}
    post_mix = list((rules.get("postTypeMix") or {}).keys()) or ["heroPost", "galleryPost", "momentPost", "articlePost", "videoCoverPost"]
    targets = dict(rules["targets"])
    posts_per_theme = int(targets["postsPerTheme"])
    cross_posts = int(targets.get("crossThemePostCount", 0))

    for theme_idx, theme in enumerate(theme_catalog["themes"]):
        theme_users = grouped_users[theme["themeId"]]
        theme_circles = circles_by_theme[theme["themeId"]]
        title_seeds = list(theme.get("titleSeeds") or [theme["displayName"]])
        moment_seeds = list(theme.get("momentSeeds") or [theme["displayName"]])
        for index in range(posts_per_theme):
            post_type = post_mix[index % len(post_mix)]
            author = theme_users[index % len(theme_users)]
            circle = theme_circles[index % len(theme_circles)]
            source_id = choose_source(theme, "postSourceIds", index)
            format_ext = "jpg" if post_type != "momentPost" else "png"
            cover_variant = media_spec(f"fixture_post_{slug(theme['themeId'])}_{index + 1:03d}", "cover", source_id, 1280, 960 if post_type == "galleryPost" else 720, format_ext)
            cover = derive_image(
                SHARED / source_index[source_id]["download"]["storedRelativePath"],
                cover_variant["objectKey"],
                cover_variant["width"],
                cover_variant["height"],
                cover_variant["format"],
            )
            supporting_specs: list[dict[str, Any]] = []
            supporting_assets: list[dict[str, Any]] = [cover]
            extra_count = 3 if post_type == "galleryPost" else (1 if post_type in {"articlePost", "videoCoverPost"} else 0)
            for extra_idx in range(extra_count):
                extra_source = choose_source(theme, "postSourceIds", index + extra_idx + 1)
                spec = media_spec(f"fixture_post_{slug(theme['themeId'])}_{index + 1:03d}", f"detail_{extra_idx + 1}", extra_source, 1280, 720, "jpg")
                asset = derive_image(
                    SHARED / source_index[extra_source]["download"]["storedRelativePath"],
                    spec["objectKey"],
                    spec["width"],
                    spec["height"],
                    spec["format"],
                )
                supporting_specs.append(spec)
                supporting_assets.append(asset)
            post_id = f"fixture_post_{slug(theme['themeId'])}_{index + 1:03d}"
            post_assets[post_id] = supporting_assets
            posts.append(
                {
                    "postId": post_id,
                    "postType": post_type,
                    "authorUserId": author["userId"],
                    "authorProfile": {
                        "displayName": author["displayName"],
                        "avatar": author["profile"]["avatar"],
                        "background": author["profile"]["background"],
                    },
                    "primaryTheme": theme["themeId"],
                    "secondaryThemes": list(theme.get("adjacentThemes") or [])[:1],
                    "themeTags": ordered_theme_tags(theme["themeId"], list(theme.get("adjacentThemes") or [])[:1]),
                    "circleRef": circle["circleId"],
                    "headline": f"{title_seeds[index % len(title_seeds)]} #{index + 1}",
                    "summary": f"{moment_seeds[index % len(moment_seeds)]}，用于 {post_type} 视觉与作者头像同源验证。",
                    "body": f"共享池真实图片样本，主题={theme['displayName']}，作者={author['displayName']}，圈子={circle['displayName']}。",
                    "coverAsset": cover,
                    "supportingAssets": supporting_assets[1:],
                    "publishedAt": iso_at(320 + len(posts)),
                    "stats": {"likeCount": 48 + index * 3, "commentCount": 4 + index % 6, "shareCount": 2 + index % 4},
                    "isCoreFixture": index < 3,
                    "videoObjectKey": BETA_VIDEO_OBJECT_KEY if post_type == "videoCoverPost" else None,
                }
            )

    for pair_index, (left_theme, right_theme) in enumerate(CROSS_THEME_PAIRS):
        left = next(item for item in theme_catalog["themes"] if item["themeId"] == left_theme)
        right = next(item for item in theme_catalog["themes"] if item["themeId"] == right_theme)
        left_users = grouped_users[left_theme]
        right_users = grouped_users[right_theme]
        left_circles = circles_by_theme[left_theme]
        right_circles = circles_by_theme[right_theme]
        pair_total = max(1, cross_posts // len(CROSS_THEME_PAIRS))
        for index in range(pair_total):
            author = left_users[index % len(left_users)] if index % 2 == 0 else right_users[index % len(right_users)]
            circle = left_circles[index % len(left_circles)] if index % 2 == 0 else right_circles[index % len(right_circles)]
            source_id = choose_source(left if index % 2 == 0 else right, "postSourceIds", index)
            post_id = f"fixture_post_cross_{slug(left_theme)}_{slug(right_theme)}_{index + 1:03d}"
            cover = derive_image(
                SHARED / source_index[source_id]["download"]["storedRelativePath"],
                f"media/image/post/{post_id}/v1/cover.jpg",
                1280,
                720,
                "jpg",
            )
            posts.append(
                {
                    "postId": post_id,
                    "postType": "heroPost",
                    "authorUserId": author["userId"],
                    "authorProfile": {"displayName": author["displayName"], "avatar": author["profile"]["avatar"], "background": author["profile"]["background"]},
                    "primaryTheme": left_theme,
                    "secondaryThemes": [right_theme],
                    "themeTags": ordered_theme_tags(left_theme, [right_theme]),
                    "circleRef": circle["circleId"],
                    "headline": f"{left['displayName']} x {right['displayName']} 联动 #{index + 1}",
                    "summary": f"跨主题联动内容，覆盖 {left['displayName']} 与 {right['displayName']} 组合场景。",
                    "body": "跨主题联动样本，用于验证相邻主题在 feed 与聊天分享中的视觉差异。",
                    "coverAsset": cover,
                    "supportingAssets": [],
                    "publishedAt": iso_at(600 + pair_index * 10 + index),
                    "stats": {"likeCount": 120 + index * 2, "commentCount": 8 + index % 5, "shareCount": 6 + index % 3},
                    "isCoreFixture": False,
                    "videoObjectKey": None,
                }
            )
            post_assets[post_id] = [cover]

    return posts, post_assets


def build_conversations(users: list[dict[str, Any]], circles: list[dict[str, Any]], user_assets: dict[str, dict[str, Any]], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    grouped = users_by_theme(users)
    conversations: list[dict[str, Any]] = []
    conversation_members: dict[str, list[str]] = {}
    direct_target = int(rules["targets"].get("directConversationCount", 0))
    group_target = int(rules["targets"].get("groupConversationCount", 0))

    core_directs = [
        ("fixture_conv_direct_current_friend", ["fixture_user_current", "fixture_user_friend"], "契约好友"),
        ("fixture_conv_direct_current_photo", ["fixture_user_current", "fixture_user_photo"], "契约摄影师"),
        ("fixture_conv_direct_current_article", ["fixture_user_current", "fixture_user_article"], "契约撰稿人"),
    ]
    for conv_id, members, name in core_directs:
        conversations.append(
            {
                "conversationId": conv_id,
                "conversationType": "directConversation",
                "displayName": name,
                "avatar": user_assets[members[1]],
                "memberUserIds": members,
                "groupAvatarVersion": 0,
                "groupAvatarSourceUserIds": [],
                "primaryTheme": "",
                "secondaryThemes": [],
                "themeTags": [],
                "groupPersonaMix": [],
                "summary": "核心私聊夹具。",
                "messages": [],
                "isCoreFixture": True,
                "circleRef": None,
            }
        )
        conversation_members[conv_id] = members

    for theme_id, users_in_theme in grouped.items():
        for index in range(max(1, direct_target // max(1, len(grouped)))):
            left = "fixture_user_current"
            right = users_in_theme[index % len(users_in_theme)]["userId"]
            if right == left:
                right = users_in_theme[(index + 1) % len(users_in_theme)]["userId"]
            conv_id = f"fixture_conv_direct_{slug(theme_id)}_{index + 1:02d}"
            conversation_members[conv_id] = [left, right]
            conversations.append(
                {
                    "conversationId": conv_id,
                    "conversationType": "directConversation",
                    "displayName": next(user["displayName"] for user in users if user["userId"] == right),
                    "avatar": user_assets[right],
                    "memberUserIds": [left, right],
                    "groupAvatarVersion": 0,
                    "groupAvatarSourceUserIds": [],
                    "primaryTheme": "",
                    "secondaryThemes": [],
                    "themeTags": [],
                    "groupPersonaMix": [],
                    "summary": f"{theme_id} 主题私聊，用于联系人与消息列表头像验证。",
                    "messages": [],
                    "isCoreFixture": False,
                    "circleRef": None,
                }
            )

    group_circles = circles[:group_target]
    for circle in group_circles:
        members = circle["memberUserIds"][: min(9, len(circle["memberUserIds"]))]
        conv_id = circle["groupConversationId"]
        composite = render_group_composite(
            f"media/avatar/group/{conv_id}/v1/composite.png",
            [MEDIA_ROOT / user_assets[user_id]["objectKey"] for user_id in members],
        )
        conversation_members[conv_id] = members
        conversations.append(
            {
                "conversationId": conv_id,
                "conversationType": "circlePublicGroupConversation" if circle["isCoreFixture"] else "interestGroupConversation",
                "displayName": f"{circle['displayName']} 讨论组",
                "avatar": composite,
                "memberUserIds": members,
                "groupAvatarVersion": 1,
                "groupAvatarSourceUserIds": members,
                "primaryTheme": circle["primaryTheme"],
                "secondaryThemes": list(circle.get("secondaryThemes") or []),
                "themeTags": list(circle.get("themeTags") or []),
                "groupPersonaMix": [],
                "summary": f"圈子 {circle['displayName']} 关联群聊。",
                "messages": [],
                "isCoreFixture": bool(circle["isCoreFixture"]),
                "circleRef": circle["circleId"],
            }
        )

    return conversations, conversation_members


def attach_messages(conversations: list[dict[str, Any]], conversation_members: dict[str, list[str]], posts: list[dict[str, Any]], users: list[dict[str, Any]]) -> None:
    user_index = {user["userId"]: user for user in users}
    post_index = {post["postId"]: post for post in posts}
    ordered_posts = list(post_index.keys())
    for conv_index, conversation in enumerate(conversations):
        members = conversation_members[conversation["conversationId"]]
        messages: list[dict[str, Any]] = []
        for message_index in range(6 if conversation["conversationType"] == "directConversation" else 8):
            sender_id = members[message_index % len(members)]
            sender = user_index[sender_id]
            post_ref = ordered_posts[(conv_index * 3 + message_index) % len(ordered_posts)] if message_index in {2, 5} else None
            messages.append(
                {
                    "messageId": f"{conversation['conversationId']}_msg_{message_index + 1:02d}",
                    "senderUserId": sender_id,
                    "senderDisplayName": sender["displayName"],
                    "senderAvatar": sender["profile"]["avatar"],
                    "text": f"{sender['displayName']} 在 {conversation['displayName']} 中发送的共享池消息 #{message_index + 1}。",
                    "sharedPostId": post_ref,
                    "sharedPostHeadline": post_index[post_ref]["headline"] if post_ref else None,
                    "sentAt": iso_at(760 + conv_index * 2 + message_index),
                }
            )
        conversation["messages"] = messages


def attach_cross_refs(users: list[dict[str, Any]], circles: list[dict[str, Any]], conversations: list[dict[str, Any]], posts: list[dict[str, Any]]) -> None:
    user_index = {user["userId"]: user for user in users}
    circles_by_id = {circle["circleId"]: circle for circle in circles}
    group_member_samples: dict[str, list[str]] = {user["userId"]: [] for user in users}
    for post in posts:
        author = user_index[post["authorUserId"]]
        author["crossDomainRefs"]["posts"].append(post["postId"])
        author["postThemeRefs"] = stable_unique([*author["postThemeRefs"], post["primaryTheme"], *post.get("secondaryThemes", [])])
    for circle in circles:
        owner = user_index[circle["ownerUserId"]]
        owner["crossDomainRefs"]["circles"].append(circle["circleId"])
        owner["circleThemeRefs"] = stable_unique([*owner["circleThemeRefs"], circle["primaryTheme"], *circle.get("secondaryThemes", [])])
        for member_id in circle["memberUserIds"]:
            member = user_index[member_id]
            member["stats"]["circleCount"] = member["stats"].get("circleCount", 0) + 1
            member["circleThemeRefs"] = stable_unique([*member["circleThemeRefs"], circle["primaryTheme"], *circle.get("secondaryThemes", [])])
    for conversation in conversations:
        if conversation.get("circleRef") and conversation["circleRef"] in circles_by_id:
            circle = circles_by_id[conversation["circleRef"]]
            conversation["primaryTheme"] = circle["primaryTheme"]
            conversation["secondaryThemes"] = list(circle.get("secondaryThemes") or [])
        else:
            conversation_themes: list[str] = []
            for member_id in conversation["memberUserIds"]:
                conversation_themes.extend(user_index[member_id]["themeTags"])
            ordered_themes = stable_unique(conversation_themes)
            conversation["primaryTheme"] = ordered_themes[0] if ordered_themes else "lifestyle"
            conversation["secondaryThemes"] = ordered_themes[1:3]
        conversation["themeTags"] = ordered_theme_tags(conversation["primaryTheme"], list(conversation.get("secondaryThemes") or []))
        conversation["groupPersonaMix"] = role_mix(user_index, conversation["memberUserIds"]) if conversation["conversationType"] != "directConversation" else []
        for member_id in conversation["memberUserIds"]:
            user_index[member_id]["crossDomainRefs"]["conversations"].append(conversation["conversationId"])
            if conversation["conversationType"] != "directConversation":
                group_member_samples[member_id].extend(conversation["memberUserIds"])
    for user in users:
        user["stats"]["postCount"] = len(user["crossDomainRefs"]["posts"])
        user["postThemeRefs"] = stable_unique(user["postThemeRefs"])
        user["circleThemeRefs"] = stable_unique(user["circleThemeRefs"])
        user["groupPersonaMix"] = role_mix(user_index, group_member_samples.get(user["userId"], []))


def user_index(users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {user["userId"]: user for user in users}


def circle_index(circles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {circle["circleId"]: circle for circle in circles}


def ensure_core_posts(posts: list[dict[str, Any]], post_assets: dict[str, list[dict[str, Any]]], users: list[dict[str, Any]], circles: list[dict[str, Any]], source_catalog: dict[str, Any], theme_catalog: dict[str, Any]) -> None:
    users_by_id = user_index(users)
    circles_by_id = circle_index(circles)
    themes = {theme["themeId"]: theme for theme in theme_catalog["themes"]}
    sources = {entry["sourceId"]: entry for entry in source_catalog["entries"]}
    specs = [
        {"postId": "fixture_photo_001", "themeId": "photography", "authorUserId": "fixture_user_photo", "circleId": "fixture_circle_photo", "postType": "galleryPost", "headline": "西湖晨光摄影测试详情", "summary": "西湖晨光摄影测试详情", "body": "西湖晨光下的契约照片。", "sourceIndex": 0, "extraCount": 1, "locationName": "杭州西湖"},
        {"postId": "fixture_photo_002", "themeId": "photography", "authorUserId": "fixture_user_photo", "circleId": "fixture_circle_photo", "postType": "heroPost", "headline": "城市傍晚的光影层次", "summary": "城市傍晚的光影层次", "body": "城市傍晚的光影层次。", "sourceIndex": 1, "extraCount": 0, "locationName": "杭州拱墅"},
        {"postId": "fixture_photo_003", "themeId": "travel", "authorUserId": "fixture_user_travel", "circleId": "fixture_circle_travel", "postType": "heroPost", "headline": "山路湖面与露营灯", "summary": "山路、湖面与露营灯。", "body": "山路、湖面与露营灯。", "sourceIndex": 0, "extraCount": 0, "locationName": "千岛湖"},
        {"postId": "fixture_video_001", "themeId": "travel", "authorUserId": "fixture_user_travel", "circleId": "fixture_circle_travel", "postType": "videoCoverPost", "headline": "杭州一日游契约视频", "summary": "杭州一日游契约视频。", "body": "杭州一日游契约视频。", "sourceIndex": 1, "extraCount": 1, "locationName": "杭州"},
        {"postId": "fixture_video_002", "themeId": "cityWalk", "authorUserId": "fixture_user_video", "circleId": "fixture_circle_city", "postType": "videoCoverPost", "headline": "城市街头慢镜头", "summary": "城市街头慢镜头。", "body": "城市街头慢镜头。", "sourceIndex": 0, "extraCount": 1, "locationName": "上海"},
        {"postId": "fixture_article_001", "themeId": "designWriting", "authorUserId": "fixture_user_article", "circleId": "fixture_circle_tech", "postType": "articlePost", "headline": "契约驱动的发现页文章", "summary": "契约驱动的发现页文章。", "body": "文章、攻略与长图文作者。", "sourceIndex": 0, "extraCount": 1, "locationName": "线上专栏"},
        {"postId": "fixture_article_002", "themeId": "designWriting", "authorUserId": "fixture_user_article", "circleId": "fixture_circle_tech", "postType": "articlePost", "headline": "从图片共享池到页面观感验证", "summary": "从图片共享池到页面观感验证。", "body": "用于验证文章封面、作者头像和详情配图。", "sourceIndex": 1, "extraCount": 1, "locationName": "线上专栏"},
        {"postId": "fixture_moment_001", "themeId": "lifestyle", "authorUserId": "fixture_user_current", "circleId": "fixture_circle_life", "postType": "momentPost", "headline": "契约周末早餐", "summary": "契约周末早餐。", "body": "咖啡、手账与周末早餐。", "sourceIndex": 0, "extraCount": 0, "locationName": "家附近"},
        {"postId": "fixture_moment_002", "themeId": "food", "authorUserId": "fixture_user_friend", "circleId": "fixture_circle_food", "postType": "momentPost", "headline": "午后咖啡和小店", "summary": "午后咖啡和小店。", "body": "记录城市里的咖啡馆和小店。", "sourceIndex": 0, "extraCount": 0, "locationName": "杭州上城"},
        {"postId": "fixture_moment_003", "themeId": "cityWalk", "authorUserId": "fixture_user_weekend_1", "circleId": "fixture_circle_city", "postType": "momentPost", "headline": "看展后的晚风", "summary": "看展后的晚风。", "body": "城市影像、扫街和周末看展。", "sourceIndex": 1, "extraCount": 0, "locationName": "上海西岸"},
    ]
    existing = {post["postId"]: idx for idx, post in enumerate(posts)}
    for idx, spec in enumerate(specs):
        theme = themes[spec["themeId"]]
        author = users_by_id[spec["authorUserId"]]
        circle = circles_by_id[spec["circleId"]]
        source_id = choose_source(theme, "postSourceIds", spec["sourceIndex"])
        cover_height = 960 if spec["postType"] == "galleryPost" else 720
        cover = derive_image(
            SHARED / sources[source_id]["download"]["storedRelativePath"],
            f"media/image/post/{spec['postId']}/v1/cover.png",
            1280,
            cover_height,
            "png",
        )
        assets = [cover]
        for extra_idx in range(spec["extraCount"]):
            extra_source_id = choose_source(theme, "postSourceIds", spec["sourceIndex"] + extra_idx + 1)
            detail = derive_image(
                SHARED / sources[extra_source_id]["download"]["storedRelativePath"],
                f"media/image/post/{spec['postId']}/v1/image-{extra_idx + 2}.png",
                1280,
                720,
                "png",
            )
            assets.append(detail)
        row = {
            "postId": spec["postId"],
            "postType": spec["postType"],
            "authorUserId": author["userId"],
            "authorProfile": {"displayName": author["displayName"], "avatar": author["profile"]["avatar"], "background": author["profile"]["background"]},
            "primaryTheme": spec["themeId"],
            "secondaryThemes": list(theme.get("adjacentThemes") or [])[:1],
            "themeTags": ordered_theme_tags(spec["themeId"], list(theme.get("adjacentThemes") or [])[:1]),
            "circleRef": circle["circleId"],
            "headline": spec["headline"],
            "summary": spec["summary"],
            "body": spec["body"],
            "coverAsset": cover,
            "supportingAssets": assets[1:],
            "publishedAt": iso_at(40 + idx),
            "stats": {"likeCount": 80 + idx * 17, "commentCount": 6 + idx, "shareCount": 3 + idx % 4},
            "isCoreFixture": True,
            "videoObjectKey": BETA_VIDEO_OBJECT_KEY if spec["postType"] == "videoCoverPost" else None,
            "locationName": spec["locationName"],
        }
        if spec["postType"] == "articlePost":
            row.update(
                build_article_payload(
                    title=spec["headline"],
                    summary=spec["summary"],
                    body=spec["body"],
                    cover=cover,
                )
            )
        post_assets[spec["postId"]] = assets
        if spec["postId"] in existing:
            posts[existing[spec["postId"]]] = row
        else:
            posts.insert(idx, row)


def ensure_core_conversations(conversations: list[dict[str, Any]], conversation_members: dict[str, list[str]], user_assets: dict[str, dict[str, Any]], users: list[dict[str, Any]]) -> None:
    existing = {item["conversationId"]: idx for idx, item in enumerate(conversations)}
    specs = [
        {"conversationId": "fixture_conv_direct", "type": "directConversation", "title": "契约好友", "members": ["fixture_user_current", "fixture_user_friend"], "creatorId": "fixture_user_current", "circleRef": None, "preview": "契约消息已送达"},
        {"conversationId": "fixture_conv_group", "type": "interestGroupConversation", "title": "契约周末群", "members": ["fixture_user_current", "fixture_user_weekend_1", "fixture_user_weekend_2"], "creatorId": "fixture_user_current", "circleRef": None, "preview": "周末集合时间已确认"},
        {"conversationId": "fixture_conv_photo_group", "type": "interestGroupConversation", "title": "契约摄影交流群", "members": ["fixture_user_current", "fixture_user_photo", "fixture_user_friend"], "creatorId": "fixture_user_photo", "circleRef": "fixture_circle_photo", "preview": "今晚整理照片墙和路线。"},
        {"conversationId": "fixture_conv_travel_group", "type": "interestGroupConversation", "title": "契约旅行搭子群", "members": ["fixture_user_current", "fixture_user_travel", "fixture_user_weekend_1", "fixture_user_weekend_2"], "creatorId": "fixture_user_travel", "circleRef": "fixture_circle_travel", "preview": "路线、天气和集合点都同步了。"},
        {"conversationId": "fixture_conv_article_direct", "type": "directConversation", "title": "契约撰稿人", "members": ["fixture_user_current", "fixture_user_article"], "creatorId": "fixture_user_current", "circleRef": None, "preview": "文章配图已经补齐。"},
    ]
    for idx, spec in enumerate(specs):
        avatar = user_assets[spec["members"][1]]
        group_avatar = None
        if spec["type"] != "directConversation":
            group_avatar = render_group_composite(
                f"media/avatar/group/{spec['conversationId']}/v1/composite.png",
                [MEDIA_ROOT / user_assets[user_id]["objectKey"] for user_id in spec["members"]],
            )
            avatar = group_avatar
        row = {
            "conversationId": spec["conversationId"],
            "conversationType": spec["type"],
            "displayName": spec["title"],
            "avatar": avatar,
            "memberUserIds": spec["members"],
            "groupAvatarVersion": 1 if group_avatar else 0,
            "groupAvatarSourceUserIds": spec["members"] if group_avatar else [],
            "primaryTheme": "",
            "secondaryThemes": [],
            "themeTags": [],
            "groupPersonaMix": [],
            "summary": spec["preview"],
            "messages": [],
            "isCoreFixture": True,
            "circleRef": spec["circleRef"],
            "creatorId": spec["creatorId"],
        }
        conversation_members[spec["conversationId"]] = spec["members"]
        if spec["conversationId"] in existing:
            conversations[existing[spec["conversationId"]]] = row
        else:
            conversations.insert(idx, row)


def build_user_pool_doc(
    users: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    circles: list[dict[str, Any]],
    conversations: list[dict[str, Any]],
    source_catalog: dict[str, Any],
    theme_catalog: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    post_media = {post["postId"]: {"cover": post["coverAsset"], "images": [post["coverAsset"], *post["supportingAssets"]]} for post in posts}
    circle_media = {circle["circleId"]: {"avatar": circle["avatar"], "cover": circle["cover"]} for circle in circles}
    group_media = {
        conversation["conversationId"]: {"composite": conversation["avatar"]}
        for conversation in conversations
        if conversation["conversationType"] != "directConversation"
    }
    return {
        "schemaVersion": "shared.avatar-user-pool",
        "description": "alpha/beta/gamma 共享身份、真实图片来源与媒体派生真相源。运行时只消费 media objectKey 派生后的 URL。",
        "mediaContract": {
            "urlDerivation": "runtime joins MEDIA_*_CDN_BASE_URL or gateway base with objectKey",
            "allowedMimeTypes": ["image/jpeg", "image/png", "image/webp"],
            "groupAvatarRenderer": "RenderGroupAvatarPNG",
            "groupAvatarMimeType": "image/png",
        },
        "statistics": {
            "userCount": len(users),
            "postCount": len(posts),
            "circleCount": len(circles),
            "conversationCount": len(conversations),
            "mediaAssetCount": sum(len(bundle["images"]) for bundle in post_media.values()) + len(users) * 2 + len(circle_media) * 2 + len(group_media),
            "sourceCount": len(source_catalog.get("entries") or []),
        },
        "sourceCatalogDigest": sha256_bytes(json.dumps(source_catalog, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        "taxonomy": {
            "themes": [
                {
                    "themeId": theme["themeId"],
                    "displayName": theme["displayName"],
                    "accent": theme["accent"],
                    "adjacentThemes": list(theme.get("adjacentThemes") or []),
                }
                for theme in theme_catalog.get("themes", [])
            ],
            "roles": list(rules.get("roles") or ROLE_ORDER),
            "roleHierarchy": list(rules.get("roleHierarchy") or rules.get("roles") or ROLE_ORDER),
            "roleDisplayNames": dict(rules.get("roleDisplayNames") or {}),
            "crossThemePairs": list(rules.get("crossThemePairs") or []),
            "associationRules": dict(rules.get("associationRules") or {}),
        },
        "users": [
            {
                "userId": user["userId"],
                "displayName": user["displayName"],
                "avatarObjectKey": user["profile"]["avatar"]["objectKey"],
                "backgroundObjectKey": user["profile"]["background"]["objectKey"],
                "avatarMedia": user["profile"]["avatar"],
                "backgroundMedia": user["profile"]["background"],
                "bio": user["bio"],
                "subAccountRefs": user["subAccountRefs"],
                "tags": user["roleTags"],
                "primaryTheme": user["primaryTheme"],
                "secondaryThemes": user["secondaryThemes"],
                "themeTags": user["themeTags"],
                "primaryRole": user["primaryRole"],
                "postThemeRefs": user["postThemeRefs"],
                "circleThemeRefs": user["circleThemeRefs"],
                "groupPersonaMix": user["groupPersonaMix"],
                "crossDomainRefs": user["crossDomainRefs"],
                "sourceRefs": user["sourceRefs"],
                "stats": user["stats"],
            }
            for user in users
        ],
        "posts": [
            {
                "postId": post["postId"],
                "postType": post["postType"],
                "authorUserId": post["authorUserId"],
                "circleRef": post["circleRef"],
                "primaryTheme": post["primaryTheme"],
                "secondaryThemes": post["secondaryThemes"],
                "themeTags": post["themeTags"],
            }
            for post in posts
        ],
        "circles": [
            {
                "circleId": circle["circleId"],
                "ownerUserId": circle["ownerUserId"],
                "groupConversationId": circle["groupConversationId"],
                "circleType": circle["circleType"],
                "primaryTheme": circle["primaryTheme"],
                "secondaryThemes": circle["secondaryThemes"],
                "themeTags": circle["themeTags"],
                "memberUserIds": circle["memberUserIds"],
            }
            for circle in circles
        ],
        "conversations": [
            {
                "conversationId": conversation["conversationId"],
                "conversationType": conversation["conversationType"],
                "circleRef": conversation["circleRef"],
                "memberUserIds": conversation["memberUserIds"],
                "primaryTheme": conversation["primaryTheme"],
                "secondaryThemes": conversation["secondaryThemes"],
                "themeTags": conversation["themeTags"],
                "groupPersonaMix": conversation["groupPersonaMix"],
                "groupAvatarSourceUserIds": conversation["groupAvatarSourceUserIds"],
            }
            for conversation in conversations
        ],
        "postMedia": post_media,
        "circleMedia": circle_media,
        "groupAvatarMedia": group_media,
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


def content_kind(post_type: str) -> tuple[str, str]:
    if post_type == "videoCoverPost":
        return "video", "work"
    if post_type == "articlePost":
        return "article", "work"
    if post_type == "momentPost":
        return "moment", "moment"
    return "image", "work"


def content_row(post: dict[str, Any], circles_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    content_type, identity = content_kind(post["postType"])
    assets = [post["coverAsset"], *post["supportingAssets"]]
    circle = circles_by_id[post["circleRef"]]
    row = {
        "postId": post["postId"],
        "id": post["postId"],
        "contentType": content_type,
        "type": content_type,
        "contentIdentity": identity,
        "identity": identity,
        "authorId": post["authorUserId"],
        "subAccountId": post["authorUserId"],
        "displayName": post["authorProfile"]["displayName"],
        "authorAvatarUrl": post["authorProfile"]["avatar"]["objectKey"],
        "avatarUrl": post["authorProfile"]["avatar"]["objectKey"],
        "authorBackgroundUrl": post["authorProfile"]["background"]["objectKey"],
        "postType": post["postType"],
        "primaryTheme": post["primaryTheme"],
        "secondaryThemes": post["secondaryThemes"],
        "themeTags": post["themeTags"],
        "title": post["headline"],
        "summary": post["summary"],
        "body": post["body"],
        "coverUrl": post["coverAsset"]["objectKey"],
        "thumbnailUrl": post["coverAsset"]["objectKey"],
        "mediaUrls": [asset["objectKey"] for asset in assets],
        "imageUrls": [asset["objectKey"] for asset in assets if asset["mimeType"].startswith("image/")],
        "circleIds": [circle["circleId"]],
        "circleNames": [circle["displayName"]],
        "circleId": circle["circleId"],
        "circleName": circle["displayName"],
        "width": post["coverAsset"]["width"],
        "height": post["coverAsset"]["height"],
        "likeCount": post["stats"]["likeCount"],
        "commentCount": post["stats"]["commentCount"],
        "favoriteCount": max(0, post["stats"]["likeCount"] // 3),
        "shareCount": post["stats"]["shareCount"],
        "createdAt": post["publishedAt"],
        "authorDisplayNameSnapshot": post["authorProfile"]["displayName"],
        "authorAvatarObjectKey": post["authorProfile"]["avatar"]["objectKey"],
        "avatarObjectKey": post["authorProfile"]["avatar"]["objectKey"],
        "authorBackgroundObjectKey": post["authorProfile"]["background"]["objectKey"],
        "coverObjectKey": post["coverAsset"]["objectKey"],
        "thumbnailObjectKey": post["coverAsset"]["objectKey"],
        "mediaObjectKeys": [asset["objectKey"] for asset in assets],
        "imageObjectKeys": [asset["objectKey"] for asset in assets if asset["mimeType"].startswith("image/")],
        "tags": ["fixture", post["primaryTheme"], post["postType"]],
        "locationName": post.get("locationName", ""),
    }
    if content_type == "video":
        row["videoUrl"] = post["videoObjectKey"]
        row["durationMs"] = 45000
    if content_type == "article":
        row.update(
            build_article_payload(
                title=str(post.get("headline") or post.get("title") or post["body"]),
                summary=str(post.get("summary") or post["body"]),
                body=str(post.get("body") or post.get("summary") or ""),
                cover=post["coverAsset"],
            )
        )
    return row


def build_content_doc(posts: list[dict[str, Any]], circles: list[dict[str, Any]]) -> dict[str, Any]:
    circles_by_id = circle_index(circles)
    post_rows = [content_row(post, circles_by_id) for post in posts]
    post_ids = [row["id"] for row in post_rows]
    current_posts = [row["id"] for row in post_rows if row["authorId"] == "fixture_user_current"]
    comments = []
    reactions = []
    comment_authors = ["fixture_user_commenter", "fixture_user_friend", "fixture_user_current"]
    for idx, row in enumerate(post_rows[:48]):
        comment_id = "fixture_comment_photo_001" if row["id"] == "fixture_photo_001" else f"fixture_comment_{row['id']}"
        author_id = comment_authors[idx % len(comment_authors)]
        comments.append({
            "commentId": comment_id,
            "_id": comment_id,
            "postId": row["id"],
            "authorId": author_id,
            "authorDisplayNameSnapshot": "契约评论者" if author_id == "fixture_user_commenter" else row["displayName"],
            "authorAvatarObjectKeySnapshot": f"media/avatar/user/{author_id}/v1/avatar.png",
            "authorAvatarUrlSnapshot": f"media/avatar/user/{author_id}/v1/avatar.png",
            "content": f"共享池评论样本 #{idx + 1}",
            "createdAt": iso_at(900 + idx),
        })
    for idx, row in enumerate(post_rows[:72]):
        reactions.append({"postId": row["id"], "userId": "fixture_user_current" if idx % 2 == 0 else "fixture_user_friend", "liked": True, "favorited": idx % 3 == 0})
    return {
        "schemaVersion": "content.scenario-fixtures",
        "description": "内容域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.posts 初始化 MockContentRepository，beta/gamma 云侧服务 reset+seed 后由端侧 remote 访问。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "content_discovery_core": {"description": "发现流、详情与搜索共享真实图片主样本。", "posts": post_rows, "reactions": reactions, "comments": comments},
            "home_feed_core": {"description": "首页关注、精选与群组三个入口的组合内容种子。", "followingFeedPostIds": current_posts[:24] or post_ids[:24], "featuredFeedPostIds": post_ids[:40], "groupFeedPostIds": [row["id"] for row in post_rows if row["circleId"] == "fixture_circle_photo"][:12]},
            "content_detail_core": {"description": "内容详情、评论、reaction 与分享主样本。", "postIds": ["fixture_photo_001", "fixture_article_001", "fixture_video_001"], "commentIds": ["fixture_comment_photo_001"], "reactionPostIds": ["fixture_photo_001"], "shareTargets": [{"id": "fixture_share_chat_group", "type": "chat_conversation", "title": "契约周末群"}]},
            "search_core": {"description": "全局搜索与网络结果页可打开的内容种子。", "history": ["西湖晨光", "契约旅行", "城市漫步"], "resultPostIds": ["fixture_photo_001", "fixture_article_001", "fixture_video_001", "fixture_moment_001"], "networkResults": [{"id": "fixture_search_web_001", "title": "契约搜索网络结果", "url": "https://example.com"}]},
            "publish_core": {"description": "创作入口发布设置、草稿、可选圈子和主页。", "drafts": [{"id": "fixture_draft_photo", "type": "image", "body": "契约草稿内容"}], "selectableCircleIds": ["fixture_circle_photo", "fixture_circle_travel", "fixture_circle_life"], "selectableHomepageIds": ["fixture_homepage_author", "fixture_homepage_poi"]},
        },
        "scenarios": [{"id": "content_discovery_feed_basic", "title": "发现流契约种子基础加载", "type": "content_feed", "domainId": "content", "seedRefs": ["content_discovery_core", "home_feed_core", "content_detail_core", "search_core", "publish_core"], "uiExpectations": {"postIds": ["fixture_photo_001", "fixture_video_001", "fixture_article_001", "fixture_moment_001"], "textFragments": ["契约摄影师", "契约驱动的发现页文章"]}, "remoteExpectations": {"postIds": ["fixture_photo_001", "fixture_video_001", "fixture_article_001", "fixture_moment_001"], "detailPostId": "fixture_photo_001", "commentIds": ["fixture_comment_photo_001"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def build_user_doc(users: list[dict[str, Any]], posts: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = []
    for user in users:
        profiles.append({
            "userId": user["userId"],
            "displayName": user["displayName"],
            "avatarUrl": user["profile"]["avatar"]["objectKey"],
            "backgroundUrl": user["profile"]["background"]["objectKey"],
            "bio": user["bio"],
            "stats": user["stats"],
            "primaryRole": user["primaryRole"],
            "primaryTheme": user["primaryTheme"],
            "secondaryThemes": user["secondaryThemes"],
            "themeTags": user["themeTags"],
            "postThemeRefs": user["postThemeRefs"],
            "circleThemeRefs": user["circleThemeRefs"],
            "groupPersonaMix": user["groupPersonaMix"],
            "avatarObjectKey": user["profile"]["avatar"]["objectKey"],
            "backgroundObjectKey": user["profile"]["background"]["objectKey"],
            "subAccountRefs": user["subAccountRefs"],
            "tags": user["roleTags"],
            "media": {"avatar": user["profile"]["avatar"], "background": user["profile"]["background"]},
        })
    my_posts = [post["postId"] for post in posts if post["authorUserId"] == "fixture_user_current"][:12]
    author_posts = [post["postId"] for post in posts if post["authorUserId"] == "fixture_user_photo"][:12]
    return {
        "schemaVersion": "user.scenario-fixtures",
        "description": "用户域 alpha/beta/gamma 共享测试场景，覆盖我的主页、作者主页、persona 与关系能力。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "user_profile_core": {"description": "当前用户、作者用户、头像、昵称与统计。", "profiles": profiles},
            "persona_core": {"description": "当前 sub-account、候选 sub-account 与 active context。", "activeSubAccountId": "fixture_persona_daily", "personas": [{"subAccountId": "fixture_persona_daily", "name": "日常我", "description": "默认日常 sub-account"}, {"subAccountId": "fixture_persona_work", "name": "工作我", "description": "工作场景 sub-account"}]},
            "profile_feed_core": {"description": "我的作品、作者作品、生活记录与评论。", "myPostIds": my_posts or ["fixture_moment_001", "fixture_photo_001"], "authorPostIds": author_posts or ["fixture_photo_001", "fixture_photo_002"], "commentIds": ["fixture_comment_photo_001"]},
            "relationship_core": {"description": "关注、互关、拉黑、可聊天、可通话能力矩阵。", "relationships": [{"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_photo", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}, {"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_friend", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}, {"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_weekend_1", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}]},
            "settings_core": {"description": "外观、通话设置与开发者诊断最小数据。", "appearance": {"themeMode": "system", "fontScale": 1.0}, "callSettings": {"allowVoiceCall": True, "allowVideoCall": True}, "diagnostics": [{"id": "fixture_ops_event_settings", "message": "契约设置诊断事件"}]},
        },
        "scenarios": [{"id": "user_profile_basic", "title": "用户主页与关系能力契约种子", "type": "user_profile", "domainId": "user", "seedRefs": ["user_profile_core", "persona_core", "profile_feed_core", "relationship_core", "settings_core"], "uiExpectations": {"userIds": ["fixture_user_current", "fixture_user_photo"], "textFragments": ["契约当前用户", "契约摄影师", "日常我"]}, "remoteExpectations": {"profileUserIds": ["fixture_user_current", "fixture_user_photo"], "subAccountIds": ["fixture_persona_daily", "fixture_persona_work"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def build_circle_doc(circles: list[dict[str, Any]], memberships: dict[str, list[str]], users: list[dict[str, Any]], posts: list[dict[str, Any]]) -> dict[str, Any]:
    users_by_id = user_index(users)
    circles_rows = []
    groups: dict[str, list[dict[str, Any]]] = {}
    members_doc: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, list[dict[str, Any]]] = {}
    for idx, circle in enumerate(circles):
        circles_rows.append({
            "id": circle["circleId"],
            "name": circle["displayName"],
            "ownerId": circle["ownerUserId"],
            "role": "owner" if idx == 0 else "member",
            "joinStatus": "joined",
            "isFollowed": idx < 6,
            "coverUrl": circle["cover"]["objectKey"],
            "avatarUrl": circle["avatar"]["objectKey"],
            "description": circle["summary"],
            "visibility": "public",
            "joinPolicy": "approval" if circle["isCoreFixture"] else "open",
            "circleType": circle["circleType"],
            "primaryTheme": circle["primaryTheme"],
            "secondaryThemes": circle["secondaryThemes"],
            "themeTags": circle["themeTags"],
            "categoryId": circle["primaryCategory"],
            "subCategory": circle["secondaryCategory"],
            "domainId": circle["contentDomain"],
            "memberCount": circle["stats"]["memberCount"],
            "postCount": circle["stats"]["postCount"],
            "weeklyActiveCount": circle["stats"]["dailyActiveMemberCount"] * 2,
            "conversationId": circle["groupConversationId"],
            "autoSyncChat": True,
            "defaultPublicGroupId": f"fixture_group_{circle_suffix(circle['circleId'])}_public",
            "createdAt": circle["createdAt"],
            "updatedAt": circle["createdAt"],
            "ownerDisplayNameSnapshot": users_by_id[circle["ownerUserId"]]["displayName"],
            "avatarObjectKey": circle["avatar"]["objectKey"],
            "coverObjectKey": circle["cover"]["objectKey"],
        })
        groups[circle["circleId"]] = [{
            "_id": f"fixture_group_{circle_suffix(circle['circleId'])}_public",
            "circleId": circle["circleId"],
            "groupType": "public_group",
            "name": f"{circle['displayName']}公开群",
            "description": f"{circle['displayName']} 默认公开群。",
            "visibility": "public",
            "joinPolicy": "apply_only",
            "ownerUserId": circle["ownerUserId"],
            "memberCount": len(circle["memberUserIds"]),
            "conversationId": circle["groupConversationId"],
            "storageEnabled": True,
            "noticeEnabled": True,
            "isDefaultPublicGroup": True,
            "status": "active",
            "createdAt": circle["createdAt"],
            "updatedAt": circle["createdAt"],
            "ownerDisplayNameSnapshot": users_by_id[circle["ownerUserId"]]["displayName"],
        }]
        members_doc[circle["circleId"]] = [
            {
                "_id": f"fixture_member_{circle_suffix(circle['circleId'])}_{member_id}",
                "circleId": circle["circleId"],
                "userId": member_id,
                "role": "owner" if member_id == circle["ownerUserId"] else "member",
                "joinedAt": circle["createdAt"],
                "lastActiveAt": circle["createdAt"],
                "contribution": 10 if member_id == circle["ownerUserId"] else 3,
                "displayName": users_by_id[member_id]["displayName"],
                "avatarObjectKey": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
                "avatarUrl": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
            }
            for member_id in memberships.get(circle["circleId"], circle["memberUserIds"])
        ]
    files["fixture_circle_photo"] = [{
        "_id": "fixture_file_photo_guide",
        "circleId": "fixture_circle_photo",
        "groupId": "fixture_group_photo_public",
        "name": "摄影路线指南.png",
        "fileType": "image",
        "mimeType": "image/png",
        "sizeBytes": 4096,
        "objectKey": next(circle["cover"]["objectKey"] for circle in circles if circle["circleId"] == "fixture_circle_photo"),
        "uploaderId": "fixture_user_owner",
        "status": "active",
        "createdAt": iso_at(300),
        "updatedAt": iso_at(300),
    }]
    photo_posts = [post["postId"] for post in posts if post["circleRef"] == "fixture_circle_photo"][:12]
    return {
        "schemaVersion": "circle.scenario-fixtures",
        "description": "圈子域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.circles 初始化 MockCircleRepository。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "circle_core": {"description": "圈子列表、详情、默认群与成员共享真实图片种子。", "circles": circles_rows, "groups": groups, "members": members_doc, "files": files},
            "circle_home_feed_core": {"description": "首页群组 tab 与圈子 hub feed 所需内容映射。", "featuredCircleIds": [circle["circleId"] for circle in circles[:12]], "groupFeedPostIds": photo_posts or ["fixture_photo_001", "fixture_photo_002", "fixture_article_001", "fixture_video_001"]},
            "circle_profile_core": {"description": "圈子主页封面、统计、成员与作品。", "circleIds": ["fixture_circle_photo"], "stats": [{"circleId": "fixture_circle_photo", "memberCount": next(circle["stats"]["memberCount"] for circle in circles if circle["circleId"] == "fixture_circle_photo"), "postCount": next(circle["stats"]["postCount"] for circle in circles if circle["circleId"] == "fixture_circle_photo"), "weeklyActiveCount": next(circle["stats"]["dailyActiveMemberCount"] * 2 for circle in circles if circle["circleId"] == "fixture_circle_photo")}], "postIds": photo_posts[:4] or ["fixture_photo_001", "fixture_photo_002", "fixture_article_001", "fixture_video_001"]},
            "circle_group_chat_link_core": {"description": "圈子默认公开群与聊天会话的对齐关系。", "links": [{"circleId": circle["circleId"], "groupId": f"fixture_group_{circle_suffix(circle['circleId'])}_public", "conversationId": circle["groupConversationId"]} for circle in circles if circle["isCoreFixture"]]},
        },
        "scenarios": [{"id": "circle_list_detail_basic", "title": "圈子列表与详情契约种子", "type": "circle_list_detail", "domainId": "circle", "seedRefs": ["circle_core", "circle_home_feed_core", "circle_profile_core", "circle_group_chat_link_core"], "uiExpectations": {"circleIds": ["fixture_circle_photo", "fixture_circle_travel"], "textFragments": ["契约摄影社", "契约旅行手账"]}, "remoteExpectations": {"circleIds": ["fixture_circle_photo", "fixture_circle_travel"], "groupIds": ["fixture_group_photo_public"], "memberUserIds": ["fixture_user_owner", "fixture_user_current"], "fileIds": ["fixture_file_photo_guide"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def build_chat_doc(conversations: list[dict[str, Any]], conversation_members: dict[str, list[str]], users: list[dict[str, Any]], posts: list[dict[str, Any]]) -> dict[str, Any]:
    users_by_id = user_index(users)
    post_ids = [post["postId"] for post in posts]
    conversation_rows = []
    members_rows: dict[str, list[dict[str, Any]]] = {}
    message_rows: dict[str, list[dict[str, Any]]] = {}
    user_states = []
    for idx, conversation in enumerate(conversations):
        conv_id = conversation["conversationId"]
        is_direct = conversation["conversationType"] == "directConversation"
        messages = []
        for seq in range(6 if is_direct else 8):
            sender_id = conversation_members[conv_id][seq % len(conversation_members[conv_id])]
            sender = users_by_id[sender_id]
            shared_post_id = post_ids[(idx * 5 + seq) % len(post_ids)] if seq in {2, 5} else None
            text = f"{sender['displayName']} 在 {conversation['displayName']} 中发送的共享池消息 #{seq + 1}。"
            message_id = f"{conv_id}_msg_{seq + 1:02d}"
            if conv_id == "fixture_conv_direct" and seq == 1:
                text = "契约消息已送达"
            if conv_id == "fixture_conv_direct" and seq == 0:
                text = "这是一条契约聊天消息。"
                message_id = "fixture_msg_direct_1"
            if conv_id == "fixture_conv_direct" and seq == 1:
                message_id = "fixture_msg_direct_2"
            if conv_id == "fixture_conv_group" and seq == 0:
                text = "周末集合时间已确认"
                message_id = "fixture_msg_group_1"
            if conv_id == "fixture_conv_group" and seq == 1:
                message_id = "fixture_msg_group_2"
            if conv_id == "fixture_conv_group" and seq == 2:
                message_id = "fixture_msg_group_3"
            if conv_id == "fixture_conv_photo_group" and seq == 0:
                text = "今晚整理照片墙和路线。"
                message_id = "fixture_msg_photo_group_1"
            if conv_id == "fixture_conv_photo_group" and seq == 1:
                message_id = "fixture_msg_photo_group_2"
            if conv_id == "fixture_conv_travel_group" and seq == 0:
                text = "路线、天气和集合点都同步了。"
                message_id = "fixture_msg_travel_group_1"
            if conv_id == "fixture_conv_article_direct" and seq == 0:
                text = "文章配图已经补齐。"
                message_id = "fixture_msg_article_direct_1"
            messages.append({
                "messageId": message_id,
                "_id": message_id,
                "conversationId": conv_id,
                "senderId": sender_id,
                "content": text,
                "type": "text",
                "messageType": "text",
                "seq": seq + 1,
                "createdAt": iso_at(1000 + idx * 2 + seq),
                "senderDisplayNameSnapshot": sender["displayName"],
                "senderAvatarObjectKeySnapshot": sender["profile"]["avatar"]["objectKey"],
                "senderAvatarUrlSnapshot": sender["profile"]["avatar"]["objectKey"],
                "senderAvatar": sender["profile"]["avatar"]["objectKey"],
                "sharedPostId": shared_post_id,
            })
        message_rows[conv_id] = messages
        last_message = messages[-1]
        row = {
            "_id": conv_id,
            "id": conv_id,
            "conversationId": conv_id,
            "type": "direct" if is_direct else "group",
            "conversationType": conversation["conversationType"],
            "title": conversation["displayName"],
            "avatarUrl": conversation["avatar"]["objectKey"],
            "creatorId": conversation.get("creatorId") or conversation["memberUserIds"][0],
            "maxSeq": len(messages),
            "memberCount": len(conversation["memberUserIds"]),
            "maxGroupSize": 2 if is_direct else 500,
            "receiptEnabled": True,
            "lastMessagePreview": last_message["content"],
            "lastMessageTime": last_message["createdAt"],
            "messageCount": len(messages),
            "status": "active",
            "createdAt": messages[0]["createdAt"],
            "updatedAt": last_message["createdAt"],
            "avatarObjectKey": conversation["avatar"]["objectKey"],
            "primaryTheme": conversation["primaryTheme"],
            "secondaryThemes": conversation["secondaryThemes"],
            "themeTags": conversation["themeTags"],
            "groupPersonaMix": conversation["groupPersonaMix"],
        }
        if is_direct:
            row["targetUserId"] = conversation["memberUserIds"][1]
        else:
            row["circleId"] = conversation.get("circleRef")
            row["groupAvatarVersion"] = conversation["groupAvatarVersion"]
            row["groupAvatarSourceUserIds"] = conversation["groupAvatarSourceUserIds"]
        conversation_rows.append(row)
        members_rows[conv_id] = [
            {
                "userId": member_id,
                "displayName": users_by_id[member_id]["displayName"],
                "avatarUrl": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
                "avatarObjectKey": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
                "role": "owner" if member_id == (conversation.get("creatorId") or conversation["memberUserIds"][0]) else "member",
                "isCurrentUser": member_id == "fixture_user_current",
            }
            for member_id in conversation_members[conv_id]
        ]
        user_states.append({"_id": f"fixture_state_{conv_id}_current", "userId": "fixture_user_current", "conversationId": conv_id, "readSeq": max(0, len(messages) - 1), "unreadCount": 1 if idx % 3 == 0 else 0, "muted": False, "pinned": idx < 2, "updatedAt": last_message["createdAt"]})
    contacts = []
    seen = set()
    for user_id in ["fixture_user_friend", "fixture_user_weekend_1", "fixture_user_weekend_2", "fixture_user_photo", "fixture_user_travel", "fixture_user_article"] + [user["userId"] for user in users if "contact" in user["roleTags"]][:18]:
        if user_id in seen or user_id == "fixture_user_current":
            continue
        seen.add(user_id)
        user = users_by_id[user_id]
        contacts.append({"userId": user_id, "displayName": user["displayName"], "avatarUrl": user["profile"]["avatar"]["objectKey"], "relationship": "mutual_follow" if "contact" in user["roleTags"] else "circle_member", "isFriend": True, "bio": user["bio"], "avatarObjectKey": user["profile"]["avatar"]["objectKey"]})
    return {
        "schemaVersion": "chat.scenario-fixtures",
        "description": "聊天域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.conversations/messages/members 初始化 MockChatRepository。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "chat_core": {"description": "聊天 inbox、详情、成员与消息共享真实图片种子。", "currentUserId": "fixture_user_current", "conversations": conversation_rows, "messages": message_rows, "members": members_rows, "userStates": user_states},
            "chat_settings_core": {"description": "会话设置、免打扰、置顶、公告、管理员与转让候选人。", "settings": [{"conversationId": "fixture_conv_group", "muted": False, "pinned": False, "announcement": "契约群公告：周末集合时间已确认", "adminUserIds": ["fixture_user_current"], "transferCandidateUserIds": ["fixture_user_weekend_1", "fixture_user_weekend_2"]}]},
            "chat_contacts_core": {"description": "联系人 tab、圈子联系人与趣群联系人。", "contacts": contacts, "circleIds": ["fixture_circle_photo", "fixture_circle_travel", "fixture_circle_city", "fixture_circle_life"], "groupConversationIds": ["fixture_conv_group", "fixture_conv_photo_group", "fixture_conv_travel_group"]},
            "chat_group_flow_core": {"description": "建群、加人、管理页所需成员候选。", "candidateUserIds": ["fixture_user_friend", "fixture_user_weekend_1", "fixture_user_weekend_2"], "defaultGroupTitle": "契约新建群"},
        },
        "scenarios": [{"id": "chat_inbox_detail_basic", "title": "聊天 inbox 与详情契约种子", "type": "chat_inbox_detail", "domainId": "chat", "seedRefs": ["chat_core", "chat_settings_core", "chat_contacts_core", "chat_group_flow_core"], "uiExpectations": {"conversationIds": ["fixture_conv_direct", "fixture_conv_group"], "textFragments": ["契约好友", "契约周末群"]}, "remoteExpectations": {"conversationIds": ["fixture_conv_direct", "fixture_conv_group"], "contactUserIds": ["fixture_user_friend", "fixture_user_photo"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def main() -> int:
    ensure_beta_sample_video()
    source_catalog, theme_catalog, rules = load_catalogs()
    users, user_assets, _background_assets, source_updates = build_users(source_catalog, theme_catalog, rules)
    source_catalog["entries"] = source_updates
    circles, _circle_assets, _circle_covers, memberships = build_circles(users, user_assets, source_catalog, theme_catalog, rules)
    posts, post_assets = build_posts(users, circles, source_catalog, theme_catalog, rules)
    ensure_core_posts(posts, post_assets, users, circles, source_catalog, theme_catalog)
    conversations, conversation_members = build_conversations(users, circles, user_assets, rules)
    ensure_core_conversations(conversations, conversation_members, user_assets, users)
    attach_cross_refs(users, circles, conversations, posts)

    write_json(SOURCE_CATALOG_PATH, source_catalog)
    write_json(USER_POOL_PATH, build_user_pool_doc(users, posts, circles, conversations, source_catalog, theme_catalog, rules))
    write_json(USER_SCENARIOS, build_user_doc(users, posts))
    write_json(CONTENT_SCENARIOS, build_content_doc(posts, circles))
    write_json(CIRCLE_SCENARIOS, build_circle_doc(circles, memberships, users, posts))
    write_json(CHAT_SCENARIOS, build_chat_doc(conversations, conversation_members, users, posts))
    print(f"shared real asset pipeline synced: {USER_POOL_PATH.relative_to(ROOT)}")
    print(f"media assets written under: {MEDIA_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
