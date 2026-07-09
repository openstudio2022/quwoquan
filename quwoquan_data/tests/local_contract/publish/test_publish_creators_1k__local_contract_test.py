from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from _common.creator_pool.batch_policy import default_target_for_batch, expected_view_contract, segment_counts

REPO = Path(__file__).resolve().parents[4]
PUBLISH_ROOT = REPO / "quwoquan_data/publish"
CREATORS_ROOT = PUBLISH_ROOT / "creators"
PRESET_MANIFEST = PUBLISH_ROOT / "user_media/profile_presets/manifest.json"
CANONICAL_BATCH = "travel_photo_1k_v1"
CANONICAL_TARGET = default_target_for_batch(CANONICAL_BATCH)
CANONICAL_SEGMENTS = segment_counts(CANONICAL_BATCH, CANONICAL_TARGET)
CANONICAL_VIEWS = expected_view_contract(CANONICAL_BATCH, CANONICAL_TARGET)
SYS_USER_ID = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}$")
FORBIDDEN_PROFILE_TOKENS = (
    "华南",
    "华北",
    "华东",
    "华中",
    "西南",
    "西北",
    "东北",
    "中国",
    "公开平台信号",
    "衍生",
    "persona",
    "archetype",
    "travel_photo",
    "batch",
)
FORBIDDEN_FIELDS = {
    "schemaVersion",
    "personaVersion",
    "sourceClonePolicy",
    "profileVersion",
    "importVersion",
    "ipLocation",
    "operations",
    "provenance",
    "sourceRegionClass",
    "regionRef",
    "authorId",
    "legacyAliases",
    "avatarObjectKey",
    "coverObjectKey",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows() -> list[dict]:
    rows: list[dict] = []
    with open(CREATORS_ROOT / "creators.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_publish_creators_is_compact_sibling_package() -> None:
    assert CREATORS_ROOT.parent == PUBLISH_ROOT
    assert (PUBLISH_ROOT / "tags").is_dir()
    files = {path.name for path in CREATORS_ROOT.iterdir()}
    assert files == {"manifest.json", "creators.jsonl"}


def test_publish_manifest_records_compact_creator_contract() -> None:
    manifest = _json(CREATORS_ROOT / "manifest.json")
    assert manifest["batchId"] == CANONICAL_BATCH
    assert manifest["totalCreators"] == CANONICAL_TARGET
    assert manifest["segmentCounts"] == CANONICAL_SEGMENTS
    assert manifest["viewCounts"] == {
        "travel": int(CANONICAL_VIEWS["travelViewCount"]),
        "photography": int(CANONICAL_VIEWS["photographyViewCount"]),
        "overlap": int(CANONICAL_VIEWS["viewOverlapCount"]),
        "overlapRate": float(CANONICAL_VIEWS["viewOverlapRate"]),
    }
    assert manifest["identityPolicy"]["systemCreatorPrefix"] == "sys_"
    assert manifest["identityPolicy"]["userIdPattern"] == "sys_{topic}_{seq4}"
    assert manifest["identityPolicy"]["subAccountIdPattern"] == "{userId}_sub_{seq2}"
    assert manifest["identityPolicy"]["thirdIdentityAllowed"] is False
    assert manifest["mediaPolicy"] == "system_profile_preset_id_only"
    assert manifest["publishFiles"] == ["manifest.json", "creators.jsonl"]
    assert manifest["qualityGates"]["sloganSimilarityGte070RatioMax"] == 0.01
    assert manifest["qualityGates"]["sloganSimilarityGte088PairMax"] == 0


def test_creators_jsonl_uses_short_sys_ids_and_clean_profile_schema() -> None:
    rows = _rows()
    assert len(rows) == CANONICAL_TARGET
    assert len({row["userId"] for row in rows}) == CANONICAL_TARGET
    assert len({row["subAccountId"] for row in rows}) == CANONICAL_TARGET
    assert len({row["displayName"] for row in rows}) == CANONICAL_TARGET
    assert Counter(row["segment"] for row in rows) == CANONICAL_SEGMENTS
    for row in rows:
        assert not (FORBIDDEN_FIELDS & row.keys())
        assert SYS_USER_ID.match(row["userId"])
        assert len(row["userId"]) <= 32
        assert row["subAccountId"] == f"{row['userId']}_sub_01"
        assert len(row["subAccountId"]) <= 32
        assert 2 <= len(row["displayName"]) <= 8
        assert not re.search(r"\d", row["displayName"])
        assert 8 <= len(row["slogan"]) <= 22
        assert 20 <= len(row["bio"]) <= 60
        profile_text = f"{row['displayName']} {row['slogan']} {row['bio']} {row['handle']}"
        assert not any(token in profile_text for token in FORBIDDEN_PROFILE_TOKENS)
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}[a-z0-9]", row["handle"])
    slogan_use = Counter(row["slogan"] for row in rows)
    assert len(slogan_use) == CANONICAL_TARGET
    assert max(slogan_use.values()) == 1


def test_creator_profile_copy_is_not_mechanical_template_reuse() -> None:
    rows = _rows()
    slogans = [row["slogan"] for row in rows]
    bios = [row["bio"] for row in rows]
    assert len(set(slogans)) == CANONICAL_TARGET
    assert len(set(bios)) >= 600
    assert Counter(slogan[:4] for slogan in slogans).most_common(1)[0][1] <= 20
    assert Counter(slogan[-4:] for slogan in slogans).most_common(1)[0][1] <= 20

    total_pairs = len(slogans) * (len(slogans) - 1) // 2
    high_070 = 0
    high_086 = 0
    high_088: list[tuple[str, str]] = []
    for idx, left in enumerate(slogans):
        for right in slogans[idx + 1 :]:
            ratio = SequenceMatcher(None, left, right).ratio()
            if ratio >= 0.70:
                high_070 += 1
            if ratio >= 0.86:
                high_086 += 1
            if ratio >= 0.88:
                high_088.append((left, right))
    assert high_070 / total_pairs < 0.01
    assert high_086 <= 20
    assert high_088 == []


def test_cross_creators_have_dual_vertical_and_topic_tags() -> None:
    cross = [row for row in _rows() if row["segment"] == "travel_photography_cross"]
    assert len(cross) == CANONICAL_SEGMENTS["travel_photography_cross"]
    for row in cross:
        assert {"travel", "photography"}.issubset(set(row["verticals"]))
        tags = [str(tag) for tag in row["tags"]]
        assert any(tag.startswith("Topic/旅行/") for tag in tags)
        assert any(tag.startswith("Topic/摄影/") for tag in tags)


def test_creator_media_uses_only_system_presets_with_share_limits() -> None:
    preset = _json(PRESET_MANIFEST)
    avatar_ids = {row["presetId"] for row in preset["avatars"]}
    cover_ids = {row["presetId"] for row in preset["covers"]}
    petal_tokens = {
        "welcomePetalOrange",
        "welcomePetalYellow",
        "welcomePetalLime",
        "welcomePetalEmerald",
        "welcomePetalCyan",
        "welcomePetalSky",
        "welcomePetalPurple",
        "welcomePetalRose",
    }
    rows = _rows()
    avatar_use = Counter(row["avatarPresetId"] for row in rows)
    cover_use = Counter(row["coverPresetId"] for row in rows)
    assert len(avatar_ids) == 24
    assert len(cover_ids) == 26
    assert set(avatar_use).issubset(avatar_ids)
    assert set(cover_use).issubset(cover_ids)
    assert all("tp_" not in preset_id for preset_id in avatar_ids | cover_ids)
    avatar_kinds = {row["assetKind"] for row in preset["avatars"]}
    cover_kinds = {row["assetKind"] for row in preset["covers"]}
    assert {"illustrated_person_avatar", "illustrated_camera_avatar"}.issubset(avatar_kinds)
    assert {
        "illustrated_scenic_cover",
        "illustrated_landmark_cover",
        "illustrated_photo_cover",
    }.issubset(cover_kinds)
    assert {row["paletteToken"] for row in preset["avatars"]}.issubset(petal_tokens)
    assert {row["paletteToken"] for row in preset["covers"]}.issubset(petal_tokens)
    assert len({row["visualSubject"] for row in preset["covers"]}) == 26
