#!/usr/bin/env python3
"""Verify legacy test directory inventory and canonical naming rules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from test_directory_inventory_lib import (
    AGENT_OPS_ROOT,
    APP_ROOT,
    DATA_ROOT,
    INVENTORY_PATH,
    LAYERS,
    ROOT,
    SERVICE_ROOT,
    build_inventory,
    iter_canonical_files,
)


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: test directory inventory checked")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def load_inventory(failures: Failures) -> dict[str, Any]:
    if not INVENTORY_PATH.exists():
        failures.add(f"missing inventory file: {INVENTORY_PATH.relative_to(ROOT)}")
        return {}
    with INVENTORY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if data.get("version") != 1:
        failures.add("inventory version must be 1")
    if not isinstance(data.get("areas"), dict):
        failures.add("inventory areas must be mapping")
    return data


def expected_prefix(area: str, layer: str) -> str:
    if area == "app":
        return f"quwoquan_app/test/{layer}/"
    if area == "service":
        return f"quwoquan_service/services/"
    if area == "data":
        return f"quwoquan_data/tests/{layer}/"
    if area == "agent_ops":
        return f"agent_ops/tests/{layer}/"
    raise ValueError(area)


def expected_suffix(layer: str, ext: str) -> str:
    return f"__{layer}_test{ext}"


def validate_entry(area: str, entry: Any, failures: Failures, seen_current: set[str], seen_target: set[str]) -> None:
    if not isinstance(entry, dict):
        failures.add(f"{area} entry must be mapping")
        return
    current_path = str(entry.get("current_path") or "").strip()
    layer = str(entry.get("layer") or "").strip()
    target_path = str(entry.get("target_path") or "").strip()
    if not current_path or not target_path:
        failures.add(f"{area} entry missing current_path/target_path: {entry!r}")
        return
    if layer not in LAYERS:
        failures.add(f"{area} {current_path} uses invalid layer {layer!r}")
        return
    if area == "service" and layer == "user_acceptance":
        failures.add(f"{area} {current_path} cannot target user_acceptance")
    if current_path in seen_current:
        failures.add(f"{area} duplicate current_path {current_path}")
    seen_current.add(current_path)
    if target_path in seen_target:
        failures.add(f"{area} duplicate target_path {target_path}")
    seen_target.add(target_path)
    if area == "service":
        if f"/tests/{layer}/" not in target_path:
            failures.add(f"{area} {current_path} target path must contain /tests/{layer}/")
    else:
        if not target_path.startswith(expected_prefix(area, layer)):
            failures.add(f"{area} {current_path} target path must start with {expected_prefix(area, layer)!r}")
    ext = Path(current_path).suffix
    if not Path(target_path).name.endswith(expected_suffix(layer, ext)):
        failures.add(
            f"{area} {current_path} target file must end with {expected_suffix(layer, ext)!r}, got {Path(target_path).name!r}"
        )
    if not (ROOT / current_path).exists():
        failures.add(f"{area} current path missing on disk: {current_path}")


def validate_inventory_contents(inventory: dict[str, Any], failures: Failures) -> None:
    generated = build_inventory()
    areas = inventory.get("areas") or {}
    expected_areas = generated.get("areas") or {}
    for area_name, generated_area in expected_areas.items():
        inventory_area = areas.get(area_name)
        if not isinstance(inventory_area, dict):
            failures.add(f"missing area {area_name} in inventory")
            continue
        entries = inventory_area.get("entries")
        if not isinstance(entries, list):
            failures.add(f"{area_name} entries must be list")
            continue
        generated_entries = generated_area.get("entries") or []
        generated_by_current = {entry["current_path"]: entry for entry in generated_entries}
        inventory_by_current = {entry["current_path"]: entry for entry in entries if isinstance(entry, dict) and entry.get("current_path")}

        missing = sorted(set(generated_by_current) - set(inventory_by_current))
        extra = sorted(set(inventory_by_current) - set(generated_by_current))
        if missing:
            failures.add(f"{area_name} inventory missing {len(missing)} legacy files; e.g. {missing[0]}")
        if extra:
            failures.add(f"{area_name} inventory has stale entries; e.g. {extra[0]}")

        seen_current: set[str] = set()
        seen_target: set[str] = set()
        for entry in entries:
            validate_entry(area_name, entry, failures, seen_current, seen_target)


def validate_canonical_files(failures: Failures) -> None:
    for area, path, layer in iter_canonical_files():
        if not path.name.endswith(expected_suffix(layer, path.suffix)):
            failures.add(
                f"{path.relative_to(ROOT)} in canonical root must end with {expected_suffix(layer, path.suffix)!r}"
            )


def main() -> int:
    failures = Failures()
    inventory = load_inventory(failures)
    if inventory:
        validate_inventory_contents(inventory, failures)
    validate_canonical_files(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
