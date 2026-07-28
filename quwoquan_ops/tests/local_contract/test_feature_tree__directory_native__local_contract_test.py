from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree", MODULE_PATH)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)


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


def test_directory_is_the_only_tree_source(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001
    root = build_tree(tmp_path)
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")

    nodes = feature_tree.discover_nodes()

    assert [(node.level, node.node_id) for node in nodes] == [
        (0, "app-root"),
        (1, "domain"),
        (2, "capability"),
        (3, "story"),
    ]


def test_code_path_resolves_from_l1_engineering_ownership(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    source = root / "quwoquan_app" / "lib" / "feature.dart"
    write(source, "void main() {}\n")
    l1_spec = root / "specs" / "feature-tree" / "domain" / "spec.md"
    l1_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(
        "quwoquan_app/lib/feature.dart", feature_tree.discover_nodes()
    )

    assert owner.node_id == "domain"


def test_contract_path_resolves_from_l1_engineering_ownership(tmp_path: Path, monkeypatch) -> None:
    root = build_tree(tmp_path)
    contract = root / "quwoquan_service" / "services" / "demo-service" / "contracts" / "object.yaml"
    write(contract, "kind: aggregate_root\n")
    l1_spec = root / "specs" / "feature-tree" / "domain" / "spec.md"
    l1_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- Contracts：`quwoquan_service/services/demo-service/contracts`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(contract, feature_tree.discover_nodes())

    assert owner.node_id == "domain"


def test_ci_path_resolves_from_l1_engineering_ownership(tmp_path: Path, monkeypatch) -> None:
    root = build_tree(tmp_path).resolve()
    workflow = root / ".github" / "workflows" / "service_pipeline.yml"
    write(workflow, "name: service pipeline\n")
    l1_spec = root / "specs" / "feature-tree" / "domain" / "spec.md"
    l1_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- CI：`.github/workflows`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(
        ".github/workflows/service_pipeline.yml", feature_tree.discover_nodes()
    )

    assert owner.node_id == "domain"


def test_duplicate_same_priority_owner_is_blocked(tmp_path: Path, monkeypatch) -> None:
    root = build_tree(tmp_path)
    write(root / "quwoquan_app" / "lib" / "feature.dart", "void main() {}\n")
    for name in ("domain", "second-domain"):
        write(
            root / "specs" / "feature-tree" / name / "spec.md",
            f"# L1 Domain Service：领域 (`{name}`)\n\n## 7. 工程归属\n\n"
            "- App：`quwoquan_app/lib`\n",
        )
        write(root / "specs" / "feature-tree" / name / "design.md", f"# L1 Design：领域 (`{name}`)\n")
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")

    try:
        feature_tree.resolve_target(
            "quwoquan_app/lib/feature.dart", feature_tree.discover_nodes()
        )
    except ValueError as error:
        assert "多个 L1" in str(error)
    else:
        raise AssertionError("expected duplicate ownership to block")


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
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", root / "specs" / "feature-tree")
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
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", tree)
    monkeypatch.setattr(
        feature_tree,
        "git_changed_paths",
        lambda: ["specs/feature-tree/domain/capability/design.md"],
    )
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(feature_tree, "write_output", capture_output)

    assert feature_tree.command_change_report(argparse.Namespace()) == 0
    assert "OPEN-001 外部 Provider 未就绪" in outputs["change-report.md"]
    assert "RELEASE_GATES_BLOCKED" in capsys.readouterr().out


def test_change_report_still_blocks_unowned_engineering_change(
    tmp_path: Path, monkeypatch
) -> None:
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    unowned = root / "quwoquan_ops" / "cli" / "orphan.py"
    write(unowned, "# no owner\n")
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", tree)
    monkeypatch.setattr(
        feature_tree, "git_changed_paths", lambda: ["quwoquan_ops/cli/orphan.py"]
    )
    monkeypatch.setattr(feature_tree, "write_output", lambda name, _content: root / name)

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
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", tree)

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
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(feature_tree, "TREE_ROOT", tree)

    assert feature_tree.validate_journey_bidirection(feature_tree.discover_nodes()) == []


def test_semantic_anchor_changes_detects_added_and_removed_ids(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    path = root / "specs" / "feature-tree" / "domain" / "spec.md"
    write(path, "### REQ-002 新要求\n")
    monkeypatch.setattr(feature_tree, "REPO_ROOT", root)
    monkeypatch.setattr(
        feature_tree,
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
