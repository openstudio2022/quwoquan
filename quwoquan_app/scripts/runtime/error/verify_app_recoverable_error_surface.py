#!/usr/bin/env python3
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
APP_LIB = ROOT / "quwoquan_app/lib"
RECOVERY_CONTRACT = ROOT / "quwoquan_app/lib/runtime/errors/app_user_recovery.dart"

# These files implement the shared loading primitives themselves.  Keep the
# exception exact: excluding all of design_system would let unrelated widgets
# re-introduce raw progress indicators without being checked.
RAW_PROGRESS_PRIMITIVE_FILES = frozenset(
    {
        "quwoquan_app/lib/design_system/feedback/app_request_feedback.dart",
        "quwoquan_app/lib/design_system/feedback/error_states/app_error_action_row.dart",
        "quwoquan_app/lib/design_system/layout/ios_selection_page_components.dart",
    }
)

DIRECT_RAW_PROGRESS = re.compile(
    r"(?:CupertinoActivityIndicator|CircularProgressIndicator)\s*\("
)
DIRECT_RECOVERABLE_SEMANTIC = re.compile(
    r"(?<![A-Za-z0-9_])UiErrorSemantic\([\s\S]{0,500}?"
    r"category:\s*UiErrorCategory\."
    r"(?:pageLoad|sectionLoad|listAppend|backgroundAction|authRequired|"
    r"permissionRequired|notFound|rateLimited)"
)
DYNAMIC_SEMANTIC = re.compile(r"(?<![A-Za-z0-9_])UiErrorSemantic\(")
RECOVERABLE_CATEGORY = re.compile(
    r"category:\s*UiErrorCategory\."
    r"(?:pageLoad|sectionLoad|listAppend|backgroundAction|authRequired|"
    r"permissionRequired|notFound|rateLimited)"
)
FORBIDDEN_VISIBLE_TERMS = (
    "DNS",
    "TLS",
    "证书",
    "端口",
    "连接拒绝",
    "上游",
    "契约",
    "响应格式",
    "堆栈",
)
STRING_LITERAL = re.compile(r"(['\"])(.*?)\1")


def _canonical_ui_roots(app_lib: Path) -> tuple[Path, ...]:
    """Return canonical user-interface roots, never retired lib/ui roots."""

    return (
        *sorted(app_lib.glob("service/*/*/*/presentation")),
        app_lib / "runtime/shell",
        app_lib / "runtime/shell",
        app_lib / "design_system",
    )


def collect_ui_files(app_lib: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            {
                path
                for root in _canonical_ui_roots(app_lib)
                if root.is_dir()
                for path in root.rglob("*.dart")
                if not path.name.endswith(".g.dart")
                and "generated" not in path.parts
            }
        )
    )


def collect_ui_failures(*, repo_root: Path, app_lib: Path) -> list[str]:
    failures: list[str] = []
    for path in collect_ui_files(app_lib):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo_root).as_posix()
        for match in DIRECT_RAW_PROGRESS.finditer(text):
            if relative in RAW_PROGRESS_PRIMITIVE_FILES:
                continue
            line = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{relative}:{line}: UI loading must use AppRequestFeedback"
            )
        for match in DIRECT_RECOVERABLE_SEMANTIC.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{relative}:{line}: recoverable copy must come from AppUserRecoveryContract"
            )
        for match in DYNAMIC_SEMANTIC.finditer(text):
            context_start = max(0, match.start() - 700)
            context = text[context_start : match.start()]
            resolver_start = context.rfind("runtimeErrorSemantic(")
            resolver_context = (
                context[resolver_start:] if resolver_start >= 0 else ""
            )
            if (
                resolver_start >= 0
                and RECOVERABLE_CATEGORY.search(resolver_context) is not None
            ):
                line = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{relative}:{line}: page/section semantic must not override resolved recovery copy"
                )
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            if "debugPrint" in line_text or "developer.log" in line_text:
                continue
            for literal in STRING_LITERAL.finditer(line_text):
                value = literal.group(2)
                term = next(
                    (
                        candidate
                        for candidate in FORBIDDEN_VISIBLE_TERMS
                        if candidate in value
                    ),
                    None,
                )
                if term is not None:
                    failures.append(
                        f"{relative}:{line_number}: visible copy contains technical term {term}"
                    )
    return failures


def main() -> int:
    failures = collect_ui_failures(repo_root=ROOT, app_lib=APP_LIB)

    contract = RECOVERY_CONTRACT.read_text(encoding="utf-8")
    for group in (
        "connectNetwork",
        "reloadLater",
        "loginAgain",
        "enablePermission",
        "waitThenReload",
        "updateApp",
        "noAccess",
        "contentGone",
        "contentUnavailable",
    ):
        if f"AppUserRecoveryGroup.{group}" not in contract:
            failures.append(f"missing recovery group contract: {group}")

    if failures:
        print("[verify_app_recoverable_error_surface] FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("[verify_app_recoverable_error_surface] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
