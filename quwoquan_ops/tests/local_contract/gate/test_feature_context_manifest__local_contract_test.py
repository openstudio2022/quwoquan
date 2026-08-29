from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree_manifest", MODULE_PATH)
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
    write(
        tree / "domain" / "capability" / "spec.md",
        "# L2 Business Capability：能力 (`capability`)\n",
    )
    write(
        tree / "domain" / "capability" / "story" / "spec.md",
        "# L3 Story：故事 (`story`)\n",
    )
    return root


def test_l2_dec_owner_manifest_is_shared_by_pageflip_code_and_projected_test(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    write(root / "AGENTS.md", "# root agent\n")
    write(root / "quwoquan_app/AGENTS.md", "# app agent\n")
    code_path = root / "quwoquan_app/lib/design_system/pageflip/geometry.dart"
    test_path = (
        root
        / "quwoquan_app/test/local_contract/design_system/pageflip/"
        "geometry__local_contract_test.dart"
    )
    write(code_path, "class Geometry {}\n")
    write(test_path, "void main() {}\n")
    write(
        root
        / "quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml",
        "enable_pageflip: true\n",
    )
    write(
        root
        / "quwoquan_service/services/content-service/contracts/content/post/operations.yaml",
        "GetUnrelated: {}\n",
    )
    (tree / "domain/spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib/design_system/pageflip`\n",
        encoding="utf-8",
    )
    write(
        tree / "domain/capability/design.md",
        "# L2 Design：能力 (`capability`)\n\n"
        '<a id="dec-002"></a>\n'
        "### DEC-002 pageflip 唯一 owner\n\n"
        "- 适用工程根：`quwoquan_app/lib/design_system/pageflip`\n"
        "- 影响 Story：[`story`](./story/spec.md)\n"
        "- 关联要求：`REQ-003`\n"
        "- 关联验收：`GWT-003`\n",
    )
    write(
        tree / "domain/capability/story/spec.md",
        "# L3 Story：故事 (`story`)\n\n"
        '<a id="req-003"></a>\n'
        "### REQ-003 pageflip 主路径\n\n"
        "- 行为。\n"
        "- canonical：`quwoquan_service/services/content-service/contracts/"
        "content/post/ui_config.yaml#enable_pageflip`\n\n"
        '<a id="gwt-003"></a>\n'
        "### GWT-003 pageflip 验收\n\n"
        "- GIVEN 已进入阅读器。\n"
        "- WHEN 用户翻页。\n"
        "- THEN 路径落到唯一 Story。\n\n"
        '<a id="req-004"></a>\n'
        "### REQ-004 未选要求\n\n"
        "- canonical：`quwoquan_service/services/content-service/contracts/"
        "content/post/operations.yaml#GetUnrelated`\n",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles:\n"
        "  dart-app:\n"
        "    paths: [quwoquan_app/lib/**, quwoquan_app/test/**]\n"
        "  pageflip:\n"
        "    paths: [quwoquan_app/lib/design_system/pageflip/**]\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    nodes = feature_tree.discover_nodes()

    code_owner = feature_tree.resolve_target(code_path, nodes)
    test_owner = feature_tree.resolve_target(test_path, nodes)
    exit_code = feature_tree.command_context(
        argparse.Namespace(target=str(test_path), format="manifest")
    )

    assert exit_code == 0
    assert code_owner == test_owner
    assert test_owner.node_id == "story"
    manifest = json.loads(outputs["context-manifest.json"])
    assert manifest["resolved_owner"].endswith("/capability/story/spec.md")
    assert manifest["applicable_agents"] == ["AGENTS.md", "quwoquan_app/AGENTS.md"]
    assert manifest["profiles"] == ["dart-app", "pageflip"]
    assert {
        (item["kind"], item["anchor"])
        for item in manifest["canonical_contexts"]
        if item["anchor"]
    } == {
        ("decision", "dec-002"),
        ("requirement", "req-003"),
        ("acceptance", "gwt-003"),
        ("contract", "enable_pageflip"),
    }
    assert len((outputs["context-manifest.json"] + "\n").encode("utf-8")) <= 8192

    contract_module = sys.modules[ft_commands.declared_object.__module__]
    original_declared_fields = contract_module.declared_fields

    def drift(section: str, declaration: str) -> tuple[str, ...]:
        fields = original_declared_fields(section, declaration)
        if section == "feature_context_manifest" and declaration == "context_fields":
            return (*fields, "new_context_field")
        return fields

    monkeypatch.setattr(contract_module, "declared_fields", drift)
    assert (
        feature_tree.command_context(
            argparse.Namespace(target=str(test_path), format="manifest")
        )
        == 2
    )
