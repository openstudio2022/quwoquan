#!/usr/bin/env python3
"""Prefab user provenance gate: block new legacy fixture_user_* references."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST = REPO_ROOT / "specs" / "gates" / "prefab_user_fixture_allowlist.yaml"
PROVENANCE = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "prefab_user_provenance.yaml"
MANIFEST = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "user_pool.manifest.json"
CREATOR_SLICE = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "user_pool.creator_pool.json"
MIGRATION_MAP = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "prefab_user_migration_map.yaml"
CUTOVER = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "prefab_cutover.yaml"

FIXTURE_USER_RE = re.compile(r"fixture_user_[a-z0-9_]+")
CORE_PRESET_RE = re.compile(r"CORE_USER_PRESETS\s*=")

SCAN_ROOTS = [
    REPO_ROOT / "quwoquan_service" / "contracts" / "metadata",
    REPO_ROOT / "quwoquan_app" / "lib",
    REPO_ROOT / "quwoquan_data" / "scripts",
    REPO_ROOT / "quwoquan_data" / "templates",
]


def _load_allowlist() -> tuple[set[str], set[str]]:
    if yaml is None or not ALLOWLIST.is_file():
        return set(), set()
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    legacy = set(data.get("legacyUserIds") or [])
    presets = set(data.get("coreUserPresets") or [])
    return legacy, presets


def _scan_fixture_user_refs() -> set[str]:
    found: set[str] = set()
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".yaml", ".yml", ".json", ".dart", ".py", ".go"}:
                continue
            if any(part in path.parts for part in ("vendor", ".gradle", "generated")):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in {
                "quwoquan_data/scripts/verify/verify_prefab_user_provenance.py",
                "specs/gates/prefab_user_fixture_allowlist.yaml",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found.update(FIXTURE_USER_RE.findall(text))
    return found


def _scan_core_user_presets() -> set[str]:
    pipeline = REPO_ROOT / "quwoquan_service" / "scripts" / "seed" / "shared_pool_real_asset_pipeline.py"
    if not pipeline.is_file():
        return set()
    text = pipeline.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r'"fixture_user_[^"]+"', text))


def main() -> int:
    issues: list[str] = []
    for required in (PROVENANCE, ALLOWLIST):
        if not required.is_file():
            issues.append(f"missing required metadata: {required.relative_to(REPO_ROOT)}")

    allow_legacy, allow_presets = _load_allowlist()
    found_legacy = _scan_fixture_user_refs()
    found_presets = {p.strip('"') for p in _scan_core_user_presets()}

    new_legacy = sorted(found_legacy - allow_legacy)
    new_presets = sorted(found_presets - allow_presets)
    if new_legacy:
        issues.append(f"new fixture_user_* references ({len(new_legacy)}): {new_legacy[:10]}")
    if new_presets:
        issues.append(f"new CORE_USER_PRESETS entries: {new_presets}")

    if CREATOR_SLICE.is_file() and MANIFEST.is_file():
        creator = json.loads(CREATOR_SLICE.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        users = creator.get("users") or []
        if len(users) < 101:
            issues.append(f"creator slice expects 101 users (100 authors + currentUserVariant), got {len(users)}")
        slot_roles = [u.get("slotRole") for u in users if isinstance(u, dict)]
        if "currentUserVariant" not in slot_roles:
            issues.append("creator slice missing currentUserVariant slot")
        if manifest.get("currentUserVariant", {}).get("subAccountId") is None:
            issues.append("manifest missing currentUserVariant.subAccountId")
    else:
        issues.append("T1 artifacts missing: user_pool.creator_pool.json or user_pool.manifest.json")

    for optional in (MIGRATION_MAP, CUTOVER):
        if not optional.is_file():
            issues.append(f"missing migration/cutover metadata: {optional.relative_to(REPO_ROOT)}")

    if issues:
        print("[verify-prefab-user-provenance] FAILED", file=sys.stderr)
        for item in issues:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        f"[verify-prefab-user-provenance] PASSED "
        f"(allowlist legacy={len(allow_legacy)} presets={len(allow_presets)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
