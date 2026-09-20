"""feature_tree CLI 的实现包。

唯一稳定入口是 ``quwoquan_ops/cli/feature_tree.py``（薄壳 re-export）；
本包按职责切分：

- ``context``：REPO_ROOT / TREE_ROOT / OUTPUT_ROOT（测试可 monkeypatch 的配置）。
- ``patterns``：全部正则与目录/文件闭集常量。
- ``nodes``：Node 与目录原生树发现。
- ``parsing``：spec/design Markdown 解析（锚点、OPEN 与结果子句）。
- ``gitio``：git 增量与 HEAD 文本读取。
- ``delta``：Git 增量语义（锚点变化、OPEN/子句棘轮触发点）。
- ``evidence``：测试树 spec_ref 证据扫描。
- ``commands``：context / overview / change-report 子命令。
- ``verify``：verify 子命令与结构校验。
- ``cli_entry``：argparse 与 main。
"""
from __future__ import annotations

from . import context  # noqa: F401
from .cli_entry import build_parser, main  # noqa: F401
from .commands import (  # noqa: F401
    command_change_report,
    command_context,
    command_overview,
    write_output,
)
from .delta import (  # noqa: F401
    clause_binding_transitions,
    open_anchor_ratchet_targets,
    semantic_anchor_changes,
)
from .evidence import (  # noqa: F401
    canonical_spec_ref,
    extract_spec_refs,
    iter_test_files,
    test_spec_refs,
)
from .gitio import (  # noqa: F401
    git_changed_paths,
    git_head_text,
    git_index_text,
    git_range_paths,
    git_staged_paths,
    use_private_index_documents,
)
from .nodes import Node, discover_nodes, node_for_spec, parent_chain  # noqa: F401
from .parsing import (  # noqa: F401
    acceptance_clause_counts,
    acceptance_clause_counts_in_text,
    acceptance_ids,
    acceptance_refs_in_open,
    acceptance_refs_in_open_text,
    anchor_sections,
    anchorless_opens_in_text,
    block_open_items,
    headings,
    ids,
    invalid_acceptance_refs_in_open,
    markdown_anchor,
    open_blocks_in_text,
    open_completion_field,
    open_item_details,
    outcome_bullets,
    outcome_clause_count,
    outcome_sub_clauses,
    section,
    title,
    validate_acceptance_clause_coverage,
)
from .patterns import *  # noqa: F401,F403
from .verify import (  # noqa: F401
    UNBOUND_COMPOUND_BASELINE,
    command_verify,
    unbound_compound_anchors,
    validate_journey_bidirection,
    validate_links,
    validate_policy_governance,
    validate_repo_spec_paths,
)
