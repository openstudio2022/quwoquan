#!/usr/bin/env python3
"""Ratchet gate: forbid NEW `import 'dart:io'` in quwoquan_app/lib (rule 14).

Cross-platform portability requires `dart:io` to be funnelled through the
anti-corruption layer (`lib/core/platform/**` today, `lib/runtime/platform/**`
after the cross-cutting migration, e.g. FileStorageGateway) so that web (no file
system) and HarmonyOS can supply their own implementations.

Policy:
  - `lib/core/platform/**` and `lib/runtime/platform/**` are the boundary and may
    use `dart:io` freely.
  - Every other current `dart:io` importer is recorded in an allowlist baseline.
  - Files NOT in the baseline (and outside the boundary) that import `dart:io`
    fail the gate. The baseline may only shrink (only-decrease), never grow
    without an explicit, reviewed `--write-baseline`.
  - `lib/cloud/runtime/**` and `lib/cloud/remote/**` are production transport
    paths and may never import `dart:io`, including if a future baseline entry
    would otherwise permit it.

Allowlist (present only while debt remains):
  quwoquan_ops/policies/gates/lib_dart_io_import_allowlist.yaml
  { "allowed": [ "<rel/path.dart>", ... ] }

Regenerate baseline (after migrating files behind the gateway, intentionally):
  python3 quwoquan_app/scripts/runtime/platform/verify_lib_dart_io_budget.py --write-baseline
"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import argparse
import re
import sys
from pathlib import Path

ROOT = REPO_ROOT
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOWLIST = ROOT / "quwoquan_ops" / "policies" / "gates" / "lib_dart_io_import_allowlist.yaml"

# Anti-corruption boundary: allowed to use dart:io without allowlisting. The
# layer spans two prefixes while the cross-cutting migration runs: `core/platform/`
# is today's location, `runtime/platform/` is the target derived by
# `quwoquan_ops/gate/object_path_map.py`. Files move one by one, so a file must
# not lose its boundary status merely by landing at its target path.
BOUNDARY_PREFIXES = ("core/platform/", "runtime/platform/")
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


def _write_baseline(importers: set[str]) -> tuple[int, list[str]]:
    """退役后 ``--write-baseline`` 只能删除陈旧文件，不能重建豁免。

    规则 14 对这条门禁的措辞是「存量已清零、allowlist 已退役，命中即 BLOCK，不接受
    豁免登记」。只要脚本还能重建 allowlist，任何人新加一个 ``dart:io`` 导入再跑一次
    ``--write-baseline`` 就能把它固化成豁免、让门禁转绿——那条规则也就名存实亡。

    返回未被边界豁免的违规条目，由调用方决定退出码。
    """
    entries = sorted(r for r in importers if not _is_boundary(r))
    if not entries:
        ALLOWLIST.unlink(missing_ok=True)
    return len(entries), entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    importers = _scan_importers()

    if args.write_baseline:
        kept, entries = _write_baseline(importers)
        if kept == 0:
            print(
                "verify_lib_dart_io_budget: retired empty baseline "
                f"(removed {ALLOWLIST})"
            )
            return 0
        print(
            "verify_lib_dart_io_budget: BLOCK: allowlist is retired and cannot be "
            f"rebuilt; migrate these {kept} importer(s) behind the platform ACL",
            file=sys.stderr,
        )
        for path in entries:
            print(f"  {path}", file=sys.stderr)
        return 2

    if not ALLOWLIST.is_file():
        current = sorted(r for r in importers if not _is_boundary(r))
        if current:
            print(
                "verify_lib_dart_io_budget: BLOCK: allowlist is retired but "
                "non-platform dart:io importers exist",
                file=sys.stderr,
            )
            for path in current:
                print(f"  new importer: {path}", file=sys.stderr)
            return 2
        print("verify_lib_dart_io_budget: OK (allowlist=retired, current=0)")
        return 0

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
    empty_retired_baseline = not allowed and not any(
        not _is_boundary(r) for r in importers
    )

    if (
        new_violations
        or transport_violations
        or stale_entries
        or empty_retired_baseline
    ):
        print("verify_lib_dart_io_budget: BLOCK: baseline drift", file=sys.stderr)
        for v in new_violations:
            print(f"  new importer: {v}", file=sys.stderr)
        for v in transport_violations:
            print(f"  production transport importer: {v}", file=sys.stderr)
        for v in stale_entries:
            print(f"  stale allowlist entry: {v}", file=sys.stderr)
        if empty_retired_baseline:
            print(
                f"  stale empty allowlist: delete {ALLOWLIST}",
                file=sys.stderr,
            )
        print(
            "  Production runtime/remote must not access local files; route "
            "platform file access through FileStorageGateway "
            "(lib/core/platform/ or lib/runtime/platform/).",
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
