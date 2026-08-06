#!/usr/bin/env python3
"""
verify_error_code_semantic.py

Scans quwoquan_app/lib/**/*.dart for hardcoded error code strings
(e.g. 'INTEGRATION.USER.location_unavailable') that should use
*ErrorCode enum .code (e.g. IntegrationLocationErrorCode.locationUnavailable.code).

Excluded paths: generated outputs, lib/design_system/, lib/l10n/copy/

Usage:
  python3 quwoquan_app/scripts/runtime/error/verify_error_code_semantic.py [--targets PATH]

Exit 0 on success, 1 on failure.
"""

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
import os
import re
import sys

# Match string literals that look like metadata error codes: MODULE.KIND.reason
# e.g. 'INTEGRATION.USER.location_unavailable', "CONTENT.USER.post_not_found",
# 'ASSISTANT.MIDDLEWARE.upstream_timeout', "CIRCLE.USER.not_found".
#
# 覆盖全部业务 MODULE（USER/CONTENT/INTEGRATION/RTC/CIRCLE/CHAT/ASSISTANT/ENTITY）
# 与全部 KIND（含 AUTH/PERSONA/GREETING/INVITE/CONTACT/SETTING 等用户域细分），
# 唯一真相源为 contracts/metadata/**/errors.yaml。新增模块/类别时在此同步扩展。
_MODULES = "USER|CONTENT|INTEGRATION|RTC|CIRCLE|CHAT|ASSISTANT|ENTITY"
_KINDS = "USER|AUTH|PERSONA|GREETING|INVITE|CONTACT|SETTING|MIDDLEWARE|SYSTEM"
PATTERN = re.compile(
    rf"['\"](?:{_MODULES})\.(?:{_KINDS})\.[a-z0-9_]+['\"]"
)
HINT = "错误码应使用 *ErrorCode.xxx.code，禁止硬编码字符串；见 quwoquan_app/AGENTS.md"

# Canonical roots excluded by exact lib-relative prefix. Generated outputs keep
# their suffix-based exemption while generated-like business directories do not.
EXCLUDE_PREFIXES = (
    "design_system/",
    "l10n/copy/",
)


def should_skip(path: str, lib_root: str) -> bool:
    rel = os.path.relpath(path, lib_root).replace("\\", "/")
    return rel.endswith(".g.dart") or any(
        rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES
    )


def scan_file(path: str, lib_root: str) -> list[tuple[int, str]]:
    """Return list of (line_no, line_content) for violations."""
    violations = []
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                if PATTERN.search(line):
                    violations.append((i, line.rstrip()))
    except OSError as e:
        rel = os.path.relpath(path, lib_root).replace("\\", "/")
        print(f"verify_error_code_semantic: ERROR reading {rel}: {e}", file=sys.stderr)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify error code semantic (no hardcoded strings)")
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib",
        help="Path to scan (default: quwoquan_app/lib)",
    )
    args = parser.parse_args()

    root = str(REPO_ROOT)
    lib_root = os.path.normpath(os.path.join(root, args.targets))
    if not os.path.isdir(lib_root):
        print(f"verify_error_code_semantic: ERROR {lib_root} not found", file=sys.stderr)
        return 1

    all_violations: list[tuple[str, int, str]] = []

    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            if should_skip(path, lib_root):
                continue
            rel = os.path.relpath(path, root).replace("\\", "/")
            for line_no, line_content in scan_file(path, lib_root):
                all_violations.append((rel, line_no, line_content))

    found = False
    for rel, line_no, line_content in all_violations:
        print(f"{rel}:{line_no}: {HINT}")
        print(f"  {line_content.strip()}")
        found = True

    if found:
        print(f"\nverify_error_code_semantic: {HINT}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
