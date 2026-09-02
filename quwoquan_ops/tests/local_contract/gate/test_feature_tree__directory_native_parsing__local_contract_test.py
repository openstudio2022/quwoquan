from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree_directory_parsing", MODULE_PATH)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)

from quwoquan_ops.cli.lib.feature_tree import commands as ft_commands  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import context as ft_context  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import gitio as ft_gitio  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    tree = root / "specs" / "feature-tree"
    write(tree / "spec.md", "# AppRoot Spec：演示\n")
    write(tree / "design.md", "# AppRoot Design：演示\n")
    write(tree / "domain" / "spec.md", "# L1 Domain Service：领域 (`domain`)\n")
    write(tree / "domain" / "design.md", "# L1 Design：领域 (`domain`)\n")
    write(tree / "domain" / "capability" / "spec.md", "# L2 Business Capability：能力 (`capability`)\n")
    write(tree / "domain" / "capability" / "story" / "spec.md", "# L3 Story：故事 (`story`)\n")
    return root


def test_app_root_spec_ref_is_discovered() -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001
    content = "# " + "spec_" + "ref: specs/feature-tree/spec.md#uat-001\n"

    assert feature_tree.SPEC_REF_RE.findall(content) == [
        "specs/feature-tree/spec.md#uat-001"
    ]


