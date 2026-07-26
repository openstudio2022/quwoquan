from __future__ import annotations

import pytest

from content.execution.context import ExecutionContext
from content.execution.target_integrity import frozen_target_names
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def _context(entity_ids: list[str], target_names: list[str]) -> ExecutionContext:
    return ExecutionContext(
        execution_id="20260716--travel-homepage-coverage--test-region-a--pilot-099",
        entity_ids=entity_ids,
        spec=ExecutionFixtureBuilder(
            "20260716--travel-homepage-coverage--test-region-a--pilot-099",
            targets=tuple(
                {"name": name, "entityType": "地点/景区"}
                for name in target_names
            ),
        ).spec(),
    )


def test_frozen_targets_require_exact_ordered_context_identity() -> None:
    ctx = _context(["测试实体甲", "测试实体乙"], ["测试实体甲", "测试实体乙"])
    assert frozen_target_names(ctx) == ("测试实体甲", "测试实体乙")


@pytest.mark.parametrize(
    ("entity_ids", "target_names"),
    [
        (["测试实体甲"], ["测试实体甲", "测试实体乙"]),
        (["测试实体乙", "测试实体甲"], ["测试实体甲", "测试实体乙"]),
        (["测试实体甲", "测试实体甲"], ["测试实体甲", "测试实体甲"]),
    ],
)
def test_frozen_targets_reject_shortfall_reorder_and_duplicates(
    entity_ids: list[str],
    target_names: list[str],
) -> None:
    with pytest.raises(ValueError):
        frozen_target_names(_context(entity_ids, target_names))
