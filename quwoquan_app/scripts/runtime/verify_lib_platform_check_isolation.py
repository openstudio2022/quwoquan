#!/usr/bin/env python3
"""Ratchet gate: keep platform branching out of the business layer (rule 14).

Capability-first means business / UI code must NOT ask "which platform am I on"
or talk to native channels directly. It must consume `PlatformCapabilities`
(via platformCapabilitiesProvider) and the anti-corruption gateways.

This gate scans quwoquan_app/lib (excluding the platform ACL itself) for:
  - bare platform discrimination:  `Platform.isAndroid/isIOS/isMacOS/...`,
    `Platform.operatingSystem`, `kIsWeb`
  - raw native channels:           `MethodChannel(` / `EventChannel(` /
    `BasicMessageChannel(`
  - page-private width breakpoints: `MediaQuery...width > <num>` / `.width >= <num>`
    style hard-coded layout breakpoints (must use AppSpacing breakpoints).
  - platform SDK imports:          LiveKit / CallKit / native video SDKs

Current occurrences are recorded as an allowlist baseline; new ones fail.
Allowlist may only shrink (only-decrease).

Allowlist: specs/gates/lib_platform_check_allowlist.yaml
  { "allowed": [ { "path": "<rel.dart>", "kind": "<kind>" }, ... ] }

Regenerate (intentionally, after isolating behind the ACL):
  python3 quwoquan_app/scripts/runtime/verify_lib_platform_check_isolation.py --write-baseline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOWLIST = ROOT / "specs" / "gates" / "lib_platform_check_allowlist.yaml"

# The anti-corruption layer is the ONLY place allowed to do these.
EXEMPT_PREFIXES = ("core/platform/",)

CHECKS: list[tuple[str, re.Pattern[str]]] = [
    (
        "platform_branch",
        re.compile(
            r"\bPlatform\s*\.\s*(isAndroid|isIOS|isMacOS|isWindows|isLinux|isFuchsia|operatingSystem)\b"
        ),
    ),
    ("kIsWeb", re.compile(r"\bkIsWeb\b")),
    (
        "raw_channel",
        re.compile(r"\b(MethodChannel|EventChannel|BasicMessageChannel)\s*\("),
    ),
    (
        "private_breakpoint",
        re.compile(r"\.width\s*(?:>=|>|<=|<)\s*\d{2,4}(?:\.\d+)?"),
    ),
    (
        "platform_sdk_import",
        re.compile(
            r"package:(?:livekit_client|flutter_callkit_incoming|video_thumbnail)/"
        ),
    ),
]


def _scan() -> set[tuple[str, str]]:
    hits: set[tuple[str, str]] = set()
    for path in APP_LIB.rglob("*.dart"):
        rel = path.relative_to(APP_LIB).as_posix()
        if any(rel.startswith(p) for p in EXEMPT_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for kind, rx in CHECKS:
            if rx.search(text):
                hits.add((rel, kind))
    return hits


def _load_allowed() -> set[tuple[str, str]]:
    import yaml  # type: ignore

    if not ALLOWLIST.is_file():
        return set()
    raw = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    out: set[tuple[str, str]] = set()
    for row in raw.get("allowed") or []:
        p = str(row.get("path", "")).strip().replace("\\", "/")
        k = str(row.get("kind", "")).strip()
        if p and k:
            out.add((p, k))
    return out


def _write_baseline(hits: set[tuple[str, str]]) -> None:
    ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Baseline of business-layer platform branching in quwoquan_app/lib.",
        "# Managed by verify_lib_platform_check_isolation.py (rule 14).",
        "# Only-decrease: migrate behind PlatformCapabilities / platform ACL to remove rows.",
        "allowed:",
    ]
    for p, k in sorted(hits):
        lines.append(f"  - path: {p}")
        lines.append(f"    kind: {k}")
    ALLOWLIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    hits = _scan()

    if args.write_baseline:
        _write_baseline(hits)
        print(
            f"verify_lib_platform_check_isolation: wrote baseline rows={len(hits)} -> {ALLOWLIST}"
        )
        return 0

    if not ALLOWLIST.is_file():
        print(
            "verify_lib_platform_check_isolation: BLOCK: missing "
            f"{ALLOWLIST} (run once with --write-baseline)",
            file=sys.stderr,
        )
        return 2

    try:
        allowed = _load_allowed()
    except Exception as e:  # noqa: BLE001
        print(
            f"verify_lib_platform_check_isolation: FAIL load allowlist: {e}",
            file=sys.stderr,
        )
        return 1

    violations = sorted(hits - allowed)
    stale_entries = sorted(allowed - hits)
    if violations or stale_entries:
        print(
            "verify_lib_platform_check_isolation: BLOCK: baseline drift",
            file=sys.stderr,
        )
        for p, k in violations:
            print(f"  new hit: {p}: {k}", file=sys.stderr)
        for p, k in stale_entries:
            print(f"  stale allowlist entry: {p}: {k}", file=sys.stderr)
        print(
            "  Use PlatformCapabilities (platformCapabilitiesProvider), the native "
            "bridge, or AppSpacing breakpoints instead.",
            file=sys.stderr,
        )
        return 1

    print(f"verify_lib_platform_check_isolation: OK (allowlisted={len(allowed)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
