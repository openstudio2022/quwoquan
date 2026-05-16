#!/usr/bin/env python3
"""Validate specs/gates/metadata_driven_ui_gap_inventory.yaml and registered UI paths.

- Every ui_pages.path must exist under the repo root.
- Optional: QWQ_METADATA_UI_GATE_STRICT=1 fails if any row has status current_map.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("metadata_driven_ui_gate: PyYAML required", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    inv_path = ROOT / "specs" / "gates" / "metadata_driven_ui_gap_inventory.yaml"
    if not inv_path.is_file():
        print(f"metadata_driven_ui_gate: missing {inv_path}", file=sys.stderr)
        return 1

    data = yaml.safe_load(inv_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("metadata_driven_ui_gate: inventory root must be a mapping", file=sys.stderr)
        return 1

    missing: list[str] = []
    current = 0
    for dom in data.get("domains", []):
        if not isinstance(dom, dict):
            continue
        for page in dom.get("ui_pages", []):
            if not isinstance(page, dict):
                continue
            rel = page.get("path")
            if not rel or not isinstance(rel, str):
                continue
            if page.get("status") == "current_map":
                current += 1
            p = ROOT / rel
            if not p.is_file():
                missing.append(rel)

    if missing:
        print("metadata_driven_ui_gate: ui_pages paths missing on disk:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1

    strict = os.environ.get("QWQ_METADATA_UI_GATE_STRICT") == "1"
    if strict and current:
        print(
            f"metadata_driven_ui_gate: STRICT mode: {current} current_map row(s) remain",
            file=sys.stderr,
        )
        return 1

    print(f"metadata_driven_ui_gate: ok (current_map rows: {current})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
