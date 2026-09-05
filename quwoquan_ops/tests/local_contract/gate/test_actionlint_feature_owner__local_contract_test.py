"""The repository actionlint config has one narrow Feature owner.

spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
"""
from __future__ import annotations

from quwoquan_ops.cli.lib.feature_tree import discover_nodes, resolve_target_details


def test_actionlint_config_resolves_to_local_continuous_integration() -> None:
    resolution = resolve_target_details(".github/actionlint.yaml", discover_nodes())

    assert resolution.l1_owner is not None
    assert resolution.l1_owner.node_id == "runtime"
    assert resolution.node.node_id == "local-continuous-integration"
    assert resolution.design_ownership is not None
    assert resolution.design_ownership.anchor == "dec-011"
