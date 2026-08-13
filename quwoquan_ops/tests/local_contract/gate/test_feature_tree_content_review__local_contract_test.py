from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree_content_review.py"
# REPO_ROOT 的真实绑定在包内 context 模块;门面 re-export 的副本 patch 了也不会
# 被 canonical_spec_ref 读到,所以测试必须直接 patch context。
from quwoquan_ops.cli.lib.feature_tree import context as ft_context  # noqa: E402

SPEC = importlib.util.spec_from_file_location("feature_tree_content_review", MODULE_PATH)
assert SPEC and SPEC.loader
reviewer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reviewer
SPEC.loader.exec_module(reviewer)


def issues_for(content: str, *, kind: str = "L3 Story") -> list[str]:
    review = reviewer.Review(path="spec.md", kind=kind)
    reviewer.validate_content(review, content)
    return review.issues


def test_explicit_html_anchor_is_not_a_template_placeholder() -> None:
    assert issues_for('<a id="gwt-001"></a>') == []


def test_template_marker_is_blocked() -> None:
    assert issues_for("作为 <用户或平台调用方> 完成行为") == ["存在模板占位符"]


def test_contract_type_and_path_variable_are_not_template_placeholders() -> None:
    assert issues_for(
        "`List<IntersectionReason>` 与 `services/<service>/contracts/<context>`"
    ) == []


def test_canonical_natural_language_pseudo_reference_is_blocked() -> None:
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_repo_refs(review, "- canonical：`Some contract label`\n")

    assert review.issues == ["canonical 使用含空格的自然语言伪引用"]


def test_migration_and_generic_acceptance_copy_are_blocked() -> None:
    issues = issues_for(
        "- 来源迁移：`GWT1`\n"
        "- GIVEN 前置条件明确。\n"
        "- WHEN 用户或系统动作发生。\n"
        "- THEN 可观察结果符合预期。\n"
    )

    assert issues == [
        "GIVEN 使用占位语句",
        "WHEN 使用占位语句",
        "THEN 使用占位语句",
        "保留来源迁移历史",
    ]


def test_historical_status_and_dated_snapshot_are_blocked() -> None:
    issues = issues_for("- 本期完成迁移。\n- 2026-07-22 状态快照。\n")

    assert issues == [
        "使用历史状态或阶段性计划口径",
        "在当前规格或设计中冻结日期快照",
    ]


def test_session_status_and_bulk_migration_prose_are_blocked() -> None:
    issues = issues_for(
        "- operation per-op ready，测试全绿。\n"
        "- 本次只冻结当前变更。\n"
        "作为用户，我希望系统提供“某能力”。\n"
        "从而获得一致、可诊断且可复现的工程能力。\n"
        "- 子节点：- 机械拼接说明。\n"
    )

    assert issues == [
        "使用阶段状态、测试日报或退役契约版本口径",
        "保留会话增量、冻结或迁移记录",
        "使用批量迁移生成的通用用户价值或行为占位",
        "用户价值仍使用批量迁移的通用结果占位",
        "父子说明保留机械拼接列表标记",
    ]


def test_generic_requirement_wrappers_and_test_as_behavior_are_blocked() -> None:
    issues = issues_for(
        "- 必须满足“资料保存”的核心行为：Widget 测试通过。\n"
        "- 成功时必须返回可观察结果；失败时必须返回 canonical failure，且不得写入成功事实。\n"
    )

    assert issues == [
        "REQ 保留批量迁移的核心行为套话",
        "REQ 保留全节点重复的成功失败套话",
        "行为要求或验收把测试实现当成产品结果",
    ]


def test_behavior_section_rejects_layer_specific_test_details() -> None:
    issues = issues_for(
        "## 3. 行为要求\n\n"
        "### REQ-001 保存资料\n\n"
        "- local_contract 覆盖字段顺序和错误恢复。\n"
    )

    assert issues == ["行为要求或验收包含应留在测试代码中的证据细节"]


def test_truncated_title_is_blocked() -> None:
    node = type("Node", (), {"level": 3, "node_id": "story"})()
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_title(review, "# L3 Story：被截断（Operation (`story`)", node)

    assert review.issues == ["标题括号不完整，疑似机械迁移截断"]


