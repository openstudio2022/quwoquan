"""Build and verify deterministic user profile media presets."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw

from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT, SERVICE_CONTRACTS_METADATA_ROOT, now_iso

AVATAR_COUNT = 24
COVER_COUNT = 26
PRESET_ROOT = PUBLISH_ROOT / "user_media" / "profile_presets"
SERVICE_MEDIA_ROOT = SERVICE_CONTRACTS_METADATA_ROOT / "_shared" / "test_fixtures" / "media"

PETAL_COLORS = {
    "welcomePetalOrange": "#FB923C",
    "welcomePetalYellow": "#FDE047",
    "welcomePetalLime": "#A3E635",
    "welcomePetalEmerald": "#34D399",
    "welcomePetalCyan": "#22D3EE",
    "welcomePetalSky": "#38BDF8",
    "welcomePetalPurple": "#A78BFA",
    "welcomePetalRose": "#FB7185",
}
BRAND_BLUE = "#2563EB"
INK = "#0F172A"
PAPER = "#F8FAFC"

AVATAR_PRESETS = (
    ("avatar_travel_wayfinder", "travel", "person_wayfinder", "illustrated_person_avatar", "welcomePetalOrange"),
    ("avatar_travel_backpacker", "travel", "person_backpacker", "illustrated_person_avatar", "welcomePetalLime"),
    ("avatar_travel_map_reader", "travel", "person_map_reader", "illustrated_person_avatar", "welcomePetalYellow"),
    ("avatar_travel_lighthouse", "travel", "coastal_lighthouse", "illustrated_landmark_avatar", "welcomePetalSky"),
    ("avatar_travel_train_window", "travel", "train_window_view", "illustrated_landmark_avatar", "welcomePetalCyan"),
    ("avatar_travel_camp_sunset", "travel", "camp_sunset", "illustrated_scenic_avatar", "welcomePetalRose"),
    ("avatar_travel_rooftop_viewer", "travel", "rooftop_viewer", "illustrated_person_avatar", "welcomePetalPurple"),
    ("avatar_travel_ferry_reader", "travel", "ferry_reader", "illustrated_person_avatar", "welcomePetalEmerald"),
    ("avatar_photo_lens_portrait", "photography", "lens_portrait", "illustrated_camera_avatar", "welcomePetalPurple"),
    ("avatar_photo_film_grain", "photography", "film_grain", "illustrated_camera_avatar", "welcomePetalOrange"),
    ("avatar_photo_viewfinder", "photography", "viewfinder_frame", "illustrated_camera_avatar", "welcomePetalSky"),
    ("avatar_photo_darkroom_profile", "photography", "darkroom_profile", "illustrated_person_avatar", "welcomePetalRose"),
    ("avatar_photo_street_frame", "photography", "street_frame", "illustrated_camera_avatar", "welcomePetalYellow"),
    ("avatar_photo_drone_mark", "photography", "drone_mark", "illustrated_camera_avatar", "welcomePetalCyan"),
    ("avatar_photo_gallery_curator", "photography", "gallery_curator", "illustrated_person_avatar", "welcomePetalLime"),
    ("avatar_photo_flash_meter", "photography", "flash_meter", "illustrated_camera_avatar", "welcomePetalEmerald"),
    ("avatar_travelphoto_mountain_guide", "travel_photography", "mountain_guide", "illustrated_person_avatar", "welcomePetalEmerald"),
    ("avatar_travelphoto_city_shooter", "travel_photography", "city_shooter", "illustrated_person_avatar", "welcomePetalSky"),
    ("avatar_travelphoto_coast_walker", "travel_photography", "coast_walker", "illustrated_person_avatar", "welcomePetalCyan"),
    ("avatar_travelphoto_heritage_observer", "travel_photography", "heritage_observer", "illustrated_landmark_avatar", "welcomePetalPurple"),
    ("avatar_travelphoto_food_visualist", "travel_photography", "food_visualist", "illustrated_person_avatar", "welcomePetalOrange"),
    ("avatar_travelphoto_mobile_creator", "travel_photography", "mobile_creator", "illustrated_person_avatar", "welcomePetalLime"),
    ("avatar_travelphoto_desert_shooter", "travel_photography", "desert_shooter", "illustrated_person_avatar", "welcomePetalYellow"),
    ("avatar_travelphoto_lake_tripod", "travel_photography", "lake_tripod", "illustrated_camera_avatar", "welcomePetalRose"),
)

COVER_PRESETS = (
    ("cover_travel_snowpeak_route", "travel", "snowpeak_route", "illustrated_scenic_cover", "welcomePetalSky"),
    ("cover_travel_desert_stars", "travel", "desert_stars", "illustrated_scenic_cover", "welcomePetalYellow"),
    ("cover_travel_coastal_lighthouse", "travel", "coastal_lighthouse", "illustrated_landmark_cover", "welcomePetalCyan"),
    ("cover_travel_forest_road", "travel", "forest_road", "illustrated_scenic_cover", "welcomePetalEmerald"),
    ("cover_travel_canyon_bridge", "travel", "canyon_bridge", "illustrated_landmark_cover", "welcomePetalOrange"),
    ("cover_travel_lake_sunrise", "travel", "lake_sunrise", "illustrated_scenic_cover", "welcomePetalRose"),
    ("cover_travel_train_window", "travel", "train_window", "illustrated_landmark_cover", "welcomePetalPurple"),
    ("cover_travel_oldtown_roofs", "travel", "oldtown_roofs", "illustrated_landmark_cover", "welcomePetalLime"),
    ("cover_photo_city_bluehour", "photography", "city_bluehour", "illustrated_photo_cover", "welcomePetalSky"),
    ("cover_photo_darkroom_contactsheet", "photography", "darkroom_contactsheet", "illustrated_photo_cover", "welcomePetalRose"),
    ("cover_photo_gallery_wall", "photography", "gallery_wall", "illustrated_photo_cover", "welcomePetalPurple"),
    ("cover_photo_studio_light", "photography", "studio_light", "illustrated_photo_cover", "welcomePetalYellow"),
    ("cover_photo_street_shadow", "photography", "street_shadow", "illustrated_photo_cover", "welcomePetalOrange"),
    ("cover_photo_aerial_grid", "photography", "aerial_grid", "illustrated_photo_cover", "welcomePetalCyan"),
    ("cover_photo_film_table", "photography", "film_table", "illustrated_photo_cover", "welcomePetalLime"),
    ("cover_photo_night_tripod", "photography", "night_tripod", "illustrated_photo_cover", "welcomePetalEmerald"),
    ("cover_travelphoto_mountain_pass", "travel_photography", "mountain_pass", "illustrated_scenic_cover", "welcomePetalSky"),
    ("cover_travelphoto_landmark_silhouette", "travel_photography", "landmark_silhouette", "illustrated_landmark_cover", "welcomePetalPurple"),
    ("cover_travelphoto_harbor_sunset", "travel_photography", "harbor_sunset", "illustrated_scenic_cover", "welcomePetalOrange"),
    ("cover_travelphoto_rice_terrace", "travel_photography", "rice_terrace", "illustrated_scenic_cover", "welcomePetalLime"),
    ("cover_travelphoto_temple_roof", "travel_photography", "temple_roof", "illustrated_landmark_cover", "welcomePetalRose"),
    ("cover_travelphoto_waterfall_mist", "travel_photography", "waterfall_mist", "illustrated_scenic_cover", "welcomePetalCyan"),
    ("cover_travelphoto_citywalk_neon", "travel_photography", "citywalk_neon", "illustrated_landmark_cover", "welcomePetalSky"),
    ("cover_travelphoto_glacier_light", "travel_photography", "glacier_light", "illustrated_scenic_cover", "welcomePetalEmerald"),
    ("cover_travelphoto_cafe_window", "travel_photography", "cafe_window", "illustrated_landmark_cover", "welcomePetalYellow"),
    ("cover_travelphoto_night_sky", "travel_photography", "night_sky", "illustrated_scenic_cover", "welcomePetalPurple"),
)


def run_media_presets_build(*, preset_set: str, dry_run: bool = False) -> dict[str, Any]:
    manifest = build_preset_manifest(preset_set)
    if dry_run:
        return {
            "presetSetId": preset_set,
            "avatars": len(manifest["avatars"]),
            "covers": len(manifest["covers"]),
            "dryRun": True,
        }
    _write_preset_assets(manifest)
    write_json(PRESET_ROOT / "manifest.json", manifest)
    return {
        "presetSetId": preset_set,
        "manifestPath": str(PRESET_ROOT / "manifest.json"),
        "avatars": len(manifest["avatars"]),
        "covers": len(manifest["covers"]),
        "dryRun": False,
    }


def run_media_presets_verify(*, preset_set: str) -> dict[str, Any]:
    manifest_path = PRESET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing media preset manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    issues = preset_manifest_issues(manifest, preset_set=preset_set)
    if issues:
        raise ValueError("media preset gate failed: " + "; ".join(issues))
    return {
        "presetSetId": preset_set,
        "avatars": len(manifest.get("avatars") or []),
        "covers": len(manifest.get("covers") or []),
        "decision": "go",
    }


def build_preset_manifest(preset_set: str) -> dict[str, Any]:
    avatars = [
        _preset_row(
            preset_id=preset_id,
            object_key=f"media/preset/avatar/{preset_id}.png",
            theme=theme,
            visual_subject=visual_subject,
            asset_kind=asset_kind,
            palette_token=palette_token,
            usage=_usage_for_theme(theme),
        )
        for preset_id, theme, visual_subject, asset_kind, palette_token in AVATAR_PRESETS
    ]
    covers = [
        _preset_row(
            preset_id=preset_id,
            object_key=f"media/preset/cover/{preset_id}.jpg",
            theme=theme,
            visual_subject=visual_subject,
            asset_kind=asset_kind,
            palette_token=palette_token,
            usage=_usage_for_theme(theme),
        )
        for preset_id, theme, visual_subject, asset_kind, palette_token in COVER_PRESETS
    ]
    return {
        "presetSetId": preset_set,
        "mediaPolicy": "system_profile_preset_id_only",
        "brandPaletteSource": "quwoquan_app WelcomeAppearance.petalColors",
        "avatars": avatars,
        "covers": covers,
        "generatedAt": now_iso(),
    }


def preset_manifest_issues(manifest: dict[str, Any], *, preset_set: str) -> list[str]:
    issues: list[str] = []
    if manifest.get("presetSetId") != preset_set:
        issues.append(f"presetSetId {manifest.get('presetSetId')} != {preset_set}")
    avatars = [row for row in (manifest.get("avatars") or []) if isinstance(row, dict)]
    covers = [row for row in (manifest.get("covers") or []) if isinstance(row, dict)]
    if len(avatars) < AVATAR_COUNT:
        issues.append(f"avatar preset count {len(avatars)} < {AVATAR_COUNT}")
    if len(covers) < COVER_COUNT:
        issues.append(f"cover preset count {len(covers)} < {COVER_COUNT}")
    _append_visual_manifest_issues(issues, avatars=avatars, covers=covers)
    seen_ids: set[str] = set()
    for row in [*avatars, *covers]:
        preset_id = str(row.get("presetId") or "")
        object_key = str(row.get("objectKey") or "")
        if not preset_id:
            issues.append("blank presetId")
        if preset_id in seen_ids:
            issues.append(f"duplicate presetId {preset_id}")
        seen_ids.add(preset_id)
        if "tp_" in preset_id:
            issues.append(f"{preset_id}: presetId must be semantic, not tp sequence")
        if not object_key.startswith("media/preset/"):
            issues.append(f"{preset_id}: objectKey must use media/preset: {object_key}")
        if not (PRESET_ROOT / _publish_asset_rel(object_key)).is_file():
            issues.append(f"{preset_id}: missing publish asset {object_key}")
        if not (SERVICE_MEDIA_ROOT / object_key).is_file():
            issues.append(f"{preset_id}: missing service fixture asset {object_key}")
    return issues


def _append_visual_manifest_issues(
    issues: list[str],
    *,
    avatars: list[dict[str, Any]],
    covers: list[dict[str, Any]],
) -> None:
    allowed_kinds = {
        "illustrated_person_avatar",
        "illustrated_landmark_avatar",
        "illustrated_scenic_avatar",
        "illustrated_camera_avatar",
        "illustrated_scenic_cover",
        "illustrated_landmark_cover",
        "illustrated_photo_cover",
    }
    required_cover_kinds = {
        "illustrated_scenic_cover",
        "illustrated_landmark_cover",
        "illustrated_photo_cover",
    }
    avatar_kinds = {str(row.get("assetKind") or "") for row in avatars}
    cover_kinds = {str(row.get("assetKind") or "") for row in covers}
    if not {"illustrated_person_avatar", "illustrated_camera_avatar"}.issubset(avatar_kinds):
        issues.append("avatar presets must include person and camera symbols")
    if not required_cover_kinds.issubset(cover_kinds):
        issues.append("cover presets must include scenic, landmark and photo covers")
    if len({row.get("visualSubject") for row in covers}) != len(covers):
        issues.append("cover visualSubject must be unique")
    for row in [*avatars, *covers]:
        preset_id = str(row.get("presetId") or "")
        if str(row.get("paletteToken") or "") not in PETAL_COLORS:
            issues.append(f"{preset_id}: missing valid petal paletteToken")
        if str(row.get("assetKind") or "") not in allowed_kinds:
            issues.append(f"{preset_id}: missing valid assetKind")
        if not str(row.get("visualSubject") or ""):
            issues.append(f"{preset_id}: missing visualSubject")


def _preset_row(
    *,
    preset_id: str,
    object_key: str,
    theme: str,
    visual_subject: str,
    asset_kind: str,
    palette_token: str,
    usage: list[str],
) -> dict[str, Any]:
    palette = _palette_for_token(palette_token)
    return {
        "presetId": preset_id,
        "objectKey": object_key,
        "theme": theme,
        "style": visual_subject,
        "visualSubject": visual_subject,
        "assetKind": asset_kind,
        "paletteToken": palette_token,
        "palette": palette,
        "usage": usage,
        "sourceHash": "sha256:"
        + hashlib.sha256(f"{preset_id}:{object_key}:{visual_subject}:{palette_token}".encode()).hexdigest(),
    }


def _palette_for_token(token: str) -> list[str]:
    accent = PETAL_COLORS[token]
    return [
        _mix(INK, accent, 0.22),
        accent,
        _mix(PAPER, accent, 0.35),
        _mix(BRAND_BLUE, accent, 0.28),
        PAPER,
    ]


def _write_preset_assets(manifest: dict[str, Any]) -> None:
    _reset_preset_asset_dirs()
    for row in manifest["avatars"]:
        path = PRESET_ROOT / _publish_asset_rel(row["objectKey"])
        _draw_avatar(path, row)
        _copy_to_service_media(path, row["objectKey"])
    for row in manifest["covers"]:
        path = PRESET_ROOT / _publish_asset_rel(row["objectKey"])
        _draw_cover(path, row)
        _copy_to_service_media(path, row["objectKey"])


def _publish_asset_rel(object_key: str) -> Path:
    parts = Path(object_key).parts
    if len(parts) >= 4 and parts[:3] == ("media", "preset", "avatar"):
        return Path("avatar") / parts[-1]
    if len(parts) >= 4 and parts[:3] == ("media", "preset", "cover"):
        return Path("cover") / parts[-1]
    return Path(object_key).name


def _usage_for_theme(theme: str) -> list[str]:
    if theme == "travel":
        return ["travel"]
    if theme == "photography":
        return ["photography"]
    return ["cross"]


def _reset_preset_asset_dirs() -> None:
    for path in (
        PRESET_ROOT / "avatar",
        PRESET_ROOT / "cover",
        SERVICE_MEDIA_ROOT / "media" / "preset" / "avatar",
        SERVICE_MEDIA_ROOT / "media" / "preset" / "cover",
    ):
        if path.exists():
            shutil.rmtree(path)


def _draw_avatar(path: Path, row: dict[str, Any]) -> None:
    palette = row["palette"]
    subject = str(row["visualSubject"])
    path.parent.mkdir(parents=True, exist_ok=True)
    img = _vertical_gradient((512, 512), palette[0], palette[3])
    draw = ImageDraw.Draw(img)
    draw.ellipse((42, 42, 470, 470), fill=palette[2])
    draw.ellipse((68, 68, 444, 444), fill=_mix(palette[2], palette[0], 0.14))
    if "lighthouse" in subject:
        _draw_avatar_lighthouse(draw, palette)
    elif "window" in subject:
        _draw_avatar_window(draw, palette)
    elif "camp" in subject:
        _draw_avatar_mountain(draw, palette, tent=True)
    elif (
        "lens" in subject
        or "film" in subject
        or "viewfinder" in subject
        or "frame" in subject
        or "drone" in subject
        or "meter" in subject
        or "tripod" in subject
    ):
        _draw_avatar_camera(draw, palette, subject)
    elif "heritage" in subject:
        _draw_avatar_arch(draw, palette)
    else:
        _draw_avatar_person(draw, palette, subject)
    img.save(path, format="PNG")


def _draw_cover(path: Path, row: dict[str, Any]) -> None:
    palette = row["palette"]
    subject = str(row["visualSubject"])
    path.parent.mkdir(parents=True, exist_ok=True)
    img = _vertical_gradient((1600, 900), palette[0], _mix(palette[3], palette[0], 0.18))
    draw = ImageDraw.Draw(img)
    _draw_sky_glow(draw, palette)
    if "contactsheet" in subject or "gallery" in subject or "studio" in subject or "film_table" in subject:
        _draw_photo_cover(draw, palette, subject)
    elif "city" in subject or "oldtown" in subject or "temple" in subject or "landmark" in subject:
        _draw_landmark_cover(draw, palette, subject)
    else:
        _draw_scenic_cover(draw, palette, subject)
    _draw_cover_frame_marks(draw, palette)
    img.save(path, format="JPEG", quality=90)


def _draw_avatar_person(draw: ImageDraw.ImageDraw, palette: list[str], subject: str) -> None:
    draw.ellipse((198, 118, 314, 234), fill=palette[1])
    draw.pieslice((154, 210, 358, 438), 200, -20, fill=palette[0])
    draw.rounded_rectangle((174, 268, 338, 336), radius=24, fill=palette[3])
    draw.rounded_rectangle((210, 256, 302, 318), radius=12, fill=palette[4])
    draw.ellipse((232, 268, 280, 316), fill=palette[0])
    if "backpack" in subject or "guide" in subject or "walker" in subject:
        draw.arc((142, 234, 222, 410), 260, 90, fill=palette[1], width=14)
        draw.arc((290, 234, 370, 410), 90, 280, fill=palette[1], width=14)
    if "map" in subject:
        draw.polygon([(122, 332), (230, 304), (230, 406), (122, 430)], fill=palette[4])
        draw.line((142, 350, 208, 336), fill=palette[1], width=5)
    if "food" in subject:
        draw.ellipse((120, 330, 232, 420), fill=palette[4])
        draw.arc((140, 348, 212, 400), 20, 340, fill=palette[1], width=8)
    if "mobile" in subject:
        draw.rounded_rectangle((330, 284, 396, 414), radius=18, fill=palette[4])
        draw.rounded_rectangle((342, 300, 384, 386), radius=8, fill=palette[0])


def _draw_avatar_camera(draw: ImageDraw.ImageDraw, palette: list[str], subject: str) -> None:
    draw.rounded_rectangle((122, 196, 390, 346), radius=38, fill=palette[0])
    draw.rounded_rectangle((168, 158, 258, 208), radius=18, fill=palette[3])
    draw.ellipse((206, 202, 334, 330), fill=palette[4])
    draw.ellipse((234, 230, 306, 302), fill=palette[1])
    draw.ellipse((254, 250, 286, 282), fill=palette[0])
    if "film" in subject:
        for x in range(108, 410, 48):
            draw.rectangle((x, 372, x + 28, 404), fill=palette[4])
    if "viewfinder" in subject or "frame" in subject:
        draw.line((120, 112, 212, 112), fill=palette[1], width=12)
        draw.line((120, 112, 120, 204), fill=palette[1], width=12)
        draw.line((392, 308, 392, 400), fill=palette[1], width=12)
        draw.line((300, 400, 392, 400), fill=palette[1], width=12)
    if "drone" in subject:
        for x, y in ((120, 134), (392, 134), (120, 400), (392, 400)):
            draw.ellipse((x - 36, y - 36, x + 36, y + 36), outline=palette[1], width=10)
            draw.line((256, 256, x, y), fill=palette[3], width=8)


def _draw_avatar_lighthouse(draw: ImageDraw.ImageDraw, palette: list[str]) -> None:
    draw.polygon([(226, 152), (286, 152), (318, 406), (194, 406)], fill=palette[0])
    draw.rounded_rectangle((206, 122, 306, 162), radius=12, fill=palette[1])
    draw.rectangle((230, 86, 282, 130), fill=palette[4])
    draw.polygon([(104, 420), (246, 318), (408, 420)], fill=palette[3])
    for y in (214, 282, 350):
        draw.line((210, y, 302, y - 18), fill=palette[1], width=10)


def _draw_avatar_window(draw: ImageDraw.ImageDraw, palette: list[str]) -> None:
    draw.rounded_rectangle((118, 116, 394, 382), radius=34, fill=palette[0])
    draw.rounded_rectangle((152, 150, 360, 348), radius=22, fill=palette[4])
    draw.line((256, 150, 256, 348), fill=palette[0], width=10)
    draw.line((152, 252, 360, 252), fill=palette[0], width=10)
    draw.polygon([(158, 340), (244, 260), (330, 340)], fill=palette[3])
    draw.ellipse((292, 174, 336, 218), fill=palette[1])


def _draw_avatar_mountain(draw: ImageDraw.ImageDraw, palette: list[str], *, tent: bool = False) -> None:
    draw.polygon([(86, 392), (214, 168), (342, 392)], fill=palette[0])
    draw.polygon([(206, 182), (252, 260), (178, 260)], fill=palette[4])
    draw.polygon([(206, 392), (332, 210), (458, 392)], fill=palette[3])
    if tent:
        draw.polygon([(166, 410), (252, 304), (338, 410)], fill=palette[1])
        draw.line((252, 304, 252, 410), fill=palette[0], width=8)


def _draw_avatar_arch(draw: ImageDraw.ImageDraw, palette: list[str]) -> None:
    draw.rectangle((132, 300, 380, 400), fill=palette[0])
    for x in (164, 256, 348):
        draw.rectangle((x - 26, 198, x + 26, 400), fill=palette[3])
        draw.ellipse((x - 48, 158, x + 48, 254), fill=palette[3])
    draw.rectangle((122, 178, 390, 218), fill=palette[1])
    draw.polygon([(116, 178), (256, 106), (396, 178)], fill=palette[0])


def _draw_sky_glow(draw: ImageDraw.ImageDraw, palette: list[str]) -> None:
    draw.ellipse((1110, 84, 1390, 364), fill=_mix(palette[1], palette[4], 0.35))
    draw.ellipse((1160, 134, 1340, 314), fill=palette[1])
    for y in (168, 248, 328):
        draw.line((80, y, 880, y - 70), fill=_mix(palette[2], palette[4], 0.24), width=3)


def _draw_scenic_cover(draw: ImageDraw.ImageDraw, palette: list[str], subject: str) -> None:
    if "waterfall" in subject:
        draw.rectangle((720, 230, 930, 900), fill=palette[2])
        draw.rectangle((774, 210, 875, 900), fill=palette[4])
        draw.polygon([(0, 790), (540, 410), (1020, 790)], fill=palette[0])
        draw.polygon([(780, 900), (1600, 420), (1600, 900)], fill=palette[3])
        return
    if "terrace" in subject:
        for i in range(8):
            y = 390 + i * 58
            draw.arc((110 + i * 70, y - 110, 1540 - i * 50, y + 240), 190, 345, fill=palette[2 if i % 2 else 1], width=16)
        return
    if "road" in subject or "route" in subject or "pass" in subject:
        draw.polygon([(0, 790), (450, 410), (850, 790)], fill=palette[0])
        draw.polygon([(430, 790), (1030, 290), (1600, 790)], fill=palette[3])
        draw.polygon([(690, 900), (820, 560), (960, 900)], fill=palette[4])
        draw.line((824, 594, 824, 900), fill=palette[1], width=8)
        return
    if "stars" in subject or "night_sky" in subject:
        for x in range(110, 1500, 140):
            y = 120 + (x * 37) % 310
            draw.ellipse((x, y, x + 8, y + 8), fill=palette[4])
        draw.polygon([(0, 780), (500, 420), (960, 780)], fill=palette[0])
        draw.polygon([(580, 780), (1180, 330), (1600, 780)], fill=palette[3])
        return
    draw.polygon([(0, 760), (440, 360), (880, 760)], fill=palette[0])
    draw.polygon([(470, 750), (1050, 250), (1600, 750)], fill=palette[3])
    draw.polygon([(990, 270), (1088, 430), (890, 430)], fill=palette[4])
    draw.rectangle((0, 760, 1600, 900), fill=palette[2])


def _draw_landmark_cover(draw: ImageDraw.ImageDraw, palette: list[str], subject: str) -> None:
    if "temple" in subject or "oldtown" in subject:
        for x in range(160, 1420, 260):
            draw.polygon([(x, 530), (x + 120, 410), (x + 260, 530)], fill=palette[1])
            draw.rectangle((x + 38, 530, x + 218, 760), fill=palette[0])
        draw.rectangle((0, 760, 1600, 900), fill=palette[3])
        return
    if "lighthouse" in subject:
        draw.polygon([(1030, 250), (1120, 250), (1170, 760), (980, 760)], fill=palette[4])
        draw.rectangle((995, 206, 1155, 262), fill=palette[1])
        draw.rectangle((1048, 142, 1102, 206), fill=palette[4])
        draw.polygon([(0, 810), (1060, 590), (1600, 810)], fill=palette[0])
        return
    if "neon" in subject or "city" in subject:
        for idx, x in enumerate(range(80, 1520, 140)):
            h = 240 + (idx * 73) % 320
            draw.rectangle((x, 760 - h, x + 92, 760), fill=palette[0 if idx % 2 else 3])
            for y in range(760 - h + 38, 740, 54):
                draw.rectangle((x + 20, y, x + 42, y + 18), fill=palette[1])
        draw.rectangle((0, 760, 1600, 900), fill=palette[2])
        return
    draw.rectangle((640, 300, 960, 760), fill=palette[0])
    draw.polygon([(560, 300), (800, 130), (1040, 300)], fill=palette[1])
    draw.arc((690, 410, 910, 720), 180, 360, fill=palette[4], width=36)
    draw.rectangle((0, 760, 1600, 900), fill=palette[3])


def _draw_photo_cover(draw: ImageDraw.ImageDraw, palette: list[str], subject: str) -> None:
    if "contactsheet" in subject or "gallery" in subject:
        for row in range(2):
            for col in range(5):
                x = 150 + col * 270
                y = 180 + row * 260
                draw.rectangle((x, y, x + 190, y + 150), fill=palette[4])
                draw.rectangle((x + 18, y + 18, x + 172, y + 132), fill=palette[(row + col) % 3])
        return
    if "studio" in subject:
        draw.polygon([(250, 900), (780, 150), (1050, 900)], fill=_mix(palette[1], palette[4], 0.45))
        draw.rectangle((1130, 180, 1240, 680), fill=palette[0])
        draw.ellipse((1040, 110, 1330, 270), fill=palette[1])
        return
    if "film_table" in subject:
        for x in range(100, 1500, 210):
            draw.rectangle((x, 300, x + 150, 640), fill=palette[0])
            for y in range(326, 620, 54):
                draw.rectangle((x + 20, y, x + 130, y + 34), fill=palette[4])
        return
    draw.rounded_rectangle((500, 265, 1100, 650), radius=54, fill=palette[0])
    draw.rounded_rectangle((610, 205, 820, 292), radius=28, fill=palette[3])
    draw.ellipse((675, 320, 925, 570), fill=palette[4])
    draw.ellipse((735, 380, 865, 510), fill=palette[1])


def _draw_cover_frame_marks(draw: ImageDraw.ImageDraw, palette: list[str]) -> None:
    color = _mix(palette[4], palette[1], 0.16)
    marks = ((72, 72, 240, 72, 72, 240), (1528, 72, 1360, 72, 1528, 240), (72, 828, 240, 828, 72, 660), (1528, 828, 1360, 828, 1528, 660))
    for x1, y1, x2, y2, x3, y3 in marks:
        draw.line((x1, y1, x2, y2), fill=color, width=9)
        draw.line((x1, y1, x3, y3), fill=color, width=9)


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    t = ImageColor.getrgb(top)
    b = ImageColor.getrgb(bottom)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        color = tuple(int(t[i] + (b[i] - t[i]) * ratio) for i in range(3))
        draw.line((0, y, w, y), fill=color)
    return img


def _mix(a: str, b: str, amount: float) -> str:
    ca = ImageColor.getrgb(a)
    cb = ImageColor.getrgb(b)
    mixed = tuple(int(ca[i] + (cb[i] - ca[i]) * amount) for i in range(3))
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def _copy_to_service_media(source: Path, object_key: str) -> None:
    target = SERVICE_MEDIA_ROOT / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
