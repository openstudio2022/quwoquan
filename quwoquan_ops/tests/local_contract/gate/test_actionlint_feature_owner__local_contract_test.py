"""The repository actionlint config has one narrow Feature context.

spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
"""
from __future__ import annotations

from quwoquan_ops.cli.lib.feature_tree import discover_nodes
from quwoquan_ops.cli.lib.feature_tree.commands import _context_manifest


def test_actionlint_config_is_non_authoritative_context_input() -> None:
    manifest = _context_manifest(".github/actionlint.yaml", discover_nodes())

    assert manifest["context_status"] == "context_unresolved"
    assert manifest["feature_chain"] == []
    assert manifest["canonical_contexts"] == []
