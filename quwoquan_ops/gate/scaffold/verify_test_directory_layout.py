#!/usr/bin/env python3
"""Verify physical three-layer test directories and canonical file names."""
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001

from __future__ import annotations

import re
import sys
from pathlib import Path

from test_directory_layout_lib import (
    APP_ROOT,
    DATA_ROOT,
    LAYERS,
    OPS_ACCEPTANCE_ROOT,
    OPS_TEST_ROOT,
    ROOT,
    RUNTIME_ROOT,
    RUNTIME_TEST_ROOT,
    SERVICE_DOMAIN_ROOT,
    SERVICE_ROOT,
    contains_generated_bridge_marker,
    iter_canonical_files,
    evidence_path_is_canonical,
)


APP_LAYER_DIRS = {
    "local_contract": {"ui", "cloud", "core", "app", "quality"},
    "api_integration": {"ui", "cloud", "observability", "security", "performance"},
    "user_acceptance": {"journeys", "pages", "patrol", "quality"},
}
APP_TEST_ROOT_DIRS = {*LAYERS, "support"}
DATA_TEST_ROOT_DIRS = {*LAYERS, "support"}
DATA_LAYER_DIRS = {
    "local_contract": {"core", "execution", "source", "homepage", "post", "governance", "release"},
    "api_integration": {"execution", "release"},
    "user_acceptance": {"journeys", "quality"},
}
OPS_TEST_ROOT_DIRS = {"local_contract", "acceptance", "support"}
OPS_ACCEPTANCE_DIRS = {"api_integration", "user_acceptance"}
SERVICE_TEST_DIRS = {"local_contract", "api_integration", "support"}
IGNORED_TEST_CACHE_DIRS = {"__pycache__", ".pytest_cache"}

TEST_SUFFIX_BY_LAYER = {
    ".dart": {
        "local_contract": "__local_contract_test.dart",
        "api_integration": "__api_integration_test.dart",
        "user_acceptance": "__user_acceptance_test.dart",
    },
    ".go": {
        "local_contract": "__local_contract_test.go",
        "api_integration": "__api_integration_test.go",
    },
    ".py": {
        "local_contract": "__local_contract_test.py",
        "api_integration": "__api_integration_test.py",
        "user_acceptance": "__user_acceptance_test.py",
    },
}
DATA_TEST_NAME_RE = re.compile(
    r"^test_[a-z0-9]+(?:_[a-z0-9]+)*__[a-z0-9]+(?:_[a-z0-9]+)*__"
    r"(functional|contract|reliability|availability|observability|experience|security|performance|data_consistency)"
    r"__(local_contract|api_integration|user_acceptance)_test\.py$"
)


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
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and (
            path.name.endswith("_test.dart")
            or path.name.endswith("_test.go")
            or (path.name.startswith("test_") and path.name.endswith(".py"))
        )
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


def verify_app(failures: Failures) -> None:
    ensure_allowed_children(APP_ROOT, APP_TEST_ROOT_DIRS, failures)
    verify_support_has_no_tests(APP_ROOT / "support", failures)
    for layer, allowed_dirs in APP_LAYER_DIRS.items():
        layer_root = APP_ROOT / layer
        ensure_allowed_children(layer_root, allowed_dirs, failures)
        for path in sorted(layer_root.rglob("*_test.dart")):
            require_layer_suffix(path, layer, failures)
        for child in (sorted(layer_root.iterdir()) if layer_root.exists() else []):
            if child.is_file():
                failures.add(f"{rel(child)} must live under a test object directory")


def verify_data(failures: Failures) -> None:
    ensure_allowed_children(DATA_ROOT, DATA_TEST_ROOT_DIRS, failures, allow_files={"conftest.py"})
    verify_support_has_no_tests(DATA_ROOT / "support", failures)
    for layer in LAYERS:
        layer_root = DATA_ROOT / layer
        if not layer_root.exists():
            failures.add(f"missing data test layer: {rel(layer_root)}")
            continue
        ensure_allowed_children(layer_root, DATA_LAYER_DIRS[layer], failures)
        for path in sorted(layer_root.rglob("test_*.py")):
            require_layer_suffix(path, layer, failures)
            if not DATA_TEST_NAME_RE.fullmatch(path.name):
                failures.add(
                    f"{rel(path)} must use test_<subject>__<case>__<facet>__{layer}_test.py"
                )


