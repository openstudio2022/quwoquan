"""Git 增量语义：锚点变化与 OPEN/子句棘轮触发点。"""
from __future__ import annotations

from . import context, gitio
from .parsing import (
    acceptance_clause_counts_in_text,
    acceptance_refs_in_open_text,
    anchor_sections,
    open_blocks_in_text,
)

# git 读取经 gitio 模块属性访问，保证测试对 gitio 的 monkeypatch 全链路生效。


def semantic_anchor_changes(rel: str) -> dict[str, list[str]]:
    path = context.REPO_ROOT / rel
    before = anchor_sections(gitio.git_head_text(rel))
    after = anchor_sections(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        "added": sorted(set(after) - set(before)),
        "modified": sorted(key for key in set(before) & set(after) if before[key] != after[key]),
        "deleted": sorted(set(before) - set(after)),
    }


def open_anchor_ratchet_targets(spec_rel: str) -> set[str]:
    """返回本次 Git 增量中新增或改写的 OPEN。

    与子句级棘轮同一思路：存量不被追溯，代价只由真正动到该 OPEN 的改动承担，
    因此不需要 allowlist 或豁免名单。
    """

    path = context.REPO_ROOT / spec_rel
    if not path.is_file():
        return set()
    before = open_blocks_in_text(gitio.git_head_text(spec_rel))
    after = open_blocks_in_text(path.read_text(encoding="utf-8"))
    return {open_id for open_id, block in after.items() if before.get(open_id) != block}


def clause_binding_transitions(spec_rel: str) -> set[str]:
    """返回本次 Git 增量中「开始声称已闭合」的验收锚点。

    棘轮触发点，覆盖三种声称闭合的动作：认领它的 OPEN 被删除、直接新增一个不挂
    OPEN 的锚点、以及改写一个已声称闭合锚点的正文。存量锚点不被追溯，代价只由
    真正做出闭合声称的改动承担。
    """

    head = gitio.git_head_text(spec_rel)
    path = context.REPO_ROOT / spec_rel
    now = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not now:
        return set()
    before_pending = acceptance_refs_in_open_text(head)
    after_pending = acceptance_refs_in_open_text(now)
    before_clauses = acceptance_clause_counts_in_text(head)
    after_clauses = acceptance_clause_counts_in_text(now)
    transitions: set[str] = set()
    for anchor_id, count in after_clauses.items():
        if anchor_id in after_pending:
            continue
        was_pending = anchor_id in before_pending
        newly_added = anchor_id not in before_clauses
        body_changed = anchor_id in before_clauses and before_clauses[anchor_id] != count
        if was_pending or newly_added or body_changed:
            transitions.add(anchor_id)
    return transitions
