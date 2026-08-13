"""Data 三层测试目录与 test_<subject>__<case>__<facet> 命名校验。"""

from __future__ import annotations

from test_directory_layout_lib import DATA_ROOT, LAYERS

from .common import (
    Failures,
    ensure_allowed_children,
    rel,
    require_layer_suffix,
    verify_support_has_no_tests,
)
from .constants import DATA_LAYER_DIRS, DATA_TEST_NAME_RE, DATA_TEST_ROOT_DIRS


def verify_data(failures: Failures) -> None:
    ensure_allowed_children(DATA_ROOT, DATA_TEST_ROOT_DIRS, failures, allow_files={"conftest.py"})
    verify_support_has_no_tests(DATA_ROOT / "support", failures)
    for layer in sorted(LAYERS):
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
