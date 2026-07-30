#!/usr/bin/env python3
"""
verify_domain_error_code_registry.py

确保所有客户端可见的生成 *ErrorCode 都被 DomainErrorCodeRegistry 注册消费。
禁止出现“生成了 typed enum，但 CloudErrorMapper/registry 无法识别”的半闭环。
"""

from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

GENERATED_ENUMS = {
    "content": ("CONTENT", "quwoquan_app/lib/cloud/content/generated/content_errors.g.dart"),
    "user": ("USER", "quwoquan_app/lib/cloud/runtime/generated/user/user_errors.g.dart"),
    "chat": ("CHAT", "quwoquan_app/lib/cloud/chat/generated/chat_errors.g.dart"),
    "rtc": ("RTC", "quwoquan_app/lib/cloud/rtc/generated/rtc_errors.g.dart"),
    "integration_location": (
        "INTEGRATION",
        "quwoquan_app/lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
    ),
    "assistant": (
        "ASSISTANT",
        "quwoquan_app/lib/cloud/assistant/generated/assistant_errors.g.dart",
    ),
    "circle": ("CIRCLE", "quwoquan_app/lib/cloud/circle/generated/circle_errors.g.dart"),
    "circle_membership": (
        "CIRCLE",
        "quwoquan_app/lib/cloud/circle/generated/circle_membership_errors.g.dart",
    ),
    "entity": ("ENTITY", "quwoquan_app/lib/cloud/entity/generated/entity_errors.g.dart"),
}

REGISTRY_PATH = "quwoquan_app/lib/cloud/runtime/errors/domain_error_code.dart"
CODE_RE = re.compile(r"'([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)'")
ENUM_RE = re.compile(r"^enum\s+(\w+ErrorCode)\s*\{", re.MULTILINE)


def read(path: str) -> str:
    with open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def main() -> int:
    registry = read(REGISTRY_PATH)
    failed = False
    for label, (module, rel_path) in GENERATED_ENUMS.items():
        if not os.path.isfile(os.path.join(REPO_ROOT, rel_path)):
            print(f"[{label}] missing generated enum: {rel_path}")
            failed = True
            continue
        content = read(rel_path)
        codes = {code for code in CODE_RE.findall(content) if code.startswith(module + ".")}
        if not codes:
            print(f"[{label}] no codes found in {rel_path}")
            failed = True
            continue
        if f"code.startsWith('{module}.')" not in registry:
            print(f"[{label}] DomainErrorCodeRegistry missing {module} module branch")
            failed = True
        enum_match = ENUM_RE.search(content)
        if enum_match is None:
            print(f"[{label}] no generated *ErrorCode enum declaration found")
            failed = True
            continue
        enum_name = enum_match.group(1)
        if f"{enum_name}.fromCode" not in registry:
            print(f"[{label}] DomainErrorCodeRegistry does not consume {enum_name}")
            failed = True
    if failed:
        print(
            "\nverify_domain_error_code_registry: generated *ErrorCode 未完全注册到 DomainErrorCodeRegistry",
            file=sys.stderr,
        )
        return 1
    print("verify_domain_error_code_registry: all generated *ErrorCode modules registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
