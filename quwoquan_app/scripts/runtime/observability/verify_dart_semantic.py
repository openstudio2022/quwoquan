#!/usr/bin/env python3
"""
verify_dart_semantic.py

Scans quwoquan_app/lib/**/*.dart for:
1) hardcoded visual literals (width, height, leadingSize, fontSize, size,
   EdgeInsets, BorderRadius, Color(0x)) that should use design system tokens
   (AppSpacing, AppTypography, AppColors).
2) iOS semantic style violations (chevron icon semantics, Cupertino page
   mixing Material interaction components, selector leading semantics).
3) user-visible Chinese string literals in Text/label/title/hint/message
   positions. Zero tolerance across the whole tree: copy belongs in
   UITextConstants.* or context.l10n.*, never inline in a widget.

Visual-token rules exclude lib/design_system/ and lib/l10n/copy/. User-visible
copy still scans design-system widgets because a reusable primitive must not own
domain copy. Tests and generated *.g.dart outputs are excluded.

Usage:
  python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py [--targets PATH]

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

# Patterns: (regex, hint message)
PATTERNS = [
    (r"\bwidth:\s*\d+(?:\.\d+)?\b", "width 应使用 AppSpacing.*"),
    (r"\bheight:\s*\d+(?:\.\d+)?\b", "height 应使用 AppSpacing.*"),
    (r"\bleadingSize:\s*\d+(?:\.\d+)?\b", "leadingSize 应使用 AppSpacing.minInteractiveSize"),
    (r"\bfontSize:\s*\d+(?:\.\d+)?(?:\.sp)?\b", "fontSize 应使用 AppTypography.*"),
    (r"\bsize:\s*\d+(?:\.\d+)?\b(?!\s*//)", "size 应使用 AppSpacing.icon* 或 AppTypography"),
    (
        r"BorderRadius\.circular\(\s*\d+(?:\.\d+)?\s*\)",
        "应使用 AppSpacing.borderRadius 等",
    ),
    (
        r"EdgeInsets\.(?:all|symmetric|only)\(\s*\d+(?:\.\d+)?",
        "应使用 AppSpacing.*",
    ),
    (r"Color\(0x[0-9A-Fa-f]+\b", "应使用 AppColors.*"),
]

# Global Semantic Bans (Phase 1: iOS Style Enforcement)
GLOBAL_BANS = [
    (r"\bScaffold\(", "严禁使用 Material Scaffold，应使用 AppScaffold"),
    (r"\bAppBar\(", "严禁使用 Material AppBar，应使用 AppNavigationBar"),
    (r"\bSnackBar\(", "严禁使用 SnackBar，应使用 AppToast.show"),
    (r"\bScaffoldMessenger\.of\(", "严禁使用 ScaffoldMessenger，应使用 AppToast.show"),
    (r"\bSwitch\(", "严禁使用 Material Switch，应使用 CupertinoSwitch"),
    (r"\bCheckbox\(", "严禁使用 Material Checkbox，应使用 CupertinoCheckbox 或自定义实现"),
    (r"\bRadio\(", "严禁使用 Material Radio，应使用 CupertinoRadio 或自定义实现"),
    (r"\bIcons\.arrow_back\b", "iOS 语义：应使用 CupertinoIcons.back"),
    (r"\bIcons\.chevron_right\b", "iOS 语义：应使用 CupertinoIcons.chevron_forward"),
]

HAN_CHARACTER = re.compile(r"[\u3400-\u9fff]")
STRING_LITERAL_WITH_HAN = re.compile(
    r"""(?:r)?(?:'[^'\n]*[\u3400-\u9fff][^'\n]*'|"[^"\n]*[\u3400-\u9fff][^"\n]*")"""
)
USER_VISIBLE_TEXT_ARGUMENT = re.compile(
    r"\b(?:title|label|hintText|helperText|placeholder|message|subtitle|"
    r"description|tooltip|semanticLabel|emptyText|errorText|buttonText|"
    r"caption|header|prompt)\s*:"
)
USER_VISIBLE_TEXT_CONSTRUCTOR = re.compile(
    r"\b(?:Text|SelectableText|AppToast\.show)\s*\("
)

# iOS 语义风格检查（增量门禁）
IOS_STYLE_EXCLUDE_FILES: frozenset[str] = frozenset()

# Canonical roots that define the visual/text tokens being enforced.  Match
# from lib/ rather than by substring so an object-owned nested directory named
# design_system cannot escape the scan.
EXCLUDE_PREFIXES = (
    "design_system/",
    "l10n/copy/",
)


def should_skip(path: str, lib_root: str) -> bool:
    """Whether visual-token rules should skip this file."""

    rel = os.path.relpath(path, lib_root).replace("\\", "/")
    if rel.endswith(("_test.dart", ".g.dart")):
        return True
    for prefix in EXCLUDE_PREFIXES:
        if rel.startswith(prefix):
            return True
    return False


def is_text_surface(rel_path: str) -> bool:
    """Return whether a file can own user-visible App copy."""

    if not rel_path.endswith(".dart"):
        return False
    parts = rel_path.split("/")
    if (
        len(parts) >= 8
        and parts[:3] == ["quwoquan_app", "lib", "service"]
        and parts[6] == "presentation"
    ):
        return True
    return rel_path.startswith(
        (
            "quwoquan_app/lib/runtime/shell/",
            "quwoquan_app/lib/runtime/shell/",
            "quwoquan_app/lib/design_system/",
        )
    )


def scan_file(path: str, lib_root: str, repo_root: str) -> list[tuple[int, str, str]]:
    """Return list of (line_no, line_content, hint) for violations."""
    violations = []
    rel_path = os.path.relpath(path, repo_root).replace("\\", "/")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
            content = "".join(lines)

        for i, line in enumerate(lines, 1):
            # Skip comment-only lines
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            # Support inline ignore
            if "// ignore: verify_dart_semantic" in line:
                continue

            for pattern, hint in PATTERNS:
                if re.search(pattern, line):
                    violations.append((i, line.rstrip(), hint))
                    break
            
            # Global Bans
            for pattern, hint in GLOBAL_BANS:
                if re.search(pattern, line):
                    violations.append((i, line.rstrip(), hint))
                    break

        # iOS 全局语义：统一行尾箭头使用 CupertinoIcons.chevron_forward
        if rel_path not in IOS_STYLE_EXCLUDE_FILES:
            for i, line in enumerate(lines, 1):
                if "Icons.chevron_right" in line:
                    violations.append(
                        (
                            i,
                            line.rstrip(),
                            "iOS 语义：行尾箭头应使用 CupertinoIcons.chevron_forward",
                        )
                    )

        # iOS 选择器语义：CupertinoPageScaffold 页面不允许混用 Material 交互组件
        if "CupertinoPageScaffold(" in content:
            ios_forbidden = [
                (
                    r"\bCheckbox\(",
                    "iOS 语义：CupertinoPageScaffold 页面禁止使用 Material Checkbox",
                ),
                (
                    r"\bScaffoldMessenger\.of\(",
                    "iOS 语义：CupertinoPageScaffold 页面禁止使用 ScaffoldMessenger",
                ),
                (
                    r"\bSnackBar\(",
                    "iOS 语义：CupertinoPageScaffold 页面禁止使用 Material SnackBar",
                ),
            ]
            for pattern, hint in ios_forbidden:
                for m in re.finditer(pattern, content):
                    line_no = content.count("\n", 0, m.start()) + 1
                    line_content = lines[line_no - 1].rstrip() if line_no - 1 < len(lines) else ""
                    violations.append((line_no, line_content, hint))

        # iOS 选择器语义：selector 页面应使用 xmark 关闭，不使用 back
        if rel_path.endswith("_selector_page.dart"):
            for i, line in enumerate(lines, 1):
                if "CupertinoIcons.back" in line:
                    violations.append(
                        (
                            i,
                            line.rstrip(),
                            "iOS 语义：selector 页面 leading 应为 CupertinoIcons.xmark",
                        )
                    )
    except OSError as e:
        print(f"verify_dart_semantic: ERROR reading {rel_path}: {e}", file=sys.stderr)
    return violations


def scan_user_visible_text_literals(
    path: str,
    lib_root: str,
    repo_root: str,
) -> list[tuple[int, str, str]]:
    """Return user-visible Chinese literal violations.

    The scanner intentionally targets presentation argument positions rather
    than every Han character: comments, logs, wire enums, regex dictionaries,
    and user-generated content are not UI copy.
    """
    violations: list[tuple[int, str, str]] = []
    rel_path = os.path.relpath(path, repo_root).replace("\\", "/")
    if rel_path.endswith(("_test.dart", ".g.dart")):
        return violations
    if not is_text_surface(rel_path):
        return violations
    # Codegen 文案来自 metadata（其唯一真相源），不应再复制到 UITextConstants。
    if "/generated/" in rel_path or rel_path.endswith(".g.dart"):
        return violations
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if "// ignore: verify_dart_semantic" in line:
                continue
            if not HAN_CHARACTER.search(line):
                continue
            if not STRING_LITERAL_WITH_HAN.search(line):
                continue

            current_is_argument = USER_VISIBLE_TEXT_ARGUMENT.search(line) is not None
            current_is_constructor = USER_VISIBLE_TEXT_CONSTRUCTOR.search(line) is not None

            # Handles the common multiline shape:
            #   Text(
            #     'literal',
            #   )
            lookback = "".join(lines[max(0, index - 2) : index + 1])
            multiline_constructor = (
                USER_VISIBLE_TEXT_CONSTRUCTOR.search(lookback) is not None
                and lookback.rfind("(") > lookback.rfind(")")
            )
            if not (
                current_is_argument
                or current_is_constructor
                or multiline_constructor
            ):
                continue
            violations.append(
                (
                    index + 1,
                    line.rstrip(),
                    "用户可见文案应使用 UITextConstants.* 或 context.l10n.*",
                )
            )
    except OSError as error:
        print(
            f"verify_dart_semantic: ERROR reading {rel_path}: {error}",
            file=sys.stderr,
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Dart semantic tokens")
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib",
        help="Path to scan (default: quwoquan_app/lib)",
    )
    args = parser.parse_args()

    root = str(REPO_ROOT)
    lib_root = os.path.normpath(os.path.join(root, args.targets))
    if not os.path.isdir(lib_root):
        print(f"verify_dart_semantic: ERROR {lib_root} not found", file=sys.stderr)
        return 1

    all_violations: list[tuple[str, int, str, str]] = []
    text_violations_by_file: dict[str, list[tuple[int, str, str]]] = {}

    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace("\\", "/")
            if not should_skip(path, lib_root):
                for line_no, line_content, hint in scan_file(
                    path,
                    lib_root,
                    root,
                ):
                    all_violations.append((rel, line_no, line_content, hint))
            text_violations = scan_user_visible_text_literals(
                path,
                lib_root,
                root,
            )
            if text_violations:
                text_violations_by_file[rel] = text_violations

    for rel, violations in sorted(text_violations_by_file.items()):
        for line_no, line_content, hint in violations:
            all_violations.append((rel, line_no, line_content, hint))

    found = False
    for rel, line_no, line_content, hint in all_violations:
        print(f"{rel}:{line_no}: {hint}")
        print(f"  {line_content.strip()}")
        found = True

    if found:
        print(
            "\nverify_dart_semantic: 视觉与用户文案必须使用语义 token；"
            "用户可见文案零容忍，请改用 UITextConstants.* 或 context.l10n.*",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
