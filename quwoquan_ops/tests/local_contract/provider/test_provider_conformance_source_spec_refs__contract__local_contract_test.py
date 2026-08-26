"""Provider Conformance 源 spec_ref 提取收编到唯一 lexical 入口的合约。

`_source_spec_refs` 的绑定成员资格来自 feature-tree 库 `extract_spec_refs`
（语法单轨），顺序按原文行序重建——evidence_validation 对 acceptanceRefs 做
精确列表比对，已落盘 evidence 依赖该顺序。fixture 内 marker 与路径用源码级
相邻字符串拆开，避免本文件被证据扫描器计入假绑定。
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import quwoquan_ops.cli.lib.provider_conformance as _pc  # noqa: E402,F401 薄壳先行避免循环导入
from quwoquan_ops.cli.lib.provider_conformance_lib.sources import (  # noqa: E402
    _source_spec_refs,
)

MARKER = "spec_" + "ref"
REF_A = "specs/feature-tree/sample/capability/spec.md#gwt-001"
REF_B = "specs/feature-tree/sample/capability/spec.md#sit-002"
REF_C = "specs/feature-tree/sample/spec.md#req-001"


def test_inline_comment_refs_keep_source_order_and_dedupe() -> None:
    raw = (
        f"# {MARKER}: {REF_B}\n"
        f"# {MARKER}: {REF_A}\n"
        f"# {MARKER}: {REF_B}\n"
        "def test_case():\n    assert True\n"
    )
    assert _source_spec_refs(raw, location="sample.py") == [REF_B, REF_A]


def test_list_block_refs_bind_with_inline_form_in_source_order() -> None:
    """列表块与同行 marker 同源生效；非验收锚点（req）词法上同样是合法绑定。"""
    raw = (
        f"// {MARKER}:\n"
        f"//   - {REF_C}\n"
        f"// {MARKER}: {REF_A}\n"
    )
    assert _source_spec_refs(raw, location="sample.go") == [REF_C, REF_A]


def test_bare_string_is_not_binding_and_absence_fails_closed() -> None:
    """裸字符串不构成绑定；零显式绑定必须 raise，不得降级为空列表。"""
    raw = f'bare = "{REF_A}"\n'
    with pytest.raises(ValueError, match="must declare at least one"):
        _source_spec_refs(raw, location="sample.py")
