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
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001.t1
    root = build_tree(tmp_path)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

    nodes = feature_tree.discover_nodes()

    assert [(node.level, node.node_id) for node in nodes] == [
        (0, "app-root"),
        (1, "domain"),
        (2, "capability"),
        (3, "story"),
    ]


def test_broken_spec_link_is_blocked(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/directory-native-sdd/spec.md#gwt-001.t2
    root = build_tree(tmp_path)
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")
    story_spec = root / "specs" / "feature-tree" / "domain" / "capability" / "story" / "spec.md"
    story_spec.write_text(
        story_spec.read_text(encoding="utf-8") + "\n[缺失的链接](./missing.md)\n",
        encoding="utf-8",
    )

    errors = ft_verify.validate_links(story_spec)

    assert errors, "broken markdown link must be blocked"
    assert "链接目标不存在" in errors[0]


def test_feature_context_outputs_parent_chain_acceptance_and_open(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t1
    root = build_tree(tmp_path)
    tree = root / "specs" / "feature-tree"
    write(root / "quwoquan_app" / "lib" / "feature.dart", "void main() {}\n")
    (tree / "domain" / "spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib`\n",
        encoding="utf-8",
    )
    (tree / "domain" / "capability" / "story" / "spec.md").write_text(
        "# L3 Story：故事 (`story`)\n\n"
        '<a id="gwt-001"></a>\n'
        "### GWT-001 演示验收\n\n"
        "- GIVEN 前置。\n"
        "- WHEN 行为。\n"
        "- THEN 结果一。\n\n"
        "## 8. 开放事项\n\n"
        "### OPEN-001 未完成主路径\n\n"
        "- 类型：`missing_capability`\n"
        "- 优先级：`P1`\n"
        "- 准出影响：`block`\n"
        "- 完成判定：`GWT-001` 对应行为满足。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", lambda: [])
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)

    # 代码路径解析出唯一 L1 owner。
    code_owner = feature_tree.resolve_target(
        "quwoquan_app/lib/feature.dart", feature_tree.discover_nodes()
    )
    assert code_owner.node_id == "domain"

    # L3 目标输出完整父链、相关验收与当前 OPEN。
    exit_code = feature_tree.command_context(
        argparse.Namespace(target="specs/feature-tree/domain/capability/story/spec.md")
    )
    capsys.readouterr()

    assert exit_code == 0
    context_md = outputs["context.md"]
    assert "- 归属节点：`specs/feature-tree/domain/capability/story/spec.md`" in context_md
    assert "L1 Domain Service · domain" in context_md
    assert "L2 Business Capability · capability" in context_md
    assert "L3 Story · story" in context_md
    # 相关验收与当前 OPEN 一并输出。
    assert "GWT-001 演示验收" in context_md
    assert "OPEN-001 未完成主路径" in context_md


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
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(
        "quwoquan_app/lib/feature.dart", feature_tree.discover_nodes()
    )

    assert owner.node_id == "domain"


def test_agent_asset_path_resolves_from_l1_agent_ownership(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    write(root / ".agents" / "skills" / "review" / "SKILL.md", "# skill\n")
    write(root / ".cursor" / "skills" / "demo" / "SKILL.md", "# stub\n")
    l1_spec = root / "specs" / "feature-tree" / "domain" / "spec.md"
    l1_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- Agent：`.agents`、`.claude`、`.codex`、`.cursor`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")
    nodes = feature_tree.discover_nodes()

    assert feature_tree.resolve_target(".agents/skills/review/SKILL.md", nodes).node_id == "domain"
    assert feature_tree.resolve_target(".cursor/skills/demo/SKILL.md", nodes).node_id == "domain"


def test_canonical_app_object_test_resolves_from_its_production_domain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t3
    root = build_tree(tmp_path)
    test_path = (
        root
        / "quwoquan_app/test/local_contract/service/content_service/content/post/"
        "publish_location_selector_initial_timeout__local_contract_test.dart"
    )
    write(test_path, "void main() {}\n")
    write(root / "quwoquan_app/lib/service/content_service/content/post/page.dart", "class Page {}\n")
    domain_spec = root / "specs/feature-tree/domain/spec.md"
    domain_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib/service/content_service/content/post`\n",
        encoding="utf-8",
    )
    write(
        root / "specs/feature-tree/runtime/spec.md",
        "# L1 Domain Service：运行时 (`runtime`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app`、`quwoquan_app/lib/runtime`\n",
    )
    write(
        root / "specs/feature-tree/runtime/design.md",
        "# L1 Design：运行时 (`runtime`)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    owner = feature_tree.resolve_target(test_path, feature_tree.discover_nodes())

    assert owner.node_id == "domain"


def test_canonical_app_test_does_not_fall_back_to_project_level_runtime_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    test_path = (
        root
        / "quwoquan_app/test/local_contract/unowned/context/object/"
        "behavior__local_contract_test.dart"
    )
    write(test_path, "void main() {}\n")
    write(
        root / "specs/feature-tree/runtime/spec.md",
        "# L1 Domain Service：运行时 (`runtime`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app`、`quwoquan_app/lib/runtime`\n",
    )
    write(
        root / "specs/feature-tree/runtime/design.md",
        "# L1 Design：运行时 (`runtime`)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    try:
        feature_tree.resolve_target(test_path, feature_tree.discover_nodes())
    except ValueError as error:
        assert "未被任何 L1 工程归属认领" in str(error)
    else:
        raise AssertionError("project-level runtime ownership swallowed a business test")


def test_cross_object_app_journey_does_not_claim_project_level_runtime_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    journey = (
        root
        / "quwoquan_app/test/user_acceptance/journeys/forward_share/"
        "forward_share__user_acceptance_test.dart"
    )
    write(journey, "void main() {}\n")
    write(
        root / "specs/feature-tree/runtime/spec.md",
        "# L1 Domain Service：运行时 (`runtime`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app`、`quwoquan_app/lib/runtime`\n",
    )
    write(
        root / "specs/feature-tree/runtime/design.md",
        "# L1 Design：运行时 (`runtime`)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    try:
        feature_tree.resolve_target(journey, feature_tree.discover_nodes())
    except ValueError as error:
        assert "未被任何 L1 工程归属认领" in str(error)
    else:
        raise AssertionError("project-level runtime ownership swallowed a Journey")


def test_cross_object_app_journey_resolves_from_exact_explicit_l1_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    journey = (
        root
        / "quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync/"
        "viewer_profile_state_sync__local_contract_test.dart"
    )
    write(journey, "void main() {}\n")
    domain_spec = root / "specs/feature-tree/domain/spec.md"
    domain_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib/content`\n"
        "- 测试：\n"
        "  - `local_contract`："
        "`quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync`\n",
        encoding="utf-8",
    )
    write(
        root / "specs/feature-tree/runtime/spec.md",
        "# L1 Domain Service：运行时 (`runtime`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app`、`quwoquan_app/lib/runtime`\n",
    )
    write(
        root / "specs/feature-tree/runtime/design.md",
        "# L1 Design：运行时 (`runtime`)\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    owner = feature_tree.resolve_target(journey, feature_tree.discover_nodes())

    assert owner.node_id == "domain"


def test_cross_object_app_journey_rejects_non_exact_parent_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    journey = (
        root
        / "quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync/"
        "viewer_profile_state_sync__local_contract_test.dart"
    )
    write(journey, "void main() {}\n")
    domain_spec = root / "specs/feature-tree/domain/spec.md"
    domain_spec.write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/test/local_contract/journeys`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    try:
        feature_tree.resolve_target(journey, feature_tree.discover_nodes())
    except ValueError as error:
        assert "未被任何 L1 工程归属认领" in str(error)
    else:
        raise AssertionError("a shared journeys parent became an implicit owner")


def test_cross_object_app_journey_rejects_duplicate_exact_l1_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    root = build_tree(tmp_path)
    journey_root = (
        "quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync"
    )
    journey = root / journey_root / "viewer_profile_state_sync__local_contract_test.dart"
    write(journey, "void main() {}\n")
    for node_id in ("domain", "other-domain"):
        write(
            root / f"specs/feature-tree/{node_id}/spec.md",
            f"# L1 Domain Service：领域 (`{node_id}`)\n\n"
            "## 7. 工程归属\n\n"
            f"- 测试：`{journey_root}`\n",
        )
        write(
            root / f"specs/feature-tree/{node_id}/design.md",
            f"# L1 Design：领域 (`{node_id}`)\n",
        )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    try:
        feature_tree.resolve_target(journey, feature_tree.discover_nodes())
    except ValueError as error:
        message = str(error)
        assert "被多个 L1 同优先级认领" in message
        assert "domain" in message
        assert "other-domain" in message
    else:
        raise AssertionError("duplicate exact Journey owners were not rejected")


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
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

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
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(
        ".github/workflows/service_pipeline.yml", feature_tree.discover_nodes()
    )

    assert owner.node_id == "domain"


def test_duplicate_same_priority_owner_is_blocked(tmp_path: Path, monkeypatch) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t2
    root = build_tree(tmp_path)
    write(root / "quwoquan_app" / "lib" / "feature.dart", "void main() {}\n")
    for name in ("domain", "second-domain"):
        write(
            root / "specs" / "feature-tree" / name / "spec.md",
            f"# L1 Domain Service：领域 (`{name}`)\n\n## 7. 工程归属\n\n"
            "- App：`quwoquan_app/lib`\n",
        )
        write(root / "specs" / "feature-tree" / name / "design.md", f"# L1 Design：领域 (`{name}`)\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

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
    """假绑定负例：无 spec_ref 标记的裸字符串字面量不计入证据。

    只认单行形态——ref 所在行、ref 之前有大小写不敏感的 `spec_ref` 记号
    （注释或常量声明）。fixture 字面量、断言消息、Go 结构体字段 `SpecRef:`
    （无下划线，属 readiness 数据）都不构成绑定。
    """
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
    from quwoquan_ops.cli.lib.feature_tree import evidence as ft_evidence

    root = tmp_path / "repo"
    write(
        root / "quwoquan_ops" / "tests" / "sample__local_contract_test.py",
        "# spec_ref: specs/feature-tree/spec.md#uat-001\n"
        'SPEC_REF = "specs/feature-tree/spec.md#uat-002"\n'
        'bare = "specs/feature-tree/spec.md#uat-003"\n'
        'msg = "见 specs/feature-tree/spec.md#uat-004 锚点"\n',
    )
    write(
        root / "quwoquan_service" / "x" / "readiness__contract__local_contract_test.go",
        'SpecRef: "specs/feature-tree/spec.md#uat-005",\n',
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)

    assert ft_evidence.test_spec_refs() == {
        "quwoquan_ops/tests/sample__local_contract_test.py": {
            "specs/feature-tree/spec.md#uat-001",
            "specs/feature-tree/spec.md#uat-002",
        }
    }
