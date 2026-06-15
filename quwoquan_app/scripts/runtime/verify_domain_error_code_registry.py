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
    "CONTENT": "quwoquan_app/lib/cloud/content/generated/content_errors.g.dart",
    "USER": "quwoquan_app/lib/cloud/runtime/generated/user/user_errors.g.dart",
    "CHAT": "quwoquan_app/lib/cloud/chat/generated/chat_errors.g.dart",
    "RTC": "quwoquan_app/lib/cloud/rtc/generated/rtc_errors.g.dart",
    "INTEGRATION": "quwoquan_app/lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
    "ASSISTANT": "quwoquan_app/lib/cloud/assistant/generated/assistant_errors.g.dart",
    "CIRCLE": "quwoquan_app/lib/cloud/circle/generated/circle_errors.g.dart",
    "ENTITY": "quwoquan_app/lib/cloud/entity/generated/entity_errors.g.dart",
}

REGISTRY_PATH = "quwoquan_app/lib/cloud/runtime/errors/domain_error_code.dart"
CODE_RE = re.compile(r"'([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)'")


def read(path: str) -> str:
    with open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def main() -> int:
    registry = read(REGISTRY_PATH)
    failed = False
    for module, rel_path in GENERATED_ENUMS.items():
        if not os.path.isfile(os.path.join(REPO_ROOT, rel_path)):
            print(f"[{module}] missing generated enum: {rel_path}")
            failed = True
            continue
        content = read(rel_path)
        codes = {code for code in CODE_RE.findall(content) if code.startswith(module + ".")}
        if not codes:
            print(f"[{module}] no codes found in {rel_path}")
            failed = True
            continue
        if f"code.startsWith('{module}.')" not in registry:
            print(f"[{module}] DomainErrorCodeRegistry missing module branch")
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
