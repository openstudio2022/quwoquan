#!/usr/bin/env python3
"""禁止 HTTP API 路径携带 /vN、/internal/vN、/callbacks/vN 版本段。

扫描 metadata、网关、codegen、Portal、服务手写 client、App/Ops/Data 测试与
活跃特性树/门禁文档等 API 语境。

排除：媒体 object key（media/**/vN/）、第三方 URL、Go module path、
文档身份 schema 名、历史 changelog、负例合同测构造串。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VERSIONED_API = re.compile(
    r"(?:^|[\s\"'`(=\[])/(?:internal/|callbacks/)?v[0-9]+/"
)
MEDIA_OBJECT_KEY = re.compile(r"(?:^|[\s\"'`(=])media/")
IMMUTABLE_MEDIA_SLICE_ASSERTION = re.compile(
    r"(?:public\s+(?:slice|fixture)|公共媒体).*(?:canonical|唯一).*/v[0-9]+/",
    re.I,
)
THIRD_PARTY = re.compile(
    r"https?://(?:api\.openverse|api2?\.cursor|cursor\.com|openai\.com|github\.com|"
    r"restapi\.amap\.com|amap\.com)"
)
THIRD_PARTY_PATH = re.compile(
    r"""["'`]/v[0-9]+/(?:geocode|place|direction|weather|distance)/"""
)
EXTERNAL_PROVIDER_PATH = re.compile(
    r"""["'`]/v[0-9]+/(?:chat/completions(?:["'`]|$)|projects/)"""
)
GO_MODULE = re.compile(r"github\.com/.+/v[0-9]+")
SCHEMA_IDENTITY = re.compile(
    r"""(?:schemaVersion|schema)\s*[:=]\s*["'][^"']*/v?[0-9]+["']"""
)

SCAN_ROOTS = [
    "quwoquan_service/contracts",
    "quwoquan_service/internal/metadata",
    "quwoquan_service/services",
    "quwoquan_service/scripts",
    "quwoquan_ops/environments",
    "quwoquan_ops/cli",
    "quwoquan_ops/gate",
    "quwoquan_ops/portal/src",
    "quwoquan_ops/observability",
    "quwoquan_ops/tests",
    "quwoquan_app/lib/cloud/runtime/generated",
    "quwoquan_app/packages/quwoquan_cloud_contracts",
    "quwoquan_app/configs",
    "quwoquan_app/scripts",
    "quwoquan_app/test",
    "quwoquan_data/scripts/content/release",
    "quwoquan_data/tests",
    "specs/feature-tree",
    "quwoquan_ops/policies/gates",
    ".cursor/rules",
]

SUFFIXES = {
    ".go",
    ".dart",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".ts",
    ".tsx",
    ".sh",
    ".md",
    ".mdc",
}
EXTRA_NAMES = {"Caddyfile"}
SKIP_DIR_PARTS = {
    "node_modules",
    ".git",
    "vendor",
    "__pycache__",
    ".dart_tool",
    "test_fixtures",
    "changelog",  # historical CR narratives
}


def should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIR_PARTS:
        return True
    if "media" in path.parts and "test_fixtures" in path.as_posix():
        return True
    # Gate script and its contract test intentionally mention forbidden patterns.
    if path.name == "verify_api_path_unversioned.py":
        return True
    if path.name == "verify_api_path_runtime_unversioned.py":
        return True
    if path.name == "verify_entrypoint_script_paths.py":
        return True
    if path.name == "test_api_path_unversioned__contract__local_contract_test.py":
        return True
    if path.name == (
        "test_api_path_runtime_unversioned__contract__local_contract_test.py"
    ):
        return True
    if path.name == "allowed_path__contract__local_contract_test.go":
        return True
    return False


def line_is_excluded(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return True
    if MEDIA_OBJECT_KEY.search(line) and re.search(r"/v[0-9]+/", line):
        if not re.search(r"""["'`\s(=]/(?:internal/|callbacks/)?v[0-9]+/""", line):
            if not re.search(r"https?://[^/\s\"']+/(?:internal/|callbacks/)?v[0-9]+/", line):
                return True
    if IMMUTABLE_MEDIA_SLICE_ASSERTION.search(line):
        return True
    if (
        THIRD_PARTY.search(line)
        or GO_MODULE.search(line)
        or THIRD_PARTY_PATH.search(line)
        or EXTERNAL_PROVIDER_PATH.search(line)
    ):
        return True
    if SCHEMA_IDENTITY.search(line):
        return True
    if "versioned API path is forbidden" in line or "media object keys may contain" in line:
        return True
    if "VERSIONED_API.search" in line:
        return True
    # Negative assertions that forbid versioned paths.
    if "assertNotIn" in line and "/v1/" in line:
        return True
    if 'pathTemplate: "/v1/' in line and "assertNotIn" in line:
        return True
    if "/v1/" in line and "StatusNotFound" in line:
        return True
    return False


def iter_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        if base.is_file():
            files.append(base)
            continue
        for path in base.rglob("*"):
            if not path.is_file() or should_skip_path(path):
                continue
            if path.name in EXTRA_NAMES or path.suffix in SUFFIXES:
                files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line_is_excluded(line):
                continue
            if VERSIONED_API.search(line):
                failures.append(f"{rel}:{lineno}: versioned API path is forbidden: {line.strip()}")
    if failures:
        print("[verify_api_path_unversioned] FAIL:", file=sys.stderr)
        for item in failures[:200]:
            print(f"  {item}", file=sys.stderr)
        if len(failures) > 200:
            print(f"  ... and {len(failures) - 200} more", file=sys.stderr)
        return 1
    print("[verify_api_path_unversioned] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
