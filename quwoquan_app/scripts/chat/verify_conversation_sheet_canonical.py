#!/usr/bin/env python3
"""
verify_conversation_sheet_canonical.py

Ensures modal presentation stays centralized (see specs/ux/page-layout-semantics.md §4.4).

Reads scripts/chat/conversation_sheet_manifest.yaml and:
- Discovers quwoquan_app/lib/**/*.dart containing `showAppBottomModal`
- Each bottom modal caller must appear in allowed_modal_popup.path
- Business code must not call raw Cupertino/General modal APIs directly
- Business code must not use ColorType.modalScrim as a route/sheet mask

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import re
import sys

try:
    import yaml
except ImportError:
    print(
        "verify_conversation_sheet_canonical: ERROR PyYAML required (pip install pyyaml)",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
MANIFEST = os.path.join(
    ROOT, "quwoquan_app", "scripts", "chat", "conversation_sheet_manifest.yaml"
)
APP_LIB = os.path.join(ROOT, "quwoquan_app", "lib")

BOTTOM_MODAL_CALL_RE = re.compile(r"\bshowAppBottomModal\s*(?:<|\()")
RAW_MODAL_API_RE = re.compile(
    r"\b(showCupertinoModalPopup|showCupertinoDialog|showGeneralDialog)\s*\("
)

CANONICAL_MODAL_FILES = {
    "quwoquan_app/lib/core/widgets/app_modal_presenter.dart",
    "quwoquan_app/lib/core/widgets/app_top_anchored_dropdown.dart",
}

ROUTE_BARRIER_ALLOWLIST = CANONICAL_MODAL_FILES | {
    "quwoquan_app/lib/app/navigation/app_router.dart",
}

MODAL_SCRIM_ALLOWLIST = {
    "quwoquan_app/lib/core/widgets/app_modal_presenter.dart",
    "quwoquan_app/lib/core/design_system/colors/app_colors.dart",
}


def _dart_files() -> list[str]:
    out: list[str] = []
    for dirpath, _, filenames in os.walk(APP_LIB):
        for fname in filenames:
            if fname.endswith(".dart"):
                out.append(os.path.join(dirpath, fname))
    return out


def _rel(abs_path: str) -> str:
    return os.path.relpath(abs_path, ROOT).replace("\\", "/")


def _read(abs_path: str) -> str:
    try:
        with open(abs_path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _line_for(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _manifest_paths(data: object) -> set[str]:
    if not isinstance(data, dict):
        print(
            "verify_conversation_sheet_canonical: ERROR manifest must be a mapping",
            file=sys.stderr,
        )
        raise SystemExit(1)
    allowed = data.get("allowed_modal_popup") or []
    manifest_paths: set[str] = set()
    for entry in allowed:
        if not isinstance(entry, dict):
            print(
                f"verify_conversation_sheet_canonical: ERROR bad entry {entry!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        rel = (entry.get("path") or "").replace("\\", "/")
        if not rel:
            print(
                f"verify_conversation_sheet_canonical: ERROR bad entry {entry!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        manifest_paths.add(rel)
    return manifest_paths


def _discover_bottom_modal_callers() -> set[str]:
    discovered: set[str] = set()
    for abs_path in _dart_files():
        rel = _rel(abs_path)
        if rel in CANONICAL_MODAL_FILES:
            continue
        if BOTTOM_MODAL_CALL_RE.search(_read(abs_path)):
            discovered.add(rel)
    return discovered


def _check_no_raw_modal_apis() -> int:
    for abs_path in _dart_files():
        rel = _rel(abs_path)
        if rel in CANONICAL_MODAL_FILES:
            continue
        text = _read(abs_path)
        match = RAW_MODAL_API_RE.search(text)
        if match:
            print(
                "verify_conversation_sheet_canonical: FAIL "
                f"{rel}:{_line_for(text, match.start())} uses raw {match.group(1)}; "
                "use AppModalPresenter wrappers instead",
                file=sys.stderr,
            )
            return 1
    return 0


def _check_barrier_colors() -> int:
    for abs_path in _dart_files():
        rel = _rel(abs_path)
        text = _read(abs_path)
        if "barrierColor:" not in text:
            continue
        if rel not in ROUTE_BARRIER_ALLOWLIST:
            offset = text.index("barrierColor:")
            print(
                "verify_conversation_sheet_canonical: FAIL "
                f"{rel}:{_line_for(text, offset)} declares route barrierColor outside "
                "the canonical modal presenters",
                file=sys.stderr,
            )
            return 1
        for match in re.finditer(r"barrierColor:\s*([^,\n]+)", text):
            value = match.group(1).strip()
            if value not in {"AppColors.transparent", "Colors.transparent"}:
                print(
                    "verify_conversation_sheet_canonical: FAIL "
                    f"{rel}:{_line_for(text, match.start())} uses non-transparent "
                    f"route barrierColor {value!r}",
                    file=sys.stderr,
                )
                return 1
    return 0


def _check_modal_scrim_usage() -> int:
    for abs_path in _dart_files():
        rel = _rel(abs_path)
        if rel in MODAL_SCRIM_ALLOWLIST:
            continue
        text = _read(abs_path)
        offset = text.find("ColorType.modalScrim")
        if offset >= 0:
            print(
                "verify_conversation_sheet_canonical: FAIL "
                f"{rel}:{_line_for(text, offset)} uses ColorType.modalScrim outside "
                "the unified brightness layer",
                file=sys.stderr,
            )
            return 1
    return 0


def main() -> int:
    if not os.path.isfile(MANIFEST):
        print(
            f"verify_conversation_sheet_canonical: ERROR missing {MANIFEST}",
            file=sys.stderr,
        )
        return 1

    with open(MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    manifest_paths = _manifest_paths(data)
    discovered = _discover_bottom_modal_callers()

    for rel in sorted(discovered):
        if rel not in manifest_paths:
            print(
                "verify_conversation_sheet_canonical: FAIL "
                f"{rel} uses showAppBottomModal but is not listed in "
                "conversation_sheet_manifest.yaml",
                file=sys.stderr,
            )
            return 1

    for rel in sorted(manifest_paths):
        abs_path = os.path.join(ROOT, rel)
        if not os.path.isfile(abs_path):
            print(
                "verify_conversation_sheet_canonical: FAIL "
                f"manifest path missing file: {rel}",
                file=sys.stderr,
            )
            return 1

    for check in (
        _check_no_raw_modal_apis,
        _check_barrier_colors,
        _check_modal_scrim_usage,
    ):
        result = check()
        if result != 0:
            return result

    print("verify_conversation_sheet_canonical: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