def test_open_completion_marks_acceptance_as_pending(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    write(
        spec,
        "# L3 Story：故事 (`story`)\n\n"
        "### GWT-001 主路径\n\n"
        "- GIVEN 条件。\n"
        "- WHEN 动作。\n"
        "- THEN 结果。\n\n"
        "## 7. 开放事项\n\n"
        "### OPEN-001 未完成主路径\n\n"
        "- 类型：`capability_gap`\n"
        "- 优先级：`P1`\n"
        "- 准出影响：`block`\n"
        "- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效\n",
    )

    assert feature_tree.acceptance_refs_in_open(spec) == {"GWT-001"}


def test_open_completion_reads_nested_evidence_bullets(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    # 完成判定常写成「总述 + 逐条证据子 bullet」，锚点引用落在子 bullet 里。只读首行
    # 会把已可裁定的 OPEN 误报为不可裁定，也会放过子 bullet 里引用不存在锚点的 OPEN。
    spec = tmp_path / "spec.md"
    write(
        spec,
        "# L3 Story：故事 (`story`)\n\n"
        "### GWT-001 主路径\n\n"
        "- GIVEN 条件。\n"
        "- WHEN 动作。\n"
        "- THEN 结果。\n\n"
        "## 7. 开放事项\n\n"
        "### OPEN-001 三层证据同时通过\n\n"
        "- 完成判定：以下三层 release-bound 证据同时通过。\n"
        "  - 仓内 local_contract 证明状态机语义。\n"
        "  - 真机 CaseResult 直接引用 `GWT-001`。\n"
        "- 依赖：受管设备。\n",
    )

    assert feature_tree.acceptance_refs_in_open(spec) == {"GWT-001"}
    assert feature_tree.anchorless_opens_in_text(spec.read_text(encoding="utf-8")) == set()

    # 同一入口也让子 bullet 里的悬空引用无法逃过校验。
    write(
        spec,
        spec.read_text(encoding="utf-8").replace("`GWT-001`", "`GWT-404`"),
    )
    assert feature_tree.invalid_acceptance_refs_in_open(spec) == {"GWT-404"}


def test_open_item_details_are_searchable_without_a_registry(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_tree(tmp_path)
    story = root / "specs" / "feature-tree" / "domain" / "capability" / "story" / "spec.md"
    story.write_text(
        "# L3 Story：故事 (`story`)\n\n"
        "## 7. 开放事项\n\n"
        "### OPEN-001 外部依赖未就绪\n\n"
        "- 类型：`external_blocker`\n"
        "- 优先级：`P0`\n"
        "- 准出影响：`block`\n"
        "- 影响或价值：无法完成主路径。\n"
        "- 完成判定：`GWT-001` 通过。\n"
        "- 依赖：供应商凭据。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")
    node = next(item for item in feature_tree.discover_nodes() if item.node_id == "story")

    assert feature_tree.open_item_details(node) == [
        {
            "node": "specs/feature-tree/domain/capability/story/spec.md",
            "level": 3,
            "id": "OPEN-001",
            "title": "外部依赖未就绪",
            "type": "external_blocker",
            "priority": "P0",
            "releaseImpact": "block",
            "impactOrValue": "无法完成主路径。",
            "completion": "`GWT-001` 通过。",
            "dependency": "供应商凭据。",
        }
    ]


def test_change_report_keeps_release_open_visible_without_blocking_remediation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-008
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    (tree / "domain" / "spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_ops`\n",
        encoding="utf-8",
    )
    (tree / "domain" / "capability" / "spec.md").write_text(
        "# L2 Business Capability：能力 (`capability`)\n\n"
        "## 8. 开放事项\n\n"
        "### OPEN-001 外部 Provider 未就绪\n\n"
        "- 类型：`external_blocker`\n"
        "- 优先级：`P0`\n"
        "- 准出影响：`block`\n"
        "- 完成判定：真实 Provider 回执。\n",
        encoding="utf-8",
    )
    write(tree / "domain" / "capability" / "design.md", "# L2 Design：能力\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(
        ft_gitio,
        "git_changed_paths",
        lambda: ["specs/feature-tree/domain/capability/design.md"],
    )
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)

    assert feature_tree.command_change_report(argparse.Namespace()) == 0
    assert "OPEN-001 外部 Provider 未就绪" in outputs["change-report.md"]
    assert "RELEASE_GATES_BLOCKED" in capsys.readouterr().out


def test_change_report_still_blocks_unowned_engineering_change(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001.t2
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    unowned = root / "quwoquan_ops" / "cli" / "orphan.py"
    write(unowned, "# no owner\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(
        ft_gitio, "git_changed_paths", lambda: ["quwoquan_ops/cli/orphan.py"]
    )
    monkeypatch.setattr(ft_commands, "write_output", lambda name, _content: root / name)

    assert feature_tree.command_change_report(argparse.Namespace()) == 2


def test_journey_scenario_requires_exact_l1_handoff_reference(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    write(
        tree / "spec.md",
        "# AppRoot Spec：演示\n\n"
        "### JNY-001 演示旅程\n\n"
        "- 参与领域：\n"
        "  - [domain](./domain/spec.md)\n\n"
        "#### SCN-001 演示场景\n\n"
        "- 领域交接：domain\n",
    )
    write(
        tree / "domain" / "spec.md",
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "- [`JNY-001 / SCN-001`](../spec.md#scn-001)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)

    assert feature_tree.validate_journey_bidirection(feature_tree.discover_nodes()) == []

    write(
        tree / "domain" / "spec.md",
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "- [`JNY-001 / SCN-999`](../spec.md#scn-999)\n",
    )
    errors = feature_tree.validate_journey_bidirection(feature_tree.discover_nodes())

    assert any("未反向引用 JNY-001 / SCN-001" in error for error in errors)
    assert any("AppRoot 不存在" in error for error in errors)


def test_last_journey_does_not_consume_links_from_following_approot_sections(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    write(
        tree / "spec.md",
        "# AppRoot Spec：演示\n\n"
        "### JNY-001 演示旅程\n\n"
        "- 参与领域：\n"
        "  - [domain](./domain/spec.md)\n\n"
        "#### SCN-001 演示场景\n\n"
        "- 领域交接：domain\n\n"
        "## 5. 全局验收\n\n"
        "- [unrelated](./unrelated/spec.md)\n",
    )
    write(
        tree / "domain" / "spec.md",
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "- [`JNY-001 / SCN-001`](../spec.md#scn-001)\n",
    )
    write(
        tree / "unrelated" / "spec.md",
        "# L1 Domain Service：无关领域 (`unrelated`)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)

    assert feature_tree.validate_journey_bidirection(feature_tree.discover_nodes()) == []


def test_semantic_anchor_changes_detects_added_and_removed_ids(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    path = root / "specs" / "feature-tree" / "domain" / "spec.md"
    write(path, "### REQ-002 新要求\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(
        ft_gitio,
        "git_head_text",
        lambda _rel: "### REQ-001 旧要求\n",
    )

    assert feature_tree.semantic_anchor_changes(
        "specs/feature-tree/domain/spec.md"
    ) == {
        "added": ["REQ-002"],
        "modified": [],
        "deleted": ["REQ-001"],
    }


def test_outcome_clause_split_ignores_separators_inside_code_spans() -> None:
    """中文子句误切负例：反引号内的分隔符是标识符的一部分，不是子句边界。"""
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
    from quwoquan_ops.cli.lib.feature_tree.parsing import outcome_sub_clauses

    assert outcome_sub_clauses("回读 `a；b` 字段，且校验通过") == [
        "回读 `a；b` 字段",
        "校验通过",
    ]
    assert outcome_sub_clauses("写入成功，并发请求不阻塞") == ["写入成功，并发请求不阻塞"]
    assert outcome_sub_clauses("A 成立；B 成立") == ["A 成立", "B 成立"]


def test_bare_string_literal_spec_ref_is_not_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    """显式单行/列表块计证据；裸字符串、相似 token 与 readiness 字段不计。"""
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
    from quwoquan_ops.cli.lib.feature_tree import evidence as ft_evidence

    root = tmp_path / "repo"
    # fixture 内 marker token 用源码级相邻字符串拆开：本文件自身也在证据扫描
    # 范围内，同行完整 marker 会把 fixture 行泄漏为本文件的假绑定（test 复审
    # 实证 uat-002 曾被计入 coverage map）。
    write(
        root / "quwoquan_ops" / "tests" / "sample__local_contract_test.py",
        "# spec_" "ref: specs/feature-tree/spec.md#uat-001\n"
        "SPEC_" 'REF = "specs/feature-tree/spec.md#uat-002"\n'
        "spec_ref:\n"
        "  - specs/feature-tree/spec.md#uat-006\n"
        "  - specs/feature-tree/spec.md#uat-007\n"
        "spec_ref:\n"
        "\n"
        "  - specs/feature-tree/spec.md#uat-009\n"
        'bare = "specs/feature-tree/spec.md#uat-003"\n'
        'msg = "见 specs/feature-tree/spec.md#uat-004 锚点"\n'
        'not_a_spec_ref = "specs/feature-tree/spec.md#uat-008"\n',
    )
    write(
        root / "quwoquan_service" / "x" / "readiness__contract__local_contract_test.go",
        'SpecRef: "specs/feature-tree/spec.md#uat-005",\n',
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)

    # `.mjs` 不在 canonical evidence suffix 闭集；Portal 的直接可执行绑定必须
    # 落到职责匹配的 Python local_contract/gate，不能靠扫描器不可见的 JS 注释。
    write(
        root / "quwoquan_ops" / "portal" / "src" / "role_card.test.mjs",
        "// spec_ref: specs/feature-tree/spec.md#uat-010\n",
    )

    assert ft_evidence.test_spec_refs() == {
        "quwoquan_ops/tests/sample__local_contract_test.py": {
            "specs/feature-tree/spec.md#uat-001",
            "specs/feature-tree/spec.md#uat-002",
            "specs/feature-tree/spec.md#uat-006",
            "specs/feature-tree/spec.md#uat-007",
        }
    }
