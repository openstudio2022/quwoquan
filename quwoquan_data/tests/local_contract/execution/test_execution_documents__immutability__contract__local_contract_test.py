"""Execution domain documents are immutable after boundary decoding."""
from __future__ import annotations

import pytest

from core.runtime_policy import active_runtime_policy
from content.execution.agent.managed_checkpoint import _managed_checkpoint_worker_count
from content.execution.agent.managed_checkpoint import _managed_checkpoint_ref
from content.execution.context import ExecutionContext, _managed_local_cursor_worker_cap
from content.execution.spec_contract import ExecutionSpec
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_execution_context_snapshots_spec_and_returns_defensive_values() -> None:
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-901"
    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    context = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("测试实体乙",),
        spec=raw,
    )

    raw["content"]["quotas"]["entityHomepagesPerTarget"] = 9
    assert isinstance(context.spec, ExecutionSpec)
    assert context.spec.content.quotas.entity_homepages_per_target == 1


def test_managed_checkpoint_worker_cap_comes_only_from_runtime_policy() -> None:
    policy = active_runtime_policy()
    context = ExecutionContext(
        execution_id="20260716--travel-homepage-coverage--test-region-a--pilot-902",
        entity_ids=("测试实体乙",),
        spec=ExecutionFixtureBuilder(
            "20260716--travel-homepage-coverage--test-region-a--pilot-902"
        ).spec(),
        max_workers=policy.author_workers,
    )
    expected = min(policy.author_workers, policy.cursor_bridge_instances)

    assert _managed_local_cursor_worker_cap(context) == expected
    assert _managed_checkpoint_worker_count(context, policy.author_workers + 1) == expected


def test_execution_context_rejects_spec_identity_drift() -> None:
    with pytest.raises(ValueError, match="must match"):
        ExecutionContext(
            execution_id="20260716--travel-homepage-coverage--test-region-a--pilot-903",
            entity_ids=("测试实体乙",),
            spec=ExecutionFixtureBuilder(
                "20260716--travel-homepage-coverage--test-region-a--pilot-904"
            ).spec(),
        )


def test_execution_spec_rejects_schema_and_target_count_drift() -> None:
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-905"
    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    raw["schema"] = "quwoquan.content.execution_spec.shadow"
    with pytest.raises(ValueError, match="schema must be"):
        ExecutionSpec.from_mapping(raw)

    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    raw["executionPolicy"]["targetEntityCount"] = 2
    with pytest.raises(ValueError, match="targetEntityCount"):
        ExecutionSpec.from_mapping(raw)


def test_execution_spec_rejects_carrier_quota_and_object_count_drift() -> None:
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-906"
    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    raw["content"]["quotas"]["entityHomepagesPerTarget"] = 0
    raw["content"]["quotas"]["imageWorksPerTarget"] = 1
    with pytest.raises(ValueError, match="content.carriers"):
        ExecutionSpec.from_mapping(raw)

    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    raw["executionPolicy"]["targetObjectCount"] = 2
    with pytest.raises(ValueError, match="targetObjectCount"):
        ExecutionSpec.from_mapping(raw)


def test_execution_spec_rejects_multiple_active_carriers() -> None:
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-907"
    raw = ExecutionFixtureBuilder(execution_id).spec_payload()
    raw["content"]["carriers"] = ["homepage", "article"]
    raw["content"]["research"]["lanes"] = ["homepage", "article"]
    raw["content"]["quotas"]["entityArticlesPerTarget"] = 1
    raw["executionPolicy"]["targetObjectCount"] = 2
    raw["acceptance"]["minPostsPerEntity"] = 2
    with pytest.raises(ValueError, match="exactly one positive content quota"):
        ExecutionSpec.from_mapping(raw)


def test_homepage_checkpoint_run_has_stable_entity_ref() -> None:
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-908"
    fixture = ExecutionFixtureBuilder(
        execution_id,
        targets=({"name": "测试实体", "entityType": "地点/景区"},),
    )
    fixture.build()
    context = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("测试实体",),
        spec=fixture.spec(),
    )

    assert _managed_checkpoint_ref(
        context,
        "build_homepage",
        "[AGENT_LANE:homepage]\n对象: 测试实体\n",
    ) == "entities/地点/景区/测试实体"
