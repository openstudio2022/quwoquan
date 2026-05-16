#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
METADATA_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
ALPHA_MANIFEST = METADATA_ROOT / "_shared" / "test_fixtures" / "app_alpha_seed_manifest.json"
ALPHA_LITE_MANIFEST = METADATA_ROOT / "_shared" / "test_fixtures" / "app_alpha_dev_lite_seed_manifest.json"

LITE_REFS: dict[str, list[str]] = {
    "assistant/test_fixtures/scenarios/assistant_scenarios.json": [
        "assistant_p0_core",
    ],
    "content/test_fixtures/scenarios/content_scenarios.json": [
        "content_discovery_core",
    ],
    "social/circle/test_fixtures/scenarios/circle_scenarios.json": [
        "circle_core",
    ],
    "messages/chat/test_fixtures/scenarios/chat_scenarios.json": [
        "chat_core",
        "chat_contacts_core",
    ],
    "user/test_fixtures/scenarios/user_scenarios.json": [
        "user_profile_core",
        "profile_feed_core",
        "relationship_core",
    ],
    "entity/test_fixtures/scenarios/entity_scenarios.json": [
        "entity_homepage_core",
    ],
    "integration/test_fixtures/scenarios/integration_scenarios.json": [
        "location_poi_core",
    ],
    "notification/test_fixtures/scenarios/notification_scenarios.json": [
        "notification_core",
    ],
    "rtc/test_fixtures/scenarios/rtc_scenarios.json": [
        "rtc_core",
    ],
}

