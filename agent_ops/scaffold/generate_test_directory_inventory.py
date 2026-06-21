#!/usr/bin/env python3
"""Generate the legacy test directory inventory baseline."""

from __future__ import annotations

from pathlib import Path

import yaml

from test_directory_inventory_lib import INVENTORY_PATH, build_inventory


def main() -> int:
    inventory = build_inventory()
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INVENTORY_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            inventory,
            handle,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    print(f"[inventory] wrote {INVENTORY_PATH.relative_to(Path.cwd())}")
    for area_name, area in inventory["areas"].items():
        print(f"[inventory] {area_name}: {area['legacy_count']} legacy files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
