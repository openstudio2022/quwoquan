#!/usr/bin/env python3
"""
verify_conversation_sheet_canonical.py

Ensures modal presentation stays centralized (see runtime/runtime-client-foundation/page-layout-semantics/spec.md).

- `showAppBottomModal` is the canonical business entry and needs no registry
- Business code must not call raw Cupertino/General modal APIs directly
- Business code must not use ColorType.modalScrim as a route/sheet mask

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
APP_LIB = os.path.join(ROOT, "quwoquan_app", "lib")

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
