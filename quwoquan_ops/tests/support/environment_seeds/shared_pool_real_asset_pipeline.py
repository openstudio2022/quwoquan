#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_service").is_dir() and (parent / "quwoquan_ops").is_dir()
)
SERVICE_ROOT = ROOT / "quwoquan_service"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
ORIGINAL_ROOT = SHARED / "original_media"
USER_POOL_PATH = (
    ROOT
    / "quwoquan_service/services/user-service/tests/support/contract_fixtures/user_pool.json"
)
SOURCE_CATALOG_PATH = SHARED / "source_catalog.json"
THEME_CATALOG_PATH = SHARED / "theme_catalog.json"
COMPOSITION_RULES_PATH = SHARED / "composition_rules.json"
USER_SCENARIOS = ROOT / "quwoquan_service/services/user-service/tests/support/contract_fixtures/scenarios/user_scenarios.json"
CONTENT_SCENARIOS = ROOT / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json"
CIRCLE_SCENARIOS = ROOT / "quwoquan_service/services/circle-service/tests/support/contract_fixtures/scenarios/circle_scenarios.json"
CHAT_SCENARIOS = ROOT / "quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json"
GROUP_RENDER_PACKAGE = "./tools/render_group_avatar"

_CONTRACT_DIR = SERVICE_ROOT / "scripts" / "contract"
if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))
from verify_content_fixture_comment_counts import realign_payload_counts  # noqa: E402

PRIMARY_VIDEO_PUBLIC_SLICE_KEY = "media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
# 真实可播放样例视频源（CC0, H.264/AAC, faststart），随仓库提交，供服务端样例
# 视频对象拷贝；远大于历史 24B ftyp 占位桩，用于拦截占位桩回退。
PRIMARY_VIDEO_SOURCE_FILENAME = "primary_video.mp4"
PRIMARY_VIDEO_MIN_BYTES = 4096
PRIMARY_ATTACHMENT_PUBLIC_SLICE_KEY = (
    "media/attachment/s/archived-attachment/post/fixture_chat_file_001/spec.txt"
)
PRIMARY_ATTACHMENT_BYTES = (
    "Quwoquan contract attachment\n"
    "This deterministic text file validates chat attachment delivery.\n"
).encode("utf-8")

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
DEFAULT_NICKNAME_PREFIX = "新同学"
DEFAULT_NICKNAME_SAMPLE_TIME = datetime(2026, 6, 22, 1, 51, 38, 421000)
DEFAULT_NICKNAME_SAMPLE_ENTROPY = 271


def build_default_nickname(
    now: datetime,
    *,
    prefix: str = DEFAULT_NICKNAME_PREFIX,
    extra_entropy: int = 0,
) -> str:
    date_part = now.strftime("%y%m%d")
    millis_of_day = (
        ((now.hour * 60 + now.minute) * 60 + now.second) * 1000
        + now.microsecond // 1000
    )
    suffix = (millis_of_day + max(extra_entropy, 0)) % 10_000_000
    return f"{prefix}_{date_part}_{suffix:07d}"


FIXTURE_CURRENT_USER_DEFAULT_NICKNAME = build_default_nickname(
    DEFAULT_NICKNAME_SAMPLE_TIME,
    extra_entropy=DEFAULT_NICKNAME_SAMPLE_ENTROPY,
)

