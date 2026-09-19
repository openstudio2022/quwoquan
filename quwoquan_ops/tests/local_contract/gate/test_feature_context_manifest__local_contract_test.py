"""spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002"""
from pathlib import Path
from quwoquan_ops.cli.lib.feature_tree import commands
from quwoquan_ops.cli.lib.feature_tree.nodes import discover_nodes

ROOT = Path(__file__).resolve().parents[4]

def test_direct_feature_path_returns_directory_parent_chain() -> None:
    nodes = discover_nodes()
    manifest = commands._context_manifest("specs/feature-tree/runtime/development-workflow-governance/spec.md", nodes)
    assert manifest["context_status"] == "context_resolved"
    assert [item["node_id"] for item in manifest["feature_chain"]] == ["app-root", "runtime", "development-workflow-governance"]
    assert "resolved_owner" not in manifest and "owner_chain" not in manifest

def test_code_path_without_feature_relation_is_nonblocking_unresolved() -> None:
    manifest = commands._context_manifest("README.md", discover_nodes())
    assert manifest["context_status"] == "context_unresolved"
    assert manifest["feature_chain"] == []
    assert manifest["canonical_contexts"] == []

def test_contexts_are_stably_sorted_and_dependency_evidence_is_explicit() -> None:
    manifest = commands._context_manifest("specs/feature-tree/runtime/development-workflow-governance/spec.md", discover_nodes())
    contexts = manifest["canonical_contexts"]
    assert contexts == sorted(contexts, key=lambda item: (item["path"].encode(), (item["anchor"] or "").encode(), item["kind"].encode()))
    assert manifest["dependency_evidence"] == sorted(set(manifest["dependency_evidence"]), key=lambda item: item.encode())