def verify_ops(failures: Failures) -> None:
    ensure_allowed_children(OPS_TEST_ROOT, OPS_TEST_ROOT_DIRS, failures)
    verify_support_has_no_tests(OPS_TEST_ROOT / "support", failures)
    if OPS_ACCEPTANCE_ROOT.exists():
        ensure_allowed_children(OPS_ACCEPTANCE_ROOT, OPS_ACCEPTANCE_DIRS, failures)
    for path in sorted((OPS_TEST_ROOT / "local_contract").rglob("test_*.py")):
        require_layer_suffix(path, "local_contract", failures)
    for layer in OPS_ACCEPTANCE_DIRS:
        layer_root = OPS_ACCEPTANCE_ROOT / layer
        if not layer_root.exists():
            failures.add(f"missing ops acceptance layer: {rel(layer_root)}")
            continue
        for path in sorted(layer_root.rglob("test_*.py")):
            require_layer_suffix(path, layer, failures)


def verify_service_tests_dir(tests_root: Path, failures: Failures) -> None:
    ensure_allowed_children(tests_root, SERVICE_TEST_DIRS, failures, allow_files={"__init__.py"})
    verify_support_has_no_tests(tests_root / "support", failures)
    if (tests_root / "ops").exists():
        failures.add(f"{rel(tests_root / 'ops')} is retired; cross-environment tests belong to quwoquan_ops/tests/acceptance")
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, failures)
        for path in sorted(layer_root.rglob("test_*.py")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, failures)


def require_service_object_test_path(
    path: Path,
    layer_root: Path,
    failures: Failures,
) -> None:
    parts = path.relative_to(layer_root).parts
    if len(parts) < 3:
        failures.add(
            f"{rel(path)} must live under "
            "<context>/<object>/.../file"
        )
        return
    if any(part in {"internal", "cmd", "generated"} for part in parts[:2]):
        failures.add(
            f"{rel(path)} must use a business context/object owner before "
            "any optional Go package subpath"
        )


def verify_service(failures: Failures) -> None:
    if not SERVICE_ROOT.exists():
        failures.add(f"missing service root: {rel(SERVICE_ROOT)}")
        return
    for service_dir in sorted(path for path in SERVICE_ROOT.iterdir() if path.is_dir()):
        tests_root = service_dir / "tests"
        if tests_root.exists():
            verify_service_tests_dir(tests_root, failures)
        for path in sorted(service_dir.rglob("*_test.go")):
            rel_text = rel(path)
            if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                continue
            failures.add(
                f"{rel_text} is a service test outside canonical "
                "tests/local_contract/<context>/<object> or "
                "tests/api_integration/<context>/<object>"
            )
        for path in sorted(service_dir.rglob("test_*.py")):
            rel_text = rel(path)
            if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                continue
            failures.add(
                f"{rel_text} is a service test outside canonical "
                "tests/local_contract/<context>/<object> or "
                "tests/api_integration/<context>/<object>"
            )


def verify_runtime(failures: Failures) -> None:
    if not RUNTIME_ROOT.exists():
        failures.add(f"missing runtime root: {rel(RUNTIME_ROOT)}")
        return
    verify_runtime_tests_dir(RUNTIME_TEST_ROOT, failures)
    for path in sorted(RUNTIME_ROOT.rglob("*_test.go")):
        rel_text = rel(path)
        if (
            "/tests/local_contract/" in rel_text
            or "/tests/api_integration/" in rel_text
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "//go:build api_integration" in text:
            failures.add(
                f"{rel_text} is a runtime api_integration test outside canonical "
                "tests/api_integration/<package>"
            )


def verify_runtime_tests_dir(tests_root: Path, failures: Failures) -> None:
    ensure_allowed_children(
        tests_root,
        SERVICE_TEST_DIRS,
        failures,
        allow_files={"__init__.py"},
    )
    verify_support_has_no_tests(tests_root / "support", failures)
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            parts = path.relative_to(layer_root).parts
            if len(parts) != 2:
                failures.add(
                    f"{rel(path)} must live directly under <runtime-package>/file"
                )
            elif parts[0] in {"internal", "cmd", "generated"}:
                failures.add(
                    f"{rel(path)} must not recreate a production source root "
                    "inside runtime tests/"
                )


def verify_all_canonical_files_recognized(failures: Failures) -> None:
    for _, path, layer in iter_canonical_files():
        if not evidence_path_is_canonical(rel(path)):
            failures.add(f"{rel(path)} is not recognized as canonical {layer} evidence")


def main() -> int:
    failures = Failures()
    verify_app(failures)
    verify_data(failures)
    verify_ops(failures)
    verify_service(failures)
    verify_runtime(failures)
    verify_no_generated_bridges(APP_ROOT, failures)
    verify_no_generated_bridges(DATA_ROOT, failures)
    verify_no_generated_bridges(OPS_TEST_ROOT, failures)
    verify_no_generated_bridges(SERVICE_ROOT, failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "internal", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "runtime", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "tools", failures)
    verify_all_canonical_files_recognized(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
