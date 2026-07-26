#!/usr/bin/env python3
"""拒绝活跃运行入口重新写入退役 output/state 路径。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = (
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_data" / "scripts",
    ROOT / "quwoquan_ops",
    ROOT / "quwoquan_service" / "scripts",
    ROOT / "quwoquan_service" / "services",
    ROOT / ".github" / "workflows",
    ROOT / ".cursor" / "commands",
    ROOT / ".cursor" / "skills" / "environment-ops",
)
ROOT_CONFIG_FILES = (
    ROOT / "Makefile",
    ROOT / "pytest.ini",
)
TEXT_SUFFIXES = frozenset({".py", ".sh", ".yaml", ".yml", ".md", ".dart", ".go", ".json", ".toml"})
NEGATIVE_CONTRACT_FILES = {
    ROOT / "quwoquan_data" / "scripts" / "verify" / "verify_output_root_isolation.py",
    ROOT / "quwoquan_ops" / "gate" / "verify_dev_up_cli_surface.py",
    ROOT / "quwoquan_ops" / "gate" / "verify_root_layout.py",
}
RETIRED_PATTERNS = (
    re.compile(r"data/local/runtime"),
    re.compile(r"data/release(?:/|$|(?=[._-]))"),
    re.compile(r"data-releases"),
    re.compile(r"(?:QWQ_OUTPUT_ROOT|\.qwq_output)/(?:local|runs|release|observability|repo)(?:/|$|(?=[._-]))"),
    re.compile(r"env/(?:alpha|beta|gamma|prod|repo)/(?:packages|runtime|cache|tmp)(?:/|$|(?=[._-]))"),
    re.compile(r"env/(?:alpha|beta|gamma|prod|repo)/release(?:/|$|(?=[._-]))"),
    re.compile(
        r"env/(?:alpha|beta|gamma|prod|repo)/local/[^\s\"']+/process/"
        r"(?:config|configuration|caddy|pki|tls|certificates?)(?:/|$|(?=[._-]))"
    ),
    re.compile(
        r"env/(?:alpha|beta|gamma|prod|repo)/local/[^\s\"']+/"
        r"(?:config|configuration|caddy|pki|tls|certificates?)(?:/|$|(?=[._-]))"
    ),
    re.compile(r"(?:QWQ_OUTPUT_ROOT|\.qwq_output)/data/(?:runtime|runs|objects|cache|tmp|observability)(?:/|$|(?=[._-]))"),
    re.compile(r"env/prod/control(?:/|$|(?=[._-]))"),
    re.compile(r"env/repo/local/test-cache(?:/|$|(?=[._-]))"),
    re.compile(
        r'''(?:QWQ_OUTPUT_ROOT|\.qwq_output)/[^\n]*(?:control_plane|prompts|templates|schema|specs|policies|reference|requirements\.txt)(?:/|$|["'\s])'''
    ),
    re.compile(r"QWQ_STATE_ROOT|\.qwq_state"),
)


def _sources() -> list[Path]:
    files: list[Path] = [path for path in ROOT_CONFIG_FILES if path.is_file()]
    for source_root in SOURCE_ROOTS:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            relative_parts = path.relative_to(source_root).parts
            if (
                path.is_file()
                and path.suffix in TEXT_SUFFIXES
                and not {"node_modules", "vendor", ".qwq_output"}.intersection(relative_parts)
                and path != Path(__file__)
                and path not in NEGATIVE_CONTRACT_FILES
                and "/tests/" not in path.as_posix()
                and not path.name.startswith("test_")
            ):
                files.append(path)
    return sorted(set(files))


def source_path_issues() -> list[str]:
    issues: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in RETIRED_PATTERNS):
                try:
                    rendered = path.relative_to(ROOT).as_posix()
                except ValueError:
                    rendered = path.as_posix()
                issues.append(f"{rendered}:{line_number}: retired output/state path")
    return issues


def main() -> int:
    issues = source_path_issues()
    if issues:
        print("[verify_output_path_source_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_output_path_source_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
