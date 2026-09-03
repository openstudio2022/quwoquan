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
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
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
        argparse.Namespace(
            target="specs/feature-tree/domain/capability/story/spec.md",
            format="expanded",
        )
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


def test_l2_dec_owner_rejects_same_priority_ambiguity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-004
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    code_path = root / "quwoquan_app/lib/design_system/pageflip/geometry.dart"
    write(code_path, "class Geometry {}\n")
    (tree / "domain/spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib/design_system/pageflip`\n",
        encoding="utf-8",
    )
    for capability in ("capability", "other-capability"):
        write(
            tree / f"domain/{capability}/spec.md",
            f"# L2 Business Capability：能力 (`{capability}`)\n",
        )
        write(
            tree / f"domain/{capability}/story/spec.md",
            "# L3 Story：故事 (`story`)\n\n"
            '<a id="req-003"></a>\n'
            "### REQ-003 要求\n\n- 行为。\n\n"
            '<a id="gwt-003"></a>\n'
            "### GWT-003 验收\n\n- THEN 结果。\n",
        )
        write(
            tree / f"domain/{capability}/design.md",
            f"# L2 Design：能力 (`{capability}`)\n\n"
            '<a id="dec-002"></a>\n'
            "### DEC-002 同优先级归属\n\n"
            "- 适用工程根：`quwoquan_app/lib/design_system/pageflip`\n"
            "- 影响 Story：[`story`](./story/spec.md)\n"
            "- 关联要求：`REQ-003`\n"
            "- 关联验收：`GWT-003`\n",
        )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)

    try:
        feature_tree.resolve_target(code_path, feature_tree.discover_nodes())
    except ValueError as error:
        assert "多个 L2 DEC 同优先级认领" in str(error)
    else:
        raise AssertionError("same-priority L2 DEC ownership must be blocked")

    try:
        feature_tree.resolve_target(
            root / "quwoquan_app/lib/unowned/object.dart",
            feature_tree.discover_nodes(),
        )
    except ValueError as error:
        assert str(error).startswith("GATE_BLOCK:")
        assert "未被任何 L1 工程归属认领" in str(error)
    else:
        raise AssertionError("unowned target must be blocked")


def test_repository_pageflip_roots_resolve_to_one_story_with_exact_anchors() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    nodes = feature_tree.discover_nodes()
    targets = (
        "quwoquan_app/lib/design_system/pageflip/geometry.dart",
        (
            "quwoquan_app/lib/service/content_service/content/post/presentation/"
            "article_reader/pageflip/host/article_read_only_book_deck.dart"
        ),
        (
            "quwoquan_app/test/local_contract/design_system/pageflip/"
            "pageflip_core__local_contract_test.dart"
        ),
        (
            "quwoquan_app/test/local_contract/service/content_service/content/post/"
            "presentation/article_reader/pageflip/host/"
            "article_read_only_book_deck__local_contract_test.dart"
        ),
    )

    resolutions = [feature_tree.resolve_target_details(target, nodes) for target in targets]

    assert {
        resolution.node.rel for resolution in resolutions
    } == {
        (
            "specs/feature-tree/discovery-content/dual-rail-discovery-redesign/"
            "works-immersive-viewer/spec.md"
        )
    }
    assert {
        resolution.design_ownership.anchor
        for resolution in resolutions
        if resolution.design_ownership is not None
    } == {"dec-002"}
    assert all(
        resolution.design_ownership is not None
        and resolution.design_ownership.requirement_anchors
        == (
            "req-003",
            "req-009",
            "req-011",
            "req-016",
            "req-017",
            "req-018",
            "req-019",
            "req-020",
            "req-021",
        )
        and resolution.design_ownership.acceptance_anchors
        == (
            "gwt-003",
            "gwt-010",
            "gwt-015",
            "gwt-016",
            "gwt-017",
            "gwt-018",
            "gwt-019",
            "gwt-020",
        )
        for resolution in resolutions
    )
    args = feature_tree.build_parser().parse_args(
        ["context", "--target", targets[0]]
    )
    assert args.format == "manifest"


