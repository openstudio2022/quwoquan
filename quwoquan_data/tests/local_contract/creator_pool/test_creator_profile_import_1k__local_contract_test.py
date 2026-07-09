from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _common.creator_pool.batch_policy import default_target_for_batch, expected_view_contract, segment_counts
from _common.creator_pool.io import artifacts_readiness_path
from governance.creator_pool.content_bind import CARRIERS, WORKLOAD_LANES
from governance.creator_pool.content_rollout import write_prod_rollout_dryrun

REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "quwoquan_service/contracts/metadata/_shared/test_fixtures"
CANONICAL_BATCH = "travel_photo_1k_v1"
CANONICAL_TARGET = default_target_for_batch(CANONICAL_BATCH)
CANONICAL_SEGMENTS = segment_counts(CANONICAL_BATCH, CANONICAL_TARGET)
CANONICAL_VIEWS = expected_view_contract(CANONICAL_BATCH, CANONICAL_TARGET)
SEED = FIXTURES / "creator_pool/creator_travel_photo_1k_v1.seed.json"
USER_POOL = FIXTURES / "user_pool.creator_pool.travel_photo_1k_v1.json"
USER_MANIFEST = FIXTURES / "user_pool.manifest.travel_photo_1k_v1.json"
CONTENT_BIND = FIXTURES / "creator_pool/creator_content.travel_photo_1k_v1.seed.json"
PROFILES = REPO / "quwoquan_data/templates/creator_profiles/travel/travel_photo_1k_v1"
ROLLOUT = artifacts_readiness_path("creator_content_prod_rollout_dryrun.travel_photo_1k_v1.json")
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


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_sys_creator_ids(user: dict) -> None:
    assert SYS_USER_ID.match(user["creatorProfileId"])
    assert len(user["creatorProfileId"]) <= 32
    assert user["subAccountId"] == f"{user['creatorProfileId']}_sub_01"
    assert len(user["subAccountId"]) <= 32


def test_travel_photo_1k_seed_contains_compact_profile_metadata() -> None:
    payload = _json(SEED)
    users = payload["users"]
    assert payload["batchId"] == CANONICAL_BATCH
    assert len(users) == CANONICAL_TARGET
    assert Counter(user["verticalSegment"] for user in users) == CANONICAL_SEGMENTS
    assert len({user["creatorProfileId"] for user in users}) == CANONICAL_TARGET
    assert len({user["subAccountId"] for user in users}) == CANONICAL_TARGET
    assert len({user["displayName"] for user in users}) == CANONICAL_TARGET
    assert len({user["slogan"] for user in users}) == CANONICAL_TARGET
    assert len({user["bio"] for user in users}) >= 600
    assert len(list(PROFILES.glob("*.creator.yaml"))) == CANONICAL_TARGET
    for user in users[:80]:
        _assert_sys_creator_ids(user)
        for field in ("displayName", "userHandle", "avatarPresetId", "coverPresetId", "headline", "slogan", "bio"):
            assert user.get(field), f"{user.get('creatorProfileId')} missing {field}"
        assert "ipLocation" not in user
        assert "authorId" not in user
        assert "legacyAliases" not in user
        assert "avatarObjectKey" not in user
        assert "coverObjectKey" not in user
        assert not re.search(r"\d", user["displayName"])
        text = f"{user['displayName']} {user['slogan']} {user['bio']} {user['userHandle']}"
        assert not any(token in text for token in FORBIDDEN_PROFILE_TOKENS)
    cross = [user for user in users if user["verticalSegment"] == "travel_photography_cross"]
    assert len(cross) == CANONICAL_SEGMENTS["travel_photography_cross"]
    assert all({"travel", "photography"}.issubset(set(user["verticalRefs"])) for user in cross)
    assert all(any(str(ref).startswith("Topic/旅行/") for ref in user["interestTagRefs"]) for user in cross)
    assert all(any(str(ref).startswith("Topic/摄影/") for ref in user["interestTagRefs"]) for user in cross)


def test_travel_photo_1k_user_pool_and_env_manifest_are_importable() -> None:
    user_pool = _json(USER_POOL)
    manifest = _json(USER_MANIFEST)
    assert user_pool["batchId"] == CANONICAL_BATCH
    assert user_pool["userCount"] == CANONICAL_TARGET + 1
    assert manifest["mergeRules"]["creatorPoolPath"] == "_shared/test_fixtures/user_pool.creator_pool.travel_photo_1k_v1.json"
    sample = user_pool["users"][1]
    assert sample["slogan"]
    assert "ipLocation" not in sample
    assert "authorId" not in sample
    assert "archiveAliases" not in sample
    assert sample["avatarPresetId"].startswith("avatar_")
    assert sample["coverPresetId"].startswith("cover_")
    assert sample["verticalRefs"]
    for name in ("app_alpha_seed_manifest.json", "app_beta_seed_manifest.json", "app_gamma_seed_manifest.json"):
        data = _json(FIXTURES / name)
        creator_entry = next(item for item in data["seedRefs"] if item["domain"] == "creator_pool")
        assert "creator_travel_photo_1k_v1" in creator_entry["refs"]
        assert "creator_travel_photo_1k_v1_core" in creator_entry["refs"]


def test_travel_photo_1k_content_binding_uses_new_author_ids() -> None:
    content = _json(CONTENT_BIND)
    seed = _json(SEED)
    by_id = {user["creatorProfileId"]: user for user in seed["users"]}
    assert content["batchId"] == CANONICAL_BATCH
    assert content["previewOnly"] is False
    assert len(content["posts"]) == len(CARRIERS) * len(WORKLOAD_LANES)
    assert {post["carrier"] for post in content["posts"]} == set(CARRIERS)
    assert {post["workloadLane"] for post in content["posts"]} == set(WORKLOAD_LANES)
    for post in content["posts"]:
        creator = by_id[post["creatorProfileId"]]
        assert post["authorId"] == creator["subAccountId"]
        assert post["subAccountId"] == creator["subAccountId"]
        assert post["authorDisplayName"] == creator["displayName"]
        assert post["authorAvatarObjectKey"].startswith("media/preset/avatar/")
        assert post["contentTagRefs"]
        assert post["entityRefs"]
        assert post["circleRefs"]
    write_prod_rollout_dryrun(batch_id=CANONICAL_BATCH)
    rollout = _json(ROLLOUT)
    assert rollout["batchId"] == CANONICAL_BATCH
    assert rollout["decision"] == "go"
    assert rollout["prodPurity"]["prodCarriesTestFixtures"] is False


def test_travel_photo_1k_publish_manifest_exposes_dual_view_contract() -> None:
    manifest = _json(REPO / "quwoquan_data/publish/creators/manifest.json")
    assert manifest["batchId"] == CANONICAL_BATCH
    assert manifest["totalCreators"] == CANONICAL_TARGET
    assert manifest["segmentCounts"] == CANONICAL_SEGMENTS
    assert manifest["viewCounts"] == {
        "travel": int(CANONICAL_VIEWS["travelViewCount"]),
        "photography": int(CANONICAL_VIEWS["photographyViewCount"]),
        "overlap": int(CANONICAL_VIEWS["viewOverlapCount"]),
        "overlapRate": float(CANONICAL_VIEWS["viewOverlapRate"]),
    }
