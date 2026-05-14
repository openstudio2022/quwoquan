#!/usr/bin/env python3
"""
verify_cloud_services_semantic.py

Scans quwoquan_app/lib/cloud/services/**/*.dart for:
1) hardcoded route literals containing /vN/
2) hardcoded CloudRequestHeaders.forPage('...')
3) hardcoded default magic numbers on limit/pageSize/batchSize/maxParticipants

Excluded paths: */mock/*, generated files, tests.
"""

import argparse
import os
import re
import sys

BASELINE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".verify_cloud_services_semantic_baseline.txt",
)

RULES = [
    (
        re.compile(r"['\"]/v\d+/"),
        "云服务路径应引用 metadata/codegen 常量，禁止硬编码 /vN/ 路由",
    ),
    (
        re.compile(r"CloudRequestHeaders\.forPage\(\s*['\"][^'\"]+['\"]\s*\)"),
        "pageId 应引用生成常量，禁止 forPage('...') 字面量",
    ),
    (
        re.compile(
            r"\b(?:int|double)\s+(?:limit|pageSize|batchSize|maxParticipants)\s*=\s*\d+\b"
        ),
        "默认分页/批量/参与人数值应引用统一常量，禁止硬编码魔鬼数字",
    ),
]

EXCLUDE_SUBSTRINGS = [
    f"{os.sep}mock{os.sep}",
    "generated",
    "_test.dart",
]


def should_skip(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(token.replace("\\", "/") in normalized for token in EXCLUDE_SUBSTRINGS)


def scan_file(path: str, repo_root: str) -> list[tuple[int, str, str]]:
    violations: list[tuple[int, str, str]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                for pattern, hint in RULES:
                    if pattern.search(line):
                        violations.append((line_no, line.rstrip(), hint))
                        break
    except OSError as exc:
        rel = os.path.relpath(path, repo_root).replace("\\", "/")
        print(f"verify_cloud_services_semantic: ERROR reading {rel}: {exc}", file=sys.stderr)
    return violations


def load_baseline() -> set[str]:
    entries: set[str] = set()
    if os.path.isfile(BASELINE_FILE):
        with open(BASELINE_FILE, encoding="utf-8") as handle:
            for line in handle:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    entries.add(entry)
    return entries


def save_baseline(entries: set[str]) -> None:
    with open(BASELINE_FILE, "w", encoding="utf-8") as handle:
        handle.write("# verify_cloud_services_semantic baseline: 已知违规，逐步修复\n")
        for entry in sorted(entries):
            handle.write(entry + "\n")


def collect_violations(target_root: str, repo_root: str) -> list[tuple[str, int, str, str]]:
    found: list[tuple[str, int, str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(target_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            if should_skip(path):
                continue
            rel = os.path.relpath(path, repo_root).replace("\\", "/")
            for line_no, line_content, hint in scan_file(path, repo_root):
                found.append((rel, line_no, line_content, hint))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify cloud service repositories use generated route/page constants"
    )
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib/cloud/services",
        help="Path to scan (default: quwoquan_app/lib/cloud/services)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current violations to baseline and exit 0",
    )
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    target_root = os.path.normpath(os.path.join(repo_root, args.targets))
    if not os.path.isdir(target_root):
        print(f"verify_cloud_services_semantic: ERROR {target_root} not found", file=sys.stderr)
        return 1

    violations = collect_violations(target_root, repo_root)

    if args.update_baseline:
        save_baseline({f"{rel}:{line_no}" for rel, line_no, _content, _hint in violations})
        print(f"verify_cloud_services_semantic: baseline 已更新，共 {len(violations)} 条")
        return 0

    baseline = load_baseline()
    has_new_violation = False
    for rel, line_no, line_content, hint in violations:
        entry = f"{rel}:{line_no}"
        if entry in baseline:
            continue
        print(f"{rel}:{line_no}: {hint}")
        print(f"  {line_content.strip()}")
        has_new_violation = True

    if has_new_violation:
        print(
            "\nverify_cloud_services_semantic: 云服务层必须使用 metadata/codegen 常量",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
