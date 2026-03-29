#!/usr/bin/env python3
"""
verify_settings_canonical.py

Ensures settings-family pages stay on the canonical shells (see specs/ux/page-layout-semantics.md §4.3).

Reads scripts/settings_canonical_manifest.yaml and:
- For inset_form: file must contain SettingsInsetFormPageScaffold
- For inset_member_picker: file must contain SettingsInsetMemberPickerPageScaffold
- For webview_shell | prototype_exception | wizard_deferred | deferred_inset:
  first 160 lines must include a comment with "settings-canonical-exception:"

Also verifies every file matched by DISCOVER_* exists in the manifest.

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import glob
import os
import sys

try:
    import yaml
except ImportError:
    print(
        "verify_settings_canonical: ERROR PyYAML required (pip install pyyaml)",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "scripts", "settings_canonical_manifest.yaml")

EXCEPTION_SHELLS = frozenset(
    {
        "webview_shell",
        "prototype_exception",
        "wizard_deferred",
        "deferred_inset",
    }
)

DISCOVER_GLOBS = [
    "quwoquan_app/lib/ui/settings/**/*_page.dart",
]

DISCOVER_FILES = [
    "quwoquan_app/lib/ui/chat/pages/chat_settings_page.dart",
    "quwoquan_app/lib/ui/chat/pages/group_manage_page.dart",
    "quwoquan_app/lib/ui/chat/pages/transfer_ownership_page.dart",
    "quwoquan_app/lib/ui/chat/pages/group_admins_page.dart",
    "quwoquan_app/lib/ui/chat/pages/start_group_chat_page.dart",
    "quwoquan_app/lib/ui/assistant/pages/assistant_management_page.dart",
    "quwoquan_app/lib/ui/assistant/pages/assistant_chat_settings_page.dart",
    "quwoquan_app/lib/ui/assistant/pages/assistant_reference_webview_page.dart",
    "quwoquan_app/lib/ui/assistant/pages/assistant_skill_center_page.dart",
    "quwoquan_app/lib/ui/circle/pages/circle_edit_settings_page.dart",
]

EXCEPTION_MARK = "settings-canonical-exception:"


def _discovered_paths() -> set[str]:
    out: set[str] = set()
    for g in DISCOVER_GLOBS:
        pattern = os.path.join(ROOT, g)
        for abs_path in glob.glob(pattern, recursive=True):
            if abs_path.endswith(".dart"):
                out.add(os.path.relpath(abs_path, ROOT).replace("\\", "/"))
    for rel in DISCOVER_FILES:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            out.add(rel.replace("\\", "/"))
    return out


def _head_lines(path: str, n: int = 160) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [f.readline() for _ in range(n)]


def main() -> int:
    if not os.path.isfile(MANIFEST):
        print(f"verify_settings_canonical: ERROR missing {MANIFEST}", file=sys.stderr)
        return 1

    with open(MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    pages = data.get("pages") or []
    manifest_paths: dict[str, str] = {}
    for entry in pages:
        rel = entry.get("path", "").replace("\\", "/")
        shell = entry.get("shell", "")
        if not rel or not shell:
            print(f"verify_settings_canonical: ERROR bad entry {entry!r}", file=sys.stderr)
            return 1
        manifest_paths[rel] = shell

    discovered = _discovered_paths()
    for rel in sorted(discovered):
        if rel not in manifest_paths:
            print(
                f"verify_settings_canonical: FAIL {rel} is discovered but not in "
                f"settings_canonical_manifest.yaml",
                file=sys.stderr,
            )
            return 1

    for rel, shell in sorted(manifest_paths.items()):
        abs_path = os.path.join(ROOT, rel)
        if not os.path.isfile(abs_path):
            print(
                f"verify_settings_canonical: FAIL manifest path missing file: {rel}",
                file=sys.stderr,
            )
            return 1
        try:
            with open(abs_path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"verify_settings_canonical: ERROR reading {rel}: {e}", file=sys.stderr)
            return 1

        if shell == "inset_form":
            if "SettingsInsetFormPageScaffold" not in text:
                print(
                    f"verify_settings_canonical: FAIL {rel} shell=inset_form but "
                    f"SettingsInsetFormPageScaffold not found",
                    file=sys.stderr,
                )
                return 1
        elif shell == "inset_member_picker":
            if "SettingsInsetMemberPickerPageScaffold" not in text:
                print(
                    f"verify_settings_canonical: FAIL {rel} shell=inset_member_picker but "
                    f"SettingsInsetMemberPickerPageScaffold not found",
                    file=sys.stderr,
                )
                return 1
        elif shell in EXCEPTION_SHELLS:
            head = "".join(_head_lines(abs_path, 160))
            if EXCEPTION_MARK not in head:
                print(
                    f"verify_settings_canonical: FAIL {rel} shell={shell} must contain "
                    f"'{EXCEPTION_MARK}' in first 160 lines",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"verify_settings_canonical: ERROR unknown shell {shell!r} for {rel}",
                file=sys.stderr,
            )
            return 1

    print("verify_settings_canonical: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