def test_truncated_heading_prefix_and_unbalanced_chinese_parenthesis_are_blocked() -> None:
    issues = issues_for(
        "### REQ-002 必须返回成\n\n"
        "- 系统必须返回成功事实。\n"
        "- 存储配置（覆盖内容与用户。\n"
    )

    assert issues == [
        "中文括号不完整，疑似机械迁移截断 `- 存储配置（覆盖内容与用户。`",
        "三级标题疑似为正文截断前缀 `### REQ-002 必须返回成`",
    ]


def test_semantically_duplicate_open_items_are_blocked(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## 7. 开放事项\n\n"
        "### OPEN-001 缺少证据\n\n"
        "- 类型：`capability_gap`\n"
        "- 优先级：`P1`\n"
        "- 准出影响：`track`\n"
        "- 影响或价值：尚缺直接证据。\n"
        "- 完成判定：`GWT-001` 有真实 `spec_ref`。\n\n"
        "### OPEN-002 同一缺口重复登记\n\n"
        "- 类型：`capability_gap`\n"
        "- 优先级：`P1`\n"
        "- 准出影响：`track`\n"
        "- 影响或价值：尚缺直接证据。\n"
        "- 完成判定：`GWT-001` 有真实 `spec_ref`。\n",
        encoding="utf-8",
    )
    node = SimpleNamespace(spec=spec, rel="domain/capability/story", level=3)
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_open_items(review, spec.read_text(encoding="utf-8"), node)

    assert review.issues == ["OPEN-002 与 OPEN-001 是同一未完成事项的重复登记"]


def test_capability_gap_requires_explicit_missing_state(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## 7. 开放事项\n\n"
        "### OPEN-001 目标态冒充缺口\n\n"
        "- 类型：`capability_gap`\n"
        "- 优先级：`P1`\n"
        "- 准出影响：`track`\n"
        "- 影响或价值：测试全部通过。\n"
        "- 完成判定：`GWT-001` 有真实 `spec_ref`。\n",
        encoding="utf-8",
    )
    node = SimpleNamespace(spec=spec, rel="domain/capability/story", level=3)
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_open_items(review, spec.read_text(encoding="utf-8"), node)

    assert review.issues == ["OPEN-001 未明确说明尚缺的实现或验收证据"]


def test_section_outside_template_is_blocked() -> None:
    review = reviewer.Review(path="spec.md", kind="L3 Story")
    text = "\n".join(
        [
            *(f"## {heading}\n- 内容" for heading in reviewer.SPEC_SECTIONS[3]),
            "## 历史状态\n- 已完成",
        ]
    )

    reviewer.validate_sections(
        review,
        text,
        reviewer.SPEC_SECTIONS[3],
        reviewer.SPEC_OPTIONAL_SECTIONS[3],
    )

    assert review.issues == ["存在模板外章节 `历史状态`"]


def test_acceptance_rejects_unmarked_list_step(tmp_path: Path, monkeypatch) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## 5. 验收场景\n\n"
        "### GWT-001 主路径\n\n"
        "- GIVEN 输入有效。\n"
        "- WHEN 用户提交。\n"
        "- THEN 返回结果。\n"
        "- 未标记的续行。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", tmp_path)
    node = SimpleNamespace(level=3, spec=spec)
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_acceptance(review, spec.read_text(), node, {})

    assert review.issues == [
        "GWT-001 既无真实 spec_ref，也未由同节点 OPEN 声明未完成",
        "GWT-001 存在未标记为 GIVEN/WHEN/THEN/AND 的步骤",
    ]


def test_acceptance_folds_valid_clause_ref_into_top_level_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## 5. 验收场景\n\n"
        "### GWT-001 复合结果\n\n"
        "- GIVEN 输入有效。\n"
        "- WHEN 用户提交。\n"
        "- THEN 返回结果。\n"
        "- AND 写入审计事实。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", tmp_path)
    node = SimpleNamespace(level=3, spec=spec)
    review = reviewer.Review(path="spec.md", kind="L3 Story")
    canonical = reviewer.feature_tree.canonical_spec_ref(spec, "GWT-001")

    reviewer.validate_acceptance(
        review,
        spec.read_text(encoding="utf-8"),
        node,
        {"runner": {f"{canonical}.t2"}},
    )

    assert review.issues == []
    assert review.evidence == [canonical]


