#!/usr/bin/env python3
"""Ratchet: new lib/ code must not call openAppSettings outside Coordinator.

Business/UI layers should use AppPermissionCoordinator.openSettings() so
settings-return suppress and single-feedback semantics stay consistent.

Allowlist: specs/gates/permission_coordinator_adoption_allowlist.yaml
Regenerate baseline (intentional migration only):
  python3 quwoquan_app/scripts/runtime/verify_permission_coordinator_adoption.py --write-baseline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOWLIST = ROOT / "specs" / "gates" / "permission_coordinator_adoption_allowlist.yaml"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openAppSettings", re.compile(r"\bopenAppSettings\s*\(")),
    (
        "geolocator_open_settings",
        re.compile(r"\bGeolocator\s*\.\s*openAppSettings\s*\("),
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


def _load_allowed_paths() -> set[str]:
    import yaml  # type: ignore

    if not ALLOWLIST.is_file():
        return set()
    raw = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    out: set[str] = set()
    for row in raw.get("allowed") or []:
        p = str(row.get("path", "")).strip().replace("\\", "/")
        if p:
            out.add(p)
    return out


def _write_baseline(hits: set[tuple[str, str]]) -> None:
    import yaml  # type: ignore

    paths = sorted({rel for rel, _ in hits})
    payload = {"allowed": [{"path": p} for p in paths]}
    ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(paths)} paths to {ALLOWLIST.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite allowlist from current scan (intentional only)",
    )
    args = parser.parse_args()

    hits = _scan()
    if args.write_baseline:
        _write_baseline(hits)
        return 0

    allowed_paths = _load_allowed_paths()
    violations: list[str] = []
    for rel, kind in sorted(hits):
        if rel not in allowed_paths:
            violations.append(f"{rel} ({kind})")

    if violations:
        print("FAIL: openAppSettings outside permission coordinator allowlist:")
        for line in violations:
            print(f"  - {line}")
        print(
            "Use AppPermissionCoordinator.openSettings(); "
            f"allowlist: {ALLOWLIST.relative_to(ROOT)}"
        )
        return 1

    print(
        f"OK: permission coordinator adoption "
        f"({len(allowed_paths)} allowlisted paths, {len(hits)} total hits)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
