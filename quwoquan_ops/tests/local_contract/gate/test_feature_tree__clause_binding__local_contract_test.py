"""feature_tree 子句级绑定与棘轮契约（从 directory_native 套件按场景拆出）。

覆盖：结果子句计数、AND/分隔符折叠漏口、子句级绑定完整性、棘轮触发点
（OPEN 删除/新增闭合声称/anchorless OPEN）与 baseline 登记语义。
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree", MODULE_PATH)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)

# 实现单轨位于包内；monkeypatch 必须指向真实绑定所在的模块：
# 路径配置在 context，git 读取在 gitio，报告落盘在 commands。
from quwoquan_ops.cli.lib.feature_tree import commands as ft_commands  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import context as ft_context  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import gitio as ft_gitio  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import verify as ft_verify  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")



COMPOSITE_ANCHOR = (
    "### GWT-001 复合验收\n\n"
    "- GIVEN 前置成立。\n"
    "- WHEN 参与者发起动作。\n"
    "- THEN 第一条结果。\n"
    "- THEN 第二条结果。\n"
    "- THEN 第三条结果。\n"
)

PRECONDITION_AND_ANCHOR = (
    "### GWT-003 前置续写\n\n"
    "- GIVEN 条件甲。\n"
    "- AND 条件乙。\n"
    "- WHEN 参与者发起动作。\n"
    "- THEN 唯一结果。\n"
)

FOLDED_AND_ANCHOR = (
    "### GWT-004 把独立结果折叠进 AND\n\n"
    "- GIVEN 前置成立。\n"
    "- WHEN 参与者发起动作。\n"
    "- THEN 第一条独立结果。\n"
    "- AND 第二条独立结果。\n"
    "- AND 第三条独立结果。\n"
)

DOM_ANCHOR = (
    "### DOM-001 领域验收\n\n"
    "- 条件：前置成立。\n"
    "- 可观察结果：第一条结果。\n"
    "- 第二条结果。\n"
    "- 禁止结果：第三条结果。\n"
)

SEPARATOR_FOLDED_ANCHOR = (
    "### GWT-005 把独立结果折叠进同一个 bullet\n\n"
    "- GIVEN 前置成立。\n"
    "- WHEN 参与者发起动作。\n"
    "- THEN 返回 canonical failure，且不产生伪成功事实。\n"
    "- AND 事件写入审计流；告警在同一窗口触发。\n"
)

NATURAL_PHRASING_ANCHOR = (
    "### GWT-006 单一结果的自然中文表述\n\n"
    "- GIVEN 前置成立。\n"
    "- WHEN 参与者发起动作。\n"
    "- THEN 非 mutual 且未拉黑的用户可发起一条 pending 请求。\n"
    "- AND 合并结果按 seq 严格有序且无重复，终态明确且可恢复。\n"
)


def test_clause_count_treats_every_outcome_bullet_as_one_clause() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    counts = feature_tree.acceptance_clause_counts_in_text(
        COMPOSITE_ANCHOR + "\n" + DOM_ANCHOR + "\n" + PRECONDITION_AND_ANCHOR
    )

    # 一个顶层结果 bullet 就是一条子句；GIVEN/WHEN/条件 是前置条件。
    assert counts == {"GWT-001": 3, "DOM-001": 3, "GWT-003": 1}


def test_and_cannot_hide_an_independent_outcome_from_clause_counting() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 折叠漏口：把独立结果写成 AND 曾使锚点降为 C=1 并完全豁免复合规则。
    counts = feature_tree.acceptance_clause_counts_in_text(FOLDED_AND_ANCHOR)
    assert counts == {"GWT-004": 3}

    # 判据只看行首关键字，不读标点，因此删掉句号不能把子句数改回 1。
    assert feature_tree.acceptance_clause_counts_in_text(
        FOLDED_AND_ANCHOR.replace("独立结果。", "独立结果")
    ) == {"GWT-004": 3}

    # 缩进续行属于同一个 bullet，不额外计一条子句。
    assert feature_tree.outcome_clause_count(
        "- GIVEN 前置成立。\n- THEN 一条结果，\n  续写仍在同一 bullet 内。\n"
    ) == 1


def test_separator_folded_outcomes_each_take_one_clause_slot() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 折叠漏口：把多个相互独立的结果用 `；` 或 `，且` 塞进同一个 bullet，曾让整组结果
    # 只占一个子句位，测试覆盖其中任意一个即让全部结果显示为已绑定。
    assert feature_tree.acceptance_clause_counts_in_text(SEPARATOR_FOLDED_ANCHOR) == {
        "GWT-005": 4
    }

    assert feature_tree.outcome_sub_clauses(
        "THEN 返回 canonical failure，且不产生伪成功事实。"
    ) == ["THEN 返回 canonical failure", "不产生伪成功事实。"]
    assert feature_tree.outcome_sub_clauses(
        "THEN 事件写入审计流；告警在同一窗口触发。"
    ) == ["THEN 事件写入审计流", "告警在同一窗口触发。"]
    # `，并` 与 `，同时` 同样是顶层并列小句的停顿标记。
    assert len(feature_tree.outcome_sub_clauses("THEN 写入回执，并立即回流详情页。")) == 2
    assert len(feature_tree.outcome_sub_clauses("THEN 关联日志与指标，同时限制标签基数。")) == 2


def test_single_outcome_natural_phrasing_is_not_split_into_noise() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 判据是「前置停顿 + 并列连词」：定语并列与形容词并列从不在连词前带停顿，
    # 因此同一个结果的多个属性不会被拆成互相无法独立验证的噪音子句。
    assert feature_tree.acceptance_clause_counts_in_text(NATURAL_PHRASING_ANCHOR) == {
        "GWT-006": 2
    }

    for single in (
        "THEN 非 mutual 且未拉黑的用户可发起一条 pending 请求。",
        "THEN 合并结果按 seq 严格有序且无重复。",
        "THEN 评论、超时与权限拒绝都有明确且可恢复的终态。",
        # `以及` 只并列名词短语，拆开会撕碎同一个主语列表。
        "THEN completed 的 answerText，以及状态与 trace 仍来自 Run Store。",
        # `并发/并行/并列` 是构词，不是并列连词。
        "THEN 聚合 feed 只使用有界并发扇出，并发请求数不超过配额上限。",
    ):
        assert feature_tree.outcome_sub_clauses(single) == [single], single


def test_code_span_punctuation_is_not_a_clause_separator() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 标识符里的分号属于代码片段，不表达并列结果。
    assert feature_tree.outcome_sub_clauses(
        "THEN 返回 `a；b` 作为单个 token。"
    ) == ["THEN 返回 `a；b` 作为单个 token。"]


def test_separator_folded_outcome_cannot_escape_clause_level_binding() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 负例：一条 `；` 折叠的 THEN 声称已闭合时，必须逐条绑定，不能以「只有一条子句」
    # 为由整体豁免复合判据。
    counts = feature_tree.acceptance_clause_counts_in_text(
        "### GWT-007 折叠后声称已闭合\n\n"
        "- GIVEN 前置成立。\n"
        "- WHEN 参与者发起动作。\n"
        "- THEN 返回 409；写入审计事件。\n"
    )
    assert counts == {"GWT-007": 2}

    errors = feature_tree.validate_acceptance_clause_coverage(
        "specs/feature-tree/domain/spec.md", counts, set(), {}, {"GWT-007"}
    )
    assert len(errors) == 1
    assert "gwt-007.t1..t2" in errors[0]


def test_nested_bullets_do_not_add_outcome_clauses() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    assert feature_tree.outcome_clause_count(
        "- GIVEN 前置成立。\n- THEN 一条结果。\n  - 说明：不是独立结果；也不是子句。\n"
    ) == 1


def test_anchorless_open_completion_is_detected_and_ratcheted(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    tautology = (
        "### OPEN-001 同义反复\n\n"
        "- 影响或价值：尚缺主路径由真实服务契约驱动。\n"
        "- 完成判定：主路径由真实服务契约驱动。\n"
    )
    adjudicable = (
        "### OPEN-002 可裁定\n\n"
        "- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。\n"
    )

    assert feature_tree.anchorless_opens_in_text(tautology + "\n" + adjudicable) == {"OPEN-001"}

    # 棘轮：存量不被追溯，只有本次增量新增或改写的 OPEN 才需要补齐。
    root = tmp_path / "repo"
    rel = "specs/feature-tree/domain/spec.md"
    write(root / rel, tautology + "\n" + adjudicable)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_gitio, "git_head_text", lambda _rel: tautology)

    # OPEN-001 原样存在于 HEAD，不追溯；OPEN-002 是本次新增，落入棘轮。
    assert feature_tree.open_anchor_ratchet_targets(rel) == {"OPEN-002"}


def test_partial_clause_binding_is_rejected() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    errors = feature_tree.validate_acceptance_clause_coverage(
        "specs/feature-tree/domain/spec.md",
        {"GWT-001": 3},
        set(),
        {"GWT-001": {1, 3}},
        set(),
    )

    assert len(errors) == 1
    assert "缺 t2" in errors[0]

    assert not feature_tree.validate_acceptance_clause_coverage(
        "specs/feature-tree/domain/spec.md",
        {"GWT-001": 3},
        set(),
        {"GWT-001": {1, 2, 3}},
        set(),
    )


def test_newly_closed_composite_acceptance_requires_clause_binding() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    args = ("specs/feature-tree/domain/spec.md", {"GWT-001": 3}, set(), {})

    # 存量锚点不被追溯，代价只由本次做出闭合声称的改动承担。
    assert not feature_tree.validate_acceptance_clause_coverage(*args, set())

    errors = feature_tree.validate_acceptance_clause_coverage(*args, {"GWT-001"})
    assert len(errors) == 1
    assert "gwt-001.t1..t3" in errors[0]

    # 仍挂在 OPEN 上的验收是公开债务，不要求覆盖。
    assert not feature_tree.validate_acceptance_clause_coverage(
        "specs/feature-tree/domain/spec.md", {"GWT-001": 3}, {"GWT-001"}, {}, {"GWT-001"}
    )

    # 单结果锚点仍由双向门禁承担，不受复合判据约束。
    assert not feature_tree.validate_acceptance_clause_coverage(
        "specs/feature-tree/domain/spec.md", {"GWT-002": 1}, set(), {}, {"GWT-002"}
    )


def build_verifiable_tree(tmp_path: Path) -> Path:
    """建一棵能通过完整 command_verify 的最小树。

    比 build_tree 多出的都是结构性硬门要求：README、逐层子节点链接、无本层 design
    时指向父 L1 DEC、以及真实存在的工程归属路径。
    """
    root = tmp_path / "repo"
    tree = root / "specs" / "feature-tree"
    (root / "quwoquan_app" / "lib").mkdir(parents=True, exist_ok=True)
    write(tree / "README.md", "# 特性树\n")
    write(tree / "spec.md", "# AppRoot Spec：演示\n\n- [domain](./domain/spec.md)\n")
    write(tree / "design.md", "# AppRoot Design：演示\n")
    write(
        tree / "domain" / "spec.md",
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n- App：`quwoquan_app/lib`\n\n"
        "- [capability](./capability/spec.md)\n",
    )
    write(
        tree / "domain" / "design.md",
        '# L1 Design：领域 (`domain`)\n\n<a id="dec-001"></a>\n### DEC-001 决策\n',
    )
    write(
        tree / "domain" / "capability" / "spec.md",
        "# L2 Business Capability：能力 (`capability`)\n\n"
        "- 父级设计：[L1 DEC-001](../design.md#dec-001)\n\n"
        "- [story](./story/spec.md)\n",
    )
    write(
        tree / "domain" / "capability" / "story" / "spec.md",
        "# L3 Story：故事 (`story`)\n\n"
        "- 父级设计：[L1 DEC-001](../../design.md#dec-001)\n",
    )
    return root


def test_unbound_compound_acceptance_blocks_unless_registered(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """无子句级绑定的复合验收必须真的阻断，而不是只打印一个数字。

    这里刻意走完整 command_verify 而不是单测判据函数：旧实现的判据本身是对的，
    算完却既不读基线也不比对就 return 0，「只减不增」从未被执行过。只有端到端断言
    退出码，才能防止这段逻辑再次被从 errors 上摘掉。
    """
    root = build_verifiable_tree(tmp_path)
    story = root / "specs" / "feature-tree" / "domain" / "capability" / "story" / "spec.md"
    write(
        story,
        story.read_text(encoding="utf-8")
        + '\n<a id="gwt-001"></a>\n'
        + COMPOSITE_ANCHOR,
    )
    rel = "specs/feature-tree/domain/capability/story/spec.md"
    # 整体 spec_ref 让双向门满意，但三条结果子句一条都没有被指名断言过——这正是
    # 新门要抓的形态，也是既有双向门看不见的盲区。
    write(
        root / "quwoquan_app" / "test" / "story__local_contract_test.dart",
        f"// spec_ref: {rel}#gwt-001\nvoid main() {{}}\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")
    monkeypatch.setattr(ft_gitio, "git_changed_paths", lambda: [])
    args = argparse.Namespace(changes=False)

    assert feature_tree.command_verify(args) == 1
    assert "gwt-001" in capsys.readouterr().err

    # 登记后放行，且末尾统计把它算进在册存量。
    write(
        root / feature_tree.UNBOUND_COMPOUND_BASELINE,
        "governance:\n"
        "  owner: feature-tree-governance\n"
        "  reason: 测试夹具\n"
        "  expires_when: entries 归零\n"
        f"entries:\n- spec: {rel}\n  anchor: GWT-001\n",
    )
    assert feature_tree.command_verify(args) == 0
    assert "复合验收 1 条" in capsys.readouterr().out


def test_compound_acceptance_owed_by_an_open_is_not_double_counted(
    tmp_path: Path, monkeypatch
) -> None:
    """挂在 OPEN 上的复合验收是公开债务，不必再登记进无绑定基线。"""
    root = build_verifiable_tree(tmp_path)
    story = root / "specs" / "feature-tree" / "domain" / "capability" / "story" / "spec.md"
    write(
        story,
        story.read_text(encoding="utf-8")
        + "\n"
        + COMPOSITE_ANCHOR
        + "\n## 7. 开放事项\n\n### OPEN-001 尚未闭合\n\n"
        + "- 完成判定：`GWT-001.t1`、`GWT-001.t2` 与 `GWT-001.t3` 各自被真实测试 `spec_ref` 绑定。\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")
    monkeypatch.setattr(ft_gitio, "git_changed_paths", lambda: [])

    assert feature_tree.command_verify(argparse.Namespace(changes=False)) == 0


def test_clause_transition_detects_open_deletion(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    root = tmp_path / "repo"
    rel = "specs/feature-tree/domain/spec.md"
    head = (
        COMPOSITE_ANCHOR
        + "\n### OPEN-001 尚未闭合\n\n"
        + "- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。\n"
    )
    write(root / rel, COMPOSITE_ANCHOR)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_gitio, "git_head_text", lambda _rel: head)

    assert feature_tree.clause_binding_transitions(rel) == {"GWT-001"}
