#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app/lib"
ALLOWLIST = ROOT / "specs/gates/app_network_image_policy_allowlist.yaml"
EXEMPT_PATHS = {
    "core/widgets/app_image.dart",
    "core/widgets/app_cached_network_image.dart",
}
PATTERN = re.compile(
    r"\bImage\.network\s*\(|\bNetworkImage\s*\(|\bCachedNetworkImage\s*\("
)


def _scan() -> dict[str, int]:
    current: dict[str, int] = {}
    for path in APP_LIB.rglob("*.dart"):
        relative = path.relative_to(APP_LIB).as_posix()
        if relative in EXEMPT_PATHS:
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))
        if count > 0:
            current[relative] = count
    return current


def _load() -> dict[str, int]:
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    return {
        str(item["path"]): int(item.get("maxCount", 0))
        for item in data.get("allowed", [])
    }


def _write(current: dict[str, int]) -> None:
    lines = [
        "version: 1",
        "description: Transitional baseline for pre-AppImage direct image APIs. Counts may only decrease.",
        "allowed:",
    ]
    for path, count in sorted(current.items()):
        lines.extend(
            [
                f"  - path: {path}",
                f"    maxCount: {count}",
            ]
        )
    ALLOWLIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    current = _scan()
    if args.write_baseline:
        _write(current)
        print(f"[app-network-image] wrote baseline entries={len(current)}")
        return 0

    allowed = _load()
    violations: list[str] = []
    for path in sorted(set(current) | set(allowed)):
        current_count = current.get(path, 0)
        allowed_count = allowed.get(path, 0)
        if current_count > allowed_count:
            violations.append(f"{path}: {current_count} > allowlist {allowed_count}")
        elif allowed_count > current_count:
            violations.append(
                f"{path}: stale allowlist budget {allowed_count} > current {current_count}"
            )
    if violations:
        print("[app-network-image] FAIL")
        print("\n".join(violations))
        return 2
    print(f"[app-network-image] OK entries={len(current)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
