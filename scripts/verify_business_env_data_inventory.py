#!/usr/bin/env python3
"""Verify business env data inventory seedRefs are backed by manifests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "specs" / "gates" / "business_env_data_inventory.md"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
MANIFESTS = [
    METADATA / "_shared" / "test_fixtures" / "app_alpha_seed_manifest.json",
    METADATA / "_shared" / "test_fixtures" / "app_beta_seed_manifest.json",
    METADATA / "_shared" / "test_fixtures" / "app_gamma_seed_manifest.json",
]


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def manifest_seed_refs() -> set[str]:
    refs: set[str] = set()
    for path in MANIFESTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("seedRefs", []):
            refs.update(str(ref) for ref in item.get("refs", []))
    return refs


def inventory_seed_refs() -> set[str]:
    text = INVENTORY.read_text(encoding="utf-8")
    refs: set[str] = set()
    for line in text.splitlines():
        if "|" not in line or "_core" not in line:
            continue
        if line.startswith("|---") or line.startswith("| 范围"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        for raw in re.findall(r"`([^`]+)`", cells[-1]):
            token = raw.strip()
            if token.endswith("_core"):
                refs.add(token)
    return refs


def main() -> int:
    if not INVENTORY.is_file():
        fail(f"missing inventory: {INVENTORY.relative_to(ROOT)}")
    inventory_refs = inventory_seed_refs()
    manifest_refs = manifest_seed_refs()
    missing = sorted(ref for ref in inventory_refs if ref not in manifest_refs)
    if missing:
        fail(f"inventory seedRefs missing from manifests: {missing}")
    print(f"[verify] OK: business env data inventory ({len(inventory_refs)} seedRefs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
