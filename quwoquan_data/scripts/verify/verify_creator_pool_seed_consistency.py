#!/usr/bin/env python3
"""Verify creator pool seed ↔ yaml ↔ overlay consistency + single canonical batch.

Phase 0 single-source guard: every downstream surface (seed / overlay / slice /
manifest / scenarios / seed-runner / source api_integration go test / app fallback)
must reference the SAME canonical batch and carry no residual v2_live batch strings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_FIXTURES = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures"
SEED_DIR = SERVICE_FIXTURES / "creator_pool"
PROFILES_ROOT = REPO_ROOT / "quwoquan_data/templates/creator_profiles/travel"

CANONICAL_BATCH = "travel_batch_100_v1"
CANONICAL_SEED_REFS = ["creator_travel_batch100", f"creator_travel_{CANONICAL_BATCH}_core"]
CANONICAL_SCENARIO_ID = f"creator_travel_{CANONICAL_BATCH}_core"
MEDIA_ROOT = SERVICE_FIXTURES / "media"

# Substrings that must never appear in canonical creator_pool surfaces again.
FORBIDDEN_TOKENS = ("v2_live", "batch100_v2", "batch_100_v2")

# Curated set of creator_pool single-source surfaces scanned for residual tokens.
RESIDUAL_SCAN_FILES = [
    SEED_DIR / "creator_pool_scenarios.json",
    SEED_DIR / "creator_travel_batch100.seed.json",
    SEED_DIR / f"creator_travel_{CANONICAL_BATCH}_user_overlay.json",
    SERVICE_FIXTURES / "app_alpha_seed_manifest.json",
    SERVICE_FIXTURES / "app_beta_seed_manifest.json",
    SERVICE_FIXTURES / "app_gamma_seed_manifest.json",
    SERVICE_FIXTURES / "user_pool.creator_pool.json",
    SERVICE_FIXTURES / "user_pool.manifest.json",
    SERVICE_FIXTURES / "user_pool.t4_merged_preview.json",
    SERVICE_FIXTURES / "prefab_user_migration_map.yaml",
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/prefab_cutover.yaml",
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/prefab_user_provenance.yaml",
    REPO_ROOT / "quwoquan_service/scripts/seed/run_business_beta_db_seed.py",
    REPO_ROOT / "quwoquan_service/services/user-service/tests/creator_pool_contract_fixture_seed_test.go",
    REPO_ROOT / "quwoquan_app/lib/cloud/runtime/prefab_user_resolver.dart",
    REPO_ROOT / "quwoquan_app/lib/cloud/services/user/user_repository.dart",
]

# v2 residual files/dirs that must no longer exist.
FORBIDDEN_PATHS = [
    SEED_DIR / "creator_travel_batch100_v2.seed.json",
    SEED_DIR / "creator_travel_travel_batch_100_v2_live_user_overlay.json",
    REPO_ROOT / "artifacts/creator_batch100_v2_commercial_readiness.json",
    REPO_ROOT / "quwoquan_app/test/user_acceptance/creator_travel_batch100_v2",
    PROFILES_ROOT / "travel_batch_100_v2_live",
]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _check_seed_overlay_yaml(issues: list[str]) -> None:
    seed_path = SEED_DIR / "creator_travel_batch100.seed.json"
    overlay_path = SEED_DIR / f"creator_travel_{CANONICAL_BATCH}_user_overlay.json"
    profile_dir = PROFILES_ROOT / CANONICAL_BATCH
    if not seed_path.is_file():
        issues.append(f"missing seed: {_rel(seed_path)}")
    if not overlay_path.is_file():
        issues.append(f"missing overlay: {_rel(overlay_path)}")
    if not profile_dir.is_dir():
        issues.append(f"missing profiles dir: {_rel(profile_dir)}")
    if issues:
        return
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    if seed.get("batchId") != CANONICAL_BATCH:
        issues.append(f"seed batchId {seed.get('batchId')} != {CANONICAL_BATCH}")
    seed_users = seed.get("users") or []
    overlay_users = overlay.get("users") or []
    if len(seed_users) != len(overlay_users):
        issues.append(f"user count mismatch seed={len(seed_users)} overlay={len(overlay_users)}")
    yaml_count = len(list(profile_dir.glob("*.creator.yaml")))
    if yaml_count != len(seed_users):
        issues.append(f"yaml count {yaml_count} != seed users {len(seed_users)}")
    overlay_ids = {u.get("userId") for u in overlay_users}
    for user in seed_users:
        if user.get("creatorProfileId") not in overlay_ids:
            issues.append(f"missing overlay user for {user.get('creatorProfileId')}")


def _check_manifest_refs(issues: list[str]) -> None:
    for name in ("app_alpha_seed_manifest.json", "app_beta_seed_manifest.json", "app_gamma_seed_manifest.json"):
        path = SERVICE_FIXTURES / name
        if not path.is_file():
            issues.append(f"missing manifest: {_rel(path)}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        cp = next(
            (item for item in (data.get("seedRefs") or []) if isinstance(item, dict) and item.get("domain") == "creator_pool"),
            None,
        )
        if cp is None:
            issues.append(f"{name}: missing creator_pool seedRefs entry")
            continue
        if list(cp.get("refs") or []) != CANONICAL_SEED_REFS:
            issues.append(f"{name}: creator_pool refs {cp.get('refs')} != {CANONICAL_SEED_REFS}")


def _check_scenarios(issues: list[str]) -> None:
    path = SEED_DIR / "creator_pool_scenarios.json"
    if not path.is_file():
        issues.append(f"missing scenarios: {_rel(path)}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    seed_sets = data.get("seedSets") or {}
    for ref in CANONICAL_SEED_REFS:
        if ref not in seed_sets:
            issues.append(f"creator_pool_scenarios.json missing seedSet {ref}")
    ids = {s.get("id") for s in (data.get("scenarios") or []) if isinstance(s, dict)}
    if CANONICAL_SCENARIO_ID not in ids:
        issues.append(f"creator_pool_scenarios.json missing scenario {CANONICAL_SCENARIO_ID}")


def _check_slice_and_manifest(issues: list[str]) -> None:
    slice_path = SERVICE_FIXTURES / "user_pool.creator_pool.json"
    manifest_path = SERVICE_FIXTURES / "user_pool.manifest.json"
    if slice_path.is_file():
        batch = json.loads(slice_path.read_text(encoding="utf-8")).get("batchId")
        if batch != CANONICAL_BATCH:
            issues.append(f"user_pool.creator_pool.json batchId {batch} != {CANONICAL_BATCH}")
    else:
        issues.append("missing user_pool.creator_pool.json")
    if manifest_path.is_file():
        batch = json.loads(manifest_path.read_text(encoding="utf-8")).get("batchId")
        if batch != CANONICAL_BATCH:
            issues.append(f"user_pool.manifest.json batchId {batch} != {CANONICAL_BATCH}")
    else:
        issues.append("missing user_pool.manifest.json")


def _check_seed_runner_and_go(issues: list[str]) -> None:
    runner = REPO_ROOT / "quwoquan_service/scripts/seed/run_business_beta_db_seed.py"
    if runner.is_file():
        text = runner.read_text(encoding="utf-8")
        if CANONICAL_SCENARIO_ID not in text:
            issues.append(f"seed runner missing canonical scenario {CANONICAL_SCENARIO_ID}")
    else:
        issues.append("missing run_business_beta_db_seed.py")
    go_test = REPO_ROOT / "quwoquan_service/services/user-service/tests/creator_pool_contract_fixture_seed_test.go"
    if go_test.is_file():
        if "creator_travel_batch100.seed.json" not in go_test.read_text(encoding="utf-8"):
            issues.append("go contract test does not read creator_travel_batch100.seed.json")
    else:
        issues.append("missing creator_pool_contract_fixture_seed_test.go")


def _check_content_bind(issues: list[str]) -> None:
    """Phase 3 binding truth source: creator_content.seed.json must bind real
    article/image/video posts to active batch creators via match_creator."""
    content_path = SEED_DIR / "creator_content.seed.json"
    seed_path = SEED_DIR / "creator_travel_batch100.seed.json"
    if not content_path.is_file():
        issues.append(f"missing content bind seed: {_rel(content_path)}")
        return
    if not seed_path.is_file():
        return  # already reported by _check_seed_overlay_yaml
    content = json.loads(content_path.read_text(encoding="utf-8"))
    batch_creator_ids = {
        u.get("creatorProfileId")
        for u in (json.loads(seed_path.read_text(encoding="utf-8")).get("users") or [])
    }
    if content.get("batchId") != CANONICAL_BATCH:
        issues.append(f"content seed batchId {content.get('batchId')} != {CANONICAL_BATCH}")
    if content.get("previewOnly") is not False:
        issues.append("content seed must set previewOnly=false (production binding)")
    if content.get("routedBy") != "match_creator":
        issues.append("content seed must be routedBy=match_creator")
    posts = content.get("posts") or []
    carriers = sorted(p.get("carrier") for p in posts)
    if carriers != ["article", "image", "video"]:
        issues.append(f"content seed carriers {carriers} != article/image/video")
    authors = {p.get("authorId") for p in posts}
    if len(authors) != len(posts):
        issues.append("content seed authors not distinct")
    for post in posts:
        if post.get("creatorProfileId") not in batch_creator_ids:
            issues.append(f"content post {post.get('postId')} bound to non-batch creator {post.get('creatorProfileId')}")
        for key in (post.get("authorAvatarUrl"), post.get("coverUrl")):
            if not key or not (MEDIA_ROOT / key).is_file():
                issues.append(f"content post {post.get('postId')} missing media {key}")


def _check_no_residual(issues: list[str]) -> None:
    for path in RESIDUAL_SCAN_FILES:
        if not path.is_file():
            issues.append(f"missing single-source surface: {_rel(path)}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                issues.append(f"residual '{token}' in {_rel(path)}")
    for path in FORBIDDEN_PATHS:
        if path.exists():
            issues.append(f"v2 residual must be deleted: {_rel(path)}")


def main() -> int:
    issues: list[str] = []
    _check_seed_overlay_yaml(issues)
    _check_manifest_refs(issues)
    _check_scenarios(issues)
    _check_slice_and_manifest(issues)
    _check_seed_runner_and_go(issues)
    _check_content_bind(issues)
    _check_no_residual(issues)
    if issues:
        print("[verify-creator-pool-seed-consistency] FAILED", file=sys.stderr)
        for item in issues:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        f"[verify-creator-pool-seed-consistency] PASSED canonical={CANONICAL_BATCH} "
        f"(single-source seed/overlay/slice/manifest/scenarios/seed-runner/go/app/content-bind, no v2_live residual)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
