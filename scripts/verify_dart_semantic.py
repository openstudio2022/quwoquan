#!/usr/bin/env python3
"""
verify_dart_semantic.py

Scans quwoquan_app/lib/**/*.dart for:
1) hardcoded visual literals (width, height, leadingSize, fontSize, size,
   EdgeInsets, BorderRadius, Color(0x)) that should use design system tokens
   (AppSpacing, AppTypography, AppColors).
2) iOS semantic style violations (chevron icon semantics, Cupertino page
   mixing Material interaction components, selector leading semantics).

Excluded paths: lib/core/design_system/, lib/core/constants/, *_test.dart

Usage:
  python3 scripts/verify_dart_semantic.py [--targets PATH] [--update-baseline]
  --update-baseline: 将当前违规写入 baseline，用于首次建立或刷新

Exit 0 on success, 1 on failure.
"""

import argparse
import os
import re
import sys

BASELINE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".verify_dart_semantic_baseline.txt"
)

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

# iOS 语义风格检查（增量门禁）
IOS_STYLE_EXCLUDE_FILES = {
    "quwoquan_app/lib/ui/user/pages/author_profile_page.dart",
    "quwoquan_app/lib/features/profile/pages/my_profile_page.dart",
}

# Path substrings to exclude from scanning
EXCLUDE_SUBSTRINGS = [
    os.path.join("lib", "core", "design_system"),
    os.path.join("lib", "core", "constants"),
]


def should_skip(path: str, lib_root: str) -> bool:
    rel = os.path.relpath(path, lib_root).replace("\\", "/")
    if rel.endswith("_test.dart"):
        return True
    for exc in EXCLUDE_SUBSTRINGS:
        if exc in rel:
            return True
    return False


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
            for pattern, hint in PATTERNS:
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


def load_baseline() -> set[str]:
    """Load baseline entries: 'path:line_no'."""
    out = set()
    if os.path.isfile(BASELINE_FILE):
        with open(BASELINE_FILE, encoding="utf-8") as f:
            for line in f:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    out.add(entry)
    return out


def save_baseline(entries: set[str]) -> None:
    """Write baseline file."""
    sorted_entries = sorted(entries)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        f.write("# verify_dart_semantic baseline: 已知违规，逐步修复\n")
        for e in sorted_entries:
            f.write(e + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Dart semantic tokens")
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib",
        help="Path to scan (default: quwoquan_app/lib)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current violations to baseline and exit 0",
    )
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib_root = os.path.normpath(os.path.join(root, args.targets))
    if not os.path.isdir(lib_root):
        print(f"verify_dart_semantic: ERROR {lib_root} not found", file=sys.stderr)
        return 1

    baseline = load_baseline()
    all_violations: list[tuple[str, int, str, str]] = []

    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            if should_skip(path, lib_root):
                continue
            rel = os.path.relpath(path, root).replace("\\", "/")
            for line_no, line_content, hint in scan_file(path, lib_root, root):
                entry = f"{rel}:{line_no}"
                if entry not in baseline:
                    all_violations.append((rel, line_no, line_content, hint))

    if args.update_baseline:
        # Collect all current violations for baseline
        baseline_entries = set()
        for dirpath, _dirnames, filenames in os.walk(lib_root):
            for name in filenames:
                if not name.endswith(".dart"):
                    continue
                path = os.path.join(dirpath, name)
                if should_skip(path, lib_root):
                    continue
                rel = os.path.relpath(path, root).replace("\\", "/")
                for line_no, _lc, _h in scan_file(path, lib_root, root):
                    baseline_entries.add(f"{rel}:{line_no}")
        save_baseline(baseline_entries)
        print(f"verify_dart_semantic: baseline 已更新，共 {len(baseline_entries)} 条")
        return 0

    found = False
    for rel, line_no, line_content, hint in all_violations:
        print(f"{rel}:{line_no}: {hint}")
        print(f"  {line_content.strip()}")
        found = True

    if found:
        print(
            "\nverify_dart_semantic: 硬编码视觉字面量应使用 AppSpacing/AppTypography/AppColors",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
