"""coverage-map 门禁的绑定提取合约：语法解析同源于 feature-tree 唯一入口。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "gate" / "scaffold" / "verify_test_coverage_map.py"
SPEC = importlib.util.spec_from_file_location("verify_test_coverage_map", MODULE_PATH)
assert SPEC and SPEC.loader
coverage_map = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage_map
SPEC.loader.exec_module(coverage_map)

# fixture 内的标记用拼接构造，避免本测试文件自身被证据扫描器计入假绑定。
REF = "spec_" + "ref"


def test_inline_marker_bindings_include_app_root_uat_and_nested_acceptance() -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001
    source = "\n".join(
        (
            f"// {REF}: specs/feature-tree/spec.md#uat-009",
            f"// {REF}: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001",
        )
    )

    assert coverage_map.case_bindings(source) == [
        ("specs/feature-tree/runtime/runtime-test-pyramid/spec.md", "sit-001"),
        ("specs/feature-tree/spec.md", "uat-009"),
    ]


def test_list_block_bindings_count_with_clause_suffix_stripped() -> None:
    """列表块与同行形态同源生效；`.tN` 子句剥离后同文件去重。"""
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001
    source = "\n".join(
        (
            '"""Docstring contract.',
            f"{REF}:",
            "  - specs/feature-tree/runtime/runtime-test-pyramid/spec.md#gwt-004.t1",
            "  - specs/feature-tree/runtime/runtime-test-pyramid/spec.md#gwt-004.t2",
            "  - specs/feature-tree/spec.md#uat-002",
            '"""',
        )
    )

    assert coverage_map.case_bindings(source) == [
        ("specs/feature-tree/runtime/runtime-test-pyramid/spec.md", "gwt-004"),
        ("specs/feature-tree/spec.md", "uat-002"),
    ]


def test_bare_strings_and_non_acceptance_anchors_are_not_bindings() -> None:
    """裸字符串、`not_a_...` 相似 token 与非验收锚点不得进入映射。"""
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001
    source = "\n".join(
        (
            'bare = "specs/feature-tree/spec.md#uat-003"',
            f'not_a_{REF} = "specs/feature-tree/spec.md#uat-008"',
            f"# {REF}: specs/feature-tree/spec.md#req-004",
        )
    )

    assert coverage_map.case_bindings(source) == []
