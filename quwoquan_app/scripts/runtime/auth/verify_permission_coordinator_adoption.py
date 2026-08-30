#!/usr/bin/env python3
"""Enforce AppPermissionCoordinator as the only settings-opening owner.

Business/UI/platform gateway code must use AppPermissionCoordinator.openSettings()
so settings-return, suppression and feedback semantics stay on one path. The
coordinator itself owns the sole raw permission_handler ``openAppSettings``
reference; there is intentionally no compatibility allowlist.
"""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
APP_LIB = ROOT / "quwoquan_app" / "lib"
COORDINATOR_PATH = "runtime/platform/permissions/app_permission_coordinator.dart"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openAppSettings", re.compile(r"\bopenAppSettings\b")),
    (
        "geolocator_open_settings",
        re.compile(r"\bGeolocator\s*\.\s*openAppSettings\s*\("),
    ),
    (
        "plugin_permissions_open_settings",
        re.compile(r"\.\s*permissions\s*\.\s*openSettings\s*\("),
    ),
]


def _scan() -> set[tuple[str, str]]:
    hits: set[tuple[str, str]] = set()
    for path in APP_LIB.rglob("*.dart"):
        rel = path.relative_to(APP_LIB).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for kind, rx in PATTERNS:
            if rx.search(text):
                hits.add((rel, kind))
    return hits


def main() -> int:
    hits = _scan()
    owner_hits = sorted(kind for rel, kind in hits if rel == COORDINATOR_PATH)
    violations = [
        f"{rel} ({kind})"
        for rel, kind in sorted(hits)
        if rel != COORDINATOR_PATH
    ]

    if owner_hits != ["openAppSettings"]:
        print(
            "FAIL: permission coordinator must own exactly one raw "
            f"openAppSettings reference; found {owner_hits}"
        )
        return 1

    if violations:
        print("FAIL: raw settings opener outside AppPermissionCoordinator:")
        for line in violations:
            print(f"  - {line}")
        print("Use AppPermissionCoordinator.openSettings(); no allowlist exists.")
        return 1

    print("OK: AppPermissionCoordinator exclusively owns settings opening")
    return 0


if __name__ == "__main__":
    sys.exit(main())