CORE_USER_PRESETS = {
    "fixture_user_current": {
        "themeId": "lifestyle",
        "role": "currentUserVariant",
        "displayName": FIXTURE_CURRENT_USER_DEFAULT_NICKNAME,
        "bio": "",
        "avatarSourceId": "portrait_archived_lifestyle_01",
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
        "avatarSourceId": "portrait_archived_photography_01",
        "backgroundSourceId": "scene_photo_architecture_01",
        "tags": ["author", "photo", "contact"],
        "format": "png",
    },
    "fixture_user_travel": {
        "themeId": "travel",
        "role": "leadAuthor",
        "displayName": "契约旅行家",
        "bio": "旅行、天气和行程记录作者。",
        "avatarSourceId": "portrait_archived_travel_01",
        "backgroundSourceId": "landscape_travel_01",
        "tags": ["author", "travel", "contact"],
        "format": "png",
    },
    "fixture_user_video": {
        "themeId": "cityWalk",
        "role": "groupOrganizer",
        "displayName": "契约剪辑师",
        "bio": "视频剪辑与城市影像作者。",
        "avatarSourceId": "portrait_archived_city_01",
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
        "avatarSourceId": "portrait_archived_food_01",
        "backgroundSourceId": "scene_coffee_night_01",
        "tags": ["contact", "direct-chat"],
        "format": "png",
    },
    "fixture_user_weekend_1": {
        "themeId": "lifestyle",
        "role": "groupOrganizer",
        "displayName": "契约同伴一",
        "bio": "周末群成员，也是联系人同好。",
        "avatarSourceId": "portrait_archived_design_01",
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
ADDITIONAL_CIRCLE_PRESETS = (
    {
        "sourceThemeId": "tech",
        "circleId": "fixture_circle_gold_invest",
        "conversationId": "fixture_conv_circle_gold_invest",
        "groupId": "fixture_group_gold_invest_public",
        "name": "黄金投资圈",
        "summary": "围绕黄金、贵金属和长期资产配置展开事实讨论。",
        "ownerId": "fixture_user_article",
        "format": "png",
        "primaryTheme": "finance",
        "secondaryThemes": ["investment", "gold"],
        "themeTags": ["finance", "investment", "gold"],
        "displayTags": ["黄金", "贵金属", "资产配置"],
        "primaryCategory": "finance",
        "secondaryCategory": "黄金",
        "contentDomain": "finance",
        "stats": {
            "memberCount": 8400,
            "postCount": 1200,
            "dailyActiveMemberCount": 163,
            "discussionCount": 326,
        },
    },
    {
        "sourceThemeId": "designWriting",
        "circleId": "fixture_circle_neworiental_alumni",
        "conversationId": "fixture_conv_circle_neworiental_alumni",
        "groupId": "fixture_group_neworiental_alumni_public",
        "name": "新东方校友圈",
        "summary": "新东方校友围绕学习、成长和职业转型形成的兴趣圈。",
        "ownerId": "fixture_user_commenter",
        "format": "png",
        "primaryTheme": "education",
        "secondaryThemes": ["alumni", "growth"],
        "themeTags": ["education", "alumni", "growth"],
        "primaryCategory": "education",
        "secondaryCategory": "校友",
        "contentDomain": "education",
    },
)
CORE_MENTION_CONVERSATION_ID = "fixture_conv_group"

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_owned_fixture(path: Path, generated: dict[str, Any]) -> dict[str, Any]:
    """Replace generator-owned seed sets without deleting independent fixtures."""
    if not path.exists():
        return generated

    existing = load_json(path)
    merged = dict(existing)
    merged.update(
        {
            key: value
            for key, value in generated.items()
            if key not in {"seedSets", "scenarios"}
        }
    )

    seed_sets = dict(existing.get("seedSets") or {})
    seed_sets.update(generated.get("seedSets") or {})
    merged["seedSets"] = seed_sets

    generated_scenarios = {
        str(item.get("id") or "").strip(): item
        for item in generated.get("scenarios") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    scenarios: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for item in existing.get("scenarios") or []:
        if not isinstance(item, dict):
            continue
        scenario_id = str(item.get("id") or "").strip()
        if scenario_id in generated_scenarios:
            scenarios.append(generated_scenarios[scenario_id])
            consumed.add(scenario_id)
        else:
            scenarios.append(item)
    scenarios.extend(
        item
        for scenario_id, item in generated_scenarios.items()
        if scenario_id not in consumed
    )
    merged["scenarios"] = scenarios
    return merged


def slug(value: str) -> str:
    return value.replace(" ", "-").replace("/", "-").replace("_", "-").lower()


def user_suffix(user_id: str) -> str:
    return user_id.replace("fixture_user_", "").replace("fixture_", "")


def circle_suffix(circle_id: str) -> str:
    return circle_id.replace("fixture_circle_", "").replace("fixture_", "")


def canonical_media_object_key(object_key: str) -> str:
    return object_key.strip().lstrip("/")


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
        "markdownDialect": "qwq-rich-md",
        "articleMarkdownDigest": markdown_digest,
        "articleAssetManifest": {
            "schema": "article-asset-manifest",
            "markdownDialect": "qwq-rich-md",
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
    object_key = canonical_media_object_key(object_key)
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
    output_key = canonical_media_object_key(output_key)
    dst = MEDIA_ROOT / output_key
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        ["go", "run", GROUP_RENDER_PACKAGE, str(dst), *[str(path) for path in input_paths[:9]]],
        cwd=SERVICE_ROOT,
    )
    raw = dst.read_bytes()
    return {"objectKey": output_key, "version": 1, "mimeType": "image/png", "width": 256, "height": 256, "sizeBytes": len(raw), "sourceHash": sha256_bytes(raw)}


def ensure_primary_delivery_video() -> None:
    # 服务端样例视频必须是真实可播放的 H.264/AAC MP4（faststart）。
    # 历史实现写入 24B 的 ftyp 占位桩（无 moov/mdat、无音视频轨），导致端侧
    # 聚焦后只能持续「加载中…」且无法播放；这里改为从受控真实源拷贝，并禁止
    # 回退占位桩。真实源随仓库提交在 original_media 下。
    source = ORIGINAL_ROOT / PRIMARY_VIDEO_SOURCE_FILENAME
    if not source.is_file() or source.stat().st_size < PRIMARY_VIDEO_MIN_BYTES:
        raise SystemExit(
            "missing playable primary video source: "
            f"{source.relative_to(ROOT)}（禁止回退为不可播放的占位桩）"
        )
    path = MEDIA_ROOT / canonical_media_object_key(PRIMARY_VIDEO_PUBLIC_SLICE_KEY)
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_copy = (
        not path.is_file()
        or path.stat().st_size != source.stat().st_size
        or path.read_bytes() != source.read_bytes()
    )
    if needs_copy:
        shutil.copyfile(source, path)


def ensure_primary_delivery_attachment() -> None:
    path = MEDIA_ROOT / canonical_media_object_key(
        PRIMARY_ATTACHMENT_PUBLIC_SLICE_KEY
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != PRIMARY_ATTACHMENT_BYTES:
        path.write_bytes(PRIMARY_ATTACHMENT_BYTES)


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


def build_time_fields(
    *,
    created_offset_hours: int,
    published_offset_hours: int | None = None,
    updated_offset_hours: int | None = None,
) -> dict[str, str]:
    created_at = iso_at(created_offset_hours)
    published_at = iso_at(
        created_offset_hours + 24
        if published_offset_hours is None
        else published_offset_hours
    )
    updated_at = iso_at(
        created_offset_hours
        if updated_offset_hours is None
        else updated_offset_hours
    )
    return {
        "createdAt": created_at,
        "updatedAt": updated_at,
        "publishedAt": published_at,
    }


def media_spec(post_id: str, variant: str, source_id: str, width: int, height: int, format_ext: str) -> dict[str, Any]:
    return {
        "sourceId": source_id,
        "objectKey": canonical_media_object_key(
            f"media/image/s/archived-image/post/{post_id}/{variant}.{format_ext}"
        ),
        "width": width,
        "height": height,
        "format": format_ext,
    }


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
        entry_copy = dict(entry)
        source_ref_values = entry_copy.pop("sourceRefs", None)
        if source_ref_values is not None and "sourceRefs" not in entry_copy:
            entry_copy["sourceRefs"] = source_ref_values
        source_updates.append({**entry_copy, "download": download})

    source_index = {entry["sourceId"]: entry for entry in source_updates}

    for preset_id, preset in CORE_USER_PRESETS.items():
        avatar_format = preset.get("format", "png")
        avatar = derive_image(
            SHARED / source_index[preset["avatarSourceId"]]["download"]["storedRelativePath"],
            f"media/avatar/s/archived-avatar/user/{preset_id}/avatar.{avatar_format}",
            512,
            512,
            avatar_format,
        )
        background = derive_image(
            SHARED / source_index[preset["backgroundSourceId"]]["download"]["storedRelativePath"],
            f"media/background/s/archived-avatar/user/{preset_id}/background.{avatar_format}",
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
                f"media/avatar/s/archived-avatar/user/{user_id}/avatar.{avatar_format}",
                512,
                512,
                avatar_format,
            )
            background = derive_image(
                SHARED / source_index[background_source_id]["download"]["storedRelativePath"],
                f"media/background/s/archived-avatar/user/{user_id}/background.{background_format}",
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
                f"media/image/s/archived-image/circle/{circle_id}/cover.{cover_format}",
                1440,
                900,
                cover_format,
            )
            avatar = derive_image(
                SHARED / source_index[source_id]["download"]["storedRelativePath"],
                f"media/avatar/s/archived-avatar/circle/{circle_id}/avatar.{avatar_format}",
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

    required_presets = [
        {"sourceThemeId": theme_id, **preset}
        for theme_id, preset in CORE_CIRCLE_PRESETS.items()
    ] + list(ADDITIONAL_CIRCLE_PRESETS)
    for preset in required_presets:
        source_theme_id = preset["sourceThemeId"]
        theme = next(
            item
            for item in theme_catalog["themes"]
            if item["themeId"] == source_theme_id
        )
        source_id = choose_source(theme, "circleSourceIds", 0)
        cover = derive_image(
            SHARED / source_index[source_id]["download"]["storedRelativePath"],
            f"media/image/s/archived-image/circle/{preset['circleId']}/cover.{preset['format']}",
            1440,
            900,
            preset['format'],
        )
        avatar = derive_image(
            SHARED / source_index[source_id]["download"]["storedRelativePath"],
            f"media/avatar/s/archived-avatar/circle/{preset['circleId']}/avatar.{preset['format']}",
            512,
            512,
            preset['format'],
        )
        circle_assets[preset["circleId"]] = avatar
        circle_covers[preset["circleId"]] = cover
        member_ids = [user["userId"] for user in grouped[source_theme_id][:6]]
        memberships[preset["circleId"]] = member_ids
        primary, secondary, domain = CIRCLE_CATEGORY[source_theme_id]
        circles.insert(
            0,
            {
                "circleId": preset["circleId"],
                "displayName": preset["name"],
                "summary": preset.get(
                    "summary",
                    f"{theme['displayName']} 核心夹具圈子。",
                ),
                "avatar": avatar,
                "cover": cover,
                "ownerUserId": preset["ownerId"],
                "primaryTheme": preset.get("primaryTheme", source_theme_id),
                "secondaryThemes": preset.get(
                    "secondaryThemes",
                    list(theme.get("adjacentThemes") or [])[:1],
                ),
                "themeTags": preset.get(
                    "themeTags",
                    ordered_theme_tags(
                        source_theme_id,
                        list(theme.get("adjacentThemes") or [])[:1],
                    ),
                ),
                "displayTags": preset.get("displayTags"),
                "circleType": "flagshipCircle",
                "groupConversationId": preset["conversationId"],
                "memberUserIds": member_ids,
                "contentDomain": preset.get("contentDomain", domain),
                "primaryCategory": preset.get("primaryCategory", primary),
                "secondaryCategory": preset.get("secondaryCategory", secondary),
                "stats": preset.get(
                    "stats",
                    {
                        "memberCount": len(member_ids),
                        "postCount": 18,
                        "dailyActiveMemberCount": 8,
                    },
                ),
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
                    **build_time_fields(created_offset_hours=320 + len(posts)),
                    "stats": {"likeCount": 48 + index * 3, "commentCount": 4 + index % 6, "shareCount": 2 + index % 4},
                    "isCoreFixture": index < 3,
                    "videoObjectKey": PRIMARY_VIDEO_PUBLIC_SLICE_KEY if post_type == "videoCoverPost" else None,
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
                f"media/image/s/archived-image/post/{post_id}/cover.jpg",
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
                    **build_time_fields(
                        created_offset_hours=600 + pair_index * 10 + index
                    ),
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
            f"media/avatar/s/archived-avatar/group/{conv_id}/composite.png",
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
        {"postId": "fixture_article_001", "themeId": "designWriting", "authorUserId": "fixture_user_article", "circleId": "fixture_circle_tech", "postType": "articlePost", "headline": "契约驱动的发现页文章", "summary": "契约驱动的发现页文章。", "body": "文章、攻略与长图文作者。", "sourceIndex": 0, "extraCount": 1, "locationName": "线上专栏", "publishedOffsetHours": 69, "updatedOffsetHours": 93},
        {"postId": "fixture_article_002", "themeId": "designWriting", "authorUserId": "fixture_user_article", "circleId": "fixture_circle_tech", "postType": "articlePost", "headline": "从图片共享池到页面观感验证", "summary": "从图片共享池到页面观感验证。", "body": "用于验证文章封面、作者头像和详情配图。", "sourceIndex": 1, "extraCount": 1, "locationName": "线上专栏", "publishedOffsetHours": 70, "updatedOffsetHours": 46},
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
            f"media/image/s/archived-image/post/{spec['postId']}/cover.png",
            1280,
            cover_height,
            "png",
        )
        assets = [cover]
        for extra_idx in range(spec["extraCount"]):
            extra_source_id = choose_source(theme, "postSourceIds", spec["sourceIndex"] + extra_idx + 1)
            detail = derive_image(
                SHARED / sources[extra_source_id]["download"]["storedRelativePath"],
                f"media/image/s/archived-image/post/{spec['postId']}/image-{extra_idx + 2}.png",
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
            **build_time_fields(
                created_offset_hours=40 + idx,
                published_offset_hours=spec.get("publishedOffsetHours"),
                updated_offset_hours=spec.get("updatedOffsetHours"),
            ),
            "stats": {"likeCount": 80 + idx * 17, "commentCount": 6 + idx, "shareCount": 3 + idx % 4},
            "isCoreFixture": True,
            "videoObjectKey": PRIMARY_VIDEO_PUBLIC_SLICE_KEY if spec["postType"] == "videoCoverPost" else None,
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
                f"media/avatar/s/archived-avatar/group/{spec['conversationId']}/composite.png",
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
        "schema": "shared.avatar-user-pool",
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
        return "micro", "moment"
    return "image", "work"


def content_row(post: dict[str, Any], circles_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    content_type, identity = content_kind(post["postType"])
    assets = [post["coverAsset"], *post["supportingAssets"]]
    circle = circles_by_id[post["circleRef"]]
    row = {
        "postId": post["postId"],
        "contentType": content_type,
        "contentIdentity": identity,
        "authorId": post["authorUserId"],
        "subAccountId": post["authorUserId"],
        "authorDisplayName": post["authorProfile"]["displayName"],
        "authorAvatarUrl": post["authorProfile"]["avatar"]["objectKey"],
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
        "createdAt": post["createdAt"],
        "updatedAt": post["updatedAt"],
        "publishedAt": post["publishedAt"],
        "authorDisplayNameSnapshot": post["authorProfile"]["displayName"],
        "authorAvatarObjectKey": post["authorProfile"]["avatar"]["objectKey"],
        "avatarObjectKey": post["authorProfile"]["avatar"]["objectKey"],
        "authorBackgroundObjectKey": post["authorProfile"]["background"]["objectKey"],
        "coverObjectKey": post["coverAsset"]["objectKey"],
        "thumbnailObjectKey": post["coverAsset"]["objectKey"],
        "mediaObjectKeys": [asset["objectKey"] for asset in assets],
        "imageObjectKeys": [asset["objectKey"] for asset in assets if asset["mimeType"].startswith("image/")],
        "tagRefs": ["fixture", post["primaryTheme"], post["postType"]],
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


def build_comment_thread_core_seed() -> dict[str, Any]:
    """评论二级线程统一种子（单一版本，无 v1/v2）。

    覆盖 0 / 1 / 5 / 10 / 50 / 100+ 条回复磁度，含置顶、作者赞过、IP 属地与图片回复，
    供端云「列表 + 排序 + 二级展开」契约同源验证。所有回复均为真实记录，
    `replyCount` 由实际回复条数派生，保证换排序不换集合、计数与条目一致。
    """
    post_id = "fixture_photo_001"

    def avatar(uid: str) -> str:
        return f"media/avatar/s/archived-avatar/user/{uid}/avatar.png"

    repliers = [
        ("fixture_user_friend", "契约好友"),
        ("fixture_user_photo", "契约摄影师"),
        ("fixture_user_commenter", "契约评论者"),
        ("fixture_user_current", FIXTURE_CURRENT_USER_DEFAULT_NICKNAME),
    ]
    comments: list[dict[str, Any]] = []

    def add_comment(
        comment_id: str,
        author_id: str,
        author_name: str,
        content: str,
        offset_minutes: int,
        **extra: Any,
    ) -> None:
        base = datetime(2026, 6, 5, 12, 0, 0)
        created_at = (base + timedelta(minutes=offset_minutes)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        row: dict[str, Any] = {
            "commentId": comment_id,
            "_id": comment_id,
            "postId": post_id,
            "authorId": author_id,
            "authorDisplayNameSnapshot": author_name,
            "authorAvatarObjectKeySnapshot": avatar(author_id),
            "authorAvatarUrlSnapshot": avatar(author_id),
            "content": content,
            "createdAt": created_at,
        }
        row.update(extra)
        comments.append(row)

    def add_replies(
        parent_id: str,
        parent_author_id: str,
        parent_author_name: str,
        total: int,
        base_offset: int,
        image_on_first: bool = False,
    ) -> None:
        for i in range(total):
            replier_id, replier_name = repliers[i % len(repliers)]
            reply_id = f"{parent_id}_r{i + 1:03d}"
            extra: dict[str, Any] = {
                "parentCommentId": parent_id,
                "replyToCommentId": parent_id,
                "replyToUserId": parent_author_id,
                "replyToDisplayName": parent_author_name,
            }
            if image_on_first and i == 0:
                extra["attachmentMediaIds"] = [f"{reply_id}_media"]
                extra["attachments"] = [
                    {
                        "mediaId": f"{reply_id}_media",
                        "type": "image",
                        "url": "media/comment/s/archived-comment/"
                        f"{reply_id}/comment.png",
                        "width": 1200,
                        "height": 900,
                    }
                ]
            add_comment(
                reply_id,
                replier_id,
                replier_name,
                f"回复样本 #{i + 1}",
                base_offset + i + 1,
                **extra,
            )

    # 1 条回复（置顶 + 作者赞过 + IP 属地）：保留契约稳定 ID，供 seed manifest 端点引用。
    add_comment(
        "fixture_comment_parent_001",
        "fixture_user_current",
        FIXTURE_CURRENT_USER_DEFAULT_NICKNAME,
        "主评论示例",
        0,
        authorIpLocation="浙江",
        isPinned=True,
        pinnedAt="2026-06-05T12:30:00Z",
        authorLiked=True,
        likeCount=128,
        hotScore=128.0,
    )
    add_comment(
        "fixture_comment_reply_001",
        "fixture_user_commenter",
        "契约评论者",
        "回复示例",
        5,
        authorIpLocation="广东",
        parentCommentId="fixture_comment_parent_001",
        replyToCommentId="fixture_comment_parent_001",
        replyToUserId="fixture_user_current",
        replyToDisplayName=FIXTURE_CURRENT_USER_DEFAULT_NICKNAME,
    )

    # 0 条回复。
    add_comment(
        "fixture_comment_thread_empty",
        "fixture_user_friend",
        "契约好友",
        "零回复评论示例",
        10,
        authorIpLocation="北京",
        likeCount=3,
        hotScore=3.0,
    )
    # 5 条回复（首次展开即加载完毕）。
    add_comment(
        "fixture_comment_thread_five",
        "fixture_user_photo",
        "契约摄影师",
        "五条回复评论示例",
        20,
        authorIpLocation="上海",
        likeCount=12,
        hotScore=12.0,
    )
    add_replies("fixture_comment_thread_five", "fixture_user_photo", "契约摄影师", 5, 100)
    # 10 条回复（演示 1→5→10 三段展开 + 图片回复）。
    add_comment(
        "fixture_comment_thread_ten",
        "fixture_user_commenter",
        "契约评论者",
        "十条回复评论示例",
        30,
        authorIpLocation="江苏",
        likeCount=24,
        hotScore=24.0,
    )
    add_replies(
        "fixture_comment_thread_ten",
        "fixture_user_commenter",
        "契约评论者",
        10,
        200,
        image_on_first=True,
    )
    # 50 条回复（多次「展开更多回复」）。
    add_comment(
        "fixture_comment_thread_fifty",
        "fixture_user_friend",
        "契约好友",
        "五十条回复评论示例",
        40,
        authorIpLocation="四川",
        likeCount=56,
        hotScore=56.0,
    )
    add_replies("fixture_comment_thread_fifty", "fixture_user_friend", "契约好友", 50, 400)
    # 110 条回复（100+ 大磁度）。
    add_comment(
        "fixture_comment_thread_hundred",
        "fixture_user_photo",
        "契约摄影师",
        "上百条回复评论示例",
        50,
        authorIpLocation="广东",
        likeCount=210,
        hotScore=210.0,
    )
    add_replies("fixture_comment_thread_hundred", "fixture_user_photo", "契约摄影师", 110, 1000)

    return {
        "description": "评论二级线程统一种子：覆盖 0/1/5/10/50/100+ 回复、置顶、作者赞过、IP 属地与图片回复。",
        "comments": comments,
    }


COMMENT_THREAD_CORE_COMMENT_COUNT = 6 + 1 + 5 + 10 + 50 + 110


def build_content_doc(posts: list[dict[str, Any]], circles: list[dict[str, Any]], users: list[dict[str, Any]]) -> dict[str, Any]:
    circles_by_id = circle_index(circles)
    users_by_id = user_index(users)
    post_rows = [content_row(post, circles_by_id) for post in posts]
    post_ids = [row["postId"] for row in post_rows]
    current_posts = [
        row["postId"]
        for row in post_rows
        if row["authorId"] == "fixture_user_current"
    ]
    comments = []
    reactions = []
    comment_authors = ["fixture_user_commenter", "fixture_user_friend", "fixture_user_current"]
    for idx, row in enumerate(post_rows[:48]):
        if row["postId"] == "fixture_photo_001":
            row["commentCount"] = COMMENT_THREAD_CORE_COMMENT_COUNT
            continue
        comment_id = (
            "fixture_comment_photo_001"
            if row["postId"] == "fixture_photo_001"
            else f"fixture_comment_{row['postId']}"
        )
        author_id = comment_authors[idx % len(comment_authors)]
        comments.append({
            "commentId": comment_id,
            "_id": comment_id,
            "postId": row["postId"],
            "authorId": author_id,
            "authorDisplayNameSnapshot": users_by_id[author_id]["displayName"],
            "authorAvatarObjectKeySnapshot": users_by_id[author_id]["profile"]["avatar"]["objectKey"],
            "authorAvatarUrlSnapshot": users_by_id[author_id]["profile"]["avatar"]["objectKey"],
            "content": f"共享池评论样本 #{idx + 1}",
            "createdAt": iso_at(900 + idx),
        })
    for idx, row in enumerate(post_rows[:72]):
        reactions.append({"postId": row["postId"], "userId": "fixture_user_current" if idx % 2 == 0 else "fixture_user_friend", "liked": True, "favorited": idx % 3 == 0})
    return {
        "schema": "content.scenario-fixtures",
        "description": "内容域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.posts 初始化 MockContentRepository，beta/gamma 云侧服务 reset+seed 后由端侧 remote 访问。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "content_discovery_core": {"description": "发现流、详情与搜索共享真实图片主样本。", "posts": post_rows, "reactions": reactions, "comments": comments},
            "comment_thread_core": build_comment_thread_core_seed(),
            "home_feed_core": {"description": "首页关注、精选与群组三个入口的组合内容种子。", "followingFeedPostIds": current_posts[:24] or post_ids[:24], "featuredFeedPostIds": post_ids[:40], "groupFeedPostIds": [row["postId"] for row in post_rows if row["circleId"] == "fixture_circle_photo"][:12]},
            "content_detail_core": {"description": "内容详情、评论、reaction 与分享主样本。", "postIds": ["fixture_photo_001", "fixture_article_001", "fixture_video_001"], "commentIds": ["fixture_comment_photo_001"], "reactionPostIds": ["fixture_photo_001"], "shareTargets": [{"id": "fixture_share_chat_group", "type": "chat_conversation", "title": "契约周末群"}]},
            "search_core": {"description": "全局搜索与网络结果页可打开的内容种子。", "history": ["西湖晨光", "契约旅行", "城市漫步"], "resultPostIds": ["fixture_photo_001", "fixture_article_001", "fixture_video_001", "fixture_moment_001"], "networkResults": [{"id": "fixture_search_web_001", "title": "契约搜索网络结果", "url": "https://example.com"}]},
            "publish_core": {"description": "创作入口发布设置、草稿、可选圈子和主页。", "drafts": [{"id": "fixture_draft_photo", "type": "image", "body": "契约草稿内容"}], "selectableCircleIds": ["fixture_circle_photo", "fixture_circle_travel", "fixture_circle_life"], "selectableHomepageIds": ["fixture_homepage_author", "fixture_homepage_poi"]},
        },
        "scenarios": [{"id": "content_discovery_feed_basic", "title": "发现流契约种子基础加载", "type": "content_feed", "domainId": "content", "seedRefs": ["content_discovery_core", "home_feed_core", "content_detail_core", "search_core", "publish_core"], "uiExpectations": {"postIds": ["fixture_photo_001", "fixture_video_001", "fixture_article_001", "fixture_moment_001"], "textFragments": ["契约摄影师", "契约驱动的发现页文章"]}, "remoteExpectations": {"postIds": ["fixture_photo_001", "fixture_video_001", "fixture_article_001", "fixture_moment_001"], "detailPostId": "fixture_photo_001", "commentIds": ["fixture_comment_parent_001"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
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
        "schema": "user.scenario-fixtures",
        "description": "用户域 alpha/beta/gamma 共享测试场景，覆盖我的主页、作者主页、persona 与关系能力。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "user_profile_core": {"description": "当前用户、作者用户、头像、昵称与统计。", "profiles": profiles},
            "persona_core": {"description": "当前 sub-account、候选 sub-account 与 active context。", "activeSubAccountId": "fixture_persona_daily", "personas": [{"subAccountId": "fixture_persona_daily", "name": "日常我", "description": "默认日常 sub-account"}, {"subAccountId": "fixture_persona_work", "name": "工作我", "description": "工作场景 sub-account"}]},
            "profile_feed_core": {"description": "我的作品、作者作品、生活记录与评论。", "myPostIds": my_posts or ["fixture_moment_001", "fixture_photo_001"], "authorPostIds": author_posts or ["fixture_photo_001", "fixture_photo_002"], "commentIds": ["fixture_comment_photo_001"]},
            "relationship_core": {"description": "关注、互关、拉黑、可聊天、可通话能力矩阵。", "relationships": [{"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_photo", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}, {"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_friend", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}, {"sourceUserId": "fixture_user_current", "targetUserId": "fixture_user_weekend_1", "following": True, "mutualFollow": True, "blocked": False, "canChat": True, "canCall": True}]},
            "greeting_core": {
                "description": "打招呼破冰种子：一条待处理收件、一条已回复升级会话。",
                "inbox": [{"id": "fixture_greeting_pending_001", "requesterSubAccountId": "user_travel_photographer", "targetSubAccountId": "fixture_user_current", "requestMessage": "你好，看到你的川西照片很棒，想交流一下路线", "status": "pending", "source": "profile", "createdAt": "2026-06-02T08:00:00Z", "updatedAt": "2026-06-02T08:00:00Z"}],
                "outbox": [{"id": "fixture_greeting_replied_001", "requesterSubAccountId": "fixture_user_current", "targetSubAccountId": "user_street_photo", "requestMessage": "街拍作品很有味道，想请教构图", "status": "replied", "source": "profile", "promotedConversationId": "fixture_conversation_greeting_001", "createdAt": "2026-06-01T08:00:00Z", "updatedAt": "2026-06-01T09:00:00Z"}],
            },
            "subject_follow_core": {
                "description": "SubjectFollow 聚合种子：当前用户已关注的主页/圈子主体。",
                "follows": [{"personaId": "fixture_user_current", "subjectType": "homepage", "subjectId": "homepage_sight_emeishan", "state": "following", "followedAt": "2026-05-24T08:00:00Z"}, {"personaId": "fixture_user_current", "subjectType": "circle", "subjectId": "circle_sichuan_travel", "state": "following", "followedAt": "2026-05-22T08:00:00Z"}],
            },
            "contact_discovery_core": {
                "description": "通讯录哈希匹配种子；仅保存不可逆哈希和匹配后的 subAccountId，不含手机号原文。",
                "records": [{"id": "fixture_contact_discovery_001", "ownerAccountId": "fixture_user_current", "hashedPhones": ["7e6ee9eaabde53f4a704fd4f7fb8f66df56fe3e5d596bbfe3bc8af3cbf50fa02"], "matchedSubAccountIds": ["fixture_user_photo"], "status": "completed", "matchCount": 1, "expireAt": "2026-12-31T23:59:59Z", "createdAt": "2026-07-20T00:00:00Z", "completedAt": "2026-07-20T00:00:01Z"}],
            },
            "following_subject_core": {"description": "关注对象动态 strip 种子。", "items": [{"subjectId": "user_travel_photographer", "subjectType": "user", "displayName": "旅行摄影师", "avatarUrl": "media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png", "coverUrl": "", "subtitle": "刚更新了川西路线", "targetRouteId": "user_profile", "targetObjectId": "user_travel_photographer", "followedAt": "2026-05-20T08:00:00Z", "lastVisitedAt": "2026-06-01T08:00:00Z", "latestChangedAt": "2026-06-02T00:30:00Z", "unreadChangeCount": 2, "hasUnreadChanges": True, "latestChangeReason": "发布了新内容"}, {"subjectId": "circle_sichuan_travel", "subjectType": "circle", "displayName": "四川旅行圈", "avatarUrl": "", "coverUrl": "media/image/s/archived-image/post/fixture_photo_001/v1/cover.png", "subtitle": "圈内有新攻略", "targetRouteId": "circle_detail", "targetObjectId": "circle_sichuan_travel", "followedAt": "2026-05-22T08:00:00Z", "lastVisitedAt": "2026-06-02T01:00:00Z", "latestChangedAt": "2026-06-02T01:00:00Z", "unreadChangeCount": 0, "hasUnreadChanges": False, "latestChangeReason": ""}, {"subjectId": "homepage_sight_emeishan", "subjectType": "homepage", "displayName": "峨眉山", "avatarUrl": "", "coverUrl": "media/image/s/archived-image/post/fixture_photo_002/v1/cover.png", "subtitle": "地点动态有更新", "targetRouteId": "homepage_detail", "targetObjectId": "homepage_sight_emeishan", "followedAt": "2026-05-24T08:00:00Z", "lastVisitedAt": "2026-05-30T08:00:00Z", "latestChangedAt": "2026-06-01T12:20:00Z", "unreadChangeCount": 1, "hasUnreadChanges": True, "latestChangeReason": "新增问答和口碑"}]},
            "settings_core": {"description": "外观、通话设置与开发者诊断最小数据。", "appearance": {"themeMode": "system", "fontScale": 1.0}, "callSettings": {"allowVoiceCall": True, "allowVideoCall": True}, "diagnostics": [{"id": "fixture_ops_event_settings", "message": "契约设置诊断事件"}]},
        },
        "scenarios": [{"id": "user_profile_basic", "title": "用户主页与关系能力契约种子", "type": "user_profile", "domainId": "user", "seedRefs": ["user_profile_core", "persona_core", "profile_feed_core", "relationship_core", "greeting_core", "subject_follow_core", "contact_discovery_core", "following_subject_core", "settings_core"], "uiExpectations": {"userIds": ["fixture_user_current", "fixture_user_photo"], "textFragments": [FIXTURE_CURRENT_USER_DEFAULT_NICKNAME, "契约摄影师", "日常我"]}, "remoteExpectations": {"profileUserIds": ["fixture_user_current", "fixture_user_photo"], "subAccountIds": ["fixture_persona_daily", "fixture_persona_work"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def build_circle_impact(
    circle: dict[str, Any],
    member_ids: list[str],
    users_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Project verified membership facts into the Circle impact contract."""
    representative = next(
        (users_by_id[user_id] for user_id in member_ids if user_id != circle["ownerUserId"]),
        users_by_id[member_ids[0]],
    )
    circle_id = circle["circleId"]
    circle_name = circle["displayName"]
    member_count = len(member_ids)
    snapshot_id = f"{circle_id}_membership_snapshot"
    circle_target = {
        "objectType": "circle",
        "objectId": circle_id,
        "objectKind": "circle",
        "routeId": "circleDetail",
    }
    representative_target = {
        "objectType": "user",
        "objectId": representative["userId"],
        "objectKind": "person",
        "routeId": "userProfile",
    }
    representative_avatar = representative["profile"]["avatar"]["objectKey"]
    item = {
        "helpType": "relationship",
        "action": "join_circle",
        "intersectionDimension": "relationship",
        "tagRef": circle["primaryTheme"],
        "source": "circle_membership",
        "count": member_count,
        "primaryText": f"{member_count}位成员加入了{circle_name}",
        "subtitleText": "来自已验证的圈子成员关系",
        "impactId": f"{circle_id}_membership",
        "primarySpans": [
            {"text": str(member_count), "role": "count"},
            {"text": f"位成员加入了{circle_name}", "role": "plain"},
        ],
        "sampleVisuals": [
            {
                "assetKind": "avatar",
                "imageUrl": representative_avatar,
                "displayName": representative["displayName"],
                "target": representative_target,
            }
        ],
        "representativeActor": {
            "actorId": representative["userId"],
            "displayName": representative["displayName"],
            "avatarUrl": representative_avatar,
            "relationLabel": "圈子成员",
            "privacyState": "visible",
            "target": representative_target,
            "evidenceRank": 1,
            "snapshotVersion": snapshot_id,
        },
        "actionHints": [],
        "countTarget": circle_target,
        "evidenceSnapshotId": snapshot_id,
        "countObjectKind": "person",
        "propagationPath": {
            "pathKind": "personToCircle",
            "hopCount": 1,
            "secondarySpreadCount": 0,
            "summaryText": f"成员加入{circle_name}",
            "summaryTarget": circle_target,
            "nodes": [],
        },
        "iconKey": "people",
    }
    return {"circleId": circle_id, "total": member_count, "items": [item]}


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
            "tags": circle.get("displayTags") or circle["themeTags"],
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
    profile_circles = [circle for circle in circles if circle["isCoreFixture"]]
    profile_circle_ids = {circle["circleId"] for circle in profile_circles}
    profile_impacts = {
        circle["circleId"]: build_circle_impact(
            circle,
            memberships.get(circle["circleId"], circle["memberUserIds"]),
            users_by_id,
        )
        for circle in profile_circles
    }
    profile_placements = [
        {
            "circleId": post["circleRef"],
            "postId": post["postId"],
            "status": "active",
        }
        for post in posts
        if post["circleRef"] in profile_circle_ids
    ]
    profile_stats = [
        {
            "circleId": circle["circleId"],
            "memberCount": circle["stats"]["memberCount"],
            "postCount": circle["stats"]["postCount"],
            "discussionCount": circle["stats"].get("discussionCount", 0),
            "weeklyActiveCount": circle["stats"]["dailyActiveMemberCount"] * 2,
        }
        for circle in profile_circles
    ]
    photo_posts = [post["postId"] for post in posts if post["circleRef"] == "fixture_circle_photo"][:12]
    return {
        "schema": "circle.scenario-fixtures",
        "description": "圈子域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.circles 初始化 AlphaCircle typed facets。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "circle_core": {"description": "圈子列表、详情、默认群与成员共享真实图片种子。", "circles": circles_rows, "groups": groups, "members": members_doc, "files": files},
            "circle_home_feed_core": {"description": "首页群组 tab 与圈子 hub feed 所需内容映射。", "featuredCircleIds": [circle["circleId"] for circle in circles[:12]], "groupFeedPostIds": photo_posts or ["fixture_photo_001", "fixture_photo_002", "fixture_article_001", "fixture_video_001"]},
            "circle_profile_core": {"description": "圈子主页封面、统计、成员、影响与作品。", "circleIds": sorted(profile_circle_ids), "stats": profile_stats, "impacts": profile_impacts, "placements": profile_placements},
            "circle_group_chat_link_core": {"description": "圈子默认公开群与聊天会话的对齐关系。", "links": [{"circleId": circle["circleId"], "groupId": f"fixture_group_{circle_suffix(circle['circleId'])}_public", "conversationId": circle["groupConversationId"]} for circle in circles if circle["isCoreFixture"]]},
        },
        "scenarios": [{"id": "circle_list_detail_basic", "title": "圈子列表与详情契约种子", "type": "circle_list_detail", "domainId": "circle", "seedRefs": ["circle_core", "circle_home_feed_core", "circle_profile_core", "circle_group_chat_link_core"], "uiExpectations": {"circleIds": ["fixture_circle_photo", "fixture_circle_travel"], "textFragments": ["契约摄影社", "契约旅行手账"]}, "remoteExpectations": {"circleIds": ["fixture_circle_photo", "fixture_circle_travel"], "groupIds": ["fixture_group_photo_public"], "memberUserIds": ["fixture_user_owner", "fixture_user_current"], "fileIds": ["fixture_file_photo_guide"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def build_chat_doc(conversations: list[dict[str, Any]], conversation_members: dict[str, list[str]], users: list[dict[str, Any]]) -> dict[str, Any]:
    users_by_id = user_index(users)
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
            text = f"{sender['displayName']} 在 {conversation['displayName']} 中发送的共享池消息 #{seq + 1}。"
            message_id = f"{conv_id}_msg_{seq + 1:02d}"
            sender_name: str | None = sender["displayName"]
            message_type = "text"
            media_payload: dict[str, Any] | None = None
            if conv_id == "fixture_conv_direct" and seq == 1:
                text = "契约消息已送达"
            if conv_id == "fixture_conv_direct" and seq == 0:
                text = "这是一条契约聊天消息。"
                message_id = "fixture_msg_direct_1"
            if conv_id == "fixture_conv_direct" and seq == 1:
                message_id = "fixture_msg_direct_2"
            if conv_id == "fixture_conv_direct" and seq == 2:
                text = "契约图片消息"
                message_id = "fixture_msg_direct_image_1"
                message_type = "image"
                media_payload = {
                    "url": "media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
                    "thumbnailUrl": "media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
                    "mimeType": "image/png",
                    "fileName": "fixture_photo_001_cover.png",
                    "fileSizeBytes": 128000,
                    "width": 960,
                    "height": 720,
                }
            if conv_id == "fixture_conv_direct" and seq == 3:
                text = "契约视频消息"
                message_id = "fixture_msg_direct_video_1"
                message_type = "video"
                media_payload = {
                    "url": "media/video/s/archived-video/post/fixture_video_001/v1/video.mp4",
                    "thumbnailUrl": "media/image/s/archived-image/post/fixture_video_001/v1/cover.png",
                    "mimeType": "video/mp4",
                    "fileName": "fixture_video_001.mp4",
                    "fileSizeBytes": 1048576,
                    "durationMs": 93000,
                    "width": 1280,
                    "height": 720,
                }
            if conv_id == "fixture_conv_direct" and seq == 4:
                text = "契约文件消息"
                message_id = "fixture_msg_direct_file_1"
                message_type = "file"
                media_payload = {
                    "url": PRIMARY_ATTACHMENT_PUBLIC_SLICE_KEY,
                    "mimeType": "text/plain",
                    "fileName": "spec.txt",
                    "fileSizeBytes": len(PRIMARY_ATTACHMENT_BYTES),
                }
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
            if conv_id == "fixture_conv_direct" and sender_id == "fixture_user_friend":
                sender_name = None
            message = {
                "id": message_id,
                "conversationId": conv_id,
                "seq": seq + 1,
                "clientMsgId": f"{message_id}_client",
                "senderId": sender_id,
                "senderName": sender_name,
                "senderAvatar": sender["profile"]["avatar"]["objectKey"],
                "content": text,
                "type": message_type,
                "status": "sent",
                "timestamp": iso_at(1000 + idx * 2 + seq),
            }
            if media_payload:
                message.update(
                    {
                        "mediaDeliveryUrl": media_payload["url"],
                        "mediaType": message_type,
                        "mediaContentType": media_payload["mimeType"],
                        "mediaFileSizeBytes": media_payload["fileSizeBytes"],
                    }
                )
            messages.append(message)
        message_rows[conv_id] = messages
        last_message = messages[-1]
        row = {
            "id": conv_id,
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
            "lastMessageTime": last_message["timestamp"],
            "messageCount": len(messages),
            "status": "active",
            "createdAt": messages[0]["timestamp"],
            "updatedAt": last_message["timestamp"],
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
                "displayName": "契约联系人"
                if conv_id == "fixture_conv_direct"
                and member_id == "fixture_user_friend"
                else users_by_id[member_id]["displayName"],
                "avatarUrl": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
                "avatarObjectKey": users_by_id[member_id]["profile"]["avatar"]["objectKey"],
                "role": "owner" if member_id == (conversation.get("creatorId") or conversation["memberUserIds"][0]) else "member",
                "isCurrentUser": member_id == "fixture_user_current",
            }
            for member_id in conversation_members[conv_id]
        ]
        user_states.append({"id": f"fixture_state_{conv_id}_current", "userId": "fixture_user_current", "conversationId": conv_id, "readSeq": max(0, len(messages) - 1), "unreadCount": 1 if idx % 3 == 0 else 0, "mentionUnreadCount": 1 if conv_id == CORE_MENTION_CONVERSATION_ID else 0, "muted": False, "pinned": idx < 2, "updatedAt": last_message["timestamp"]})
    contacts = []
    seen = set()
    for user_id in ["fixture_user_friend", "fixture_user_weekend_1", "fixture_user_weekend_2", "fixture_user_photo", "fixture_user_travel", "fixture_user_article"] + [user["userId"] for user in users if "contact" in user["roleTags"]][:18]:
        if user_id in seen or user_id == "fixture_user_current":
            continue
        seen.add(user_id)
        user = users_by_id[user_id]
        contacts.append({"userId": user_id, "displayName": user["displayName"], "avatarUrl": user["profile"]["avatar"]["objectKey"], "relationState": "mutual" if "contact" in user["roleTags"] else "following", "source": "follow" if "contact" in user["roleTags"] else "circle", "bio": user["bio"], "avatarObjectKey": user["profile"]["avatar"]["objectKey"]})
    realtime_events = {
        "conv_001": [
            {
                "type": "MessageSent",
                "conversationId": "conv_001",
                "payload": {
                    "messageId": "fixture_rt_conv_001_msg_13",
                    "conversationId": "conv_001",
                    "seq": 13,
                    "clientMsgId": "fixture_rt_conv_001_msg_13_client",
                    "senderId": "fixture_user_friend",
                    "senderDisplayNameSnapshot": "契约联系人",
                    "senderAvatarUrlSnapshot": "media/avatar/s/archived-avatar/user/fixture_user_friend/avatar.png",
                    "type": "text",
                    "content": "Fixture Realtime 新消息：咖啡馆门口见。",
                    "timestamp": iso_at(1010),
                },
            }
        ],
        "fixture_conv_group": [
            {
                "type": "ConversationMemberAdded",
                "conversationId": "fixture_conv_group",
                "payload": {
                    "userId": "fixture_user_weekend_2",
                },
            }
        ],
    }
    return {
        "schema": "chat.scenario-fixtures",
        "description": "聊天域 alpha/beta/gamma 共享测试场景。alpha 端侧从 seedSets.conversations/messages/members 初始化 MockChatRepository。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {
            "chat_core": {"description": "聊天 inbox、详情、成员与消息共享真实图片种子。", "currentUserId": "fixture_user_current", "conversations": conversation_rows, "messages": message_rows, "members": members_rows, "userStates": user_states},
            "chat_realtime_fixture_core": {"description": "聊天实时回放 contract fixture。", "currentUserId": "fixture_user_current", "conversations": conversation_rows, "messages": message_rows, "members": members_rows, "userStates": user_states, "realtimeEvents": realtime_events},
            "chat_settings_core": {"description": "会话设置、免打扰、置顶、公告、管理员与转让候选人。", "settings": [{"conversationId": "fixture_conv_group", "muted": False, "pinned": False, "announcement": "契约群公告：周末集合时间已确认", "adminUserIds": ["fixture_user_current"], "transferCandidateUserIds": ["fixture_user_weekend_1", "fixture_user_weekend_2"]}]},
            "chat_contacts_core": {"description": "联系人 tab、圈子联系人与趣群联系人。", "contacts": contacts, "circleIds": ["fixture_circle_photo", "fixture_circle_travel", "fixture_circle_city", "fixture_circle_life"], "groupConversationIds": ["fixture_conv_group", "fixture_conv_photo_group", "fixture_conv_travel_group"]},
            "chat_group_flow_core": {"description": "建群、加人、管理页所需成员候选。", "candidateUserIds": ["fixture_user_friend", "fixture_user_weekend_1", "fixture_user_weekend_2"], "defaultGroupTitle": "契约新建群"},
        },
        "scenarios": [{"id": "chat_inbox_detail_basic", "title": "聊天 inbox 与详情契约种子", "type": "chat_inbox_detail", "domainId": "chat", "seedRefs": ["chat_core", "chat_settings_core", "chat_contacts_core", "chat_group_flow_core"], "uiExpectations": {"conversationIds": ["fixture_conv_direct", "fixture_conv_group"], "textFragments": ["契约好友", "契约周末群"]}, "remoteExpectations": {"conversationIds": ["fixture_conv_direct", "fixture_conv_group"], "contactUserIds": ["fixture_user_friend", "fixture_user_photo"]}, "environments": {"alpha": {"enabled": True, "repository": "mock"}, "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True}, "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True}}}],
    }


def main() -> int:
    ensure_primary_delivery_video()
    ensure_primary_delivery_attachment()
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
    write_json(
        USER_SCENARIOS,
        merge_owned_fixture(USER_SCENARIOS, build_user_doc(users, posts)),
    )
    content_fixture = merge_owned_fixture(
        CONTENT_SCENARIOS,
        build_content_doc(posts, circles, users),
    )
    realign_payload_counts(content_fixture)
    write_json(CONTENT_SCENARIOS, content_fixture)
    write_json(
        CIRCLE_SCENARIOS,
        merge_owned_fixture(
            CIRCLE_SCENARIOS,
            build_circle_doc(circles, memberships, users, posts),
        ),
    )
    write_json(
        CHAT_SCENARIOS,
        merge_owned_fixture(
            CHAT_SCENARIOS,
            build_chat_doc(conversations, conversation_members, users),
        ),
    )
    print(f"shared real asset pipeline synced: {USER_POOL_PATH.relative_to(ROOT)}")
    print(f"media assets written under: {MEDIA_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
