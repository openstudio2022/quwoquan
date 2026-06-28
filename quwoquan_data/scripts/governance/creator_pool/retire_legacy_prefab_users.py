#!/usr/bin/env python3
"""T4 legacy prefab user retire helper (explicit --apply only)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures"
LEGACY = FIXTURES / "user_pool.json"
CREATOR = FIXTURES / "user_pool.creator_pool.json"
MANIFEST = FIXTURES / "user_pool.manifest.json"
CUTOVER = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "prefab_cutover.yaml"


def _cutover_ready() -> bool:
    if yaml is None or not CUTOVER.is_file():
        return False
    data = yaml.safe_load(CUTOVER.read_text(encoding="utf-8")) or {}
    domains = data.get("domains") or {}
    return all((cfg or {}).get("cutover") == "done" for cfg in domains.values() if isinstance(cfg, dict))


def run_retire_legacy_prefab_users(*, apply: bool = False) -> int:
    if not _cutover_ready():
        print("[retire-legacy-prefab] BLOCK: cutover domains not all done", file=sys.stderr)
        return 1
    if not CREATOR.is_file() or not LEGACY.is_file():
        print("[retire-legacy-prefab] BLOCK: missing user pool fixtures", file=sys.stderr)
        return 1

    creator = json.loads(CREATOR.read_text(encoding="utf-8"))
    legacy = json.loads(LEGACY.read_text(encoding="utf-8"))
    merged = dict(legacy)
    merged["schemaVersion"] = "shared.avatar-user-pool/2"
    merged["description"] = (legacy.get("description") or "") + " [T4: legacy entries retired; creator_pool canonical]"
    merged["users"] = creator.get("users") or []
    merged["statistics"] = {
        **(legacy.get("statistics") or {}),
        "userCount": len(merged["users"]),
        "legacyRetiredAt": datetime.now(timezone.utc).isoformat(),
    }

    if not apply:
        preview = FIXTURES / "user_pool.t4_merged_preview.json"
        preview.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[retire-legacy-prefab] dry-run preview written: {preview}")
        return 0

    backup = FIXTURES / f"user_pool.legacy_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    shutil.copy2(LEGACY, backup)
    LEGACY.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if MANIFEST.is_file():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["legacyTrackPolicy"] = "retired"
        manifest["statistics"]["legacyUserCount"] = 0
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[retire-legacy-prefab] applied merge; backup={backup}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply retire merge")
    args = parser.parse_args(argv)
    return run_retire_legacy_prefab_users(apply=bool(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
