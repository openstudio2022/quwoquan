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
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

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
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs" / "feature-tree")

    owner = feature_tree.resolve_target(
        "quwoquan_app/lib/feature.dart", feature_tree.discover_nodes()
    )

    assert owner.node_id == "domain"


def test_canonical_app_object_test_resolves_from_its_production_domain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
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
