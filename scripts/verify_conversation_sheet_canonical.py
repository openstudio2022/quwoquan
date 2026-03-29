#!/usr/bin/env python3
"""
verify_conversation_sheet_canonical.py

Ensures new bottom-sheet modal popups stay registered (see specs/ux/page-layout-semantics.md §4.4).

Reads scripts/conversation_sheet_manifest.yaml and:
- Discovers quwoquan_app/lib/**/*.dart containing `showCupertinoModalPopup`
- Each file must appear in allowed_modal_popup.path

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import sys

try:
    import yaml
except ImportError:
    print(
        "verify_conversation_sheet_canonical: ERROR PyYAML required (pip install pyyaml)",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "scripts", "conversation_sheet_manifest.yaml")
APP_LIB = os.path.join(ROOT, "quwoquan_app", "lib")

def _dart_files_with_popup() -> set[str]:
    out: set[str] = set()
    for dirpath, _, filenames in os.walk(APP_LIB):
        for fname in filenames:
            if not fname.endswith(".dart"):
                continue
            abs_path = os.path.join(dirpath, fname)
            try:
                text = open(abs_path, encoding="utf-8").read()
            except OSError:
                continue
            if "showCupertinoModalPopup(" not in text:
                continue
            rel = os.path.relpath(abs_path, ROOT).replace("\\", "/")
            out.add(rel)
    return out


def main() -> int:
    if not os.path.isfile(MANIFEST):
        print(
            f"verify_conversation_sheet_canonical: ERROR missing {MANIFEST}",
            file=sys.stderr,
        )
        return 1

    with open(MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    allowed = data.get("allowed_modal_popup") or []
    manifest_paths: set[str] = set()
    for entry in allowed:
        rel = (entry.get("path") or "").replace("\\", "/")
        if not rel:
            print(
                f"verify_conversation_sheet_canonical: ERROR bad entry {entry!r}",
                file=sys.stderr,
            )
            return 1
        manifest_paths.add(rel)

    discovered = _dart_files_with_popup()

    for rel in sorted(discovered):
        if rel not in manifest_paths:
            print(
                f"verify_conversation_sheet_canonical: FAIL {rel} uses "
                f"showCupertinoModalPopup but is not listed in "
                f"conversation_sheet_manifest.yaml",
                file=sys.stderr,
            )
            return 1

    for rel in sorted(manifest_paths):
        abs_path = os.path.join(ROOT, rel)
        if not os.path.isfile(abs_path):
            print(
                f"verify_conversation_sheet_canonical: FAIL manifest path missing file: {rel}",
                file=sys.stderr,
            )
            return 1

    print("verify_conversation_sheet_canonical: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