LITE_CONTENT_POST_IDS = {
    "fixture_moment_001",
    "fixture_post_lifestyle_001",
    "fixture_photo_001",
    "fixture_photo_002",
    "fixture_post_photography_001",
    "fixture_article_001",
    "fixture_video_001",
}
LITE_CONTENT_COMMENT_IDS = {"fixture_comment_photo_001"}
LITE_USER_IDS = {
    "fixture_user_current",
    "fixture_user_photo",
    "fixture_user_travel",
    "fixture_user_article",
    "fixture_user_friend",
    "fixture_user_weekend_1",
    "fixture_user_weekend_2",
}
LITE_CIRCLE_IDS = {
    "fixture_circle_life",
    "fixture_circle_photo",
    "fixture_circle_tech",
    "fixture_circle_travel",
}
LITE_CHAT_CONVERSATION_IDS = {
    "fixture_conv_direct",
    "fixture_conv_group",
    "fixture_conv_photo_group",
    "fixture_conv_article_direct",
}
LITE_CONTACT_USER_IDS = {
    "fixture_user_friend",
    "fixture_user_weekend_1",
    "fixture_user_weekend_2",
    "fixture_user_photo",
    "fixture_user_travel",
    "fixture_user_article",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scenario_lite_path(relative_path: str) -> Path:
    source = METADATA_ROOT / relative_path
    return source.with_name(source.stem + ".lite.json")


def row_id(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def prune_seed_payload(relative_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    seed_sets = payload.get("seedSets") or {}

    if relative_path == "content/test_fixtures/scenarios/content_scenarios.json":
        seed = seed_sets["content_discovery_core"]
        seed["posts"] = [
            row for row in seed.get("posts", [])
            if row_id(row, "id", "postId") in LITE_CONTENT_POST_IDS
        ]
        seed["reactions"] = [
            row for row in seed.get("reactions", [])
            if row_id(row, "postId", "contentId", "post_id") in LITE_CONTENT_POST_IDS
        ]
        seed["comments"] = [
            row for row in seed.get("comments", [])
            if row_id(row, "id", "commentId") in LITE_CONTENT_COMMENT_IDS
            or row_id(row, "postId", "contentId", "post_id") in LITE_CONTENT_POST_IDS
        ]

    if relative_path == "user/test_fixtures/scenarios/user_scenarios.json":
        profile_seed = seed_sets["user_profile_core"]
        profile_seed["profiles"] = [
            row for row in profile_seed.get("profiles", [])
            if row_id(row, "userId", "id") in LITE_USER_IDS
        ]
        feed_seed = seed_sets["profile_feed_core"]
        feed_seed["myPostIds"] = [
            row for row in feed_seed.get("myPostIds", [])
            if str(row) in LITE_CONTENT_POST_IDS
        ]
        feed_seed["authorPostIds"] = [
            row for row in feed_seed.get("authorPostIds", [])
            if str(row) in LITE_CONTENT_POST_IDS
        ]
        feed_seed["commentIds"] = [
            row for row in feed_seed.get("commentIds", [])
            if str(row) in LITE_CONTENT_COMMENT_IDS
        ]
        relationship_seed = seed_sets["relationship_core"]
        relationship_seed["relationships"] = [
            row for row in relationship_seed.get("relationships", [])
            if row_id(row, "sourceUserId") in LITE_USER_IDS
            and row_id(row, "targetUserId") in LITE_USER_IDS
        ]

    if relative_path == "social/circle/test_fixtures/scenarios/circle_scenarios.json":
        seed = seed_sets["circle_core"]
        seed["circles"] = [
            row for row in seed.get("circles", [])
            if row_id(row, "id", "circleId") in LITE_CIRCLE_IDS
        ]
        seed["groups"] = {
            key: value
            for key, value in (seed.get("groups") or {}).items()
            if key in LITE_CIRCLE_IDS
        }
        seed["members"] = {
            key: value
            for key, value in (seed.get("members") or {}).items()
            if key in LITE_CIRCLE_IDS
        }

    if relative_path == "messages/chat/test_fixtures/scenarios/chat_scenarios.json":
        core = seed_sets["chat_core"]
        core["conversations"] = [
            row for row in core.get("conversations", [])
            if row_id(row, "conversationId", "id", "_id") in LITE_CHAT_CONVERSATION_IDS
        ]
        core["members"] = {
            key: value
            for key, value in (core.get("members") or {}).items()
            if key in LITE_CHAT_CONVERSATION_IDS
        }
        core["messages"] = {
            key: value
            for key, value in (core.get("messages") or {}).items()
            if key in LITE_CHAT_CONVERSATION_IDS
        }
        core["userStates"] = [
            row for row in core.get("userStates", [])
            if row_id(row, "conversationId") in LITE_CHAT_CONVERSATION_IDS
        ]
        contacts = seed_sets["chat_contacts_core"]
        contacts["contacts"] = [
            row for row in contacts.get("contacts", [])
            if row_id(row, "userId", "id", "contactId") in LITE_CONTACT_USER_IDS
        ]
        contacts["circleIds"] = [
            row for row in contacts.get("circleIds", [])
            if str(row) in LITE_CIRCLE_IDS
        ]
        contacts["groupConversationIds"] = [
            row for row in contacts.get("groupConversationIds", [])
            if str(row) in LITE_CHAT_CONVERSATION_IDS
        ]

    return payload


def build_lite_scenarios() -> list[str]:
    written: list[str] = []
    for relative_path, refs in LITE_REFS.items():
        source_path = METADATA_ROOT / relative_path
        payload = read_json(source_path)
        seed_sets = payload.get("seedSets") or {}
        lite_seed_sets = {
            ref: seed_sets[ref]
            for ref in refs
            if ref in seed_sets
        }
        if set(lite_seed_sets) != set(refs):
            missing = sorted(set(refs) - set(lite_seed_sets))
            raise SystemExit(f"missing lite refs in {relative_path}: {missing}")
        lite_payload = dict(payload)
        lite_payload["description"] = (
            str(payload.get("description") or "").strip()
            + " [alpha-dev-lite subset]"
        ).strip()
        lite_payload["seedSets"] = lite_seed_sets
        lite_payload = prune_seed_payload(relative_path, lite_payload)
        write_json(scenario_lite_path(relative_path), lite_payload)
        written.append(str(scenario_lite_path(relative_path).relative_to(ROOT)))
    return written


def build_lite_manifest() -> None:
    manifest = read_json(ALPHA_MANIFEST)
    seed_refs: list[dict[str, Any]] = []
    allowlist: list[str] = []
    for entry in manifest.get("seedRefs", []):
        fixture_path = str(entry.get("fixturePath") or "").strip()
        lite_refs = LITE_REFS.get(fixture_path)
        if not lite_refs:
            continue
        lite_fixture = fixture_path.replace(".json", ".lite.json")
        allowlist.append(lite_fixture)
        next_entry = dict(entry)
        next_entry["fixturePath"] = lite_fixture
        next_entry["refs"] = lite_refs
        next_entry["deliveryChannels"] = ["app-fixture-json"]
        next_entry["targetStore"] = "alpha-dev-lite:app-fixture-json"
        seed_refs.append(next_entry)

    lite_manifest = dict(manifest)
    lite_manifest["description"] = (
        "alpha-dev-lite 默认本地 mock 清单：只保留 App 调试所需核心 seedRef，"
        "服务全量 seed 请继续使用 app_alpha_seed_manifest.json。"
    )
    lite_manifest["seedRefs"] = seed_refs
    lite_manifest["appAssets"] = {
        "alphaOnlyFixtureAllowlist": allowlist,
    }
    write_json(ALPHA_LITE_MANIFEST, lite_manifest)


def main() -> int:
    written = build_lite_scenarios()
    build_lite_manifest()
    print("[alpha-lite] wrote:")
    for path in written:
        print(f"  - {path}")
    print(f"  - {ALPHA_LITE_MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
