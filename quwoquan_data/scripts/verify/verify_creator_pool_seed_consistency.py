#!/usr/bin/env python3
"""Verify the active creator trial pool has a single canonical batch.

The only active importable creator pool is ``travel_photo_1k_v1``. Historical
``travel_batch_100_v1`` and ``travel_scale10`` artifacts may exist only as private
test fixtures outside service import surfaces; they must not appear in app seed
manifests, scenario wrappers, creator slices, or canonical user-pool metadata.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.creator_pool.batch_policy import (
    default_target_for_batch,
    expected_view_contract,
    segment_counts,
    view_counts_from_segments,
)
from _common.creator_pool.constants import PHOTOGRAPHY_TOPIC_REFS, TRAVEL_TOPIC_REFS

SERVICE_FIXTURES = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures"
SEED_DIR = SERVICE_FIXTURES / "creator_pool"
PUBLISH_CREATORS = REPO_ROOT / "quwoquan_data/publish/creators"
PROFILES_ROOT = REPO_ROOT / "quwoquan_data/templates/creator_profiles/travel"
METADATA_SHARED = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared"

CANONICAL_BATCH = "travel_photo_1k_v1"
CANONICAL_SEED = "creator_travel_photo_1k_v1.seed.json"
CANONICAL_CONTENT = "creator_content.travel_photo_1k_v1.seed.json"
CANONICAL_RELATIONS = "creator_relations.travel_photo_1k_v1.seed.json"
CANONICAL_USER_POOL = f"user_pool.creator_pool.{CANONICAL_BATCH}.json"
CANONICAL_MANIFEST = f"user_pool.manifest.{CANONICAL_BATCH}.json"
CANONICAL_REFS = ["creator_travel_photo_1k_v1", "creator_travel_photo_1k_v1_core"]
CANONICAL_SCENARIO_ID = "creator_travel_photo_1k_v1_core"
CANONICAL_TARGET = default_target_for_batch(CANONICAL_BATCH)
CANONICAL_SEGMENT_COUNTS = segment_counts(CANONICAL_BATCH, CANONICAL_TARGET)
CANONICAL_VIEW_COUNTS = expected_view_contract(CANONICAL_BATCH, CANONICAL_TARGET)
PUBLISHED_INTEREST_TAGS = frozenset((*TRAVEL_TOPIC_REFS, *PHOTOGRAPHY_TOPIC_REFS))

SYS_USER_ID_RE = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}$")
SYS_SUB_ID_RE = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}_sub_[0-9]{2}$")
REGION_OR_IP_TOKENS = (
    "华南",
    "华北",
    "华东",
    "华中",
    "西南",
    "西北",
    "东北",
    "ipLocation",
    "regionRef",
    "homepage/region",
    "circle/creator/",
)
LEGACY_TOKENS = (
    "travel_batch_100_v1",
    "creator_travel_batch100",
    "creator_travel_travel_batch_100_v1_core",
    "travel_scale10",
    "creator_travel_scale10",
    "batch100_v2",
    "v2_live",
)

ACTIVE_SURFACES = [
    SEED_DIR / "creator_pool_scenarios.json",
    SEED_DIR / CANONICAL_SEED,
    SEED_DIR / CANONICAL_CONTENT,
    SEED_DIR / CANONICAL_RELATIONS,
    SEED_DIR / f"creator_travel_{CANONICAL_BATCH}_user_overlay.json",
    SERVICE_FIXTURES / "app_alpha_seed_manifest.json",
    SERVICE_FIXTURES / "app_beta_seed_manifest.json",
    SERVICE_FIXTURES / "app_gamma_seed_manifest.json",
    SERVICE_FIXTURES / CANONICAL_USER_POOL,
    SERVICE_FIXTURES / CANONICAL_MANIFEST,
    SERVICE_FIXTURES / "prefab_user_migration_map.yaml",
    METADATA_SHARED / "prefab_cutover.yaml",
    METADATA_SHARED / "prefab_user_provenance.yaml",
    REPO_ROOT / "quwoquan_data/scripts/_common/prefab_user_resolver.py",
    REPO_ROOT / "quwoquan_app/lib/cloud/runtime/prefab_user_resolver.dart",
]

FORBIDDEN_ACTIVE_PATHS = [
    SEED_DIR / "creator_travel_batch100.seed.json",
    SEED_DIR / "creator_content.seed.json",
    SEED_DIR / "creator_relations.seed.json",
    SEED_DIR / "creator_travel_scale10.seed.json",
    SEED_DIR / "creator_travel_travel_batch_100_v1_user_overlay.json",
    SERVICE_FIXTURES / "user_pool.creator_pool.json",
    SERVICE_FIXTURES / "user_pool.manifest.json",
    SERVICE_FIXTURES / "user_pool.t4_merged_preview.json",
    PROFILES_ROOT / "travel_batch_100_v1",
    PROFILES_ROOT / "travel_scale10_readiness_test",
    PROFILES_ROOT / "travel_scale10_verify_20260626",
]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _check_seed(issues: list[str]) -> None:
    path = SEED_DIR / CANONICAL_SEED
    if not path.is_file():
        issues.append(f"missing canonical seed: {_rel(path)}")
        return
    payload = _json(path)
    users = payload.get("users") or []
    if payload.get("batchId") != CANONICAL_BATCH:
        issues.append(f"seed batchId {payload.get('batchId')} != {CANONICAL_BATCH}")
    if len(users) != CANONICAL_TARGET:
        issues.append(f"seed user count {len(users)} != {CANONICAL_TARGET}")
    segment_counts: dict[str, int] = {}
    seen_users: set[str] = set()
    seen_subs: set[str] = set()
    for user in users:
        if not isinstance(user, dict):
            issues.append("seed users must be objects")
            continue
        creator_id = str(user.get("creatorProfileId") or "")
        sub_id = str(user.get("subAccountId") or "")
        segment = str(user.get("verticalSegment") or "")
        segment_counts[segment] = segment_counts.get(segment, 0) + 1
        if creator_id in seen_users:
            issues.append(f"duplicate creatorProfileId {creator_id}")
        if sub_id in seen_subs:
            issues.append(f"duplicate subAccountId {sub_id}")
        seen_users.add(creator_id)
        seen_subs.add(sub_id)
        if not SYS_USER_ID_RE.match(creator_id):
            issues.append(f"invalid creatorProfileId {creator_id}")
        if not SYS_SUB_ID_RE.match(sub_id) or sub_id != f"{creator_id}_sub_01":
            issues.append(f"invalid subAccountId {sub_id} for {creator_id}")
        for field in ("displayName", "userHandle", "avatarPresetId", "coverPresetId", "headline", "slogan", "bio"):
            if not str(user.get(field) or "").strip():
                issues.append(f"{creator_id} missing {field}")
        for tag in user.get("interestTagRefs") or []:
            if str(tag).startswith("Topic/") and str(tag) not in PUBLISHED_INTEREST_TAGS:
                issues.append(f"{creator_id} carries unpublished leaf tag {tag}")
        for forbidden in ("authorId", "legacyAliases", "archiveAliases", "avatarObjectKey", "backgroundObjectKey", "coverObjectKey", "ipLocation", "provenance", "operations"):
            if forbidden in user:
                issues.append(f"{creator_id} carries forbidden field {forbidden}")
        if segment == "travel_photography_cross":
            verticals = set(user.get("verticalRefs") or [])
            tags = [str(ref) for ref in user.get("interestTagRefs") or []]
            if not {"travel", "photography"}.issubset(verticals):
                issues.append(f"{creator_id} cross creator missing travel+photography verticals")
            if not any(ref.startswith("Topic/旅行/") for ref in tags):
                issues.append(f"{creator_id} cross creator missing travel topic")
            if not any(ref.startswith("Topic/摄影/") for ref in tags):
                issues.append(f"{creator_id} cross creator missing photography topic")
    if segment_counts != CANONICAL_SEGMENT_COUNTS:
        issues.append(f"segment counts {segment_counts} != {CANONICAL_SEGMENT_COUNTS}")


def _check_user_pool(issues: list[str]) -> None:
    pool_path = SERVICE_FIXTURES / CANONICAL_USER_POOL
    manifest_path = SERVICE_FIXTURES / CANONICAL_MANIFEST
    for path in (pool_path, manifest_path):
        if not path.is_file():
            issues.append(f"missing user-pool surface: {_rel(path)}")
            return
    pool = _json(pool_path)
    manifest = _json(manifest_path)
    users = pool.get("users") or []
    if pool.get("batchId") != CANONICAL_BATCH:
        issues.append(f"user pool batchId {pool.get('batchId')} != {CANONICAL_BATCH}")
    expected_pool_count = CANONICAL_TARGET + 1
    if len(users) != expected_pool_count or pool.get("userCount") != expected_pool_count:
        issues.append(
            f"user pool count {len(users)}/{pool.get('userCount')} != {expected_pool_count}"
        )
    slot = [u for u in users if isinstance(u, dict) and u.get("slotRole") == "currentUserVariant"]
    if len(slot) != 1 or slot[0].get("userId") != "fixture_user_current":
        issues.append("user pool must carry exactly one ordinary currentUserVariant")
    if manifest.get("batchId") != CANONICAL_BATCH:
        issues.append(f"manifest batchId {manifest.get('batchId')} != {CANONICAL_BATCH}")
    merge = manifest.get("mergeRules") if isinstance(manifest.get("mergeRules"), dict) else {}
    if merge.get("creatorPoolPath") != f"_shared/test_fixtures/{CANONICAL_USER_POOL}":
        issues.append("manifest mergeRules.creatorPoolPath must point to 1k creator pool slice")


def _check_manifest_refs(issues: list[str]) -> None:
    for name in ("app_alpha_seed_manifest.json", "app_beta_seed_manifest.json", "app_gamma_seed_manifest.json"):
        path = SERVICE_FIXTURES / name
        if not path.is_file():
            issues.append(f"missing manifest: {_rel(path)}")
            continue
        data = _json(path)
        cp = next((item for item in data.get("seedRefs") or [] if isinstance(item, dict) and item.get("domain") == "creator_pool"), None)
        if cp is None:
            issues.append(f"{name}: missing creator_pool seedRefs entry")
            continue
        if list(cp.get("refs") or []) != CANONICAL_REFS:
            issues.append(f"{name}: creator_pool refs {cp.get('refs')} != {CANONICAL_REFS}")


def _check_scenarios(issues: list[str]) -> None:
    path = SEED_DIR / "creator_pool_scenarios.json"
    if not path.is_file():
        issues.append(f"missing scenarios: {_rel(path)}")
        return
    data = _json(path)
    if set((data.get("seedSets") or {}).keys()) != set(CANONICAL_REFS):
        issues.append("creator_pool_scenarios seedSets must contain only 1k refs")
    scenarios = data.get("scenarios") or []
    ids = [s.get("id") for s in scenarios if isinstance(s, dict)]
    if ids != [CANONICAL_SCENARIO_ID]:
        issues.append(f"creator_pool_scenarios scenarios {ids} != [{CANONICAL_SCENARIO_ID}]")


def _check_content_and_relations(issues: list[str]) -> None:
    content = _json(SEED_DIR / CANONICAL_CONTENT) if (SEED_DIR / CANONICAL_CONTENT).is_file() else None
    relations = _json(SEED_DIR / CANONICAL_RELATIONS) if (SEED_DIR / CANONICAL_RELATIONS).is_file() else None
    if not content:
        issues.append(f"missing content binding: {CANONICAL_CONTENT}")
    elif content.get("batchId") != CANONICAL_BATCH or content.get("previewOnly") is not False:
        issues.append("content binding must be production 1k binding")
    if not relations:
        issues.append(f"missing relations seed: {CANONICAL_RELATIONS}")
    elif relations.get("batchId") != CANONICAL_BATCH or not relations.get("edges"):
        issues.append("relations seed must be non-empty 1k relations")


def _check_provenance_and_cutover(issues: list[str]) -> None:
    provenance = _yaml(METADATA_SHARED / "prefab_user_provenance.yaml")
    creator_track = ((provenance.get("tracks") or {}).get("creator_pool") or {})
    if creator_track.get("fixturePath") != f"_shared/test_fixtures/{CANONICAL_USER_POOL}":
        issues.append("prefab provenance creator_pool.fixturePath must point to 1k user pool")
    if creator_track.get("manifestPath") != f"_shared/test_fixtures/{CANONICAL_MANIFEST}":
        issues.append("prefab provenance creator_pool.manifestPath must point to 1k manifest")
    if (provenance.get("batchPolicy") or {}).get("canonicalBatchId") != CANONICAL_BATCH:
        issues.append("prefab provenance canonicalBatchId must be travel_photo_1k_v1")
    cutover = _yaml(METADATA_SHARED / "prefab_cutover.yaml")
    user_domain = ((cutover.get("domains") or {}).get("user") or {})
    if user_domain.get("pilotScenario") != CANONICAL_SCENARIO_ID:
        issues.append("prefab cutover user.pilotScenario must be 1k core")

    migration = _yaml(SERVICE_FIXTURES / "prefab_user_migration_map.yaml")
    if (migration.get("user_pilot") or {}).get("scenarioId") != CANONICAL_SCENARIO_ID:
        issues.append("prefab migration user_pilot scenario must be 1k core")
    mappings = ((migration.get("content_pilot_20") or {}).get("mappings") or [])
    if len(mappings) != 20:
        issues.append("prefab migration content_pilot_20 must keep 20 mappings")
    for item in mappings:
        if "authorId" in item:
            issues.append("prefab migration mappings must not carry authorId")
        creator_id = str(item.get("creatorProfileId") or "")
        sub_id = str(item.get("subAccountId") or "")
        if not SYS_USER_ID_RE.match(creator_id) or not SYS_SUB_ID_RE.match(sub_id):
            issues.append(f"prefab migration mapping uses invalid 1k ids: {creator_id}/{sub_id}")


def _check_publish_creators(issues: list[str]) -> None:
    if not PUBLISH_CREATORS.is_dir():
        issues.append("missing publish creators dir")
        return
    files = {path.relative_to(PUBLISH_CREATORS).as_posix() for path in PUBLISH_CREATORS.rglob("*") if path.is_file()}
    if files != {"manifest.json", "creators.jsonl"}:
        issues.append(f"publish creators files {sorted(files)} != ['creators.jsonl', 'manifest.json']")
    manifest_path = PUBLISH_CREATORS / "manifest.json"
    if not manifest_path.is_file():
        issues.append("publish creators manifest.json missing")
        return
    manifest = _json(manifest_path)
    if manifest.get("batchId") != CANONICAL_BATCH:
        issues.append(f"publish manifest batchId {manifest.get('batchId')} != {CANONICAL_BATCH}")
    if int(manifest.get("totalCreators") or 0) != CANONICAL_TARGET:
        issues.append(
            f"publish manifest totalCreators {manifest.get('totalCreators')} != {CANONICAL_TARGET}"
        )
    if manifest.get("segmentCounts") != CANONICAL_SEGMENT_COUNTS:
        issues.append(
            f"publish manifest segmentCounts {manifest.get('segmentCounts')} != {CANONICAL_SEGMENT_COUNTS}"
        )
    manifest_views = manifest.get("viewCounts") if isinstance(manifest.get("viewCounts"), dict) else {}
    expected_manifest_views = {
        "travel": int(CANONICAL_VIEW_COUNTS["travelViewCount"]),
        "photography": int(CANONICAL_VIEW_COUNTS["photographyViewCount"]),
        "overlap": int(CANONICAL_VIEW_COUNTS["viewOverlapCount"]),
        "overlapRate": float(CANONICAL_VIEW_COUNTS["viewOverlapRate"]),
    }
    if manifest_views != expected_manifest_views:
        issues.append(f"publish manifest viewCounts {manifest_views} != {expected_manifest_views}")
    count = 0
    segment_counter: dict[str, int] = {}
    for line in (PUBLISH_CREATORS / "creators.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        row = json.loads(line)
        segment = str(row.get("segment") or "")
        segment_counter[segment] = segment_counter.get(segment, 0) + 1
        if not SYS_USER_ID_RE.match(str(row.get("userId") or "")):
            issues.append(f"publish creator invalid userId {row.get('userId')}")
        if row.get("subAccountId") != f"{row.get('userId')}_sub_01":
            issues.append(f"publish creator invalid subAccountId {row.get('subAccountId')}")
        for tag in row.get("tags") or []:
            if str(tag).startswith("Topic/") and str(tag) not in PUBLISHED_INTEREST_TAGS:
                issues.append(f"publish creator {row.get('userId')} carries unpublished leaf tag {tag}")
        for forbidden in ("authorId", "legacyAliases", "archiveAliases", "avatarObjectKey", "coverObjectKey", "ipLocation", "provenance", "operations"):
            if forbidden in row:
                issues.append(f"publish creator {row.get('userId')} carries forbidden field {forbidden}")
    if count != CANONICAL_TARGET:
        issues.append(f"publish creators jsonl count {count} != {CANONICAL_TARGET}")
    if segment_counter != CANONICAL_SEGMENT_COUNTS:
        issues.append(f"publish creators segment counts {segment_counter} != {CANONICAL_SEGMENT_COUNTS}")
    publish_views = view_counts_from_segments(segment_counter)
    if int(publish_views["travelViewCount"]) != int(CANONICAL_VIEW_COUNTS["travelViewCount"]):
        issues.append(
            "publish creators travelViewCount "
            f"{int(publish_views['travelViewCount'])} != {int(CANONICAL_VIEW_COUNTS['travelViewCount'])}"
        )
    if int(publish_views["photographyViewCount"]) != int(CANONICAL_VIEW_COUNTS["photographyViewCount"]):
        issues.append(
            "publish creators photographyViewCount "
            f"{int(publish_views['photographyViewCount'])} != {int(CANONICAL_VIEW_COUNTS['photographyViewCount'])}"
        )
    if int(publish_views["viewOverlapCount"]) != int(CANONICAL_VIEW_COUNTS["viewOverlapCount"]):
        issues.append(
            "publish creators viewOverlapCount "
            f"{int(publish_views['viewOverlapCount'])} != {int(CANONICAL_VIEW_COUNTS['viewOverlapCount'])}"
        )


def _check_no_residuals(issues: list[str]) -> None:
    for path in FORBIDDEN_ACTIVE_PATHS:
        if path.exists():
            issues.append(f"historical active creator-pool artifact must be removed: {_rel(path)}")
    for path in ACTIVE_SURFACES:
        if not path.is_file():
            issues.append(f"missing active surface: {_rel(path)}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in LEGACY_TOKENS:
            if token in text:
                issues.append(f"legacy token '{token}' in active surface {_rel(path)}")
        for token in REGION_OR_IP_TOKENS:
            if token in text:
                issues.append(f"region/ip token '{token}' in active surface {_rel(path)}")


def main() -> int:
    issues: list[str] = []
    _check_seed(issues)
    _check_user_pool(issues)
    _check_manifest_refs(issues)
    _check_scenarios(issues)
    _check_content_and_relations(issues)
    _check_provenance_and_cutover(issues)
    _check_publish_creators(issues)
    _check_no_residuals(issues)
    if issues:
        print("[verify-creator-pool-seed-consistency] FAILED", file=sys.stderr)
        for item in issues:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        "[verify-creator-pool-seed-consistency] PASSED "
        f"canonical={CANONICAL_BATCH} (single active trial pool, no legacy region/import residuals)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