def test_repository_governance_pipeline_roots_resolve_to_runtime_stories() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    nodes = feature_tree.discover_nodes()
    expected = {
        "quwoquan_ops/cli/review_dispatch.py": (
            "agent-skill-review-context-organization",
            "dec-003",
            ("req-003", "req-004", "req-006"),
            ("gwt-003", "gwt-004", "gwt-006"),
        ),
        "quwoquan_ops/cli/lib/human_agent_delivery/contract.py": (
            "human-agent-delivery-interaction",
            "dec-008",
            ("req-001", "req-002", "req-003", "req-004", "req-005", "req-006"),
            ("gwt-001", "gwt-002", "gwt-003"),
        ),
        "quwoquan_ops/cli/evidence_runner.py": (
            "agent-skill-review-context-organization",
            "dec-004",
            ("req-002", "req-005"),
            ("gwt-002", "gwt-005"),
        ),
        "quwoquan_ops/cli/lib/objective_execution/executor.py": (
            "objective-execution",
            "dec-009",
            ("req-001", "req-002", "req-003"),
            ("gwt-001", "gwt-002", "gwt-003"),
        ),
        "quwoquan_ops/cli/lib/hotl_admission/evaluator.py": (
            "hotl-expansion-control",
            "dec-010",
            ("req-001", "req-002", "req-003"),
            ("gwt-001", "gwt-002", "gwt-003"),
        ),
        "quwoquan_ops/ci/local_readiness_planner.py": (
            "local-continuous-integration",
            "dec-011",
            ("req-001", "req-002", "req-003"),
            ("gwt-001", "gwt-002", "gwt-003"),
        ),
        "quwoquan_ops/cli/lib/governance_pipeline_admission/evaluator.py": (
            "governance-pipeline-observe-only",
            "dec-013",
            ("req-001", "req-002", "req-003"),
            ("gwt-001", "gwt-002", "gwt-003"),
        ),
    }

    for target, (story, dec, requirements, acceptances) in expected.items():
        resolution = feature_tree.resolve_target_details(target, nodes)
        assert resolution.l1_owner is not None
        assert resolution.l1_owner.node_id == "runtime"
        assert resolution.node.node_id == story
        assert resolution.design_ownership is not None
        assert resolution.design_ownership.anchor == dec
        assert resolution.design_ownership.requirement_anchors == requirements
        assert resolution.design_ownership.acceptance_anchors == acceptances


def test_repository_governance_test_and_gate_roots_follow_their_runtime_stories() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    nodes = feature_tree.discover_nodes()
    expected = {
        (
            "quwoquan_ops/tests/local_contract/gate/"
            "test_named_evidence_runner__local_contract_test.py"
        ): "agent-skill-review-context-organization",
        (
            "quwoquan_ops/tests/local_contract/gate/"
            "test_objective_execution__executor_admission__local_contract_test.py"
        ): "objective-execution",
        "quwoquan_ops/gate/verify_objective_execution.py": "objective-execution",
        "quwoquan_ops/gate/verify_hotl_admission.py": "hotl-expansion-control",
        (
            "quwoquan_ops/tests/local_contract/ci/"
            "test_local_readiness__core__local_contract_test.py"
        ): "local-continuous-integration",
        (
            "quwoquan_ops/tests/local_contract/gate/"
            "test_governance_pipeline_admission__contract_cli_gate__local_contract_test.py"
        ): "governance-pipeline-observe-only",
    }

    for target, story in expected.items():
        resolution = feature_tree.resolve_target_details(target, nodes)
        assert resolution.l1_owner is not None
        assert resolution.l1_owner.node_id == "runtime"
        assert resolution.node.node_id == story
        assert resolution.design_ownership is not None


