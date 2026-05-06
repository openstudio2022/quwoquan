#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METADATA_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA_ROOT / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
GAMMA_MANIFEST = SHARED / "app_gamma_seed_manifest.json"
GAMMA_MEDIA_BUNDLE = ROOT / "deploy" / "shared" / "gamma_curated_media_bundle.json"

CONTENT_SCENARIO = "content/test_fixtures/scenarios/content_scenarios.json"
USER_SCENARIO = "user/test_fixtures/scenarios/user_scenarios.json"
CIRCLE_SCENARIO = "social/circle/test_fixtures/scenarios/circle_scenarios.json"
CHAT_SCENARIO = "messages/chat/test_fixtures/scenarios/chat_scenarios.json"

CURATED_REFS: dict[str, list[str]] = {
    CONTENT_SCENARIO: [
        "content_discovery_core",
    ],
    USER_SCENARIO: [
        "user_profile_core",
        "persona_core",
        "profile_feed_core",
        "relationship_core",
    ],
    CIRCLE_SCENARIO: [
        "circle_core",
        "circle_group_chat_link_core",
    ],
    CHAT_SCENARIO: [
        "chat_core",
        "chat_contacts_core",
        "chat_group_flow_core",
    ],
}

CURATED_CONTENT_POST_IDS = {
    "fixture_moment_001",
    "fixture_post_lifestyle_001",
    "fixture_photo_001",
    "fixture_photo_002",
    "fixture_post_photography_001",
    "fixture_article_001",
    "fixture_video_001",
    "fixture_post_travel_001",
    "fixture_post_citywalk_001",
    "fixture_post_tech_001",
    "fixture_post_outdoor_001",
}
CURATED_CONTENT_COMMENT_IDS = {"fixture_comment_photo_001"}
CURATED_USER_IDS = {
    "fixture_user_current",
    "fixture_user_photo",
    "fixture_user_travel",
    "fixture_user_video",
    "fixture_user_article",
    "fixture_user_friend",
    "fixture_user_weekend_1",
    "fixture_user_weekend_2",
    "fixture_user_owner",
    "fixture_user_travel_owner",
    "fixture_user_commenter",
    "fixture_user_travel_01",
    "fixture_user_citywalk_01",
    "fixture_user_tech_01",
    "fixture_user_outdoor_01",
}
CURATED_CIRCLE_IDS = {
    "fixture_circle_life",
    "fixture_circle_photo",
    "fixture_circle_tech",
    "fixture_circle_travel",
    "fixture_circle_food",
    "fixture_circle_city",
    "fixture_circle_travel_01",
    "fixture_circle_citywalk_01",
    "fixture_circle_tech_01",
    "fixture_circle_outdoor_01",
}
CURATED_CHAT_CONVERSATION_IDS = {
    "fixture_conv_direct",
    "fixture_conv_group",
    "fixture_conv_photo_group",
    "fixture_conv_article_direct",
}
CURATED_CONTACT_USER_IDS = {
    "fixture_user_friend",
    "fixture_user_weekend_1",
    "fixture_user_weekend_2",
    "fixture_user_photo",
    "fixture_user_travel",
    "fixture_user_article",
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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def scenario_curated_path(relative_path: str) -> Path:
    source = METADATA_ROOT / relative_path
    return source.with_name(source.stem + ".gamma-curated.json")


def row_id(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def prune_seed_payload(relative_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    seed_sets = payload.get("seedSets") or {}

    if relative_path == CONTENT_SCENARIO:
        seed = seed_sets.get("content_discovery_core") or {}
        seed["posts"] = [
            row for row in seed.get("posts", [])
            if row_id(row, "id", "postId") in CURATED_CONTENT_POST_IDS
        ]
        seed["reactions"] = [
            row for row in seed.get("reactions", [])
            if row_id(row, "postId", "contentId", "post_id") in CURATED_CONTENT_POST_IDS
        ]
        seed["comments"] = [
            row for row in seed.get("comments", [])
            if row_id(row, "id", "commentId") in CURATED_CONTENT_COMMENT_IDS
            or row_id(row, "postId", "contentId", "post_id") in CURATED_CONTENT_POST_IDS
        ]

    if relative_path == USER_SCENARIO:
        profile_seed = seed_sets.get("user_profile_core") or {}
        profile_seed["profiles"] = [
            row for row in profile_seed.get("profiles", [])
            if row_id(row, "userId", "id") in CURATED_USER_IDS
        ]
        feed_seed = seed_sets.get("profile_feed_core") or {}
        feed_seed["myPostIds"] = [
            row for row in feed_seed.get("myPostIds", [])
            if str(row) in CURATED_CONTENT_POST_IDS
        ]
        feed_seed["authorPostIds"] = [
            row for row in feed_seed.get("authorPostIds", [])
            if str(row) in CURATED_CONTENT_POST_IDS
        ]
        feed_seed["commentIds"] = [
            row for row in feed_seed.get("commentIds", [])
            if str(row) in CURATED_CONTENT_COMMENT_IDS
        ]
        relationship_seed = seed_sets.get("relationship_core") or {}
        relationship_seed["relationships"] = [
            row for row in relationship_seed.get("relationships", [])
            if row_id(row, "sourceUserId") in CURATED_USER_IDS
            and row_id(row, "targetUserId") in CURATED_USER_IDS
        ]

    if relative_path == CIRCLE_SCENARIO:
        seed = seed_sets.get("circle_core") or {}
        seed["circles"] = [
            row for row in seed.get("circles", [])
            if row_id(row, "id", "circleId") in CURATED_CIRCLE_IDS
        ]
        seed["groups"] = {
            key: value
            for key, value in (seed.get("groups") or {}).items()
            if key in CURATED_CIRCLE_IDS
        }
        seed["members"] = {
            key: value
            for key, value in (seed.get("members") or {}).items()
            if key in CURATED_CIRCLE_IDS
        }
        seed["files"] = {
            key: value
            for key, value in (seed.get("files") or {}).items()
            if key in CURATED_CIRCLE_IDS
        }
        link_seed = seed_sets.get("circle_group_chat_link_core") or {}
        link_seed["links"] = [
            row for row in link_seed.get("links", [])
            if row_id(row, "circleId") in CURATED_CIRCLE_IDS
        ]

    if relative_path == CHAT_SCENARIO:
        core = seed_sets.get("chat_core") or {}
        core["conversations"] = [
            row for row in core.get("conversations", [])
            if row_id(row, "conversationId", "id", "_id") in CURATED_CHAT_CONVERSATION_IDS
        ]
        core["members"] = {
            key: value
            for key, value in (core.get("members") or {}).items()
            if key in CURATED_CHAT_CONVERSATION_IDS
        }
        core["messages"] = {
            key: value
            for key, value in (core.get("messages") or {}).items()
            if key in CURATED_CHAT_CONVERSATION_IDS
        }
        core["userStates"] = [
            row for row in core.get("userStates", [])
            if row_id(row, "conversationId") in CURATED_CHAT_CONVERSATION_IDS
        ]
        contacts = seed_sets.get("chat_contacts_core") or {}
        contacts["contacts"] = [
            row for row in contacts.get("contacts", [])
            if row_id(row, "userId", "id", "contactId") in CURATED_CONTACT_USER_IDS
        ]
        contacts["circleIds"] = [
            row for row in contacts.get("circleIds", [])
            if str(row) in CURATED_CIRCLE_IDS
        ]
        contacts["groupConversationIds"] = [
            row for row in contacts.get("groupConversationIds", [])
            if str(row) in CURATED_CHAT_CONVERSATION_IDS
        ]
        group_flow = seed_sets.get("chat_group_flow_core") or {}
        group_flow["candidateUserIds"] = [
            row for row in group_flow.get("candidateUserIds", [])
            if str(row) in CURATED_CONTACT_USER_IDS
        ]

    return payload


def build_curated_scenarios() -> list[str]:
    written: list[str] = []
    for relative_path, refs in CURATED_REFS.items():
        source_path = METADATA_ROOT / relative_path
        payload = read_json(source_path)
        seed_sets = payload.get("seedSets") or {}
        curated_seed_sets = {
            ref: seed_sets[ref]
            for ref in refs
            if ref in seed_sets
        }
        if set(curated_seed_sets) != set(refs):
            missing = sorted(set(refs) - set(curated_seed_sets))
            raise SystemExit(f"missing gamma curated refs in {relative_path}: {missing}")
        curated_payload = dict(payload)
        curated_payload["description"] = (
            str(payload.get("description") or "").strip()
            + " [gamma-curated subset]"
        ).strip()
        curated_payload["seedSets"] = curated_seed_sets
        curated_payload = prune_seed_payload(relative_path, curated_payload)
        scenarios = []
        for item in curated_payload.get("scenarios") or []:
            next_item = dict(item)
            next_item["seedRefs"] = [ref for ref in item.get("seedRefs") or [] if ref in refs]
            scenarios.append(next_item)
        curated_payload["scenarios"] = scenarios
        destination = scenario_curated_path(relative_path)
        write_json(destination, curated_payload)
        written.append(str(destination.relative_to(ROOT)))
    return written


def build_gamma_manifest() -> dict[str, Any]:
    manifest = read_json(GAMMA_MANIFEST)
    seed_refs: list[dict[str, Any]] = []
    for entry in manifest.get("seedRefs", []):
        fixture_path = str(entry.get("fixturePath") or "").strip()
        curated_refs = CURATED_REFS.get(fixture_path)
        if curated_refs is None:
            seed_refs.append(dict(entry))
            continue
        next_entry = dict(entry)
        next_entry["fixturePath"] = fixture_path.replace(".json", ".gamma-curated.json")
        next_entry["refs"] = curated_refs
        seed_refs.append(next_entry)
    next_manifest = dict(manifest)
    next_manifest["description"] = (
        "gamma 云侧精简清单：当前 gamma 只装载约 100 图内的 curated 业务子集，"
        "alpha/beta 继续保持全量共享池。"
    )
    next_manifest["seedRefs"] = seed_refs
    next_manifest["appAssets"] = {"alphaOnlyFixtureAllowlist": []}
    return next_manifest


def walk_media_refs(value: Any, field_name: str = "") -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            refs.extend(walk_media_refs(nested, str(key)))
    elif isinstance(value, list):
        for nested in value:
            refs.extend(walk_media_refs(nested, field_name))
    elif isinstance(value, str):
        lower = field_name.lower()
        looks_like_media_field = (
            field_name in MEDIA_FIELD_NAMES
            or field_name.endswith("ObjectKey")
            or lower in {"mediaurls", "imageurls", "mediaobjectkeys", "imageobjectkeys"}
        )
        if looks_like_media_field and value.startswith("media/"):
            refs.append(value)
    return refs


def build_media_bundle(curated_paths: list[str]) -> dict[str, Any]:
    object_keys = sorted(
        {
            ref
            for relative_path in curated_paths
            for ref in walk_media_refs(read_json(ROOT / relative_path))
        }
    )
    media_objects: list[dict[str, Any]] = []
    image_count = 0
    for object_key in object_keys:
        path = MEDIA_ROOT / object_key
        if not path.is_file():
            raise SystemExit(f"missing curated media object: {path.relative_to(ROOT)}")
        raw = path.read_bytes()
        mime_type = "image/png"
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif path.suffix.lower() == ".webp":
            mime_type = "image/webp"
        elif path.suffix.lower() == ".mp4":
            mime_type = "video/mp4"
        if mime_type.startswith("image/"):
            image_count += 1
        media_objects.append(
            {
                "objectKey": object_key,
                "relativePath": str(path.relative_to(ROOT)),
                "sourceHash": sha256_bytes(raw),
                "mimeType": mime_type,
                "sizeBytes": len(raw),
            }
        )
    if image_count > 100:
        raise SystemExit(f"gamma curated image count exceeds 100: {image_count}")
    return {
        "schemaVersion": "gamma-curated-media-bundle.v1",
        "environment": "gamma",
        "selectionProfile": "gamma-curated-core-100",
        "maxImageObjectCount": 100,
        "imageObjectCount": image_count,
        "totalObjectCount": len(media_objects),
        "mediaObjects": media_objects,
    }


def sync_media_root(bundle: dict[str, Any], output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for item in bundle.get("mediaObjects") or []:
        object_key = str(item.get("objectKey") or "").strip()
        if not object_key:
            continue
        source = MEDIA_ROOT / object_key
        target = output_root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-media-root",
        default="",
        help="Optional directory that receives the curated media files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    curated_paths = build_curated_scenarios()
    gamma_manifest = build_gamma_manifest()
    write_json(GAMMA_MANIFEST, gamma_manifest)
    bundle = build_media_bundle(curated_paths)
    write_json(GAMMA_MEDIA_BUNDLE, bundle)
    if args.output_media_root.strip():
        output_root = Path(args.output_media_root)
        if not output_root.is_absolute():
            output_root = ROOT / output_root
        sync_media_root(bundle, output_root)
    print(
        json.dumps(
            {
                "status": "ok",
                "gammaManifest": str(GAMMA_MANIFEST.relative_to(ROOT)),
                "curatedScenarios": curated_paths,
                "mediaBundle": str(GAMMA_MEDIA_BUNDLE.relative_to(ROOT)),
                "imageObjectCount": bundle["imageObjectCount"],
                "totalObjectCount": bundle["totalObjectCount"],
                "outputMediaRoot": args.output_media_root or None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
