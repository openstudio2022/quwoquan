#!/usr/bin/env python3
"""Ratchet gate: forbid NEW `import 'dart:io'` in quwoquan_app/lib (rule 14).

Cross-platform portability requires `dart:io` to be funnelled through the
anti-corruption layer (`lib/core/platform/**`, e.g. FileStorageGateway) so that
web (no file system) and HarmonyOS can supply their own implementations.

Policy:
  - `lib/core/platform/**` is the boundary and may use `dart:io` freely.
  - Every other current `dart:io` importer is recorded in an allowlist baseline.
  - Files NOT in the baseline (and outside the boundary) that import `dart:io`
    fail the gate. The baseline may only shrink (only-decrease), never grow
    without an explicit, reviewed `--write-baseline`.
  - `lib/cloud/runtime/**` and `lib/cloud/remote/**` are production transport
    paths and may never import `dart:io`, including if a future baseline entry
    would otherwise permit it.

Allowlist: quwoquan_ops/policies/gates/lib_dart_io_import_allowlist.yaml
  { "allowed": [ "<rel/path.dart>", ... ] }

Regenerate baseline (after migrating files behind the gateway, intentionally):
  python3 quwoquan_app/scripts/runtime/verify_lib_dart_io_budget.py --write-baseline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOWLIST = ROOT / "quwoquan_ops" / "policies" / "gates" / "lib_dart_io_import_allowlist.yaml"

# Anti-corruption boundary: allowed to use dart:io without allowlisting.
BOUNDARY_PREFIXES = ("core/platform/",)
PRODUCTION_TRANSPORT_PREFIXES = ("cloud/runtime/", "cloud/remote/")

IMPORT_RE = re.compile(r"""^\s*import\s+['"]dart:io['"]""", re.M)


def _scan_importers() -> set[str]:
    found: set[str] = set()
    for path in APP_LIB.rglob("*.dart"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if IMPORT_RE.search(text):
            found.add(path.relative_to(APP_LIB).as_posix())
    return found


def _is_boundary(rel: str) -> bool:
    return any(rel.startswith(p) for p in BOUNDARY_PREFIXES)


def _is_production_transport(rel: str) -> bool:
    return any(rel.startswith(p) for p in PRODUCTION_TRANSPORT_PREFIXES)


def _load_allowed() -> set[str]:
    import yaml  # type: ignore

    if not ALLOWLIST.is_file():
        return set()
    raw = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    return {
        str(p).strip().replace("\\", "/")
        for p in (raw.get("allowed") or [])
        if str(p).strip()
    }


def _write_baseline(importers: set[str]) -> None:
    entries = sorted(r for r in importers if not _is_boundary(r))
    ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Baseline of quwoquan_app/lib files importing dart:io directly.",
        "# Managed by verify_lib_dart_io_budget.py (rule 14-cross-platform-portability).",
        "# Only-decrease: do not add entries without migrating behind the platform ACL.",
        "allowed:",
    ]
    lines += [f"  - {e}" for e in entries]
    ALLOWLIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    importers = _scan_importers()

    if args.write_baseline:
        _write_baseline(importers)
        kept = sum(1 for r in importers if not _is_boundary(r))
        print(
            f"verify_lib_dart_io_budget: wrote baseline count={kept} -> {ALLOWLIST}"
        )
        return 0

    if not ALLOWLIST.is_file():
        print(
            "verify_lib_dart_io_budget: BLOCK: missing "
            f"{ALLOWLIST} (run once with --write-baseline)",
            file=sys.stderr,
        )
        return 2

    try:
        allowed = _load_allowed()
    except Exception as e:  # noqa: BLE001
        print(f"verify_lib_dart_io_budget: FAIL load allowlist: {e}", file=sys.stderr)
        return 1

    new_violations = sorted(
        r for r in importers if not _is_boundary(r) and r not in allowed
    )
    transport_violations = sorted(
        r for r in importers if _is_production_transport(r)
    )
    stale_entries = sorted(
        r for r in allowed if r not in importers or _is_boundary(r)
    )

    if new_violations or transport_violations or stale_entries:
        print("verify_lib_dart_io_budget: BLOCK: baseline drift", file=sys.stderr)
        for v in new_violations:
            print(f"  new importer: {v}", file=sys.stderr)
        for v in transport_violations:
            print(f"  production transport importer: {v}", file=sys.stderr)
        for v in stale_entries:
            print(f"  stale allowlist entry: {v}", file=sys.stderr)
        print(
            "  Production runtime/remote must not access local files; route "
            "platform file access through FileStorageGateway "
            "(lib/core/platform/).",
            file=sys.stderr,
        )
        return 1

    print(
        "verify_lib_dart_io_budget: OK "
        f"(allowlisted={len(allowed)}, current={sum(1 for r in importers if not _is_boundary(r))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