def test_acceptance_rejects_dangling_clause_ref_as_top_level_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## 5. 验收场景\n\n"
        "### GWT-001 单一结果\n\n"
        "- GIVEN 输入有效。\n"
        "- WHEN 用户提交。\n"
        "- THEN 返回结果。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", tmp_path)
    node = SimpleNamespace(level=3, spec=spec)
    review = reviewer.Review(path="spec.md", kind="L3 Story")
    canonical = reviewer.feature_tree.canonical_spec_ref(spec, "GWT-001")

    reviewer.validate_acceptance(
        review,
        spec.read_text(encoding="utf-8"),
        node,
        {"runner": {f"{canonical}.t2"}},
    )

    assert review.evidence == []
    assert review.issues == [
        "GWT-001 既无真实 spec_ref，也未由同节点 OPEN 声明未完成"
    ]


def test_semantic_migration_placeholders_are_blocked() -> None:
    issues = issues_for(
        "### REQ-002 现行边界约束\n"
        "- 系统必须基于 runtime L2 能力完成该子特性的可复用封装。\n"
        "- 上游事实：owner 领域公开 query/projection。\n"
        "- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。\n"
    )

    assert issues == [
        "REQ 标题未表达具体要求",
        "使用 runtime 批量迁移占位语义",
        "依赖未声明具体事实或 owner",
        "使用已退役的 OpenAPI/中心 metadata 权威口径",
    ]


def test_generic_design_decision_is_blocked() -> None:
    issues = issues_for(
        "### DEC-001 领域采用单一事实 owner 与公开契约\n"
        "- 决策：规格拥有业务语义，metadata 拥有 wire 契约，代码与测试分别承担实现与证据。\n"
        "- 被否决方案：在节点外维护第二套索引、状态或兼容语义。\n"
        "- 约束与影响：下层设计只能细化规格，不得覆盖父级边界。\n",
        kind="L1 Domain Service Design",
    )

    assert issues == [
        "DEC 标题使用通用治理占位",
        "DEC 内容使用全局治理占位",
        "被否决方案使用全局治理占位",
        "设计影响使用全局治理占位",
    ]


def test_repeated_design_sentence_and_mechanical_list_are_blocked() -> None:
    repeated = "- 设计必须由唯一对象 owner 持有事实，并通过公开 command query event 与调用方协作。"
    issues = issues_for(
        f"{repeated}\n{repeated}\n- 决策：A；理由：B；影响：C\n",
        kind="L2 Business Capability Design",
    )

    assert issues == [
        "存在重复长句 `- 设计必须由唯一对象 owner 持有事实，并通过公开 command query event 与调用方协作。…`",
        "存在由历史文档机械拼接的多段列表项",
    ]


def test_repository_reference_allows_fragment_and_documented_path_variable(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "quwoquan_service").mkdir()
    (tmp_path / "quwoquan_service" / "contract.yaml").write_text("key: value\n")
    monkeypatch.setattr(reviewer, "REPO_ROOT", tmp_path)
    review = reviewer.Review(path="spec.md", kind="L3 Story")

    reviewer.validate_repo_refs(
        review,
        "`quwoquan_service/contract.yaml#operation` "
        "`quwoquan_service/services/<service>/contracts`",
    )

    assert review.issues == []


def test_central_business_metadata_reference_is_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "quwoquan_service" / "contracts" / "metadata" / "content"
    path.mkdir(parents=True)
    (tmp_path / "quwoquan_service" / "contracts" / "metadata" / "_shared").mkdir()
    monkeypatch.setattr(reviewer, "REPO_ROOT", tmp_path)
    review = reviewer.Review(path="spec.md", kind="L1 Domain Service")

    reviewer.validate_repo_refs(
        review,
        "`quwoquan_service/contracts/metadata/content` "
        "`quwoquan_service/contracts/metadata/_shared`",
    )

    assert review.issues == [
        "业务域契约必须引用所属服务 contracts，不得引用中心 metadata "
        "`quwoquan_service/contracts/metadata/content`"
    ]


def test_committed_feature_tree_templates_follow_the_same_section_contract() -> None:
    reviews = reviewer.review_templates()

    assert len(reviews) == 7
    assert {review.path for review in reviews} == {
        "specs/templates/feature-tree/app-root-design.md",
        "specs/templates/feature-tree/app-root-spec.md",
        "specs/templates/feature-tree/l1-design.md",
        "specs/templates/feature-tree/l1-spec.md",
        "specs/templates/feature-tree/l2-design.md",
        "specs/templates/feature-tree/l2-spec.md",
        "specs/templates/feature-tree/l3-spec.md",
    }
    assert {review.path: review.issues for review in reviews} == {
        review.path: [] for review in reviews
    }
