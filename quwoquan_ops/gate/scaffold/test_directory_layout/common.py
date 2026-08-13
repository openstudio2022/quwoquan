"""失败聚合与各域共用的目录/文件遍历、后缀与桥接标记校验原语。"""

from __future__ import annotations

import sys
from pathlib import Path

from test_directory_layout_lib import ROOT, contains_generated_bridge_marker

from .constants import IGNORED_TEST_CACHE_DIRS, TEST_SUFFIX_BY_LAYER


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: physical test directory layout checked")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def expected_suffix(path: Path, layer: str) -> str | None:
    return TEST_SUFFIX_BY_LAYER.get(path.suffix, {}).get(layer)


def require_layer_suffix(path: Path, layer: str, failures: Failures) -> None:
    suffix = expected_suffix(path, layer)
    if suffix and not path.name.endswith(suffix):
        failures.add(f"{rel(path)} must end with {suffix!r}")


def iter_test_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.name.endswith("_test.dart")
            or path.name.endswith("_test.go")
            or path.name.endswith("_test.py")
        )
    )


def iter_app_test_files(root: Path) -> list[Path]:
    """Return every runnable App Dart/Python test, independent of name prefix."""
    return [
        path
        for path in iter_test_files(root)
        if path.suffix in {".dart", ".py"}
    ]


def ensure_allowed_children(root: Path, allowed: set[str], failures: Failures, *, allow_files: set[str] | None = None) -> None:
    allow_files = allow_files or set()
    if not root.exists():
        failures.add(f"missing test root: {rel(root)}")
        return
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name in IGNORED_TEST_CACHE_DIRS:
            continue
        if child.is_dir() and child.name not in allowed:
            failures.add(f"{rel(child)} is not an allowed test directory")
        if child.is_file() and child.name not in allow_files:
            failures.add(f"{rel(child)} is not allowed at test root")


def verify_support_has_no_tests(root: Path, failures: Failures) -> None:
    if not root.exists():
        return
    for path in iter_test_files(root):
        failures.add(f"{rel(path)} is under support/; support may contain fixtures or harness only")


def verify_no_generated_bridges(root: Path, failures: Failures) -> None:
    if not root.exists():
        return
    for path in iter_test_files(root):
        if contains_generated_bridge_marker(path):
            failures.add(f"{rel(path)} contains generated bridge marker")