def test_hosted_authority_adapter_stays_with_platform_ops_owner() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    nodes = feature_tree.discover_nodes()
    targets = (
        "quwoquan_ops/cli/lib/hosted_authority/client.py",
        "quwoquan_ops/tests/local_contract/gate/test_hosted_authority_adapter__local_contract_test.py",
        (
            "quwoquan_service/control-plane/platform-ops/internal/platform_ops/"
            "human_authority/application/facade.go"
        ),
    )

    for target in targets:
        resolution = feature_tree.resolve_target_details(target, nodes)
        assert resolution.l1_owner is not None
        assert resolution.l1_owner.node_id == "platform-ops-governance"
        assert resolution.node.node_id == "hosted-human-authority"
        assert resolution.design_ownership is not None
        assert resolution.design_ownership.anchor == "dec-005"


def test_repository_root_singletons_have_exact_runtime_l1_ownership() -> None:
    # spec_ref: specs/feature-tree/runtime/spec.md#dom-001
    nodes = feature_tree.discover_nodes()
    singleton_roots = (
        "Makefile",
        "AGENTS.md",
        "README.md",
        "specs/feature-tree/README.md",
    )

    for target in singleton_roots:
        resolution = feature_tree.resolve_target_details(target, nodes)
        assert resolution.l1_owner is not None
        assert resolution.l1_owner.node_id == "runtime"
        assert resolution.node.node_id == "runtime"
        assert resolution.design_ownership is None

    non_exact_targets = (
        "report.json",
        *(f"{target}.extra" for target in singleton_roots),
        *(f"{target}/nested" for target in singleton_roots),
    )
    for target in non_exact_targets:
        try:
            feature_tree.resolve_target_details(target, nodes)
        except ValueError as error:
            assert str(error).startswith("GATE_BLOCK:")
            assert "未被任何 L1 工程归属认领" in str(error)
        else:
            raise AssertionError(f"non-exact repository root was swallowed: {target}")


def test_repository_root_makefile_rejects_duplicate_exact_l1_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/spec.md#dom-001
    root = build_tree(tmp_path)
    write(root / "Makefile", ".PHONY: all\n")
    for node_id in ("domain", "other-domain"):
        write(
            root / f"specs/feature-tree/{node_id}/spec.md",
            f"# L1 Domain Service：领域 (`{node_id}`)\n\n"
            "## 7. 工程归属\n\n"
            "- Ops：`Makefile`\n",
        )
        write(
            root / f"specs/feature-tree/{node_id}/design.md",
            f"# L1 Design：领域 (`{node_id}`)\n",
        )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    try:
        feature_tree.resolve_target_details("Makefile", feature_tree.discover_nodes())
    except ValueError as error:
        message = str(error)
        assert message.startswith("GATE_BLOCK:")
        assert "被多个 L1 同优先级认领" in message
        assert "domain" in message
        assert "other-domain" in message
    else:
        raise AssertionError("duplicate exact Makefile owners were not rejected")


def test_repository_owner_representative_paths_remain_exact_and_unique() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    nodes = feature_tree.discover_nodes()
    expected = {
        "quwoquan_ops/cli/lib/human_agent_delivery/contract.py": "human-agent-delivery-interaction",
        "quwoquan_ops/cli/review_dispatch.py": "agent-skill-review-context-organization",
        "quwoquan_ops/cli/lib/objective_execution/executor.py": "objective-execution",
        "quwoquan_ops/cli/lib/hotl_admission/evaluator.py": "hotl-expansion-control",
        "quwoquan_ops/ci/local_readiness_planner.py": "local-continuous-integration",
        "quwoquan_ops/cli/lib/governance_pipeline_admission/evaluator.py": "governance-pipeline-observe-only",
        "quwoquan_ops/cli/lib/hosted_authority/client.py": "hosted-human-authority",
    }

    for target, story in expected.items():
        resolution = feature_tree.resolve_target_details(target, nodes)
        assert resolution.node.node_id == story
        assert resolution.design_ownership is not None


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
        "- Agent：`.agents`、`.codex`、`.cursor`\n",
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
