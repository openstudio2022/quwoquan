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












































def test_feature_context_has_no_feature_owner_resolver_surface() -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t1
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t2
    # spec_ref: specs/feature-tree/runtime/runtime-agentpack/feature-context-discovery/spec.md#gwt-001.t3
    # Context is advisory/non-authoritative; mutation authority comes from exact paths and candidate evidence.
    assert not hasattr(feature_tree, "resolve_target")
    assert not hasattr(feature_tree, "resolve_target_details")
    assert importlib.util.find_spec("quwoquan_ops.cli.lib.feature_tree.ownership") is None
