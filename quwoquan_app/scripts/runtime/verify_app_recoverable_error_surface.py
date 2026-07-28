#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
UI_ROOT = ROOT / "quwoquan_app/lib/ui"
RECOVERY_CONTRACT = ROOT / "quwoquan_app/lib/core/errors/app_user_recovery.dart"

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


def main() -> int:
    failures: list[str] = []
    for path in sorted(UI_ROOT.rglob("*.dart")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for match in DIRECT_RAW_PROGRESS.finditer(text):
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
