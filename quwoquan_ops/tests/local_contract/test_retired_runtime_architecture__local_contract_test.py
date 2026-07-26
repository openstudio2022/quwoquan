from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_retired_runtime_architecture import (
    RETIRED_TERMS,
    collect_issues,
    scan_instruction_text,
    scan_markdown_links,
)


def test_current_instruction_surface_has_no_retired_runtime_architecture() -> None:
    assert collect_issues() == []


@pytest.mark.parametrize("term", RETIRED_TERMS)
def test_active_instruction_rejects_retired_term(term: str) -> None:
    issues = scan_instruction_text(
        ".cursor/commands/extend.md",
        f"服务必须使用 {term} 作为当前实现。\n",
    )
    assert issues


def test_active_instruction_rejects_dynamic_storage_factory() -> None:
    issues = scan_instruction_text(
        ".cursor/commands/extend.md",
        "根据 storage_backend 自动选择并路由到对应 factory。\n",
    )
    assert any("动态 storage backend factory" in issue for issue in issues)


def test_active_instruction_rejects_deleted_document_reference() -> None:
    issues = scan_instruction_text(
        "specs/README.md",
        "当前规范见 specs/runtime_framework_spec.md。\n",
    )
    assert any("已删除第二真相源" in issue for issue in issues)


def test_active_instruction_rejects_deleted_feature_node_reference() -> None:
    issues = scan_instruction_text(
        "specs/feature-tree/runtime/README.md",
        "当前能力节点为 runtime-repository。\n",
    )
    assert any("已删除 feature-tree 节点" in issue for issue in issues)


def test_changed_entry_docs_reject_broken_markdown_link(
    tmp_path: Path,
) -> None:
    source = tmp_path / "specs" / "entry.md"
    source.parent.mkdir(parents=True)
    issues = scan_markdown_links(
        "specs/entry.md",
        "[架构](missing.md)\n",
        tmp_path,
    )
    assert any("Markdown 链接目标不存在" in issue for issue in issues)


def test_canonical_design_may_name_a_retired_term_only_to_forbid_it() -> None:
    issues = scan_instruction_text(
        "specs/feature-tree/design.md",
        "禁止公共化：\n\n- GenericAggregateStore。\n",
    )
    assert issues == []
